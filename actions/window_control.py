"""
Window Control — безопасное управление окнами Windows через pywinauto.
Zero-Overhead: никаких фоновых циклов, только по вызову.
"""

from __future__ import annotations

import time
from typing import Optional

try:
    from pywinauto import Desktop
    from pywinauto.findwindows import ElementNotFoundError
    _PYWIN = True
except ImportError:
    _PYWIN = False


def _check() -> None:
    if not _PYWIN:
        raise RuntimeError("pywinauto not installed. Run: pip install pywinauto")


def list_windows(limit: int = 15) -> list[dict]:
    """
    Возвращает список видимых окон:
    [{"title": "...", "process": "..."}, ...]
    """
    _check()
    desktop = Desktop(backend="uia")
    result = []
    for w in desktop.windows():
        try:
            title = (w.window_text() or "").strip()
            if not title:
                continue
            if not w.is_visible():
                continue
            # пропускаем совсем системный мусор
            if title.lower() in ("program manager", "taskbar"):
                continue
            result.append({
                "title": title[:80],
                "process": w.process_id(),
            })
            if len(result) >= limit:
                break
        except Exception:
            continue
    return result


def focus_window(title_part: str) -> str:
    """
    Находит окно по части названия и выводит на передний план.
    """
    _check()
    title_part = title_part.strip().lower()
    if not title_part:
        return "Empty window title."

    desktop = Desktop(backend="uia")
    for w in desktop.windows():
        try:
            title = (w.window_text() or "").strip()
            if title_part in title.lower() and w.is_visible():
                w.set_focus()
                time.sleep(0.15)
                return f"Focused: {title[:60]}"
        except Exception:
            continue
    return f"Window containing '{title_part}' not found."


def click_center(title_part: str) -> str:
    """
    Фокусирует окно и кликает примерно в центр.
    """
    _check()
    title_part = title_part.strip().lower()
    desktop = Desktop(backend="uia")
    for w in desktop.windows():
        try:
            title = (w.window_text() or "").strip()
            if title_part in title.lower() and w.is_visible():
                w.set_focus()
                time.sleep(0.1)
                rect = w.rectangle()
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2
                w.click_input(coords=(cx - rect.left, cy - rect.top))
                return f"Clicked center of: {title[:60]}"
        except Exception:
            continue
    return f"Window containing '{title_part}' not found."


def type_text(title_part: str, text: str) -> str:
    """
    Фокусирует окно и печатает текст (как с клавиатуры).
    """
    _check()
    title_part = title_part.strip().lower()
    desktop = Desktop(backend="uia")
    for w in desktop.windows():
        try:
            title = (w.window_text() or "").strip()
            if title_part in title.lower() and w.is_visible():
                w.set_focus()
                time.sleep(0.1)
                w.type_keys(text, with_spaces=True, pause=0.02)
                return f"Typed into: {title[:60]}"
        except Exception:
            continue
    return f"Window containing '{title_part}' not found."