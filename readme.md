# ⚙️ J.A.R.V.I.S. (50)
A real-time voice AI that can hear, see, understand, and control your computer – on any OS. Supports Windows, macOS, and Linux. Built on the Gemini Live API for native audio streaming, delivering zero subscriptions and total digital autonomy.
---
## 👁️ Overview
J.A.R.V.I.S. is where the assistant stops being a tool and starts being a presence. It remembers yesterday's conversation, watches the topics you care about, and speaks first when it has something worth saying. The goal of this build was continuity – JARVIS should feel like it never fully left, even after you close it. 
It's not just an assistant – it's an extension of your digital life.
---
## 🚀 What's New in J.A.R.V.I.S.
### 🔕 Smart Do Not Disturb (DND) & Auto-Responder
The system now features a deeply integrated, context-aware DND mode. When engaged, JARVIS dynamically intercepts incoming messages, evaluates their urgency based on your current workload, and handles them autonomously. It doesn't just silence notifications; it holds conversations on your behalf, taking messages and briefing you only when you are ready.
### 📱 Seamless Telegram Integration
JARVIS has broken out of the desktop environment. You can now communicate with, control, and query your PC remotely via a secure Telegram session. Whether you need to execute a local script while away, check hardware telemetry, or continue a brainstorming session on the go, JARVIS is accessible directly from your mobile device.
### 🧠 Long-Term Vector Memory (ChromaDB)
Moving beyond simple JSON logs, JARVIS now utilizes ChromaDB for high-dimensional vector embeddings. This allows the assistant to securely recall past contexts, coding projects, personal preferences, and complex data across months of interactions. It remembers what you discussed weeks ago and naturally weaves that context into current conversations without requiring redundant prompts.
### Jarvis now has biometrical and security functions:
#1 ALL/PERSONAL Voice Mode:
    ALL: J.A.R.V.I.S. responds to every body.
    To use personal voice the user first of all has to summon "Remember my voice" command. After you summoned command you need to speak for 4 seconds for JARVIS to remember your voice.
    PERSONAL: J.A.R.V.I.S. responds only to your voice.
#2 USB/DOWNLOAD Guard:
    USB_SECURITY_GUARD: Whenever you connect the flash-card to your pc JARVIS immediately scans this flash-card. If it  has any virus or unwanted files/programs, he can put them into quarantine or delete from the flash-card.
    DOWNLOAD_SECURITY_GUARD: Whenever new files(.exe, .bat, .txt, and others) appear in Downloads Jarvis scans them, and if it has any virus or unwanted files/programs, he can put them into quarantine or delete them from the pc.

---
## 🧠 Capabilities
### Core Features

| Feature | Description |
| :--- | :--- |
| 🎙️ **Real-time Voice** | Ultra-low latency conversation in any language via Gemini Live API |
| 🎛️ **System Control** | Launch apps, adjust volume/brightness, WiFi, shortcuts, power - all by voice |
| 🧩 **Autonomous Tasks** | High-level planning for complex multi-step goals via agent mode |
| 👁️ **Visual Awareness** | Real-time screen capture and webcam vision piped into your main Gemini session |
| 🧠 **Persistent Memory** | Deeply remembers projects, preferences, and personal context across sessions |
| ⌨️ **Hybrid Input** | Seamlessly switch between keyboard typing and voice commands |
| 🌅 **Morning Briefing** | On first boot: greets you, reads the time, recaps yesterday, and fetches live news |
| 🔔 **Proactive 2.0** | Time-aware, context-aware check-ins - knows the time of day, your projects, and what you've been discussing |
| 🗃️ **Session Memory** | Summarises each conversation and mentions it naturally next morning - consumed after use, never repeats |
| 📡 **Background Monitoring** | User-configured topic watching - checks for new headlines once a day and alerts naturally |
| 📊 **Hardware Monitoring** | Continuous CPU, RAM, GPU and temperature telemetry with localized voice alerts |
| 🌤️ **Weather Report** | Live weather data for your city, personalized from memory |
| 📰 **Dynamic Content Panel** | Scrollable display layer beneath the HUD that renders web results, news, and search data |
| 🔍 **Multi-Mode Web Search** | `news` / `research` / `price` / `compare` / `search` - Gemini Grounded first, DDG fallback |
| ⏰ **Smart Reminders** | OS-native scheduled notifications (Windows Task Scheduler / macOS LaunchAgent / Linux systemd) |
| ✈️ **Flight Finder** | Live flight price and availability lookup |
| 🎮 **Game Updater** | Checks and triggers game updates on Steam and Epic Games on demand |
| 📂 **File Processor** | Read, summarize, and answer questions about local files |
| 💻 **Code Helper** | Inline code review, debugging, and generation |
| 🌐 **Browser Control** | Open URLs, navigate tabs, and interact with the browser by voice |
| ✉️ **Send Message** | Compose and send messages through WhatsApp, Telegram, and more |
| 📺 **YouTube Control** | Search, play, and control YouTube playback by voice |
| 🖥️ **Desktop Control** | Taskbar, window management, and desktop-level operations |
| 🤫 **Silent Language Memory** | Detects spoken language on first use - all future sessions adapt automatically |
| 📱 **Remote Dashboard** | Control the assistant from your phone via QR code pairing |
| ⚡ **Auto-Start on Boot** | Registers with the OS startup system (registry / LaunchAgent / .desktop) |
| 📋 **Clipboard Intelligence** | Copy any text -> floating panel with Translate / Summarise / Explain / Fix |
| 👤 **Assistant Customization** | Change the assistant name and your name from the UI - takes effect immediately |

---
## 🗺️ J.A.R.V.I.S. Roadmap (Future Milestones)

| Milestone | Focus |
| :--- | :--- |
| **MARK. 55** | **Advanced Automation:** Multi-agent workflows, allowing JARVIS to spin up sub-agents for heavy code compilation and debugging while maintaining the main conversation. |
| **MARK. 65** | **Expanded Network Control:** Deep Wake-on-LAN routing capabilities and secure remote desktop tunneling directly through the assistant's architecture. |
| **MARK. 80** | **Fully Offline Mode:** Fallback to local on-device LLMs for core tasks when internet access is unavailable, ensuring absolute privacy and zero latency. |
| **MARK. 100** | **Biomechanical & Hardware API:** Endpoints designed to interface with custom micro-controllers and external physical sensors for advanced robotics integration. |

---
## ⚡ Quick Start
```bash
run setup.py to download all pips
python main.py

​⚠️ Installation Note:
Some OS-specific dependencies are notbundled in requirements.txt to keep the repo lightweight. If you hit a ModuleNotFoundError, 
install the missing package with pip install <module_name>.

Requirements:
OS | Windows 10/11,macOS, or Linux
Python | 3.12 or 3.14
Microphone | Required for voice interaction
API Key | Free Gemini API key(config/api_keys.json)

Project Structure:
    J.A.R.V.I.S.
    ├── main.py                     # Core loop - Gemini Live session, audio I/O, tool dispatch
    ├── ui.py                       # PyQt6 HUD - waveform, log panel, interrupt button, camera feed
    ├── setup.py                    # First-run configuration wizard
    │
    ├── actions/
    │   ├── background_monitor.py   # User-configured topic watching - daily DDG checks, no crypto
    │   ├── birthday_protocol.py    # Birthday reminders and greetings
    │   ├── browser_control.py      # Web browser control
    │   ├── code_helper.py          # Code review and generation
    │   ├── code_tracker.py         # Code tracking / activity monitoring
    │   ├── computer_control.py     # Keyboard shortcuts, mouse, window management
    │   ├── computer_settings.py    # Volume, brightness, WiFi, power
    │   ├── desktop.py              # Desktop and taskbar control
    │   ├── dev_agent.py            # Developer task agent
    │   ├── download_guard.py       # Download monitoring / protection
    │   ├── file_controller.py      # File system operations
    │   ├── file_processor.py      # Document reading and summarization
    │   ├── flight_finder.py        # Flight search
    │   ├── game_updater.py         # Game update management (Steam / Epic)
    │   ├── knowledge_action.py     # Knowledge base actions / Q&A
    │   ├── messenger_assistant.py  # Messenger assistant integration
    │   ├── open_app.py             # Application launcher
    │   ├── phone_control.py        # Phone control / synchronization
    │   ├── proactive.py            # Proactive 2.0 - time/context/rotation-aware check-ins
    │   ├── reminder.py             # OS-native scheduled notifications
    │   ├── remote_server.py        # Remote server / remote access
    │   ├── sandbox.py              # Sandboxed code execution
    │   ├── screen_processor.py     # Screen capture & webcam vision via Gemini Live
    │   ├── send_message.py         # Messaging integration
    │   ├── study_helper.py         # Study assistant / learning support
    │   ├── system_controller.py    # System-level control
    │   ├── system_monitor.py       # CPU / RAM / GPU / temperature telemetry
    │   ├── usb_security.py         # USB device security monitoring
    │   ├── voice_id.py             # Voice identification / speaker recognition
    │   ├── weather_report.py       # Live weather data
    │   ├── web_search.py           # Gemini + DDG parallel search (news, research, price, compare)
    │   ├── youtube_video.py        # YouTube playback control
    │
    ├── memory/
    │   ├── memory_manager.py       # Load/save long_term.json - sessions, monitors, identity
    │   └── long_term.json          # Persistent store: identity, preferences, projects, sessions
    │
    ├── core/
    │   └── prompt.txt              # Assistant personality and tool-routing rules
    │
    └── config/
        └── api_keys.json           # API key, OS setting, assistant name, user name


⚠️ License
​Personal and non-commercial use only.
Licensed under Creative Commons BY-NC 4.0.

