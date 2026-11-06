# actions/security_scanner.py
"""
Трёхуровневый сканер безопасности Jarvis.
Zero-Overhead: ничего не грузит, пока не запущен.
Никогда не удаляет файлы сам — только сообщает.
"""

from __future__ import annotations

import os
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

# Подозрительные расширения
SUSPICIOUS_EXTENSIONS = {
    ".exe", ".vbs", ".bat", ".cmd", ".scr", ".ps1",
    ".js", ".jse", ".wsf", ".wsh", ".lnk"
}

# Известные опасные имена (лёгкий список)
KNOWN_BAD_NAMES = {
    "autorun.inf",
    "desktop.ini.exe",
    "svchost.exe",          # только если не в System32
    "explorer.exe",         # только если не в Windows
}

# Двойные расширения
DOUBLE_EXTENSIONS = (
    ".jpg.exe", ".png.exe", ".pdf.exe", ".doc.exe",
    ".mp4.exe", ".txt.exe", ".zip.exe"
)


@dataclass
class Threat:
    path: str
    reason: str
    severity: str = "medium"   # low / medium / high
    sha256: str = ""


@dataclass
class ScanResult:
    threats: List[Threat] = field(default_factory=list)
    scanned_files: int = 0
    duration_sec: float = 0.0
    level: str = "quick"       # quick / full


class SecurityScanner:
    def __init__(self):
        self._running = False
        self._last_result: Optional[ScanResult] = None
        # Колбэк, который UI/сфера подпишут позже
        self.on_threat_found: Optional[Callable[[Threat], None]] = None
        self.on_scan_finished: Optional[Callable[[ScanResult], None]] = None

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._running

    def get_last_result(self) -> Optional[ScanResult]:
        return self._last_result

    def quick_scan(self) -> ScanResult:
        """Быстрый скан: Downloads, Desktop, Temp, Startup."""
        paths = self._get_quick_paths()
        return self._scan_paths(paths, level="quick", max_depth=2)

    def full_scan(self, extra_paths: Optional[List[str]] = None) -> ScanResult:
        """Полный скан: ключевые папки + Documents + Pictures + Videos + Music, глубина выше."""
        paths = self._get_quick_paths()

        home = Path.home()
        extra = [
            str(home / "Documents"),
            str(home / "Pictures"),
            str(home / "Videos"),
            str(home / "Music"),
        ]
        for p in extra:
            if os.path.isdir(p) and p not in paths:
                paths.append(p)

        if extra_paths:
            paths.extend(extra_paths)

        return self._scan_paths(paths, level="full", max_depth=5)

    # ------------------------------------------------------------------
    # Внутренняя логика
    # ------------------------------------------------------------------

    def _get_quick_paths(self) -> List[str]:
        home = Path.home()
        paths = [
            str(home / "Downloads"),
            str(home / "Desktop"),
            os.environ.get("TEMP", ""),
            os.environ.get("TMP", ""),
        ]
        # Автозагрузка пользователя
        startup = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup.exists():
            paths.append(str(startup))

        return [p for p in paths if p and os.path.isdir(p)]

    def _scan_paths(self, paths: List[str], level: str = "quick", max_depth: int = 2) -> ScanResult:
        self._running = True
        start = time.time()
        result = ScanResult(level=level)

        try:
            for root_path in paths:
                self._walk(root_path, result, current_depth=0, max_depth=max_depth)
        finally:
            self._running = False
            result.duration_sec = round(time.time() - start, 2)
            self._last_result = result

            if self.on_scan_finished:
                self.on_scan_finished(result)

        return result

    def _walk(self, path: str, result: ScanResult, current_depth: int, max_depth: int):
        if current_depth > max_depth:
            return

        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            result.scanned_files += 1
                            threat = self._check_file(entry.path)
                            if threat:
                                result.threats.append(threat)
                                if self.on_threat_found:
                                    self.on_threat_found(threat)

                        elif entry.is_dir(follow_symlinks=False):
                            # Пропускаем тяжёлые системные папки
                            name = entry.name.lower()
                            if name in ("windows", "program files", "program files (x86)", "$recycle.bin", "system volume information"):
                                continue
                            self._walk(entry.path, result, current_depth + 1, max_depth)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            return

    def _check_file(self, filepath: str) -> Optional[Threat]:
        name = os.path.basename(filepath).lower()
        ext = os.path.splitext(name)[1]
        parent = os.path.basename(os.path.dirname(filepath)).lower()

        # 1. autorun.inf — всегда плохо
        if name == "autorun.inf":
            return Threat(filepath, "Найден autorun.inf", "high", self._sha256(filepath))

        # 2. Двойные расширения (photo.jpg.exe и т.п.)
        for de in DOUBLE_EXTENSIONS:
            if name.endswith(de):
                return Threat(filepath, f"Двойное расширение ({de})", "high", self._sha256(filepath))

        # 3. Известные опасные имена вне системных папок
        if name in KNOWN_BAD_NAMES:
            low_path = filepath.lower()
            if "\\windows\\" not in low_path and "\\system32\\" not in low_path:
                return Threat(filepath, f"Подозрительное имя: {name}", "high", self._sha256(filepath))

        # 4. Скрытые исполняемые файлы (не трогаем обычные файлы в Temp)
        dangerous_ext = {".exe", ".scr", ".bat", ".vbs", ".cmd", ".ps1"}
        if ext in dangerous_ext:
            # Только скрытые / системные атрибуты — обычные файлы в Temp игнорируем
            try:
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                FILE_ATTRIBUTE_HIDDEN = 0x2
                FILE_ATTRIBUTE_SYSTEM = 0x4
                if attrs != -1 and (attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)):
                    return Threat(filepath, f"Скрытый исполняемый файл: {name}", "high", "")
            except Exception:
                pass

        # .lnk на Desktop / в Startup — нормально, не считаем угрозой
        # Обычные .exe на Desktop тоже не считаем угрозой

        return None
    
    @staticmethod
    def _sha256(filepath: str) -> str:
        try:
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""


# Глобальный экземпляр (один на всё приложение)
scanner = SecurityScanner()