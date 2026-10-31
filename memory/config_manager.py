import json
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"          # старый файл (оставляем)
MAIN_CONFIG_FILE = CONFIG_DIR / "config.json"        # новый главный конфиг

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return CONFIG_FILE.exists()

def save_api_keys(gemini_api_key: str) -> None:
    ensure_config_dir()

    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["gemini_api_key"] = gemini_api_key.strip()

    CONFIG_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )

def load_api_keys() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to load api_keys.json: {e}")
        return {}

def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)


def get_assistant_name() -> str:
    """Return the configured assistant name, or 'JARVIS' if not set."""
    return load_api_keys().get("assistant_name", "JARVIS") or "JARVIS"


def get_user_name() -> str:
    """Return the configured user name for addressing."""
    return load_api_keys().get("user_name", "")


def save_assistant_config(assistant_name: str, user_name: str) -> None:
    """Persist assistant name and user name to config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["assistant_name"] = assistant_name.strip() or "JARVIS"
    data["user_name"] = user_name.strip()
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_brief_enabled() -> bool:
    return load_api_keys().get("morning_brief_enabled", True)


def save_brief_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["morning_brief_enabled"] = enabled
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    
# ==========================================
# New MAIN CONFIG (config/config.json)
# ==========================================

def load_main_config() -> dict:
    """Загружает главный config.json"""
    if not MAIN_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(MAIN_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"X Failed to load config.json: {e}")
        return {}


def save_main_config(data: dict) -> None:
    """Сохраняет главный config.json"""
    ensure_config_dir()
    try:
        MAIN_CONFIG_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"X Failed to save config.json: {e}")


def get_setting(section: str, key: str, default=None):
    """Получить значение настройки из главного конфига"""
    config = load_main_config()
    return config.get(section, {}).get(key, default)


def set_setting(section: str, key: str, value) -> None:
    """Установить значение настройки в главный конфиг"""
    config = load_main_config()
    if section not in config:
        config[section] = {}
    config[section][key] = value
    save_main_config(config)
    
# ==========================================
# Smart assistant with bacward compatibility
# ==========================================

def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """
    Универсальный способ получить флаг функции.
    Сначала ищет в новом config.json, потом в старых файлах.
    """
    # 1. Новый главный конфиг (config/config.json)
    if flag_name in ("usb_security_enabled", "download_guard_enabled", "sphere_alert"):
        value = get_setting("security", flag_name, None)
        if value is not None:
            return bool(value)

    if flag_name in ("morning_brief_enabled", "face_lock_enabled",
                     "gesture_control_enabled", "proactive_enabled"):
        value = get_setting("features", flag_name, None)
        if value is not None:
            return bool(value)

    if flag_name in ("messenger_enabled", "dnd_enabled", "draft_enabled"):
        # messenger_enabled → ключ "enabled" в секции messenger
        key = "enabled" if flag_name == "messenger_enabled" else flag_name
        value = get_setting("messenger", key, None)
        if value is not None:
            return bool(value)

    # 2. Обратная совместимость со старыми файлами
    try:
        if flag_name == "usb_security_enabled":
            old_path = BASE_DIR / "memory" / "usb_security.json"
            if old_path.exists():
                data = json.loads(old_path.read_text(encoding="utf-8"))
                return bool(data.get("enabled", default))

        if flag_name == "download_guard_enabled":
            old_path = BASE_DIR / "memory" / "download_guard.json"
            if old_path.exists():
                data = json.loads(old_path.read_text(encoding="utf-8"))
                return bool(data.get("enabled", default))

        if flag_name == "morning_brief_enabled":
            return bool(load_api_keys().get("morning_brief_enabled", default))
    except Exception:
        pass

    return default

def set_feature_flag(flag_name: str, value: bool) -> None:
    """
    Универсальная запись флага.
    Пишет в те же секции, что читает get_feature_flag.
    """
    value = bool(value)

    if flag_name in ("usb_security_enabled", "download_guard_enabled", "sphere_alert"):
        set_setting("security", flag_name, value)
        return

    if flag_name in ("morning_brief_enabled", "face_lock_enabled",
                     "gesture_control_enabled", "proactive_enabled"):
        set_setting("features", flag_name, value)
        return

    if flag_name in ("messenger_enabled", "dnd_enabled", "draft_enabled"):
        key = "enabled" if flag_name == "messenger_enabled" else flag_name
        set_setting("messenger", key, value)
        return

    # fallback: features
    set_setting("features", flag_name, value)

def get_modules_status() -> str:
    """Короткий отчёт о состоянии основных модулей."""
    flags = {
        "USB Security": get_feature_flag("usb_security_enabled", True),
        "Download Guard": get_feature_flag("download_guard_enabled", True),
        "Messenger": get_feature_flag("messenger_enabled", True),
        "Не беспокоить (DND)": get_feature_flag("dnd_enabled", False),
        "Черновики ответов": get_feature_flag("draft_enabled", True),
        "Утренний брифинг": get_feature_flag("morning_brief_enabled", True),
    }
    lines = []
    for name, enabled in flags.items():
        state = "включён" if enabled else "выключен"
        lines.append(f"{name} — {state}")
    return "Сэр, статус модулей:\n" + "\n".join(lines)