"""
SystemController — единый интерфейс управления Windows для Jarvis.

Без GUI (нет pyautogui).
Сайты → webbrowser | .exe → subprocess + psutil | Steam → steam:// URI
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil


@dataclass
class LaunchResult:
    status: str    # started | already_running | opened | error
    target: str
    message: str


class SystemController:
    def __init__(self) -> None:
        self.apps: dict[str, dict] = {
            "discord": {
                "process_names": ["discord.exe"],
                "paths": [
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Discord" / "Update.exe",
                ],
                "args": ["--processStart", "Discord.exe"],
            },
            "chrome": {
                "process_names": ["chrome.exe"],
                "paths": [
                    Path(os.environ.get("PROGRAMFILES", ""))
                    / "Google" / "Chrome" / "Application" / "chrome.exe",
                    Path(os.environ.get("PROGRAMFILES(X86)", ""))
                    / "Google" / "Chrome" / "Application" / "chrome.exe",
                ],
                "args": [],
            },
            "notepad": {
                "process_names": ["notepad.exe"],
                "paths": [
                    Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "notepad.exe",
                ],
                "args": [],
            },
            "spotify": {
                "process_names": ["spotify.exe"],
                "paths": [
                    Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe",
                ],
                "args": [],
            },
            "code": {
                "process_names": ["code.exe"],
                "paths": [
                    Path(os.environ.get("LOCALAPPDATA", ""))
                    / "Programs" / "Microsoft VS Code" / "Code.exe",
                ],
                "args": [],
            },
            "telegram": {
                "process_names": ["telegram.exe"],
                "paths": [
                    Path(os.environ.get("APPDATA", "")) / "Telegram Desktop" / "Telegram.exe",
                ],
                "args": [],
            },
            "steam": {
                "process_names": ["steam.exe"],
                "paths": [
                    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Steam" / "steam.exe",
                    Path(os.environ.get("PROGRAMFILES", "")) / "Steam" / "steam.exe",
                ],
                "args": [],
            },
            "epic": {
                "process_names": ["epicgameslauncher.exe"],
                "paths": [
                    Path(os.environ.get("PROGRAMFILES(X86)", ""))
                    / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win32"
                    / "EpicGamesLauncher.exe",
                    Path(os.environ.get("PROGRAMFILES", ""))
                    / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win32"
                    / "EpicGamesLauncher.exe",
                ],
                "args": [],
            },
            "fortnite": {
                "process_names": [
                    "fortniteclient-win64-shipping.exe",
                    "epicgameslauncher.exe",
                ],
                "paths": [
                    Path(os.environ.get("PROGRAMFILES(X86)", ""))
                    / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win32"
                    / "EpicGamesLauncher.exe",
                    Path(os.environ.get("PROGRAMFILES", ""))
                    / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win32"
                    / "EpicGamesLauncher.exe",
                ],
                "args": [],
            },
            "opera": {
                "process_names": ["opera.exe"],
                "paths": [
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera" / "opera.exe",
                    Path(os.environ.get("PROGRAMFILES", "")) / "Opera" / "opera.exe",
                ],
                "args": [],
            },
            "edge": {
                "process_names": ["msedge.exe"],
                "paths": [
                    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                ],
                "args": [],
            },
            "firefox": {
                "process_names": ["firefox.exe"],
                "paths": [
                    Path(os.environ.get("PROGRAMFILES", "")) / "Mozilla Firefox" / "firefox.exe",
                    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Mozilla Firefox" / "firefox.exe",
                ],
                "args": [],
            },
            "whatsapp": {
                "process_names": ["whatsapp.exe", "WhatsApp.exe"],
                "paths": [
                    Path(os.environ.get("LOCALAPPDATA", ""))
                    / "WhatsApp" / "WhatsApp.exe",
                    Path(os.environ.get("LOCALAPPDATA", ""))
                    / "Programs" / "WindowsApps",  # store-версия — часто только через shell:AppsFolder
                ],
                "args": [],
            },
            "telegram": {
                "process_names": ["telegram.exe"],
                "paths": [
                    Path(os.environ.get("APPDATA", "")) / "Telegram Desktop" / "Telegram.exe",
                ],
                "args": [],
            },
            "settings": {
                "process_names": ["systemsettings.exe"],
                "paths": [],  # запускаем через URI
                "args": [],
            },
        }

        # Имя → Steam AppID
        # Имя → Steam AppID
        self.steam_games: dict[str, str] = {
            "cs2": "730",
            "counter-strike 2": "730",
            "counter-strike": "730",
            "war thunder": "236390",
            "warthunder": "236390",
            "poppy playtime": "1721470",
            "poppy": "1721470",
            "gta 5": "271590",
            "gta v": "271590",
            "gta5": "271590",
            "dota 2": "570",
            "dota": "570",
            "pubg": "578080",
            "rust": "252490",
            "terraria": "105600",
            "minecraft": "1672970",  # Minecraft Launcher в Steam, если есть
        }

    def is_process_running(self, process_names: list[str]) -> bool:
        wanted = {n.lower() for n in process_names}
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in wanted:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def _find_exe(self, paths: list[Path], fallback_name: str) -> Optional[Path]:
        for p in paths:
            if p.is_file():
                return p
        found = shutil.which(fallback_name)
        return Path(found) if found else None

    def _popen(self, argv: list[str], cwd: Optional[str] = None) -> None:
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )

    async def open_url(self, url: str) -> LaunchResult:
        url = (url or "").strip()
        if not url:
            return LaunchResult("error", "", "Empty URL")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        def _run() -> None:
            webbrowser.open(url)

        await asyncio.to_thread(_run)
        return LaunchResult("opened", url, f"Opened {url}")

    async def launch_app(self, name: str) -> LaunchResult:
        key = (name or "").strip().lower()
        aliases = {
            "edge": "edge",
            "microsoft edge": "edge",
            "msedge": "edge",
            "firefox": "firefox",
            "mozilla": "firefox",
            "mozilla firefox": "firefox",
        }
        key = aliases.get(key, key)

        if key in ("whatsapp", "whats app", "вацап", "вотсап"):
            return await self.launch_whatsapp()
        cfg = self.apps.get(key)
        if not cfg:
            return LaunchResult("error", name, f"Unknown app: {name}")

        if self.is_process_running(cfg["process_names"]):
            return LaunchResult("already_running", key, f"{key} is already running")

        exe = self._find_exe(cfg["paths"], cfg["process_names"][0])
        if exe is None:
            return LaunchResult("error", key, f"Executable not found: {key}")

        argv = [str(exe), *cfg.get("args", [])]

        def _run() -> None:
            self._popen(argv, cwd=str(exe.parent))

        await asyncio.to_thread(_run)
        return LaunchResult("started", key, f"Started {key}")

    async def launch_exe(
        self,
        path: str,
        process_name: Optional[str] = None,
    ) -> LaunchResult:
        p = Path(path)
        proc = (process_name or p.name).lower()

        if self.is_process_running([proc]):
            return LaunchResult("already_running", str(p), f"{proc} is already running")

        if not p.is_file():
            return LaunchResult("error", str(p), f"File not found: {path}")

        def _run() -> None:
            self._popen([str(p)], cwd=str(p.parent))

        await asyncio.to_thread(_run)
        return LaunchResult("started", str(p), f"Started {p.name}")

    async def launch_steam_game(self, name_or_id: str) -> LaunchResult:
        key = (name_or_id or "").strip().lower()
        app_id = self.steam_games.get(key, key)

        if not str(app_id).isdigit():
            return LaunchResult("error", name_or_id, f"Unknown Steam game / id: {name_or_id}")

        uri = f"steam://rungameid/{app_id}"

        def _run() -> None:
            os.startfile(uri)

        await asyncio.to_thread(_run)
        return LaunchResult("started", str(app_id), f"Steam game {app_id}")

    async def install_steam_game(self, name_or_id: str) -> LaunchResult:
        """Скачать / установить игру через Steam (steam://install/<id>)."""
        key = (name_or_id or "").strip().lower()
        app_id = self.steam_games.get(key, key)

        if not str(app_id).isdigit():
            return LaunchResult(
                "error",
                name_or_id,
                f"Unknown Steam game / id: {name_or_id}",
            )

        url = f"steam://install/{app_id}"

        def _run() -> None:
            os.startfile(url)

        await asyncio.to_thread(_run)
        return LaunchResult(
            "started",
            str(app_id),
            f"Steam install requested for {app_id}",
        )

    async def uninstall_steam_game(self, name_or_id: str) -> LaunchResult:
        """Удалить игру через Steam (steam://uninstall/<id>)."""
        key = (name_or_id or "").strip().lower()
        app_id = self.steam_games.get(key, key)

        if not str(app_id).isdigit():
            return LaunchResult(
                "error",
                name_or_id,
                f"Unknown Steam game / id: {name_or_id}",
            )

        url = f"steam://uninstall/{app_id}"

        def _run() -> None:
            os.startfile(url)

        await asyncio.to_thread(_run)
        return LaunchResult(
            "started",
            str(app_id),
            f"Steam uninstall requested for {app_id}",
        )
    
    async def launch_fortnite_epic(self) -> LaunchResult:
        """Fortnite через URI Epic (если лаунчер установлен)."""
        uri = "com.epicgames.launcher://apps/Fortnite?action=launch&silent=true"

        def _run() -> None:
            try:
                os.startfile(uri)
            except OSError:
                # fallback — просто открыть Epic
                pass

        await asyncio.to_thread(_run)
        # если URI не сработал — обычный epic
        epic = await self.launch_app("epic")
        if epic.status == "error":
            return LaunchResult("error", "fortnite", "Epic / Fortnite launch failed")
        return LaunchResult("started", "fortnite", "Fortnite / Epic launch requested")

    async def activate_gaming_protocol(
        self,
        game: str = "cs2",
        with_discord: bool = True,
    ) -> list[LaunchResult]:
        coros = []
        if with_discord:
            coros.append(self.launch_app("discord"))

        g = game.strip().lower()
        if g in ("fortnite", "epic fortnite"):
            coros.append(self.launch_fortnite_epic())
        else:
            coros.append(self.launch_steam_game(game))

        raw = await asyncio.gather(*coros, return_exceptions=True)
        results: list[LaunchResult] = []
        for item in raw:
            if isinstance(item, Exception):
                results.append(LaunchResult("error", "protocol", str(item)))
            else:
                results.append(item)
        return results
    
    async def open_windows_settings(self, page: str = "") -> LaunchResult:
        # page пусто = корень; ms-settings:display, bluetooth, ...
        uri = "ms-settings:" if not page else f"ms-settings:{page}"

        def _run() -> None:
            os.startfile(uri)

        await asyncio.to_thread(_run)
        return LaunchResult("opened", uri, f"Opened {uri}")
    
    async def launch_whatsapp(self) -> LaunchResult:
        """WhatsApp Desktop (Store) через протокол / shell."""
        if self.is_process_running(["whatsapp.exe", "WhatsApp.exe"]):
            return LaunchResult("already_running", "whatsapp", "whatsapp is already running")

        def _run() -> None:
            # 1) протокол приложения
            try:
                os.startfile("whatsapp:")
                return
            except OSError:
                pass
            # 2) через cmd start
            subprocess.Popen(
                ["cmd", "/c", "start", "", "whatsapp:"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

        await asyncio.to_thread(_run)
        return LaunchResult("started", "whatsapp", "Started whatsapp")
    
    def _contacts_path(self) -> Path:
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "Jarvis"
        base.mkdir(parents=True, exist_ok=True)
        return base / "contacts.json"

    def _load_contacts(self) -> dict[str, str]:
        import json
        path = self._contacts_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                str(k).lower().strip(): str(v).lstrip("+").replace(" ", "")
                for k, v in data.items()
            }
        except Exception:
            return {}

    async def whatsapp_message(self, contact: str, text: str = "") -> LaunchResult:
        from urllib.parse import quote

        contacts = self._load_contacts()
        key = (contact or "").strip().lower()
        phone = contacts.get(key)

        if not phone:
            digits = "".join(c for c in (contact or "") if c.isdigit())
            if len(digits) >= 10:
                phone = digits
            else:
                return LaunchResult(
                    "error",
                    contact,
                    f"Контакт не найден: {contact}. Добавь в %APPDATA%\\Jarvis\\contacts.json",
                )

        if text:
            uri = f"https://wa.me/{phone}?text={quote(text)}"
        else:
            uri = f"https://wa.me/{phone}"

        def _run() -> None:
            webbrowser.open(uri)

        await asyncio.to_thread(_run)
        return LaunchResult("opened", phone, f"WhatsApp: {contact}")

    async def whatsapp_call(self, contact: str) -> LaunchResult:
        r = await self.whatsapp_message(contact, text="")
        if r.status == "error":
            return r
        return LaunchResult(
            "opened",
            r.target,
            f"Чат WhatsApp с {contact} открыт. Нажми кнопку звонка в приложении.",
        )

    async def spotify_media(self, action: str) -> LaunchResult:
        """
        Media keys: play_pause | next | previous
        Works with Spotify (and system media session) without API.
        """
        action = (action or "").strip().lower()
        # Virtual-Key codes (Windows)
        vk = {
            "play_pause": 0xB3,  # VK_MEDIA_PLAY_PAUSE
            "play": 0xB3,
            "pause": 0xB3,
            "next": 0xB0,        # VK_MEDIA_NEXT_TRACK
            "previous": 0xB1,    # VK_MEDIA_PREV_TRACK
            "prev": 0xB1,
        }.get(action)

        if vk is None:
            return LaunchResult("error", action, f"Unknown media action: {action}")

        def _run() -> None:
            import ctypes
            user32 = ctypes.windll.user32
            # key down + key up
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP = 2

        await asyncio.to_thread(_run)
        return LaunchResult("started", action, f"Spotify media: {action}")


controller = SystemController()