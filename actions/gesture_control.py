# -*- coding: utf-8 -*-
"""
Gesture Control v2 — MediaPipe Tasks (Hand Landmarker)
Zero-Overhead: camera runs only while enabled.
Works with mediapipe 1.x (no mp.solutions).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

# model next to project root / models/
_MODEL = Path(__file__).resolve().parent.parent / "models" / "hand_landmarker.task"


class GestureController:
    def __init__(self, on_gesture: Optional[Callable[[str], None]] = None):
        self.on_gesture = on_gesture
        self._enabled = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_gesture = ""
        self._last_time = 0.0
        self._cooldown = 1.2  # sec between same gesture

        self._cv2 = None
        self._landmarker = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> str:
        if self._enabled:
            return "already_running"
        if not _MODEL.is_file():
            return f"error_no_model: put hand_landmarker.task in {_MODEL.parent}"

        try:
            import cv2
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core import base_options as bo

            self._cv2 = cv2
            options = vision.HandLandmarkerOptions(
                base_options=bo.BaseOptions(model_asset_path=str(_MODEL)),
                num_hands=1,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.5,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[GESTURE] import/init error: {e}")
            return f"error_import: {e}"

        self._stop.clear()
        self._enabled = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return "started"

    def stop(self) -> str:
        self._enabled = False
        self._stop.set()
        t = self._thread
        self._thread = None
        if t and t.is_alive():
            t.join(timeout=2.0)
        # закрываем только если поток уже умер
        self._close_landmarker()
        return "gestures stopped"

    def _close_landmarker(self):
        lm = getattr(self, "_landmarker", None)
        self._landmarker = None
        if lm is not None:
            try:
                lm.close()
            except Exception:
                pass

    def _classify(self, landmarks) -> Optional[str]:
        """landmarks: list of 21 NormalizedLandmark (x,y,z)."""
        # tip ids: thumb=4, index=8, middle=12, ring=16, pinky=20
        # pip ids: 3, 6, 10, 14, 18
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]

        def up(tip_i, pip_i):
            # y smaller = higher on screen
            return landmarks[tip_i].y < landmarks[pip_i].y - 0.02

        fingers = [up(t, p) for t, p in zip(tips, pips)]
        # thumb: compare x relative to palm (simple)
        fingers[0] = landmarks[4].x < landmarks[3].x  # rough for mirrored cam

        open_count = sum(1 for f in fingers if f)

        if open_count >= 4:
            return "open_palm"
        if open_count <= 1:
            return "fist"
        return None

    def _loop(self) -> None:
        from mediapipe import Image as MPImage
        from mediapipe import ImageFormat

        cv2 = self._cv2
        cap = cv2.VideoCapture(0)
        self._cap = cap
        if not cap.isOpened():
            print("[GESTURE] cannot open camera")
            self._enabled = False
            return

        try:
            while not self._stop.is_set() and self._enabled:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue

                if self._stop.is_set() or not self._enabled:
                    break

                frame = cv2.flip(frame, 1)  # mirror
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = MPImage(image_format=ImageFormat.SRGB, data=rgb)

                try:
                    result = self._landmarker.detect(mp_image)
                except Exception:
                    break

                if result.hand_landmarks:
                    lm = result.hand_landmarks[0]
                    name = self._classify(lm)
                    now = time.monotonic()
                    if name and (name != self._last_gesture or now - self._last_time > self._cooldown):
                        self._last_gesture = name
                        self._last_time = now
                        print(f"[GESTURE] {name}")
                        try:
                            self.on_gesture(name)
                        except Exception as e:
                            print(f"[GESTURE] callback error: {e}")

                time.sleep(0.03)  # \~30 FPS max, low CPU
        finally:
            try:
                if hasattr(self, "_cap") and self._cap is not None:
                    self._cap.release()
            except Exception:
                pass
            self._cap = None
            self._close_landmarker()
            print("[GESTURE] loop stopped")