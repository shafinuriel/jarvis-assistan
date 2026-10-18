# actions/messenger_assistant.py
"""
Messenger assistant: whitelist alerts + DND auto-reply (Telegram later).
Config: memory/messenger_config.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set
import asyncio

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "memory" / "messenger_config.json"
COOLDOWN_PATH = BASE / "memory" / "messenger_cooldown.json"
STYLE_SAMPLES_PATH = BASE / "memory" / "chat_style_samples.json"

def _load_json(path: Path, default: dict) -> dict:
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[MSG] load {path.name}: {e}")
    return dict(default)


def _save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[MSG] save {path.name}: {e}")


class MessengerAssistant:
    def __init__(self, jarvis: Any = None):
        self.jarvis = jarvis
        self.cfg: Dict[str, Any] = {}
        self._running = False
        self._cooldown: Dict[str, float] = {}  # key -> last reply unix time
        self.reload_config()
        self._load_cooldown()
        self._tg_client = None
        self._tg_task = None
        self._pending_draft = None

    # ----- config -----
    def reload_config(self) -> None:
        # 1. Сначала читаем старый конфиг (whitelist, тексты, api_id и т.д.)
        self.cfg = _load_json(
            CONFIG_PATH,
            {
                "enabled": False,
                "dnd_enabled": True,
                "draft_enabled": True,
                "reply_lang": "ru",
                "reply_text_ru": "Привет, это Джарвис. Нуриэль сейчас занят, напишет потом.",
                "reply_text_en": "Hi, this is Jarvis. Nuriel is busy right now and will write later.",
                "cooldown_seconds": 3600,
                "whitelist": [],
                "telegram": {"enabled": False},
                "whatsapp": {"enabled": False},
            },
        )

        # 2. Главные флаги берём из единого config.json
        from memory.config_manager import get_feature_flag
        self.cfg["enabled"] = get_feature_flag("messenger_enabled", self.cfg.get("enabled", True))
        self.cfg["dnd_enabled"] = get_feature_flag("dnd_enabled", self.cfg.get("dnd_enabled", False))
        self.cfg["draft_enabled"] = get_feature_flag("draft_enabled", self.cfg.get("draft_enabled", True))

        print(f"[MSG] config loaded (enabled={self.cfg.get('enabled')})")

    def _load_cooldown(self) -> None:
        raw = _load_json(COOLDOWN_PATH, {})
        self._cooldown = {str(k): float(v) for k, v in raw.items()}

    def _save_cooldown(self) -> None:
        _save_json(COOLDOWN_PATH, self._cooldown)

    # ----- helpers -----
    def _whitelist_set(self) -> Set[str]:
        names = self.cfg.get("whitelist") or []
        return {str(n).strip().lower() for n in names if str(n).strip()}

    def is_whitelisted(self, name: str) -> bool:
        if not name:
            return False
        return name.strip().lower() in self._whitelist_set()

    def reply_text(self) -> str:
        lang = (self.cfg.get("reply_lang") or "ru").lower()
        if lang == "en":
            return (
                self.cfg.get("reply_text_en")
                or "Hi, this is Jarvis. Nuriel is busy right now and will write later."
            )
        return (
            self.cfg.get("reply_text_ru")
            or "Привет, это Джарвис. Нуриэль сейчас занят, напишет потом."
        )

    def cooldown_ok(self, contact_key: str) -> bool:
        """True if we may send auto-reply (not more than once per cooldown window)."""
        key = (contact_key or "").strip().lower()
        if not key:
            return False
        sec = int(self.cfg.get("cooldown_seconds") or 3600)
        last = self._cooldown.get(key, 0.0)
        return (time.time() - last) >= sec

    def mark_replied(self, contact_key: str) -> None:
        key = (contact_key or "").strip().lower()
        if not key:
            return
        self._cooldown[key] = time.time()
        self._save_cooldown()

    async def _speak(self, text: str) -> None:
        if not text:
            return
        try:
            speak = getattr(self.jarvis, "speak", None)
            if speak:
                await speak(text)
                return
        except Exception as e:
            print(f"[MSG] speak: {e}")
        print(f"[MSG] (speak) {text}")

    # ----- public API (Telegram will call these) -----
    async def on_incoming_message(self, sender_name: str, sender_id: str = "", text: str = "") -> None:
        if not self.cfg.get("enabled", True):
            return

        name = (sender_name or "").strip() or "Unknown"
        key = (sender_id or name).strip()
        incoming = (text or "").strip()
        dnd = bool(self.cfg.get("dnd_enabled", False))  # ordinary mode by default

        # --- DND + whitelist: announce only, never reply ---
        if dnd and self.is_whitelisted(name):
            await self._speak(f"Вам пишет {name}")
            print(f"[MSG] whitelist (DND) from {name}")
            return

        # --- DND + others: fixed phrase ---
        if dnd:
            if not self.cooldown_ok(key):
                print(f"[MSG] cooldown active for {name}, skip reply")
                return
            reply = self.reply_text()
            sent = await self._send_reply(sender_id=sender_id, sender_name=name, text=reply)
            if sent:
                self.mark_replied(key)
                print(f"[MSG] DND auto-replied to {name}")
            return

        # --- Ordinary mode: draft for everyone (including family) ---
        if not self.cfg.get("draft_enabled", True):
            return
        if not incoming:
            await self._speak(f"Вам пишет {name}")
            return

        draft = await self._generate_draft(incoming, name)
        self._pending_draft = {
            "sender_id": sender_id,
            "sender_name": name,
            "incoming": incoming,
            "draft": draft,
            "ts": time.time(),
        }
        msg = f"{name} написал: {incoming}. Черновик: {draft}. Отправить или отмена?"
        await self._speak(msg)
        try:
            if hasattr(self.jarvis, "ui") and hasattr(self.jarvis.ui, "write_log"):
                self.jarvis.ui.write_log(f"MSG draft → {name}: {draft}")
        except Exception:
            pass
        print(f"[MSG] draft for {name}: {draft}")
        
    async def _generate_draft(self, incoming: str, name: str) -> str:
        hint = self.cfg.get("style_hint") or "Коротко и по-человечески."
        samples = []
        try:
            raw = _load_json(STYLE_SAMPLES_PATH, {})
            samples = [str(s).strip() for s in (raw.get("samples") or []) if str(s).strip()]
        except Exception:
            samples = []

        style_block = ""
        if samples:
            lines = [f"- {s}" for s in samples[:12]]
            style_block = "Примеры как я обычно пишу:\n" + "\n".join(lines) + "\n"

        base = samples[0] if samples else "Ок, принял. Напишу позже."
        prompt = (
            f"{hint}\n"
            f"{style_block}"
            f"Входящее от {name}: {incoming}\n"
            f"Напиши ОДИН короткий ответ от лица Нуриэля, без кавычек и без пояснений."
        )

        try:
            gen = getattr(self.jarvis, "generate_text", None)
            if gen:
                out = await gen(prompt)
                if out and len(str(out).strip()) > 1:
                    return str(out).strip()[:500]
        except Exception as e:
            print(f"[MSG] draft gen: {e}")

        return str(base)[:200]
    
    async def confirm_draft(self) -> bool:
        p = self._pending_draft
        if not p:
            await self._speak("Нет черновика.")
            return False
        if time.time() - p.get("ts", 0) > 600:
            self._pending_draft = None
            await self._speak("Черновик устарел.")
            return False
        ok = await self._send_reply(p["sender_id"], p["sender_name"], p["draft"])
        self._pending_draft = None
        if ok:
            await self._speak("Отправил.")
        return ok

    async def cancel_draft(self) -> None:
        self._pending_draft = None
        await self._speak("Отменил.")

    async def on_incoming_call(self, caller_name: str) -> None:
        """Whitelist: announce only. Others: optional future reject + SMS-style reply."""
        if not self.cfg.get("enabled", True):
            return
        name = (caller_name or "").strip() or "Unknown"
        if self.is_whitelisted(name):
            await self._speak(f"Вам звонит {name}")
            print(f"[MSG] whitelist call from {name}")
            return
        # Non-whitelist calls: for now only log; call reject needs client support
        print(f"[MSG] call from non-whitelist: {name}")

    async def _send_reply(self, sender_id: str, sender_name: str, text: str) -> bool:
        if not text:
            return False
        client = self._tg_client
        if client is None:
            print(f"[MSG] SEND (no TG client) → {sender_name}: {text}")
            return False
        try:
            entity = int(sender_id) if str(sender_id).lstrip("-").isdigit() else sender_id
            await client.send_message(entity, text)
            return True
        except Exception as e:
            print(f"[MSG] send failed: {e}")
            return False

    # ----- lifecycle -----
    def start(self) -> bool:
        if self._running:
            return True
        self.reload_config()
        if not self.cfg.get("enabled", True):
            print("[MSG] disabled in config")
            return False
        self._running = True
        print("[MSG] started")

        tg = self.cfg.get("telegram") or {}
        if tg.get("enabled") and tg.get("api_id") and tg.get("api_hash"):
            try:
                loop = asyncio.get_event_loop()
                self._tg_task = loop.create_task(self._run_telegram())
            except Exception as e:
                print(f"[MSG] cannot schedule Telegram: {e}")
        else:
            print("[MSG] Telegram disabled or missing api_id/api_hash")
        return True

    def stop(self) -> None:
        self._running = False
        self._save_cooldown()
        if self._tg_task and not self._tg_task.done():
            self._tg_task.cancel()
        self._tg_task = None
        client = self._tg_client
        self._tg_client = None
        if client is not None:
            try:
                asyncio.get_event_loop().create_task(client.disconnect())
            except Exception:
                pass
        print("[MSG] stopped")

    async def _run_telegram(self) -> None:
        try:
            from telethon import TelegramClient, events
        except ImportError:
            print("[MSG] pip install telethon")
            return

        tg = self.cfg.get("telegram") or {}
        api_id = int(tg.get("api_id") or 0)
        api_hash = str(tg.get("api_hash") or "").strip()
        session = str(tg.get("session_name") or "jarvis_tg").strip()
        if not api_id or not api_hash:
            print("[MSG] Telegram api_id/api_hash empty")
            return

        session_path = str(BASE / "memory" / session)
        client = TelegramClient(session_path, api_id, api_hash)
        self._tg_client = client

        @client.on(events.NewMessage(incoming=True))
        async def _on_msg(event):
            if not self._running:
                return
            try:
                if not event.is_private:
                    return  # only private chats
                sender = await event.get_sender()
                name = ""
                if sender is not None:
                    name = (
                        getattr(sender, "first_name", None)
                        or getattr(sender, "username", None)
                        or ""
                    )
                    if getattr(sender, "last_name", None):
                        name = f"{name} {sender.last_name}".strip()
                if not name:
                    name = "Unknown"
                sid = str(event.sender_id)
                await self.on_incoming_message(
                    sender_name=name,
                    sender_id=sid,
                    text=event.raw_text or "",
                )
            except Exception as e:
                print(f"[MSG] on_msg: {e}")

        try:
            print("[MSG] Telegram connecting (check terminal for login code)...")
            await client.start()
            me = await client.get_me()
            print(f"[MSG] Telegram OK as {getattr(me, 'username', None) or me.id}")
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[MSG] Telegram error: {e}")
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._tg_client = None
            print("[MSG] Telegram disconnected")
    
    def is_running(self) -> bool:
        return self._running