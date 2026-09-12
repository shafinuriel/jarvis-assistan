# action/study_helper.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROGRESS_FILE = Path("memory/study_progress.json")

def _load_progress() -> Dict[str, Any]:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return{}


def _save_progress(data: Dict[str, Any]) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def study_helper(parameters: dict) -> str:
    action = (parameters.get("action") or"").lower().strip()
    subject = (parameters.get("subject") or "general").lower().strip()
    topic = (parameters.get("topic") or "").strip()
    user_answer = (parameters.get("user_answer") or "").strip()
    difficulty = (parameters.get("difficulty") or "medium").lower().strip()
    section = (parameters.get("section") or "").strip()

    progress = _load_progress()
    key = f"{subject}::{section or topic}" if (section or topic) else subject
    
    # ===== PROGRESS =====
    if action == "progress":
        if not progress:
            return "Пока нет сохранённого прогресса по Протоколу: Учения."
        lines = ["Прогресс по Протоколу: Учения:"]
        for k, v in progress.items():
            lines.append(
                f"• {k}: уровень {v.get('level', 1)} | "
                f"серия правильных: {v.get('streak', 0)} | "
                f"всего попыток: {v.get('total', 0)}"
            )
        return "\n".join(lines)

    # ===== THEORY =====
    if action == "theory":
        if not topic and not section:
            return "Укажите тему или секцию (tipic/section)."
        target= section or topic
        return (
            f"[Протокол: Учения — Теория]\n"
            f"Предмет/Экзамен: {subject.upper()}\n"
            f"Тема/Секция: {target}\n\n"
            f"Здесь должна быть краткая и чёткая теория/стратегия.\n"
            f"После теории предложи перейти к практике."
        )
    
    
    # ===== TASK =====
    if action == "task":
        level = progress.get(key, {}).get("level", 1)
        target = section or topic or subject
        return (
             f"[Протокол: Учения — Задание]\n"
            f"Предмет: {subject.upper()} | Уровень: {level} | Сложность: {difficulty}\n"
            f"Тема/Секция: {target}\n\n"
            f"Сгенерируй одну подходящую задачу/вопрос.\n"
            f"Не давай ответ. Жди ответа пользователя."
        )

    
    # ===== CHECK =====
    if action == "check":
        if not user_answer:
            return "Ты не присалал ответ. Напиши, что получилось."
        
        entry = progress.get(key, {"level": 1, "streak": 0, "total": 0})
        entry["total"] = entry.get("total", 0) + 1
        entry["streak"] = entry.get("streak", 0) + 1
        
        
        # Повышения уровня после 3 правильных подряд
        if entry["streak"] >= 3:
            entry["level"] = entry.get("level", 1) + 1
            entry["streak"] = 0

        progress[key] = entry
        _save_progress(progress)
    
        return (
            f"[Протокол: Учения — Проверка]\n"
            f"Ответ ученика: {user_answer}\n\n"
            f"Оцени правильность.\n"
            f"- Если верно → похвали и дай следующую задачу чуть сложнее.\n"
            f"- Если ошибка → дай небольшую подсказку (не полное решение).\n"
            f"Текущий уровень по этой теме: {entry['level']}"
        )
    return(
        "Неизвестное действие. Доступные action:\n"
        "• theory — теория\n"
        "• task — задание\n"
        "• check — проверка ответа\n"
        "• progress — прогресс"
    )
    
