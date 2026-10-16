"""
Offline brain for Jarvis.
1) Instant local math (zero overhead)
2) Else Gemma via Ollama (gemma3:4b)
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import urllib.error
import urllib.request
from typing import Optional, Tuple

DEFAULT_MODEL = "gemma3:4b"
OLLAMA_URL = "http://127.0.0.1:11434"


# ─── быстрая математика (без модели) ───────────────────────────────────────

def _norm(text: str) -> str:
    t = (text or "").lower().strip()
    t = t.replace("×", "*").replace("÷", "/").replace(":", "/")
    t = t.replace("^", "**")
    return t


def _extract_number(s: str) -> Optional[float]:
    m = re.search(r"-?\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def try_math(text: str) -> Optional[str]:
    t = _norm(text)
    if not t:
        return None

    # факториал
    m = re.search(r"факториал\s*(\d{1,2})\b", t)
    if m:
        n = int(m.group(1))
        if n > 20:
            return "Факториал слишком большой для offline (макс 20)."
        return str(math.factorial(n))
    m = re.search(r"\b(\d{1,2})\s*!", t)
    if m:
        n = int(m.group(1))
        if n > 20:
            return "Факториал слишком большой для offline (макс 20)."
        return str(math.factorial(n))

    # корень
    if any(k in t for k in ("корень", "sqrt", "√")):
        n = _extract_number(t)
        if n is None or n < 0:
            return None
        r = math.sqrt(n)
        if abs(r - round(r)) < 1e-10:
            return str(int(round(r)))
        return f"{r:.6g}"

    # проценты: X процентов от Y
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%?\s*процент", t)
    if m and "от" in t:
        p = float(m.group(1).replace(",", "."))
        m2 = re.search(r"от\s*(\d+(?:[.,]\d+)?)", t)
        if m2:
            n = float(m2.group(1).replace(",", "."))
            return f"{(p / 100.0) * n:.6g}"

    # степень a**b / a в степени b
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:\*\*|\^)\s*(\d{1,3})", t)
    if m:
        a = float(m.group(1).replace(",", "."))
        b = int(m.group(2))
        if b > 1000:
            return "Слишком большая степень для offline."
        return f"{a ** b:.6g}"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*в\s*степен[иь]\s*(\d{1,3})", t)
    if m:
        a = float(m.group(1).replace(",", "."))
        b = int(m.group(2))
        return f"{a ** b:.6g}"

    # простая арифметика
    m = re.search(r"[\d\.\s\+\-\*/\(\)]+", t)
    if m:
        raw = m.group(0).replace(",", ".").replace(" ", "")
        if re.fullmatch(r"[\d\.\+\-\*/\(\)]+", raw) and any(c in raw for c in "+-*/"):
            try:
                val = eval(raw, {"__builtins__": {}}, {})
                if isinstance(val, (int, float)) and abs(val - round(val)) < 1e-10:
                    return str(int(round(val)))
                return f"{val:.6g}"
            except Exception:
                pass
    return None


# ─── Ollama / Gemma ─────────────────────────────────────────────────────────

def is_ollama_up(timeout: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _chat_sync(prompt: str, model: str = DEFAULT_MODEL, timeout: float = 120.0) -> str:
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are JARVIS offline brain. Answer briefly and accurately. "
                    "Prefer short facts and numbers. Match the user's language."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    msg = payload.get("message") or {}
    return (msg.get("content") or "").strip() or "Пустой ответ offline-мозга."


async def is_available() -> bool:
    return await asyncio.to_thread(is_ollama_up)


async def ask(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """
    1) math → мгновенно
    2) иначе Gemma через Ollama
    """
    if not prompt or not str(prompt).strip():
        return "Пустой запрос."

    m = try_math(prompt)
    if m is not None:
        return m

    if not await asyncio.to_thread(is_ollama_up):
        return "Ollama не запущена. Запусти Ollama и повтори."

    try:
        return await asyncio.to_thread(_chat_sync, str(prompt).strip(), model)
    except urllib.error.URLError as e:
        return f"Offline brain недоступен: {e}"
    except Exception as e:
        return f"Offline brain error: {e}"


def answer(text: str) -> Tuple[bool, str]:
    """Совместимость со старым API: (handled, reply). Только math."""
    m = try_math(text)
    if m is not None:
        return True, m
    return False, ""