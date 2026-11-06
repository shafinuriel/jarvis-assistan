import platform as _platform
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None) # drop any stale/shared STARTUPINFO
            
            # Принудительно ставим UTF-8 для всех фоновых процессов
            if kw.get("text") or kw.get("universal_newlines"):
                kw["encoding"] = "utf-8"
                kw["errors"] = "replace"
                
            super().__init__(args, **kw)

    _subprocess.Popen = _Popen
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import re
import threading
import time
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    save_session_summary, pop_last_session,
)

from actions.file_processor import file_processor
from actions.flight_finder import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message  
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import _capture_camera, _capture_screen
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.proactive         import ProactiveEngine
from actions.background_monitor import (
    add_monitor, remove_monitor, list_monitors, check_all as monitor_check_all,
)
from actions.web_search        import _news as _fetch_news_sync
from memory.config_manager     import get_brief_enabled, get_feature_flag, get_modules_status

from actions.phone_contorl import phone_action
from actions.knowledge_action import knowledge_action
from actions.flight_finder import flight_finder
from code_monitor_ui import CodeMonitorWindow
from actions.sandbox import core_sandbox
from actions.study_helper import study_helper
from actions.remote_server import JarvisRemoteServer, generate_qr_image
from actions.voice_id import enroll_from_numpy
from actions.system_controller import controller
from actions.birthday_protocol import get_birthday_target_and_url
from actions.proactive_notes import NotesListener, make_speak_handler
from actions.messenger_assistant import MessengerAssistant
from modules.gods_eye.map_service import launch_tactical_map, close_tactical_map
from actions.window_control import list_windows, focus_window, click_center, type_text
from actions.offline_brain import ask as offline_ask, is_available as offline_available
from actions.security_scanner import scanner
from actions.gesture_control import GestureController
from actions.face_lock import FaceLock

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "gemini-3.8-live"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
# Глобальная ссылка на живой экземпляр JarvisLive
_current_jarvis = None

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

def has_internet(retries: int = 3, timeout: float = 2.0) -> bool:
    """True только если сеть реально есть. Иначе offline-brain."""
    import socket
    import urllib.request

    for _ in range(retries):
        for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
            try:
                s = socket.create_connection((host, port), timeout=timeout)
                s.close()
                return True
            except OSError:
                pass
        try:
            urllib.request.urlopen("https://www.google.com", timeout=timeout)
            return True
        except Exception:
            pass
    return False

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "gaming_protocol",
        "description": (
            "Start gaming mode: optionally Discord, then launch a game. "
            "Use when user says gaming protocol, play cs2, war thunder, fortnite with discrod."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "game": {
                    "type": "STRING",
                    "description": "cs2 | war thunder | fortnite (default cs2)",
                },
                "with_discord": {
                    "type": "BOOLEAN",
                    "description": "Launch Discrod if not running (default true),"
                },
            },
            "required": []
        },
    },
    {
        "name": "install_steam_game",
        "description": (
            "Download/install a Steam game by name or AppID. "
            "Use when user says: скачай, установи, download, install a game on Steam. "
            "Examples: CS2, Poppy Playtime, War Thunder, Terraria."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "game": {
                    "type": "STRING",
                    "description": "Game name or Steam AppID (e.g. cs2, poppy, 730)",
                },
            },
            "required": ["game"],
        },
    },
    {
        "name": "uninstall_steam_game",
        "description": (
            "Uninstall a Steam game by name or AppID. "
            "Use only when user clearly asks to delete/remove/uninstall a Steam game."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "game": {
                    "type": "STRING",
                    "description": "Game name or Steam AppID",
                },
            },
            "required": ["game"],
        },
    },
    {
        "name": "spotify_media",
        "description": (
            "Control Spotify / system media: play, pause, next track, previous track. "
            "Use when user says play, pause, next song, previous song, skip."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "play_pause | next | previous",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "offline_ask",
        "description": (
            "Local offline brain (math + Gemma). "
            "ONLY when there is NO internet. Never use if online."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "question": {
                    "type": "STRING",
                    "description": "User question",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "whatsapp_contact",
        "description": (
            "Open WhatsApp chat or prepare a message to a contact. "
            "Use when user asks to write, message, or call someone on WhatsApp."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {
                    "type": "STRING",
                    "description": "Name from contacts (e.g. мама) or phone digits",
                },
                "text": {
                    "type": "STRING",
                    "description": "Message text; empty = only open chat",
                },
                "action": {
                    "type": "STRING",
                    "description": "message or call",
                },
            },
            "required": ["contact"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web. Use for ANY question about current facts, events, prices, "
            "or topics — always prefer this over guessing. "
            "Modes: 'search' (default), 'news' (latest headlines on a topic), "
            "'research' (deep comprehensive answer), 'price' (product cost lookup), "
            "'compare' (side-by-side comparison of items)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Items to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "Comparison aspect: price | specs | reviews | features"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
            "uptime, and process count. Use when the user asks about computer performance, "
            "temperature, memory, or resource usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "get_modules_status",
        "description": (
            "Returns the enabled/disabled status of main Jarvis modules: "
            "USB Security, Download Guard, Messenger, DND, draft replies, morning briefing. "
            "Use when the user asks: module status, which modules are enabled, what is enabled, "
            "статус модулей, какие модули включены, что включено."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "vibrate_phone",
        "description": "Вибрирует подключённый телефон",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона, по умолчанию phone_1"
                }
            },
            "required": []
        }
    },
    {
        "name": "open_url_on_phone",
        "description": "Открывает ссылку на подключённом телефоне",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {
                    "type": "STRING",
                    "description": "Полная ссылка, например https://youtube.com"
                },
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона, по умолчанию phone_1"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures the screen or webcam image and lets you analyze it. "
            "MUST be called when user asks what is on screen, what you see, "
            "look at camera, analyze my screen, etc. "
            "You have NO visual ability without this tool. "
            "After the image is captured it is sent directly to you — describe what you see and answer the user's question. "
            "When using camera: the live view stays open until user says close it or calls close_camera."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "close_camera",
        "description": (
            "Closes the live camera view shown on screen. "
            "Call when user says: close camera, stop camera, turn off camera, "
            "kamerayı kapat, kapat, creepy, etc."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Simple open/search requests launch the user's own browser normally (their real profile "
            "and logged-in accounts); interactive actions (click, type, fill_form...) attach an "
            "automation browser. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "execute_python",
        "description": "Executes Python code in a secure isolated sandbox. Use for calculations, data processing, string logic, or any Python code execution. Always include print() to see the output. Results are automatically shown in Code Monitor.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {
                    "type": "STRING",
                    "description": "The full Python code to execute"
                },
                "timeout": {
                    "type": "NUMBER",
                    "description": "Maximum execution time in seconds (default 15)"
                }
            },
            "required": ["code"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "phone_flashlight",
        "description": "Включает или выключает фонарик на телефоне",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "enable": {
                    "type": "BOOLEAN",
                    "description": "true - включить, false - выключить"
                },
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона, по умолчанию phone_1"
                }
            },
            "required": ["enable"]
        }
    },
    {
        "name": "get_phone_battery",
        "description": "Запрашивает уровень заряда подключённого телефона",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона, по умолчанию phone_1"
                }
            },
            "required": []
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "speak_on_phone",
        "description": "Произносит текст голосом на подключённом телефоне",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "Что сказать"},
                "device_id": {"type": "STRING", "description": "ID телефона"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "set_phone_clipboard",
        "description": "Копирует текст в буфер обмена телефона",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {
                    "type": "STRING",
                    "description": "Текст для копирования"
                },
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "manage_monitor",
        "description": (
            "Add, remove, or list background monitoring topics. "
            "JARVIS checks these topics once a day and alerts the user when there is a new development. "
            "Use 'add' when the user says 'monitor X', 'track X', 'follow X'. "
            "Use 'remove' when the user says 'stop monitoring X'. "
            "Use 'list' when the user asks what is being monitored. "
            "Do NOT add crypto, financial, or trading topics."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type":        "STRING",
                    "description": "add | remove | list",
                },
                "topic": {
                    "type":        "STRING",
                    "description": "Topic to monitor or stop monitoring (e.g. 'space exploration', 'AI news')",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "open_app_on_phone",
        "description": "Открывает приложение на телефоне по package name",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "package": {
                    "type": "STRING",
                    "description": "Package name приложения, например com.android.chrome или com.google.android.youtube"
                },
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона"
                }
            },
            "required": ["package"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
        }
    },
    {
        "name": "ping_device",
        "description": "Отправляет ping на подключённое устройство и ждёт pong",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "device_id": {
                    "type": "STRING",
                    "description": "ID устройства, например test_phone"
                }
            },
            "required": ["device_id"]
        }
    },
    {
        "name": "send_phone_message",
        "description": "Отправляет текстовое сообщение на подключённый телефон",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {
                    "type": "STRING",
                    "description": "Текст сообщения"
                },
                "device_id": {
                    "type": "STRING",
                    "description": "ID телефона, по умолчанию phone_1"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "list_remote_devices",
        "description": "Показывает список устройств, подключённых к экосистеме Jarvis",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "study_helper",
        "description": (
            "Протокол: Учения. Помогает готовиться к школе (9–11 класс), IELTS и SAT. "
            "Используется для теории, практики, проверки ответов и прогресса. "
            "Действия: theory, task, check, progress."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "theory | task | check | progress"
                },
                "subject": {
                    "type": "STRING",
                    "description": "math, physics, chemistry, history, ielts, sat и т.д."
                },
                "topic": {
                    "type": "STRING",
                    "description": "Конкретная тема (квадратные уравнения, algebra, Writing Task 2 и т.д.)"
                },
                "section": {
                    "type": "STRING",
                    "description": "Для IELTS/SAT: Listening, Reading, Writing, Speaking, Math, Reading & Writing"
                },
                "user_answer": {
                    "type": "STRING",
                    "description": "Ответ пользователя (только для action=check)"
                },
                "difficulty": {
                    "type": "STRING",
                    "description": "easy | medium | hard | band6 | band7 | band8 | sat_easy | sat_hard"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Nuriel, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "unlock_phone",
        "description": (
            "Unlocks the user's mobile phone screen or wakes up the display."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pin": {
                    "type": "STRING",
                    "description": "Optional PIN code to unlock the device."
                }
            }
        }
    },
    {
        "name": "open_tactical_map",
        "description": (
            "Open God's Eye View 3D tactical globe in the browser on this PC. "
            "You can pass either a city name (e.g. Baku, Paris, London, Moscow) "
            "or exact coordinates (lat, lon). Zoom is optional."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g. Baku, Paris, London, Moscow, Istanbul, Tokyo, Dubai)"
                },
                "lat": {
                    "type": "number",
                    "description": "Latitude"
                },
                "lon": {
                    "type": "number",
                    "description": "Longitude"
                },
                "zoom": {
                    "type": "number",
                    "description": "Zoom level (default 10)"
                }
            },
            "required": []
        }
    },
    {
        "name": "close_tactical_map",
        "description": "Close God's Eye View map server and free resources.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_windows",
        "description": "List currently visible windows on the PC. Use when user asks what is open or which windows exist.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "focus_window",
        "description": "Bring a window to the foreground by part of its title. Example: focus Chrome, focus Discord, focus Steam.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_part": {
                    "type": "string",
                    "description": "Part of the window title to find (case-insensitive)"
                }
            },
            "required": ["title_part"]
        }
    },
    {
        "name": "type_into_window",
        "description": "Focus a window and type text into it as if from keyboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_part": {
                    "type": "string",
                    "description": "Part of the window title"
                },
                "text": {
                    "type": "string",
                    "description": "Text to type"
                }
            },
            "required": ["title_part", "text"]
        }
    },
    {
        "name": "click_window",
        "description": "Focus a window and click its center. Use to activate buttons or bring focus inside an app.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_part": {
                    "type": "string",
                    "description": "Part of the window title"
                }
            },
            "required": ["title_part"]
        }
    },
    {
        "name": "quick_scan",
        "description": "Быстрая проверка безопасности: Desktop, Downloads, Temp, Startup. Используй когда пользователь просит быстрый скан, проверить компьютер, поискать вирусы быстро.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "full_scan",
        "description": "Полная проверка безопасности (глубже и дольше). Используй когда пользователь просит полный скан, глубокую проверку, тщательный поиск угроз.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
        {
        "name": "clear_threat",
        "description": "Сбросить режим угрозы (красная сфера). Вызывать когда пользователь сказал что угроза снята, всё чисто, игнорировать угрозу, отбой тревоги.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "enable_gestures",
        "description": "Enable hand gesture control. Starts camera for MediaPipe hands. Use when user asks to enable gestures / gesture control.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "disable_gestures",
        "description": "Disable hand gesture control and release camera. Use when user asks to turn off gestures.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "enable_face_lock",
        "description": "Enable FaceLock. Starts camera and face recognition to lock the PC when the owner is away. Use when user asks to enable FaceLock / face lock / face recognition lock.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "disable_face_lock",
        "description": "Disable FaceLock and release the camera. Use when user asks to turn off FaceLock / face lock.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "set_module",
        "description": "Enable or disable a Jarvis module/feature. Use for sphere, DND, messenger, USB security, download guard, draft, morning brief, face lock, gesture control.",
        "parameters": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Module name: sphere, dnd, messenger, usb_security, download_guard, draft, morning_brief, face_lock, gesture_control"
                },
                "enabled": {
                    "type": "boolean",
                    "description": "true to enable, false to disable"
                }
            },
            "required": ["module", "enabled"]
        }
    },
    {
        "name": "set_owner_face",
        "description": "Save the currently uploaded image as the owner face for FaceLock. Use when the user says: 'this is my face', 'set owner face', 'use this photo for face lock', 'поставь это фото для фейслока', 'это моё лицо', 'запомни моё лицо'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]

# --- Plugin system ---


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self._asst_name     = "JARVIS"   # updated each session from config
        self.session              = None
        self.audio_in_queue       = None
        self.out_queue            = None
        self._loop                = None
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        self.ui.on_text_command   = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_interrupt      = self.interrupt
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._notes_listener = None
        self.messenger = MessengerAssistant(jarvis=self)
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._session_log: list[str] = []          # conversation turns for end-of-session summary
        self.conversation_history = []
        self.max_history_length = 10
        self._voice_buf = []
        self._voice_buf_max_sec = 2.0
        self._voice_allowed = True
        self._voice_last_check = 0.0
        # === Remote Server (Экосистема) ===
        self.remote_server = JarvisRemoteServer(on_message=self._on_remote_message)
        self._note_queue = []
        self._briefing_done = False
        self._threat_active = False
        self.gesture = GestureController(on_gesture=self._on_gesture)
        self._gesture_muted = False
        self.face_lock = FaceLock(jarvis=self)
        global _current_jarvis
        _current_jarvis = self
        self.ui.jarvis = self

        if get_feature_flag("gesture_control_enabled", False):
            self.start_gestures()
            
        if get_feature_flag("face_lock_enabled", False):
            self.face_lock.start()
        
            
    def _add_to_history(self, role: str, text: str):
        """Сохраняем реплики и ограничиваем размер буфера."""
        self.conversation_history.append({"role": role, "text": text})
        if len(self.conversation_history) > self.max_history_length:
            self.conversation_history = self.conversation_history[-self.max_history_length:]
                
    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        # Показываем QR для подключения устройств экосистемы
        self.show_connection_qr()
        return None
    
    def _on_gesture(self, name: str):
        print(f"[GESTURE] {name}")
        # из потока MediaPipe → в asyncio/GUI безопасно
        loop = getattr(self, "_loop", None)
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._handle_gesture, name)
        else:
            self._handle_gesture(name)

    def _handle_gesture(self, name: str):
        try:
            if name == "open_palm":
                if hasattr(self, "interrupt"):
                    self.interrupt()
                return

            if name == "fist":
                self._gesture_muted = not getattr(self, "_gesture_muted", False)
                print(f"[GESTURE] gesture_muted={self._gesture_muted}")
                return
        except Exception as e:
            print(f"[GESTURE] handle error: {e}")
    
    def start_gestures(self):
        ok = self.gesture.start()
        if ok:
            print("[JARVIS] Gestures ON")
        return ok

    def stop_gestures(self):
        self.gesture.stop()
        print("[JARVIS] Gestures OFF")
        
    def start_face_lock(self):
        ok = self.face_lock.start()
        if ok:
            print("[JARVIS] FaceLock ON")
        return ok

    def stop_face_lock(self):
        self.face_lock.stop()
        print("[JARVIS] FaceLock OFF")
    
    def _on_text_command(self, text: str):
        t = (text or "").strip().lower()
        
        # --- USB security: quarantine / ignore while pending ---
        if getattr(self, "_usb_sec", None) is not None and getattr(self, "loop", None):
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._usb_sec.handle_voice_command(text or ""),
                    self.loop,
                )
                if fut.result(timeout=8):
                    return
            except Exception as e:
                print(f"[USB-SEC] text cmd: {e}")
        
        if getattr(self, "_dl_guard", None) is not None and getattr(self, "loop", None):
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._dl_guard.handle_voice_command(text or ""),
                    self.loop,
                )
                if fut.result(timeout=8):
                    return
            except Exception as e:
                print(f"[DL-GUARD] text cmd: {e}")

        # --- Voice enroll / mode (local, no Gemini) ---
        if any(x in t for x in ("запомни мой голос", "запомни голос", "enroll voice", "remember my voice")):
            def _do_enroll():
                try:
                    import sounddevice as sd
                    from actions.voice_id import enroll_from_numpy
                    self.ui.write_log("SYS: Говори 4 секунды для записи голоса...")
                    audio = sd.rec(int(4 * 16000), samplerate=16000, channels=1, dtype="float32")
                    sd.wait()
                    msg = enroll_from_numpy(audio[:, 0], 16000)
                    self.ui.write_log(f"SYS: {msg}")
                except Exception as e:
                    self.ui.write_log(f"SYS: voice enroll error: {e}")
            import threading
            threading.Thread(target=_do_enroll, daemon=True).start()
            return

        if any(x in t for x in ("personal voice", "только мой голос", "режим personal")):
            from actions.voice_id import set_mode
            set_mode("personal")
            self.ui.write_log("SYS: Voice mode = PERSONAL")
            return

        if any(x in t for x in ("all voice", "все голоса", "режим all")):
            from actions.voice_id import set_mode
            set_mode("all")
            self.ui.write_log("SYS: Voice mode = ALL")
            return
        # --- end voice local commands ---

        # --- OFFLINE FALLBACK (только без интернета) ---
        if not has_internet(retries=3):
            user_q = (text or "").strip()
            if user_q and getattr(self, "_loop", None):
                async def _offline_reply():
                    reply = await offline_ask(user_q)
                    self.ui.write_log(f"OFFLINE: {reply}")
                    try:
                        self.ui.write_log(f"{getattr(self, '_asst_name', 'JARVIS')}: {reply}")
                    except Exception:
                        pass
                asyncio.run_coroutine_threadsafe(_offline_reply(), self._loop)
            return
        
        if not self._loop or not self.session:
            return
        
        # 1. Склеиваем историю сообщений, если она есть
        if self.conversation_history:
            history_str = "\n".join([
                f"{'Пользователь' if m['role'] == 'user' else 'Джарвис'}: {m['text']}"
                for m in self.conversation_history
            ])
            payload_text = f"Контекст беседы:\n{history_str}\n\nТекущий запрос: {text}"
        else:
            payload_text = text
            
        #2. Сохраняем твой новый запрос в историю
        self._add_to_history("user", text)
        
        #3. Отправляем итоговый текст (вместе с историей) в API
        async def _send_text():
            if not self.session:
                return
            try:
                await self.session.send_client_content(
                    turns=[{
                        "role": "user",
                        "parts": [{"text": payload_text}]
                    }],
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[JARVIS] text send failed: {e}")

        asyncio.run_coroutine_threadsafe(_send_text(), self._loop)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            if getattr(self, "_threat_active", False):
                self.ui.set_state("THREAT")
            else:
                self.ui.set_state("LISTENING")

    def open_code_monitor(self):
        # Замени self.send_text_to_jarvis на то название функции,
        # которым у тебя отправляется текст нейросити (если оно отличается)
        self.monitor_window = CodeMonitorWindow(self, request_fix_callback=self.send_text_to_jarvis)
        self.monitor_window.show()
    
    def interrupt(self) -> None:
        """Stop JARVIS mid-speech: drain queued audio and open mic immediately."""
        self._interrupted = True
        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                print(f"[JARVIS] ✋ Interrupted — {drained} audio chunks discarded")
        self.set_speaking(False)
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrupted — listening...")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        # Load customization from config
        try:
            _cfg = json.loads(open(API_CONFIG_PATH, encoding="utf-8").read())
            self._asst_name = (_cfg.get("assistant_name") or "JARVIS").strip()
            _user_name = (_cfg.get("user_name") or "").strip()
        except Exception:
            self._asst_name = "JARVIS"
            _user_name = ""

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        # Identity injection — overrides any hardcoded name in prompt.txt
        _addr = (f"ADDRESS: Always call the user '{_user_name}'."
                 if _user_name
                 else "ADDRESS: When speaking Turkish → always say \"efendim\". "
                      "When speaking English → say \"sir\". Never mix languages.")
        identity_ctx = (
            f"[IDENTITY]\n"
            f"Your name is {self._asst_name}. "
            f"Always refer to yourself as {self._asst_name}.\n"
            f"{_addr}\n\n"
        )

        parts = [time_ctx, identity_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _on_remote_message(self, data: dict, websocket):
        print(f"[Remote] Сообщение от устройства: {data}")

        action = data.get("action")

        # Ответ на ping / battery уже могут быть
        if action == "battery_status":
            level = data.get("level", "?")
            device = data.get("device_id", "телефон")
            print(f"[Remote] Батарея {device}: {level}%")
            return

        # Команды с телефона на Хаб (ПК)
        if action == "hub_command":
            hub_action = data.get("hub_action")
            value = data.get("value", "")
            from_device = data.get("from_device", "phone")

            print(f"[Remote] Команда с {from_device}: {hub_action} = {value}")

            if hub_action == "open_url":
                # Открыть ссылку на ПК
                import webbrowser
                webbrowser.open(value)
                return

            if hub_action == "show_message":
                # Пока просто в лог / можно озвучить
                print(f"[Remote] Сообщение с телефона: {value}")
                # Если хочешь голосом:
                await self.speak(f"Сообщение с телефона: {value}")
                return
            
            if hub_action == "open_explorer":
                import subprocess
                subprocess.Popen("explorer")
                return
            
            if hub_action == "show_desktop":
                import ctypes
                ctypes.windll.user32.keybd_event(0x58, 0, 0, 0) #win
                ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)  # Win
                ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)  # D
                ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)
                ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
                return
            
            if hub_action == "protocol_birthday":
                result = await self.run_birthday_protocol()
                print(f"[JARVIS] Birthday via phone: {result}")
                return
            
            if hub_action == "relay_to_device":
                target = data.get("target_device")
                device_action = data.get("device_action")
                value = data.get("value", "")
                
                payload = {
                    "target_device": target,
                    "action": device_action,
                }
                if device_action == "open_app":
                    payload["package"] = value
                elif device_action == "open_url":
                    payload["url"] = value
                    
                ok = await self.remote_server.send_to_device(target, payload)
                print(f"[Remote] Relay -> {target}: {payload} | ok={ok}")
                return
            
            if hub_action == "speak":
                text = value or ""
                if text and getattr(self, "_usb_sec", None) is not None:
                    try:
                        handled = await self._usb_sec.handle_voice_command(text)
                        if handled:
                            return
                    except Exception as e:
                        print(f"[USB-SEC] voice cmd: {e}")
                if text:
                    await self.speak(text)
                return
    
    def show_connection_qr(self):
        """Показывает QR-код для подключения устройств"""
        try:
            from PyQt6.QtWidgets import QLabel, QDialog, QVBoxLayout
            from PyQt6.QtGui import QPixmap
            from PyQt6.QtCore import Qt
            import os

            # Актуальный QR: IP + token на момент нажатия
            qr_data = self.remote_server.get_qr_data()
            qr_path = os.path.join(str(BASE_DIR), "jarvis_qr.png")
            generate_qr_image(qr_data, qr_path)
            self._qr_path = qr_path

            if not os.path.exists(qr_path):
                print(f"[Remote] файл QR не найден: {qr_path}")
                return

            dialog = QDialog()
            dialog.setWindowTitle("Подключение устройства к Jarvis")
            dialog.setFixedSize(380, 440)

            layout = QVBoxLayout(dialog)
            title = QLabel("Отсканируй QR-код с телефона")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            qr_label = QLabel()
            pixmap = QPixmap(qr_path)
            if pixmap.isNull():
                print(f"[Remote] Не удалось загрузить изображение: {qr_path}")
                qr_label.setText("Ошибка загрузки QR")
            else:
                qr_label.setPixmap(
                    pixmap.scaled(
                        300, 300,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(qr_label)

            info = QLabel(
                f"IP: {self.remote_server.local_ip}:{self.remote_server.port}\n"
                f"Token: {self.remote_server.token}"
            )
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info.setWordWrap(True)
            layout.addWidget(info)

            dialog.setModal(True)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            self._qr_dialog = dialog
        except Exception as e:
            print(f"[Remote] Ошибка показа QR: {e}")
    
    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                app_name = (args.get("app_name") or "").strip()
                key = app_name.lower()
                
                # Steam-игры
                if key in controller.steam_games or (
                    key.isdigit() and len(key) >=3
                ):
                    lr = await controller.launch_steam_game(app_name)
                    result = lr.message
                
                elif key in ("settings", "настройки", "параметры"):
                    lr = await controller.open_windows_settings()
                    result = lr.message
                    
                # Fortnite / Epic
                elif key in ("fortnite", "epic_fortnite"):
                    lr = await controller.launch_fortnite_epic()
                    result = lr.message
                    
                else:
                    #Обычные приложения
                    lr = await controller.launch_app(app_name)
                    if lr.status in ("started", "already_running"):
                        result = lr.message
                    else:
                        r = await loop.run_in_executor(
                            None,
                            lambda: open_app(
                                parameters=args, response=None, player=self.ui
                            ),
                        )
                        result = r or f"Opened {app_name}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."
            
            elif name == "gaming_protocol":
                game = (args.get("game") or "cs2").strip()
                with_discord = args.get("with_discord", True)
                if isinstance(with_discord, str):
                    with_discord = with_discord.lower() not in ("false", "0", "no")
                results = await controller.activate_gaming_protocol(
                    game=game,
                    with_discord=bool(with_discord)
                )
                result = ";".join(f"{r.target}: {r.status}" for r in results)

            elif name == "install_steam_game":
                game = (args.get("game") or "").strip()
                if not game:
                    result = "No game name provided."
                else:
                    lr = await controller.install_steam_game(game)
                    result = lr.message

            elif name == "uninstall_steam_game":
                game = (args.get("game") or "").strip()
                if not game:
                    result = "No game name provided."
                else:
                    lr = await controller.uninstall_steam_game(game)
                    result = lr.message
            
            elif name == "spotify_media":
                action = (args.get("action") or "play_pause").strip()
                lr = await controller.spotify_media(action)
                result = lr.message
            
            elif name == "offline_ask":
                # Жёстко: при наличии сети offline не используем
                if has_internet(retries=2):
                    result = "Online available — use normal Gemini path, not offline."
                else:
                    q = (args.get("question") or "").strip()
                    result = await offline_ask(q) if q else "Empty question."
            
            elif name == "send_phone_message":
                text = args.get("text", "")
                device_id = args.get("device_id", "phone_1")
                
                ok = await self.remote_server.send_to_device(device_id,{
                    "target_device": device_id,
                    "action": "show_message",
                    "text": text
                })
                
                if not ok:
                    return f"Устройство {device_id} не подключено"
                
                return f"Сообщение отправлено на {device_id}: {text}"
            
            elif name == "speak_on_phone":
                text = args.get("text", "")
                device_id = args.get("device_id", "phone_1")

                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "speak",
                    "text": text
                })

                if not ok:
                    return f"Устройство {device_id} не подключено"

                return f"Текст отправлен на телефон: {text}"
            
            elif name == "vibrate_phone":
                device_id = args.get("device_id", "phone_1")
                
                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "vibrate"
                })
                
                if not ok:
                    return f"Устройство {device_id} не подключено"
                
                return f"Команда вибрации отправлена на {device_id}"
            
            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "open_app_on_phone":
                package = args.get("package", "")
                device_id = args.get("device_id", "phone_1")

                if not package:
                    return "Не указан package приложения"

                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "open_app",
                    "package": package
                })

                if not ok:
                    return f"Устройство {device_id} не подключено"

                return f"Команда открытия {package} отправлена на {device_id}"
            
            elif name == "set_phone_clipboard":
                text = args.get("text", "")
                device_id = args.get("device_id", "phone_1")

                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "set_clipboard",
                    "text": text
                })

                if not ok:
                    return f"Устройство {device_id} не подключено"

                return f"Текст скопирован в буфер телефона: {text}"
            
            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."
            
            elif name == "whatsapp_contact":
                contact = (args.get("contact") or "").strip()
                text = args.get("text") or ""
                action = (args.get("action") or "message").lower()
                if action == "call":
                    lr = await controller.whatsapp_call(contact)
                else:
                    lr = await controller.whatsapp_message(contact, text)
                result = lr.message

            elif name == "ping_device":
                device_id = args.get("device_id", "test_phone")
                request_id = f"ping_{int(time.time())}"
                
                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "ping",
                    "reuest_id": request_id
                })
                
                if not ok:
                    return f"Устройство {device_id} не подключено"
                
                return f"Ping отпрвлен на {device_id}. Жду pong..."
            elif name == "list_remote_devices":
                return self.remote_server.list_devices()
            
            elif name == "open_url_on_phone":
                url = args.get("url", "")
                device_id = args.get("device_id", "phone_1")

                if not url:
                    return "Не указана ссылка"

                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "open_url",
                    "url": url
                })

                if not ok:
                    return f"Устройство {device_id} не подключено"

                return f"Ссылка отправлена на {device_id}: {url}"
            
            elif name == "phone_flashlight":
                enable = args.get("enable", True)
                device_id = args.get("device_id", "phone_1")
                
                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "flashlight",
                    "enable": bool(enable)
                })
                
                if not ok:
                    return f"Устройство {device_id} не подключено"
                
                return f"Фонарик на {device_id}: {'включен' if enable else 'выключен'}"
            
            elif name == "execute_python":
                code = args.get("code", "")
                timeout = float(args.get("timeout", 15.0))

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: core_sandbox.execute(code, timeout=timeout)
                )

                # Gemini Live принимает только простой текст, а не словарь
                if result.get("success"):
                    output = result.get("stdout", "").strip()
                    return output if output else "Код выполнен успешно (нет вывода)."
                else:
                    error = result.get("stderr", "").strip()
                    return f"Ошибка выполнения:\n{error}"
            
            elif name == "study_helper":
                result = await loop.run_in_executor(
                    None,
                    lambda: study_helper(args)
                )
                return result
            elif name == "knowledge_action":
                r = await loop.run_in_executor(None, lambda: knowledge_action(parameters=args))
                result = r or "Knowledge action processed."
                
            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."
                
            elif name == "protocol_birthday":
                result = await self.run_birthday_protocol()
                return result
            
            elif name == "unlock_phone":
                r = await loop.run_in_executor(None, lambda: phone_action(parameters=args, player=self.ui))
                result = r or "Телефон разблокирован."

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                if self._vision_busy or (_now - self._vision_last_time) < _cooldown:
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                        self.ui.start_camera_stream()
                        self._vision_cam_active = True
                        print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                        _stall = "camera"
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured. "
                        f"Immediately say ONE short natural sentence in the user's own language, "
                        f"telling them you are looking at their {_stall} right now. "
                        f"Do NOT describe or guess content — the actual image arrives in the NEXT message."
                    )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
                # Mirror results to the on-screen content panel
                _mode = args.get("mode", "search")
                if r and not r.startswith("No results") and not r.startswith("Search failed"):
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "get_phone_battery":
                device_id = args.get("device_id", "phone_1")
                request_id = f"battery_{int(time.time())}"

                ok = await self.remote_server.send_to_device(device_id, {
                    "target_device": device_id,
                    "action": "get_battery",
                    "request_id": request_id
                })

                if not ok:
                    return f"Устройство {device_id} не подключено"

                return f"Запрос уровня батареи отправлен на {device_id}"
            
            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)
                
            elif name == "quick_scan":
                result = await asyncio.to_thread(scanner.quick_scan)
                if result.threats:
                    self._threat_active = True
                    self.ui.set_state("THREAT")
                    panel_threats = []
                    for t in result.threats:
                        panel_threats.append({
                            "path": getattr(t, "path", None) or str(t),
                            "reason": getattr(t, "reason", None) or "suspicious",
                        })
                    try:
                        self.ui.show_security_panel("QUICK SCAN", panel_threats)
                    except Exception as e:
                        print(f"[SCAN] show_security_panel error: {e}")

                    threats_text = "\n".join(
                        [f"- {t.path}: {t.reason}" for t in result.threats[:10]]
                    )
                    return (
                        f"Быстрая проверка завершена. Найдено подозрительных файлов: {len(result.threats)}.\n"
                        f"{threats_text}\n"
                        f"Что делаем с ними, сэр? Могу отправить в карантин или проигнорировать."
                    )
                self._threat_active = False
                return (
                    f"Быстрая проверка завершена. Угроз не обнаружено.\n"
                    f"Проверено файлов: {result.scanned_files}, время: {result.duration_sec} сек. Система в норме."
                )

            elif name == "full_scan":
                result = await asyncio.to_thread(scanner.full_scan)
                if result.threats:
                    self._threat_active = True
                    self.ui.set_state("THREAT")
                    panel_threats = []
                    for t in result.threats:
                        panel_threats.append({
                            "path": getattr(t, "path", None) or str(t),
                            "reason": getattr(t, "reason", None) or "suspicious",
                        })
                    try:
                        self.ui.show_security_panel("FULL SCAN", panel_threats)
                    except Exception as e:
                        print(f"[SCAN] show_security_panel error: {e}")

                    threats_text = "\n".join(
                        [f"- {t.path}: {t.reason}" for t in result.threats[:15]]
                    )
                    return (
                        f"Полная проверка завершена. Найдено подозрительных файлов: {len(result.threats)}.\n"
                        f"{threats_text}\n"
                        f"Рекомендую проверить эти файлы. Могу отправить их в карантин."
                    )
                self._threat_active = False
                return (
                    f"Полная проверка завершена. Угроз не обнаружено.\n"
                    f"Проверено файлов: {result.scanned_files}, время: {result.duration_sec} сек. Всё чисто."
                )
            
            elif name == "clear_threat":
                self._threat_active = False
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                else:
                    self.ui.set_state("IDLE")
                return "Режим угрозы снят. Система в норме."
            
            elif name == "enable_gestures":
                status = self.start_gestures()
                return f"Gesture control: {status}"

            elif name == "disable_gestures":
                status = self.stop_gestures()
                return f"Gesture control: {status}"
            
            elif name == "enable_face_lock":
                from memory.config_manager import set_feature_flag
                set_feature_flag("face_lock_enabled", True)
                status = self.start_face_lock()
                return f"FaceLock: {'enabled' if status else 'failed to start'}"
            
            elif name == "disable_face_lock":
                from memory.config_manager import set_feature_flag
                set_feature_flag("face_lock_enabled", False)
                self.stop_face_lock()
                return "FaceLock: disabled"

            elif name == "set_module":
                from memory.config_manager import set_feature_flag, get_feature_flag

                module = (args.get("module") or "").lower().strip()
                enabled = args.get("enabled", False)

                # Маппинг удобных названий на реальные флаги
                flag_map = {
                    "sphere": "sphere_enabled",
                    "dnd": "dnd_enabled",
                    "messenger": "messenger_enabled",
                    "usb_security": "usb_security_enabled",
                    "download_guard": "download_guard_enabled",
                    "draft": "draft_enabled",
                    "morning_brief": "morning_brief_enabled",
                    "face_lock": "face_lock_enabled",
                    "gesture_control": "gesture_control_enabled",
                    "gestures": "gesture_control_enabled",
                }

                flag = flag_map.get(module)
                if not flag:
                    result = f"Unknown module: {module}. Available: sphere, dnd, messenger, usb_security, download_guard, draft, morning_brief, face_lock, gesture_control"
                else:
                    set_feature_flag(flag, bool(enabled))

                    # Живое включение/выключение для модулей, которые это поддерживают
                    if flag == "face_lock_enabled":
                        if enabled:
                            self.start_face_lock()
                        else:
                            self.stop_face_lock()
                    elif flag == "gesture_control_enabled":
                        if enabled:
                            self.start_gestures()
                        else:
                            self.stop_gestures()

                    status = "enabled" if enabled else "disabled"
                    result = f"{module} {status}"
            
            elif name == "set_owner_face":
                try:
                    src = getattr(self.ui, "current_file", None)
                    if not src:
                        result = "No file uploaded. Please drop a photo first, then say 'this is my face'."
                    else:
                        from pathlib import Path
                        import shutil

                        src_path = Path(src)
                        if not src_path.exists():
                            result = "Uploaded file not found."
                        elif src_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                            result = "This file is not an image. Please upload a photo (jpg/png)."
                        else:
                            dest = Path("memory") / "owner_face.jpg"
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            # Convert/save as jpg if needed
                            if src_path.suffix.lower() in {".jpg", ".jpeg"}:
                                shutil.copy2(src_path, dest)
                            else:
                                from PIL import Image
                                img = Image.open(src_path).convert("RGB")
                                img.save(dest, "JPEG", quality=95)

                            result = f"Owner face saved successfully as {dest}. FaceLock can now use this photo."
                except Exception as e:
                    result = f"Failed to set owner face: {e}"
            
            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.to_thread(add_monitor, topic)
                elif action == "remove" and topic:
                    result = await asyncio.to_thread(remove_monitor, topic)
                elif action == "list":
                    topics = await asyncio.to_thread(list_monitors)
                    result = ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
                else:
                    result = "Specify action (add/remove/list) and a topic."

            elif name == "open_tactical_map":
                lat = args.get("lat")
                lon = args.get("lon")
                zoom = args.get("zoom")
                city = args.get("city")

                try:
                    lat_f = float(lat) if lat is not None and str(lat).strip() != "" else None
                except (TypeError, ValueError):
                    lat_f = None
                try:
                    lon_f = float(lon) if lon is not None and str(lon).strip() != "" else None
                except (TypeError, ValueError):
                    lon_f = None
                try:
                    zoom_f = float(zoom) if zoom is not None and str(zoom).strip() != "" else None
                except (TypeError, ValueError):
                    zoom_f = None

                result = await loop.run_in_executor(
                    None,
                    lambda: launch_tactical_map(lat=lat_f, lon=lon_f, zoom=zoom_f, city=city),
                )
            
            elif name == "close_tactical_map":
                result = await loop.run_in_executor(None, close_tactical_map)
            
            elif name == "list_windows":
                wins = list_windows()
                if not wins:
                    return "No visible windows found."
                lines = [f"- {w['title']}" for w in wins]
                return "Open windows:\n" + "\n".join(lines)

            elif name == "focus_window":
                title_part = args.get("title_part", "")
                return focus_window(title_part)

            elif name == "type_into_window":
                title_part = args.get("title_part", "")
                text = args.get("text", "")
                return type_text(title_part, text)
            
            elif name == "click_window":
                title_part = args.get("title_part", "")
                return click_center(title_part)
            
            elif name == "get_modules_status":
                return get_modules_status()
            
            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                async def _do_shutdown():
                    await self._save_session_summary()
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"parts": [{"text": "Say a brief natural goodbye to the user."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                        try:
                            if getattr(self, "messenger", None):
                                self.messenger.stop()
                        except Exception:
                            pass
                        try:
                            if getattr(self, "face_lock", None):
                                self.stop_face_lock()
                        except Exception:
                            pass

                        try:
                            if getattr(self, "gesture", None):
                                self.stop_gestures()
                        except Exception:
                            pass
                    await asyncio.sleep(1.5)
                    if getattr(self, "_notes_listener", None) is not None:
                        try:
                            self._notes_listener.stop()
                        except Exception:
                            pass
                    try:
                        close_tactical_map()
                    except Exception:
                        pass
                    import os as _os
                    _os._exit(0)
                asyncio.create_task(_do_shutdown())

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            if getattr(self, "_threat_active", False):
                self.ui.set_state("THREAT")
            else:
                self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    def _start_notes_listener(self) -> None:
        """Firebase notes → log + voice. Watchdog reconnects if stream dies."""
        self._start_notes_listener_once()

        if not getattr(self, "_notes_watchdog_started", False):
            self._notes_watchdog_started = True
            loop = getattr(self, "_loop", None)
            if loop is None:
                try:
                    loop = asyncio.get_event_loop()
                except Exception:
                    loop = None
            if loop is not None:
                loop.create_task(self._notes_reconnect_loop())

    def _start_notes_listener_once(self) -> None:
        """(Re)start listener. Safe to call after stop."""
        old = getattr(self, "_notes_listener", None)
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
            self._notes_listener = None

        def speak(msg: str) -> None:
            try:
                if hasattr(self, "ui") and self.ui is not None:
                    self.ui.write_log(f"SYS: {msg}")
            except Exception as e:
                print(f"[Notes] speak log failed: {e}")

            if not getattr(self, "_briefing_done", False):
                self._note_queue.append(msg)
                print(f"[Notes] queued until briefing done ({len(self._note_queue)})")
                return

            self._schedule_note_voice(msg)

        try:
            self._notes_listener = NotesListener(
                on_note=make_speak_handler(speak)
            )
            self._notes_listener.start()
            print("[JARVIS] NotesListener started")
        except Exception as e:
            print(f"[JARVIS] NotesListener failed: {e}")
            self._notes_listener = None

    async def _notes_reconnect_loop(self) -> None:
        """Zero-overhead: check every 30s, reconnect only if dead."""
        backoff = 10
        while True:
            try:
                await asyncio.sleep(30)
                lis = getattr(self, "_notes_listener", None)
                alive = False
                if lis is not None:
                    try:
                        alive = lis.is_alive()
                    except Exception:
                        alive = False
                if alive:
                    backoff = 10
                    continue

                print(f"[JARVIS] NotesListener dead — retry in {backoff}s")
                await asyncio.sleep(backoff)
                self._start_notes_listener_once()
                if getattr(self, "_notes_listener", None) is not None:
                    backoff = 10
                    print("[JARVIS] NotesListener reconnected")
                else:
                    backoff = min(backoff * 2, 120)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[JARVIS] notes reconnect: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)

    async def _announce_note(self, msg: str) -> None:
        try:
            if getattr(self, "session", None) is not None:
                await self.session.send_client_content(
                    turns=[{"parts": [{
                        "text": (
                            "Briefly say this to the user in Russian. "
                            "Do not ask questions, just announce: "
                            + msg
                        )
                    }]}],
                    turn_complete=True,
                )
        except Exception as e:
            print(f"[Notes] session announce failed: {e}")
    
    def _schedule_note_voice(self, msg: str) -> None:
        try:
            loop = getattr(self, "_loop", None) or getattr(self, "loop", None)
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
            if loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(self._announce_note(msg), loop)
            else:
                print(f"[Notes] no loop for voice: {msg}")
        except Exception as e:
            print(f"[Notes] voice failed: {e}")

    async def _flush_note_queue(self) -> None:
        self._briefing_done = True
        q = list(getattr(self, "_note_queue", []))
        self._note_queue = []
        for msg in q:
            await self._announce_note(msg)
            await asyncio.sleep(0.8)
    
    async def run_birthday_protocol(self):
        from actions.birthday_protocol import get_birthday_target_and_url
        # если у тебя build_tv_youtube_command — см. ниже
        target, url = get_birthday_target_and_url()
        print(f"[JARVIS] Протокол День рождения → {target}: {url}")

        payload = {
            "target_device": target,
            "action": "open_url",   # как в relay: URL на устройство
            "url": url,
        }
        ok = await self.remote_server.send_to_device(target, payload)
        if not ok:
            return f"ТВ ({target}) не подключено"
        try:
            await self.speak("Запускаю протокол день рождения на телевизоре")
        except Exception:
            pass
        return f"Протокол день рождения: ссылка отправлена на {target}"
    
    async def _run_usb_security(self):
        try:
            from actions.usb_security import UsbSecurityMonitor
            self._usb_sec = UsbSecurityMonitor(self)
            await self._usb_sec.run_loop()
        except Exception as e:
            print(f"[USB-SEC] stopped: {e}")
            
    async def _run_download_guard(self):
        try:
            from actions.download_quard import DownloadGuard
            self._dl_guard = DownloadGuard(self)
            await self._dl_guard.run_loop()
        except Exception as e:
            print(f"[DL-GUARD] stopped: {e}")
    
    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            try:
                if self.session is None:
                    continue
                await self.session.send_realtime_input(audio=msg)
            except Exception as e:
                print(f"[JARVIS] send_realtime error: {e}")

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()
        
        
        
        # === Запуск Remote Server (один раз) ===
        #if not getattr(self, "_remote_started", False):
            #self._remote_started = True

        #async def _start_remote():
            #try:
                #await self.remote_server.start()
                #print("[Remote] Сервер успешно запущен!")
            #except Exception as e:
                #print(f"[Remote] ОШИБКА запуска сервера: {e}")

        #asyncio.create_task(_start_remote())

        #import os
        #qr_data = self.remote_server.get_qr_data()
        #qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_qr.png")
        #generate_qr_image(qr_data, qr_path)
        #self._qr_path = qr_path

        #print(f"[Remote] QR-код сохранён: {qr_path}")
        #print(f"[Remote] Подключение: {qr_data}")

        def callback(indata, frames, time_info, status):
            allow = True
            try:
                from actions.voice_id import get_mode, has_owner_voice, verify_numpy
                import numpy as np
                import time as _time

                if get_mode() == "personal" and has_owner_voice():
                    audio = np.asarray(indata, dtype=np.float32).reshape(-1) / 32768.0
                    self._voice_buf.append(audio.copy())
                    max_samples = int(SEND_SAMPLE_RATE * self._voice_buf_max_sec)
                    total = 0
                    kept = []
                    for c in reversed(self._voice_buf):
                        kept.append(c)
                        total += len(c)
                        if total >= max_samples:
                            break
                    self._voice_buf = list(reversed(kept))

                    now = _time.monotonic()
                    if now - self._voice_last_check >= 0.5:
                        self._voice_last_check = now
                        buf = np.concatenate(self._voice_buf)
                        ok, sim = verify_numpy(buf, SEND_SAMPLE_RATE)
                        self._voice_allowed = ok
                        # print(f"[VOICE] sim={sim:.3f} ok={ok}")  # раскомментируй для отладки
                    allow = self._voice_allowed
            except Exception:
                allow = True  # любая ошибка → не глушим mic
            # --- end gate ---

            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if (
                not jarvis_speaking
                and not self.ui.muted
                and not getattr(self, "_gesture_muted", False)
                and not self._phone_active
                and allow
            ):
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm;rate=16000"}
                )
        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._interrupted:
                            pass  # discard: interrupted
                        else:
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # If this turn_complete ends an interrupted response, clear the
                            # flag and skip all further processing for that turn.
                            if self._interrupted:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                                self._add_to_history("user", full_in)
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))
                                    
                                # --- Messenger: DND / draft ---
                                low = full_in.lower()
                                msg = getattr(self, "messenger", None)
                                if msg is not None:
                                    if any(x in low for x in (
                                        "включи не беспокоить", "dnd on", "режим не беспокоить"
                                    )):
                                        msg.cfg["dnd_enabled"] = True
                                        msg.cfg["enabled"] = True
                                        from actions.messenger_assistant import CONFIG_PATH, _save_json
                                        _save_json(CONFIG_PATH, msg.cfg)
                                        self.speak("Режим не беспокоить включён.")
                                        in_buf = []
                                        continue

                                    if any(x in low for x in (
                                        "выключи не беспокоить", "dnd off", "обычный режим сообщений"
                                    )):
                                        msg.cfg["dnd_enabled"] = False
                                        from actions.messenger_assistant import CONFIG_PATH, _save_json
                                        _save_json(CONFIG_PATH, msg.cfg)
                                        self.speak("Обычный режим сообщений.")
                                        in_buf = []
                                        continue

                                    if any(x in low for x in (
                                        "отправь черновик", "подтверди черновик", "да отправь"
                                    )):
                                        asyncio.create_task(msg.confirm_draft())
                                        in_buf = []
                                        continue

                                    if any(x in low for x in (
                                        "отмени черновик", "отмена черновика"
                                    )):
                                        asyncio.create_task(msg.cancel_draft())
                                        in_buf = []
                                        continue
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                                self._add_to_history("model", full_out)
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "jarvis",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            out_buf = []

                            # Vision injection: model finished tool-response turn → now send the image
                            if self._pending_vision and self.session:
                                import base64 as _b64
                                img_b, mime_t, question, angle = self._pending_vision
                                self._pending_vision = None
                                b64 = _b64.b64encode(img_b).decode("ascii")
                                print(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")
                                await self.session.send_client_content(
                                    turns={"parts": [
                                        {"inline_data": {"mime_type": mime_t, "data": b64}},
                                        {"text": question},
                                    ]},
                                    turn_complete=True,
                                )
                                # Mark next turn_complete behaviour depending on angle
                                if self._vision_cam_active:
                                    # Camera: keep busy until JARVIS finishes speaking the answer
                                    self._vision_cam_active    = False
                                    self._vision_close_pending = True
                                else:
                                    # Screen-only: no camera to close; release busy flag now
                                    self._vision_busy = False
                            elif self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                                    from google.genai import types

                                    fn_responses = []
                                    for fc in response.tool_call.function_calls:
                                        print(f"[JARVIS] {fc.name}")
                                        result = await self._execute_tool(fc)

                                        fn_responses.append(
                                            types.FunctionResponse(
                                                id=fc.id,
                                                name=fc.name,
                                                response={"result": result}
                                            )
                                        )

                                    await self.session.send_tool_response(
                                        function_responses=fn_responses
                                    )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)

                # Batch all immediately-available chunks into one write to reduce
                # thread-pool round-trips (was one asyncio.to_thread per 50ms slice).
                # Cap at ~200 ms so interrupt() still stops audio within ~200 ms.
                batch = bytearray(chunk)
                while len(batch) < 9600:   # 9600 bytes ≈ 200 ms at 24 kHz / 16-bit mono
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing optimized for speed:
          Phase 1 — instant greeting (no tools) → speech starts in <1s
          Phase 2 — news pre-fetched in a background thread while Phase 1 plays,
                    delivered as ready text (no Gemini tool-call round-trip) and
                    shown on the UI content panel. Waits for turn_complete event
                    instead of a fixed sleep so there is no unnecessary gap.
        """
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")
        time_str = datetime.now().strftime("%H:%M")

        # Start fetching news immediately — runs in parallel while phase 1 plays
        loop = asyncio.get_event_loop()
        news_future = loop.run_in_executor(None, _fetch_news_sync, "top world news today")

        await asyncio.sleep(0.3)
        if not self.session:
            return

        # ── Phase 1: instant greeting ─────────────────────────────────────────
        lang_clause = f" Respond in {lang}." if lang else ""
        name_clause = f" Address the user as {name}." if name else ""

        # Inject last session context if available — pop removes it so it's never repeated
        last = await asyncio.to_thread(pop_last_session)
        session_clause = ""
        if last:
            try:
                _delta = (datetime.now() - datetime.strptime(last["date"], "%Y-%m-%d")).days
                _when  = "earlier today" if _delta == 0 else ("yesterday" if _delta == 1 else f"{_delta} days ago")
            except Exception:
                _when = "last time"
            session_clause = (
                f" Also briefly and naturally mention that {_when}: {last['summary']}"
            )

        p1 = (
            f"Greet the user warmly, mention it is {time_str}, and say you are fetching today's news now.{session_clause} "
            f"Keep it to 2 short sentences max. Do not call any tools.{lang_clause}{name_clause}"
        )

        # Clear the turn-done event so we can wait for Phase 1 to finish
        if self._turn_done_event:
            self._turn_done_event.clear()

        try:
            await self.session.send_client_content(
                turns=[{
                    "role": "user",
                    "parts": [{"text": p1}]
                }],
                turn_complete=True,
            )
        except Exception as e:
            print(f"[Briefing] Phase 1 error: {e}")
            self.ui.write_log(f"SYS: Briefing phase 1 failed: {e}")
            return
        self.ui.write_log("SYS: Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fire as soon as Phase 1 audio is done ───────────────────
        async def _deliver_news():
            try:
                lang_str = f" Respond in {lang}." if lang else ""

                # Wait for news fetch (already running) and Phase 1 turn-complete
                # in parallel — whichever takes longer determines the wait time
                news_done   = asyncio.wrap_future(news_future)
                turn_waited = False
                if self._turn_done_event:
                    try:
                        await asyncio.wait_for(self._turn_done_event.wait(), timeout=6.0)
                        turn_waited = True
                    except asyncio.TimeoutError:
                        pass

                # Extra buffer: turn_complete fires when Gemini finishes *generating*
                # Phase 1, but audio may still be playing.  Waiting a beat here
                # prevents Phase 2 audio from arriving while Phase 1 is mid-sentence
                # (which sounds like a "repeated first response" to the user).
                if turn_waited:
                    await asyncio.sleep(0.8)
                else:
                    await asyncio.sleep(1.0)

                try:
                    news_text = await asyncio.wait_for(news_done, timeout=4.0)
                except Exception:
                    news_text = ""

                if not self.session:
                    await self._flush_note_queue()
                    return

                if news_text and len(news_text) > 60:
                    # Show on UI content panel immediately
                    self.ui.show_content("NEWS — top world news today", news_text)

                    p2 = (
                        f"[BRIEFING] Here are today's top news headlines:\n{news_text}\n\n"
                        "Pick ONE headline, summarise it in one sentence, then say the full list "
                        f"is displayed on screen. Do not call any tools.{lang_str}"
                    )
                else:
                    p2 = (
                        "News headlines could not be fetched right now. "
                        f"Let the user know briefly.{lang_str}"
                    )

                await self.session.send_client_content(
                    turns=[{
                    "role": "user",
                    "parts": [{"text": p2}]
                    }],
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Briefing phase 2 (news) sent.")
            except Exception as e:
                print(f"[Briefing] Phase 2 error: {e}")
                self.ui.write_log(f"SYS: Briefing phase 2 failed: {e}")
                
            await asyncio.sleep(2.0)
            await self._flush_note_queue()

        asyncio.create_task(_deliver_news())

    # ── Session memory ──────────────────────────────────────────────────────────

    async def _save_session_summary(self) -> None:
        """Summarise the current session in 1-2 sentences and save to long_term.json."""
        log = self._session_log
        if len(log) < 3:          # need at least one exchange to be worth saving
            return
        self._session_log = []    # reset immediately so the next session starts clean

        memory = load_memory()
        lang_entry = memory.get("identity", {}).get("language", {})
        lang = (lang_entry.get("value", "") if isinstance(lang_entry, dict) else str(lang_entry)).strip()
        lang = lang or "English"

        convo = "\n".join(log[-40:])   # cap at last 40 turns to stay within token budget
        prompt = (
            f"Summarize this conversation in 1-2 sentences in {lang}. "
            "Focus on what the user accomplished or discussed. "
            "Output ONLY the summary text, nothing else:\n\n" + convo
        )
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=_get_api_key())
            resp   = await asyncio.to_thread(
                client.models.generate_content,
                model="models/gemini-3.6-flash",
                contents=prompt,
            )
            summary = (resp.text or "").strip()
            if summary:
                save_session_summary(summary, lang)
        except Exception as e:
            print(f"[Memory] ⚠️ Session summary failed: {e}")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if not alert or not self.session:
                continue
            # Don't interrupt an active conversation
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking or (time.monotonic() - self._last_user_speech) < 10:
                continue
            try:
                await self.session.send_client_content(
                    turns={"parts": [{"text": alert}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Monitor] ⚠️ Could not send alert: {e}")

    # ── Background monitor ──────────────────────────────────────────────────────

    async def _run_background_monitor(self) -> None:
        """Check user-configured topics once per day; speak alerts when new headlines appear."""
        await asyncio.sleep(300)          # wait 5 min after startup before first check
        while True:
            if self.session:
                # Don't interrupt if user spoke recently or JARVIS is mid-sentence
                with self._speaking_lock:
                    speaking = self._is_speaking
                recent_speech = (time.monotonic() - self._last_user_speech) < 30
                if not speaking and not recent_speech:
                    try:
                        alerts = await asyncio.to_thread(monitor_check_all)
                        memory = load_memory()
                        lang_e = memory.get("identity", {}).get("language", {})
                        lang   = (lang_e.get("value", "") if isinstance(lang_e, dict) else str(lang_e)).strip() or "English"
                        for alert in alerts:
                            msg = (
                                f"{alert}\n\n"
                                f"Inform the user about this development naturally in {lang}. "
                                "One brief sentence only."
                            )
                            await self.session.send_client_content(
                                turns={"parts": [{"text": msg}]},
                                turn_complete=True,
                            )
                            self.ui.write_log(f"SYS: Monitor alert sent.")
                            await asyncio.sleep(6)   # gap between consecutive alerts
                    except Exception as e:
                        print(f"[Monitor] ⚠️ Background check error: {e}")
            await asyncio.sleep(1800)     # check every 30 minutes

    # ── Proactive mode ──────────────────────────────────────────────────────────

    async def _run_proactive_mode(self) -> None:
        """
        Background task: periodically checks if the user has been silent long enough,
        then hands time + memory context to Gemini so it can decide what (if anything)
        to say proactively. No hardcoded rules — Gemini makes the call.
        """
        while True:
            await asyncio.sleep(60)   # evaluate once per minute

            if not self.session:
                continue

            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue
            
            if not getattr(self, "_briefing_done", True):
                continue
            if getattr(self, "_note_queue", None):
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory       = await asyncio.to_thread(load_memory)
                monitors     = await asyncio.to_thread(list_monitors)
                recent_turns = self._session_log[-8:] if self._session_log else []
                prompt = self._proactive.build_prompt(
                    memory       = memory,
                    monitors     = monitors or None,
                    recent_turns = recent_turns or None,
                )
                await self.session.send_client_content(
                    turns={"parts": [{"text": prompt}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Proactive check-in.")
            except Exception as e:
                print(f"[Proactive] ⚠️ {e}")

    # ── Phone audio relay ────────────────────────────────────────────────────────

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()

    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": text}]},
                        turn_complete=True,
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    print(f"[Dashboard] Dropped command (no session): {text}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        
        self._start_notes_listener()
        
        # Messenger (Telegram DND / drafts)- один раз на процесс
        try:
            if getattr(self, "messenger", None) and self.messenger.start():
                print("[JARVIS] MessengerAssistant started")
        except Exception as e:
            print(f"[JARVIS] Messenger start: {e}")

        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            asyncio.create_task(self._dashboard.serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            self._dashboard = None

        while True:
            try:
                print("[JARVIS] Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                # Fresh client on every reconnect — avoids stale HTTP session state
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    # Reset transient state that must not carry over from a previous session
                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False

                    print("[JARVIS] Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_background_monitor())
                    tg.create_task(self._run_proactive_mode())
                    tg.create_task(self._run_usb_security())
                    tg.create_task(self._run_download_guard())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())

                    # Morning briefing — fires once per process launch (if enabled)
                    if not self._briefing_sent and get_brief_enabled():
                        self._briefing_sent = True
                        async def _delayed_briefing():
                            await asyncio.sleep(4.0)  # дать сессии стабилизироваться
                            if self.session:
                                await self._send_startup_briefing()
                        tg.create_task(_delayed_briefing())
                    else:
                        #брифинг выключен или уже был сразу заметки
                        self._briefing_done = True

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                # Catches both Exception and BaseExceptionGroup (Python 3.11+
                # TaskGroup raises BaseExceptionGroup when tasks are cancelled
                # externally, which `except Exception` would miss, letting the
                # exception escape the while-loop and causing asyncio.run() to
                # start shutdown — resulting in "executor after shutdown" errors).
                err_str = str(e)
                print(f"[JARVIS] Error ({type(e).__name__}): {e}")
                traceback.print_exc()

                # Invalid API key — stop hammering the API, prompt re-configuration
                if "API key not valid" in err_str or "1007" in err_str:
                    self.ui.write_log("ERR: API key invalid — please re-enter your key.")
                    self.ui.set_state("SLEEPING")
                    self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(1)
                    print("[JARVIS] New API key saved — reconnecting...")
                    _conn_backoff = 3
                    continue

                # Network / timeout errors — log clearly and back off
                is_net_err = any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                ))
                if is_net_err:
                    _conn_backoff = min(getattr(self, "_conn_backoff", 3) * 2, 60)
                    self._conn_backoff = _conn_backoff
                    self.ui.write_log(
                        f"NET: Bağlantı kurulamadı — {_conn_backoff}s sonra tekrar deneniyor. "
                        "(VPN gerekiyor olabilir)"
                    )
                else:
                    self._conn_backoff = 3
            finally:
                self.session = None
                # Only save if there was a real conversation (≥3 turns)
                if len(self._session_log) >= 3:
                    asyncio.create_task(self._save_session_summary())

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            delay = getattr(self, "_conn_backoff", 3)
            print(f"[JARVIS] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)

        # Жёсткая связь UI ↔ Jarvis (для кнопки GESTURE CONTROL)
        ui.jarvis = jarvis

        # На случай, если шестерёнка живёт внутри другого объекта
        for name in ("window", "main_window", "ui", "root", "main", "win"):
            obj = getattr(ui, name, None)
            if obj is not None:
                try:
                    obj.jarvis = jarvis
                    print(f"[JARVIS] linked jarvis → ui.{name}")
                except Exception:
                    pass
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()