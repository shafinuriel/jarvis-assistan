# actions/download_guard.py
"""Watch Downloads for HIGH-RISK new files only. Never auto-deletes."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from actions.usb_security import Threat, _sha256_file, do_quarantine, do_delete

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "memory" / "download_guard.json"


def _load_cfg() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "enabled": True,
            "sphere_alert": True,
            "speak_clean": False,
            "watch_desktop": False,
            "settle_seconds": 1.5,
            "log_skips": False,
            "flag_exe": False,
            "flag_msi": False,
            "high_risk_ext": [".bat", ".cmd", ".vbs", ".scr", ".js", ".jse", ".wsf", ".ps1"],
            "suspicious_name_hints": [
                "crack", "keygen", "patch", "loader", "payload", "worm", "stealer"
            ],
        }


def _downloads_dir() -> Path:
    home = Path.home()
    for name in ("Downloads", "Загрузки"):
        p = home / name
        if p.is_dir():
            return p
    return home / "Downloads"


def _desktop_dir() -> Path:
    return Path.home() / "Desktop"


def is_suspicious(path: Path, cfg: dict) -> Optional[str]:
    """Return reason string or None if safe/ignore."""
    if not path.is_file():
        return None
    name = path.name.lower()
    # incomplete downloads
    if name.endswith((".crdownload", ".tmp", ".partial", ".download", ".opdownload")):
        return None
    if name.startswith("\~$"):
        return None

    ext = path.suffix.lower()
    stem = path.stem.lower()

    # double extension: document.pdf.exe
    if ext == ".exe" and any(
        stem.endswith(x) for x in (".pdf", ".jpg", ".jpeg", ".png", ".txt", ".doc", ".docx", ".mp4", ".zip")
    ):
        return "double extension"

    high = {e.lower() for e in cfg.get("high_risk_ext", [])}
    if ext in high:
        return f"script {ext}"

    if name == "autorun.inf":
        return "autorun.inf"

    hints = [h.lower() for h in cfg.get("suspicious_name_hints", [])]
    if any(h in name for h in hints):
        return "suspicious name"

    if ext == ".exe" and cfg.get("flag_exe", False):
        return "new exe"
    if ext == ".msi" and cfg.get("flag_msi", False):
        return "new msi"

    return None


class _Handler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        super().__init__()
        self.loop = loop
        self.queue = queue

    def on_created(self, event):
        if getattr(event, "is_directory", False):
            return
        self.loop.call_soon_threadsafe(self.queue.put_nowait, event.src_path)

    def on_moved(self, event):
        if getattr(event, "is_directory", False):
            return
        dest = getattr(event, "dest_path", None) or event.src_path
        self.loop.call_soon_threadsafe(self.queue.put_nowait, dest)


class DownloadGuard:
    def __init__(self, jarvis: Any):
        self.jarvis = jarvis
        self.cfg = _load_cfg()
        self._queue: Optional[asyncio.Queue] = None
        self._observer = None
        self._seen: set[str] = set()
        self.last_threats: list[Threat] = []
        self.pending_decision = False

    async def run_loop(self) -> None:
        if not self.cfg.get("enabled", True):
            print("[DL-GUARD] disabled")
            return
        if Observer is None:
            print("[DL-GUARD] pip install watchdog")
            return

        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        handler = _Handler(loop, self._queue)
        obs = Observer()

        roots = [_downloads_dir()]
        if self.cfg.get("watch_desktop"):
            roots.append(_desktop_dir())

        for root in roots:
            try:
                root.mkdir(parents=True, exist_ok=True)
                obs.schedule(handler, str(root), recursive=False)
                print(f"[DL-GUARD] watching {root}")
            except Exception as e:
                print(f"[DL-GUARD] cannot watch {root}: {e}")

        obs.start()
        self._observer = obs

        try:
            while True:
                path = await self._queue.get()
                try:
                    await self._handle_path(path)
                except Exception as e:
                    print(f"[DL-GUARD] handle error: {e}")
        finally:
            obs.stop()
            obs.join(timeout=3)

    async def _handle_path(self, path_str: str) -> None:
        path = Path(path_str)
        reason = is_suspicious(path, self.cfg)
        if not reason:
            if self.cfg.get("log_skips") and path.suffix.lower() in {".exe", ".msi"}:
                print(f"[DL-GUARD] skip (installer policy): {path.name}")
            return

        settle = float(self.cfg.get("settle_seconds", 1.5))
        ok = await asyncio.to_thread(self._wait_stable, path, settle)
        if not ok or not path.is_file():
            return

        # re-check after settle
        reason = is_suspicious(path, self.cfg)
        if not reason:
            return

        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in self._seen:
            return
        self._seen.add(key)
        if len(self._seen) > 400:
            self._seen = set(list(self._seen)[-150:])

        threat = Threat(
            path=str(path),
            reason=reason,
            sha256=await asyncio.to_thread(_sha256_file, path),
            drive=str(path.parent),
        )
        self.last_threats = [threat]
        await self._report(threat)

    @staticmethod
    def _wait_stable(path: Path, settle: float, tries: int = 14) -> bool:
        last = -1
        stable = 0
        for _ in range(tries):
            try:
                sz = path.stat().st_size
            except OSError:
                time.sleep(0.35)
                continue
            if sz == last and sz > 0:
                stable += 1
                if stable >= 2:
                    return True
            else:
                stable = 0
                last = sz
            time.sleep(max(0.25, settle / 2))
        try:
            return path.is_file() and path.stat().st_size >= 0
        except OSError:
            return False

    async def _report(self, threat: Threat) -> None:
        name = Path(threat.path).name
        msg = (
            f"Sir, suspicious file in Downloads: {name} ({threat.reason}). "
            f"Quarantine, delete, or ignore?"
        )
        print(f"[DL-GUARD] THREAT: {msg}")
        self.pending_decision = True

        # share with USB voice handler
        usb = getattr(self.jarvis, "_usb_sec", None)
        if usb is not None:
            usb._last_threats = [threat]
            usb.pending_decision = True

        if self.cfg.get("sphere_alert", True):
            try:
                self.jarvis.ui.set_state("THREAT")
            except Exception:
                try:
                    self.jarvis.ui.set_state("SPEAKING")
                except Exception:
                    pass

        try:
            if hasattr(self.jarvis.ui, "show_security_panel"):
                self.jarvis.ui.show_security_panel(
                    drive="Downloads",
                    threats=[asdict(threat)],
                )
        except Exception as e:
            print(f"[DL-GUARD] panel: {e}")

        try:
            await self.jarvis.speak(msg)
        except Exception as e:
            print(f"[DL-GUARD] speak: {e}")

    async def handle_voice_command(self, text: str) -> bool:
        if not self.pending_decision:
            return False
        t = (text or "").lower()
        if any(k in t for k in ("quarantine", "карантин", "в карантин", "убери в карантин")):
            ok = fail = 0
            for th in self.last_threats:
                try:
                    do_quarantine(th.path)
                    ok += 1
                except Exception:
                    fail += 1
            self.pending_decision = False
            if getattr(self.jarvis, "_usb_sec", None):
                self.jarvis._usb_sec.pending_decision = False
            try:
                self.jarvis.ui.hide_security_panel()
            except Exception:
                pass
            try:
                await self.jarvis.speak(f"Quarantine done. {ok} file(s).")
            except Exception:
                pass
            return True
        if any(k in t for k in ("ignore", "игнор", "игнорируй", "пропусти")):
            self.pending_decision = False
            if getattr(self.jarvis, "_usb_sec", None):
                self.jarvis._usb_sec.pending_decision = False
            try:
                self.jarvis.ui.hide_security_panel()
            except Exception:
                pass
            try:
                await self.jarvis.speak("Ignored.")
            except Exception:
                pass
            return True
        if any(k in t for k in ("delete", "удали", "удалить")):
            try:
                await self.jarvis.speak(
                    "For delete, use the DELETE button and confirm on screen."
                )
            except Exception:
                pass
            return True
        return False