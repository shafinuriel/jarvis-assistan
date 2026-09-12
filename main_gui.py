"""Демо сферы Jarvis через SphereWidget."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtWidgets import QApplication, QMainWindow

from sphere_widget import SphereWidget


class SphereWindow(QMainWindow):
    def __init__(self, html_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("Jarvis Sphere")
        self.setFixedSize(500, 500)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_pos: QPoint | None = None

        self.sphere = SphereWidget(self, html_path)
        self.setCentralWidget(self.sphere)

        self._states = ["idle", "listening", "thinking", "speaking"]
        self._idx = 0
        self._demo = QTimer(self)
        self._demo.timeout.connect(self._cycle_demo)
        QTimer.singleShot(1500, lambda: self._demo.start(5000))

    def _cycle_demo(self) -> None:
        self._idx = (self._idx + 1) % len(self._states)
        st = self._states[self._idx]
        self.sphere.set_state(st)
        print(f"[sphere] state -> {st}")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None


def main() -> None:
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass

    app = QApplication(sys.argv)
    html = Path(__file__).resolve().parent / "sphere_ui.html"
    if not html.is_file():
        raise SystemExit(f"Не найден: {html}")

    w = SphereWindow(html)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()