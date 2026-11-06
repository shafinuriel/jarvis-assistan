# actions/face_lock.py
"""
Owner-only face lock (Windows) using OpenCV LBPH — no dlib.
Uses local Haar cascade: memory/haarcascade_frontalface_default.xml
Owner photo: memory/owner_face.jpg
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

BASE = Path(__file__).resolve().parent.parent
OWNER_IMG = BASE / "memory" / "owner_face.jpg"
CASCADE_LOCAL = BASE / "memory" / "haarcascade_frontalface_default.xml"

DEFAULT_INTERVAL = 7.0
DEFAULT_MISS_LIMIT = 3
DEFAULT_THRESHOLD = 110.0


def _lock_workstation() -> None:
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        print(f"[FACE-LOCK] LockWorkStation failed: {e}")


class FaceLock:
    def __init__(
        self,
        jarvis: Any = None,
        interval: float = DEFAULT_INTERVAL,
        miss_limit: int = DEFAULT_MISS_LIMIT,
        threshold: float = DEFAULT_THRESHOLD,
        owner_path: Optional[Path] = None,
        camera_index: int = 0,
    ):
        self.jarvis = jarvis
        self.interval = max(5.0, float(interval))
        self.miss_limit = max(2, int(miss_limit))
        self.threshold = float(threshold)
        self.owner_path = Path(owner_path) if owner_path else OWNER_IMG
        self.camera_index = camera_index

        self._recognizer = None
        self._face_cascade = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._miss_streak = 0
        self._enabled = True
        self._cap = None
        self._ready = False

    # ---------- public ----------
    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not self._load_owner():
            return False
        self._stop.clear()
        self._enabled = True
        self._miss_streak = 0
        self._thread = threading.Thread(
            target=self._run, name="FaceLock", daemon=True
        )
        self._thread.start()
        print(
            f"[FACE-LOCK] started (every {self.interval}s, "
            f"lock after {self.miss_limit} misses, thr={self.threshold})"
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        self._enabled = False
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=self.interval + 2)
        self._release_camera()
        print("[FACE-LOCK] stopped")

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)
            if enabled:
                self._miss_streak = 0
        print(f"[FACE-LOCK] enabled={enabled}")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------- load owner ----------
    def _load_owner(self) -> bool:
        try:
            import cv2
        except ImportError:
            print("[FACE-LOCK] pip install opencv-contrib-python")
            return False

        if not hasattr(cv2, "face"):
            print(
                "[FACE-LOCK] cv2.face missing — install opencv-contrib-python "
                "(uninstall opencv-python first)"
            )
            return False

        path = self.owner_path
        if not path.is_file():
            print(f"[FACE-LOCK] owner photo missing: {path}")
            return False

        img = cv2.imread(str(path))
        if img is None:
            print(f"[FACE-LOCK] cannot read {path}")
            return False

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # cascade: local file first, then OpenCV data paths
        candidates = [str(CASCADE_LOCAL)]
        try:
            candidates.append(
                os.path.join(
                    cv2.data.haarcascades, "haarcascade_frontalface_default.xml"
                )
            )
        except Exception:
            pass
        try:
            candidates.append(
                os.path.join(
                    os.path.dirname(cv2.__file__),
                    "data",
                    "haarcascade_frontalface_default.xml",
                )
            )
        except Exception:
            pass

        cascade_path = None
        for p in candidates:
            if p and os.path.isfile(p):
                cascade_path = p
                break

        if not cascade_path:
            print(
                "[FACE-LOCK] haarcascade XML not found — "
                "put haarcascade_frontalface_default.xml in memory/"
            )
            return False

        self._face_cascade = cv2.CascadeClassifier(cascade_path)
        if self._face_cascade.empty():
            print(f"[FACE-LOCK] cascade empty: {cascade_path}")
            return False

        print(f"[FACE-LOCK] cascade OK: {cascade_path}")

        faces = self._face_cascade.detectMultiScale(
            gray, 1.1, 5, minSize=(80, 80)
        )
        if len(faces) < 1:
            print("[FACE-LOCK] no face in owner photo")
            return False

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_roi = cv2.resize(gray[y : y + h, x : x + w], (200, 200))

        self._recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._recognizer.train([face_roi], np.array([1], dtype=np.int32))
        self._ready = True
        print(f"[FACE-LOCK] owner model trained from {path.name}")
        return True

    # ---------- camera ----------
    def _open_camera(self):
        import cv2

        if self._cap is not None and self._cap.isOpened():
            return self._cap
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print("[FACE-LOCK] cannot open camera")
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        return cap

    def _release_camera(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _grab_gray(self):
        import cv2

        cap = self._open_camera()
        if cap is None:
            return None
        cap.read()  # drop buffered frame
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # ---------- evaluate ----------
    def _evaluate(self, gray) -> str:
        """owner | stranger | none"""
        import cv2

        if not self._ready or self._recognizer is None or self._face_cascade is None:
            return "none"

        faces = self._face_cascade.detectMultiScale(
            gray, 1.1, 5, minSize=(80, 80)
        )
        if len(faces) < 1:
            return "none"

        saw_stranger = False
        for (x, y, w, h) in faces:
            roi = cv2.resize(gray[y : y + h, x : x + w], (200, 200))
            label, confidence = self._recognizer.predict(roi)
            print(f"[FACE-LOCK] face conf={confidence:.1f} (thr={self.threshold})")
            if label == 1 and confidence <= self.threshold:
                return "owner"
            saw_stranger = True

        return "stranger" if saw_stranger else "none"

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                with self._lock:
                    enabled = self._enabled
                if enabled and self._ready:
                    if getattr(self.jarvis, "_vision_cam_active", False):
                        pass  # don't fight Vision camera
                    else:
                        gray = self._grab_gray()
                        if gray is not None:
                            self._handle_status(self._evaluate(gray))
                        else:
                            print("[FACE-LOCK] no frame")
            except Exception as e:
                print(f"[FACE-LOCK] loop error: {e}")
                self._release_camera()

            elapsed = time.monotonic() - t0
            wait = max(0.2, self.interval - elapsed)
            if self._stop.wait(wait):
                break
        self._release_camera()

    def _handle_status(self, status: str) -> None:
        # A: lock only when owner face is ABSENT (no face in frame).
        # Do NOT lock on "stranger" — LBPH confuses family members.

        if status == "owner":
            if self._miss_streak:
                print("[FACE-LOCK] owner present")
            self._miss_streak = 0
            return

        if status == "stranger":
            # Treat as "someone is at the PC" — do not lock
            print("[FACE-LOCK] face seen (not matched) — no lock")
            self._miss_streak = 0
            return

        # none — no face in frame
        self._miss_streak += 1
        print(f"[FACE-LOCK] owner missing ({self._miss_streak}/{self.miss_limit})")
        if self._miss_streak >= self.miss_limit:
            print("[FACE-LOCK] miss limit → lock")
            self._miss_streak = 0
            _lock_workstation()
            self._stop.wait(3.0)