"""Виджет 3D-сферы Jarvis для встройкивui.py"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

class SphereWidget(QWebEngineView):
    def __init__(self, parent=None, html_path: Path | None = None) -> None:
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        s.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        
        if html_path is None:
            html_path = Path(__file__).resolve().parent / "sphere_ui.html"
        self._html_path= html_path
        self._ready = False
        self._pending_state: str | None = "idle"
        
        self.loadFinished.connect(self._on_loaded)
        self.load(QUrl.fromLocalFile(str(html_path.resolve())))
        
    def _on_loaded(self, ok:bool) -> None:
        self._ready = bool(ok)
        if ok and self._pending_state:
            self._js_state(self._pending_state)
            self._pending_state = None
            
    def _js_state(self, state: str)-> None:
        js = (
            "(function(){"
            f'if (typeof setJarvisState === "function") setJarvisState("{state}");'
            "})();"
        )
        self.page().runJavaScript(js)

    def set_state(self, state: str) -> None:
        state = (state or "idle").lower()
        if not self._ready:
            self._pending_state = state
            return
        self._js_state(state)

    def set_idle(self) -> None:
        self.set_state("idle")

    def set_listening(self) -> None:
        self.set_state("listening")

    def set_speaking(self) -> None:
        self.set_state("speaking")

    def set_thinking(self) -> None:
        self.set_state("thinking")