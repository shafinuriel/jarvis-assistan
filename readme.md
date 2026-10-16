# 🤖 J.A.R.V.I.S. (11.10.26)

A real-time voice AI that can hear, see, understand, and control your computer — on any OS.  
Supports Windows, macOS, and Linux. Built on the Gemini Live API for native audio streaming, delivering zero subscriptions and total digital autonomy.

---

## 📖 Overview

J.A.R.V.I.S. is where the assistant stops being a tool and starts being a presence.  
It remembers yesterday’s conversation, watches the topics you care about, and speaks first when it has something worth saying.  
The goal of this build was continuity — JARVIS should feel like it never fully left, even after you close it.  
It’s not just an assistant — it’s an extension of your digital life.

---

## 🚀 What’s New in v2 (October 2026)

### 🧠 Offline Brain (Gemma 4B)
When there is no internet, JARVIS automatically switches to a local Gemma 4B model via Ollama.  
Strict rule: if internet is available → only Gemini is used. Offline brain is never activated while online (to protect your GPU).

### 🛡️ USB Security + Download Guard
Real-time scanning of USB drives and the Downloads folder.  
Suspicious files (`.exe`, `.bat`, `.vbs`, `.scr`, etc.) trigger a red sphere alert and voice report.  
You decide: quarantine, delete or ignore. Nothing is deleted automatically.

### 📱 Remote Ecosystem (Phone + TV)
WebSocket server + QR-code pairing.  
Scan the QR on your phone or TV-box and control JARVIS (and let it control the device).  
Works completely inside your local Wi-Fi — no cloud middleman.

### 🗺️ God’s Eye View
Isolated 3D tactical globe (Three.js).  
Launch with a voice command, fly to any coordinates, then close it — zero resource usage when closed.

### 🎮 SystemController 2.0
Direct launch of apps, browsers, Steam games (install / run / pause), Spotify control and media keys.  
No more GUI automation or fragile keyboard simulation.

### 📝 Proactive Notes + Messenger Assistant
Notes written on the phone appear on the PC even without an active connection.  
Smart DND + auto-responder for Telegram with family whitelist.

### 🎂 Birthday Protocol & Study Helper
One command opens a birthday video on the kitchen TV.  
Offline/online study mode with topics from grades 6–11.

---

## 💡 Capabilities

### Core Features

| Feature | Description |
|---------|-------------|
| 🗣️ Real-time Voice | Ultra-low latency conversation in any language via Gemini Live API |
| 🖥️ System Control | Launch apps, adjust volume/brightness, WiFi, shortcuts, power — all by voice |
| 🎮 Gaming & Media | Steam install/run, Spotify control, YouTube, VLC |
| 👁️ Visual Awareness | Real-time screen capture and webcam vision piped into the main Gemini session |
| 🧠 Persistent Memory | Deeply remembers projects, preferences and personal context across sessions |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |
| 🌅 Morning Briefing | On first boot: greets you, reads the time, recaps yesterday and fetches live news |
| 🔔 Proactive 2.0 | Time-aware, context-aware check-ins — knows the time of day, your projects and what you’ve been discussing |
| 💾 Session Memory | Summarises each conversation and mentions it naturally next morning — consumed after use, never repeats |
| 📡 Background Monitoring | User-configured topic watching — checks for new headlines once a day and alerts naturally |
| 🌡️ Hardware Monitoring | Continuous CPU, RAM, GPU and temperature telemetry with localized voice alerts |
| 🌤️ Weather Report | Live weather data for your city, personalized from memory |
| 📰 Dynamic Content Panel | Scrollable display layer beneath the HUD that renders web results, news and search data |
| 🔍 Multi-Mode Web Search | news / research / price / compare / search — Gemini Grounded first, DDG fallback |
| ⏰ Smart Reminders | OS-native scheduled notifications |
| ✈️ Flight Finder | Live flight price and availability lookup |
| 🎮 Game Updater | Checks and triggers game updates on Steam and Epic Games on demand |
| 📁 File Processor | Read, summarize and answer questions about local files |
| 💻 Code Helper | Inline code review, debugging and generation |
| 🌐 Browser Control | Open URLs, navigate tabs and interact with the browser by voice |
| 💬 Send Message | Compose and send messages through WhatsApp, Telegram and more |
| 📺 YouTube Control | Search, play and control YouTube playback by voice |
| 🖥️ Desktop Control | Taskbar, window management and desktop-level operations |
| 🌍 Silent Language Memory | Detects spoken language on first use — all future sessions adapt automatically |
| 📱 Remote Dashboard | Control the assistant from your phone via QR code pairing |
| 🚀 Auto-Start on Boot | Registers with the OS startup system |
| 📋 Clipboard Intelligence | Copy any text → floating panel with Translate / Summarise / Explain / Fix |
| 🛡️ USB / Download Guard | Real-time threat detection on flash drives and Downloads folder |
| 🧠 Offline Brain | Local Gemma 4B fallback when internet is unavailable |
| 🗺️ God’s Eye View | Interactive 3D tactical map |

---

## 🗺️ J.A.R.V.I.S. Roadmap (Future Milestones)

| Milestone | Focus |
|-----------|-------|
| MARK 55 | Advanced Automation: Multi-agent workflows, allowing JARVIS to spin up sub-agents for heavy code compilation and debugging while maintaining the main conversation |
| MARK 65 | Expanded Network Control: Deep Wake-on-LAN routing capabilities and secure remote desktop tunneling directly through the assistant’s architecture |
| MARK 80 | Fully Offline Mode: Fallback to local on-device LLMs for core tasks when internet access is unavailable, ensuring absolute privacy and zero latency |
| MARK 100 | Biomechanical & Hardware API: Endpoints designed to interface with custom micro-controllers and external physical sensors for advanced robotics integration |

---

## ⚡ Quick Start

```bash
# 1. Install dependencies
python setup.py

# 2. Put your Gemini API key into config/api_keys.json
#    (copy from api_keys.example.json)

# 3. (Optional) Offline brain
ollama pull gemma2:4b

# 4. Run
python main.py

## Requirements:
*OS: Windows 10/11, macOS or Linux
*Python 3.12 or 3.14
*Microphone (required for voice interaction)
*Free Gemini API key (config/api_keys.json)

J.A.R.V.I.S.
├── main.py                 # Core loop - Gemini Live session, audio I/O, tool dispatch
├── ui.py                   # PyQt6 HUD - waveform, log panel, interrupt button, camera feed
├── setup.py                # First-run configuration wizard
├── actions/
│   ├── system_controller.py    # Apps, Steam, Spotify, browsers
│   ├── offline_brain.py        # Gemma 4B + math fallback
│   ├── remote_server.py        # WebSocket + QR pairing
│   ├── usb_security.py         # USB threat scanner
│   ├── download_guard.py       # Downloads folder monitor
│   ├── messenger_assistant.py  # Telegram DND + drafts
│   ├── proactive_notes.py      # Phone → PC notes bridge
│   ├── birthday_protocol.py    # Birthday video on TV
│   ├── study_helper.py         # Offline/online study mode
│   └── ...                     # All other tools
├── modules/gods_eye/           # Isolated 3D tactical map (vendor)
├── memory/                     # Runtime data (gitignored)
├── config/                     # api_keys.example.json only
├── core/prompt.txt             # Assistant personality and tool-routing rules
└── requirements.txt

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---