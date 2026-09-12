import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "memory" / "birthday.json"

DEFAULT_URL = "https://www.youtube.com/watch?v=ВСТАВЬ_ID"
DEFAULT_TV = "tv_kitchen"

def load_config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"youtube_url": DEFAULT_URL, "target_tv": DEFAULT_TV}

def get_birthday_target_and_url() -> tuple[str, str]:
    cfg = load_config()
    return (
        cfg.get("target_tv", DEFAULT_TV),
        cfg.get("youtube_url", DEFAULT_URL),
    )