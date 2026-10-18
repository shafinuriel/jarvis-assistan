# actions/usb_security.py
"""Lightweight USB removable-drive scanner for Jarvis. Never auto-deletes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional
from memory.config_manager import get_feature_flag

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

SUSPICIOUS_EXT = {".exe", ".vbs", ".bat", ".cmd", ".scr", ".js", ".jse", ".wsf", ".ps1"}
ALWAYS_FLAG_NAMES = {"autorun.inf"}

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "memory" / "usb_security.json"


@dataclass
class Threat:
    path: str
    reason: str
    sha256: str
    drive: str


def _load_config() -> dict:
    # Базовые настройки по умолчанию
    cfg = {
        "enabled": True,
        "sphere_alert": True,
        "speak_clean": True,
        "scan_depth": 2,
        "poll_seconds": 2.5,
        "max_files": 400,
        "quarantine_dir": "memory/quarantine",
    }
    

    # Сначала читаем старый файл (для детальных настроек)
    try:
        if CONFIG_PATH.exists():
            old = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update(old)
    except Exception:
        pass

    # Теперь перезаписываем главные флаги из нового единого конфига
    cfg["enabled"] = get_feature_flag("usb_security_enabled", cfg.get("enabled", True))
    cfg["sphere_alert"] = get_feature_flag("sphere_alert", cfg.get("sphere_alert", True))

    return cfg


def _sha256_file(path: Path, limit: int = 2_000_000) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            left = limit
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                h.update(chunk)
                left -= len(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _is_hidden_windows(path: Path) -> bool:
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x2
        FILE_ATTRIBUTE_SYSTEM = 0x4
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        return False


def list_removable_drives() -> set[str]:
    """Return mountpoints like 'E:\\' for removable volumes."""
    found: set[str] = set()
    if not psutil:
        return found
    for p in psutil.disk_partitions(all=False):
        opts = (p.opts or "").lower()
        # Windows removable / USB
        if "removable" in opts or p.fstype.upper() in ("FAT", "FAT32", "EXFAT"):
            # skip fixed system-ish if marked fixed
            if "fixed" in opts and "removable" not in opts:
                continue
            mp = p.mountpoint
            if mp and os.path.isdir(mp):
                found.add(os.path.abspath(mp))
    # fallback: letters with drive type 2 (REMOVABLE) via ctypes
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                letter = f"{chr(65 + i)}:\\"
                dtype = ctypes.windll.kernel32.GetDriveTypeW(letter)
                # DRIVE_REMOVABLE = 2
                if dtype == 2 and os.path.isdir(letter):
                    found.add(os.path.abspath(letter))
    except Exception:
        pass
    return found


def scan_drive(root: str, depth: int = 2, max_files: int = 400) -> list[Threat]:
    threats: list[Threat] = []
    root_path = Path(root)
    if not root_path.exists():
        return threats

    count = 0
    # root files
    try:
        entries = list(root_path.iterdir())
    except Exception:
        return threats

    def consider(f: Path, reason: str):
        nonlocal count
        if count >= max_files:
            return
        count += 1
        threats.append(
            Threat(
                path=str(f),
                reason=reason,
                sha256=_sha256_file(f),
                drive=root,
            )
        )

    for f in entries:
        if not f.is_file():
            continue
        name = f.name.lower()
        if name in ALWAYS_FLAG_NAMES:
            consider(f, "autorun.inf")
            continue
        ext = f.suffix.lower()
        if ext in SUSPICIOUS_EXT:
            if _is_hidden_windows(f) or name.startswith("."):
                consider(f, f"hidden/suspicious {ext}")
            elif ext in {".vbs", ".bat", ".cmd", ".scr", ".jse", ".wsf"}:
                consider(f, f"script/autorun-style {ext}")
            elif ext == ".lnk":
                consider(f, "shortcut (.lnk) on USB root")
            elif ext == ".exe" and _is_hidden_windows(f):
                consider(f, "hidden exe on USB root")
            # plain visible setup.exe etc. — optional soft flag only at root
            elif ext == ".exe" and depth >= 0:
                # soft: only flag if name looks dropper-ish
                bad_hints = ("crack", "keygen", "patch", "loader", "payload", "worm")
                if any(h in name for h in bad_hints):
                    consider(f, "suspicious exe name on USB root")

    # shallow walk
    if depth >= 1:
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root_path)
            level = len(rel.parts)
            if level > depth:
                dirnames.clear()
                continue
            if level == 0:
                continue  # root already done
            for fn in filenames:
                if count >= max_files:
                    return threats
                f = Path(dirpath) / fn
                name = fn.lower()
                ext = f.suffix.lower()
                if name in ALWAYS_FLAG_NAMES or ext in {".vbs", ".bat", ".cmd", ".scr"}:
                    consider(f, f"nested {ext or name}")
                elif ext == ".exe" and _is_hidden_windows(f):
                    consider(f, "hidden nested exe")
    return threats


def quarantine_file(src: str, quarantine_rel: str = "memory/quarantine") -> str:
    """Copy then remove original only after successful copy. Returns dest path."""
    src_p = Path(src)
    qdir = BASE / quarantine_rel
    qdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = qdir / f"{stamp}_{src_p.name}"
    shutil.copy2(src_p, dest)
    try:
        src_p.unlink()
    except Exception:
        pass
    return str(dest)


class UsbSecurityMonitor:
    def __init__(self, jarvis: Any):
        self.jarvis = jarvis
        self.cfg = _load_config()
        self._known: set[str] = set()
        self._last_threats: list[Threat] = []
        self._booted = False
        self.pending_decision = False

    @property
    def last_threats(self) -> list[Threat]:
        return list(self._last_threats)

    async def run_loop(self) -> None:
        if not self.cfg.get("enabled", True):
            print("[USB-SEC] disabled in config")
            return
        if not psutil:
            print("[USB-SEC] psutil missing — pip install psutil")
            return

        # baseline: don't alarm on already mounted drives at startup
        self._known = list_removable_drives()
        self._booted = True
        print(f"[USB-SEC] watching removable drives. known={self._known}")

        poll = float(self.cfg.get("poll_seconds", 2.5))
        while True:
            try:
                await self._tick()
            except Exception as e:
                print(f"[USB-SEC] tick error: {e}")
            await asyncio.sleep(poll)

    async def _tick(self) -> None:
        current = list_removable_drives()
        new = current - self._known
        gone = self._known - current
        self._known = current

        for d in sorted(gone):
            print(f"[USB-SEC] removed: {d}")

        for d in sorted(new):
            print(f"[USB-SEC] new drive: {d}")
            await self._handle_new_drive(d)

    async def _handle_new_drive(self, drive: str) -> None:
        depth = int(self.cfg.get("scan_depth", 2))
        max_files = int(self.cfg.get("max_files", 400))
        # disk IO off event loop
        threats = await asyncio.to_thread(scan_drive, drive, depth, max_files)
        self._last_threats = threats
        letter = drive.rstrip("\\/")

        if threats:
            await self._report_threats(letter, threats)
        else:
            await self._report_clean(letter)

    async def _report_threats(self, letter: str, threats: list) -> None:
        drive = letter.rstrip("\\/")
        root = drive if drive.endswith(("\\", "/")) else drive + "\\"
        try:
            label = await asyncio.to_thread(get_volume_label, root)
        except Exception:
            label = drive
        name = label if label and label != drive else drive

        file_names = ", ".join(Path(t.path).name for t in threats[:3])
        more = f" and {len(threats) - 3} more" if len(threats) > 3 else ""

        msg = (
            f"Sir, USB drive {name} ({drive}) scanned. "
            f"Threats found: {file_names}{more}. "
            f"Quarantine, delete, or ignore?"
        )
        print(f"[USB-SEC] THREAT {drive}: {msg}")
        self.pending_decision = True

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
                    drive=drive,
                    threats=[asdict(t) for t in threats],
                )
        except Exception as e:
            print(f"[USB-SEC] panel: {e}")

        try:
            await self.jarvis.speak(msg)
        except Exception as e:
            print(f"[USB-SEC] speak: {e}")

    async def _report_clean(self, letter: str) -> None:
        drive = letter.rstrip("\\/")
        root = drive if drive.endswith(("\\", "/")) else drive + "\\"
        try:
            label = await asyncio.to_thread(get_volume_label, root)
        except Exception:
            label = drive
        name = label if label and label != drive else drive

        msg = (
            f"Sir, USB drive {name} ({drive}) is connected. "
            f"Scan complete. No threats found."
        )
        print(f"[USB-SEC] clean: {msg}")
        self.pending_decision = False

        if self.cfg.get("speak_clean", True):
            try:
                await self.jarvis.speak(msg)
            except Exception as e:
                print(f"[USB-SEC] speak: {e}")

        if self.cfg.get("sphere_alert", True):
            try:
                self.jarvis.ui.set_state("IDLE")
            except Exception:
                pass

# helpers for Jarvis voice commands later
def do_quarantine(path: str, cfg: Optional[dict] = None) -> str:
    cfg = cfg or _load_config()
    return quarantine_file(path, cfg.get("quarantine_dir", "memory/quarantine"))


def do_delete(path: str) -> bool:
    try:
        Path(path).unlink()
        return True
    except Exception:
        return False
    
def get_volume_label(root: str) -> str:
    """Windows volume label, fallback to drive letter."""
    letter = root.rstrip("\\/")
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        volume_name = ctypes.create_unicode_buffer(1024)
        fs_name = ctypes.create_unicode_buffer(1024)
        serial = wintypes.DWORD()
        max_comp = wintypes.DWORD()
        flags = wintypes.DWORD()
        ok = kernel32.GetVolumeInformationW(
            letter + "\\",
            volume_name,
            ctypes.sizeof(volume_name),
            ctypes.byref(serial),
            ctypes.byref(max_comp),
            ctypes.byref(flags),
            fs_name,
            ctypes.sizeof(fs_name),
        )
        if ok and volume_name.value:
            return volume_name.value
    except Exception:
        pass
    return letter

async def handle_voice_command(self, text: str) -> bool:
        """Return True if command was handled (skip LLM)."""
        if not self.pending_decision:
            return False
        t = (text or "").lower().strip()
        if any(k in t for k in ("quarantine", "карантин", "в карантин", "убери в карантин")):
            from actions.usb_security import do_quarantine
            ok = fail = 0
            for th in self._last_threats:
                try:
                    do_quarantine(th.path)
                    ok += 1
                except Exception:
                    fail += 1
            self.pending_decision = False
            try:
                self.jarvis.ui.hide_security_panel()
            except Exception:
                pass
            try:
                await self.jarvis.speak(f"Quarantine done. {ok} file(s).")
            except Exception:
                pass
            return True
        if any(k in t for k in ("ignore", "игнор", "игнорируй", "пропусти", "ignore it")):
            self.pending_decision = False
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
            # только через UI confirm — голосом не удаляем
            try:
                await self.jarvis.speak(
                    "For delete, use the DELETE button and confirm on screen."
                )
            except Exception:
                pass
            return True
        return False