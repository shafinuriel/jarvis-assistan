"""
Proactive Notes (cloud) — Firebase RTDB listener.
Local silence ProactiveEngine stays in proactive.py — do not mix.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

import firebase_admin
from firebase_admin import credentials, db

# Путь к service account (относительно корня проекта Jarvis)
# Если URL другой — поменяй одну строку:
DEFAULT_CRED = os.path.join("config", "firebase_service_account.json")


def _load_db_url() -> str:
    path = os.path.join("config", "firebase_url.txt")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            url = f.read().strip()
            if url:
                return url.rstrip("/") + "/"
    # placeholder для GitHub — свой URL только в config/firebase_url.txt
    return "https://YOUR-PROJECT-default-rtdb.firebaseio.com/"


DEFAULT_DB_URL = _load_db_url()


class NotesListener:
    """Listen notes/ ; on status==new -> mark read -> callback."""

    def __init__(
        self,
        on_note: Callable[[dict], None],
        cred_path: str = DEFAULT_CRED,
        db_url: str = DEFAULT_DB_URL,
    ):
        self.on_note = on_note
        self.cred_path = cred_path
        self.db_url = db_url.rstrip("/") + "/"
        self._app = None
        self._stream = None
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if not os.path.isfile(self.cred_path):
                raise FileNotFoundError(f"Firebase cred not found: {self.cred_path}")
            try:
                if not firebase_admin._apps:
                    cred = credentials.Certificate(self.cred_path)
                    self._app = firebase_admin.initialize_app(
                        cred, {"databaseURL": self.db_url}
                    )
                else:
                    self._app = firebase_admin.get_app()
                ref = db.reference("notes")
                self._stream = ref.listen(self._on_event)
                self._started = True
                print("[NotesListener] listening on notes/")
                self._catch_up()
            except Exception as e:
                self._started = False
                self._stream = None
                raise RuntimeError(f"NotesListener start failed: {e}") from e

    def is_alive(self) -> bool:
        return bool(self._started and self._stream is not None)

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self._started = False
            print("[NotesListener] stopped")

    def _on_event(self, event) -> None:
        # event.event_type: put | patch | ...
        # event.path: relative to notes/
        # event.data: dict | None
        try:
            data = event.data
            if not isinstance(data, dict):
                return

            # put на /notes/{id} → data = один note
            # put на /notes → data = {id: note, ...}
            if "status" in data:
                self._handle_note(event.path, data)
                return

            for note_id, note in data.items():
                if isinstance(note, dict) and note.get("status") == "new":
                    self._handle_note(note_id, note)
        except Exception as e:
            print(f"[NotesListener] event error: {e}")

    def _catch_up(self) -> None:
        """Подхватить status=new, если ПК был выключен."""
        try:
            data = db.reference("notes").get() or {}
            if not isinstance(data, dict):
                return
            for key, note in data.items():
                if isinstance(note, dict) and note.get("status") == "new":
                    self._handle_note(key, note)
        except Exception as e:
            print(f"[NotesListener] catch_up failed: {e}")
    
    def _handle_note(self, path: str, note: dict) -> None:
        if note.get("status") != "new":
            return

        note_id = path.strip("/").split("/")[-1] if path else note.get("id")
        if not note_id or note_id == "notes":
            # path может быть "/" при корневом put
            note_id = note.get("id")
        if not note_id:
            return

        # Сразу read — чтобы не обработать дважды
        try:
            db.reference(f"notes/{note_id}/status").set("read")
        except Exception as e:
            print(f"[NotesListener] mark read failed: {e}")
            return

        payload = {
            "id": note_id,
            "text": note.get("text") or "",
            "summary": note.get("summary") or "",
            "tags": note.get("tags") or [],
            "checklist": note.get("checklist") or [],
            "timestamp": note.get("timestamp"),
        }
        try:
            self.on_note(payload)
        except Exception as e:
            print(f"[NotesListener] on_note error: {e}")


def make_speak_handler(speak_fn: Callable[[str], None]) -> Callable[[dict], None]:
    """Обёртка: короткое голосовое/лог сообщение."""

    def handler(note: dict) -> None:
        body = (note.get("summary") or note.get("text") or "").strip()
        if not body:
            body = "пустая заметка"
        if len(body) > 200:
            body = body[:200] + "…"
        tags = note.get("tags") or []
        tag_s = f" Теги: {', '.join(tags)}." if tags else ""
        msg = f"Сэр, заметка с телефона. {body}.{tag_s}"
        print(f"[NotesListener] {msg}")
        speak_fn(msg)

    return handler 