# J.A.R.V.I.S. (v3.0)

**It's all easy with Jarvis.**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS.  
Supports Windows, macOS, and Linux. Built on the Gemini Live API for native audio streaming.

---

## 📌 Overview

J.A.R.V.I.S. is where the assistant stops being a tool and starts being a presence.  
It remembers yesterday’s conversation, watches the topics you care about, and speaks first when it has something worth saying.

The goal of this build was continuity — JARVIS should feel like it never fully left, even after you close it.  
It’s not just an assistant — it’s an extension of your digital life.

---

## What's New in v3.0

- **FaceLock** — Camera-based PC lock. Recognizes only the owner's face. Easy setup: just drop a photo and say "this is my face".
- **set_owner_face** — Simple way to set your face photo without touching any files.
- **Voice Module Control** — Enable/disable FaceLock, gestures, sphere, DND, USB Security, Download Guard and more by voice.
- **Improved 3-level Security Scanner** — Quick / Full / Event-driven scans with visual buttons (Quarantine / Delete / Ignore).
- **Better Stability** — Safer imports, optional modules, cleaner config system.

---

## 🔥 Core Capabilities

| Feature | Description |
|---------|-------------|
| 🎙️ Real-time Voice | Ultra-low latency conversation via Gemini Live API |
| 🖥️ System Control | Launch apps, adjust volume/brightness, Wi-Fi, shortcuts, power — all by voice |
| 🎮 Gaming & Media | Steam install/run, Spotify control, YouTube, VLC |
| 👁️ Visual Awareness | Real-time screen capture and webcam vision |
| 🧠 Persistent Memory | Deeply remembers projects, preferences and personal context |
| 🔄 Hybrid Input | Seamlessly switch between keyboard typing and voice commands |
| 🌅 Morning Briefing | Greets you, reads the time, recaps yesterday and fetches live news |
| 🛡️ USB + Download Guard | Real-time threat detection on flash drives and Downloads folder |
| 📴 Offline Brain | Local Gemma 4B fallback when internet is unavailable |
| 🌐 Remote Ecosystem | Control JARVIS from phone/TV via WebSocket + QR pairing |
| 🌍 God's Eye View | Isolated 3D tactical globe (Three.js) |
| 🖐️ Gesture Control | Open palm / fist control for interrupt and mute |
| 📝 Proactive Notes | Notes from phone appear on PC even without active connection |
| 💬 Messenger Assistant | Smart DND + auto-responder for Telegram with family whitelist |
| 🔒 FaceLock | Camera face recognition lock. Only owner face unlocks the PC |
| 📸 set_owner_face | Drop photo → say "this is my face" → done |
| 🎛 Voice Module Control | Turn any feature on/off by voice |

---

## 🗺️ Roadmap

| Milestone | Focus |
|-----------|-------|
| **MARK 55** | Multi-agent workflows |
| **MARK 65** | Deep Wake-on-LAN + secure remote desktop |
| **MARK 80** | Fully offline mode with local LLMs |
| **MARK 100** | Hardware API for sensors and robotics |

---

## ⚡ Quick Start

```bash
# 1. Install dependencies
python setup.py

# 2. Put your Gemini API key into config/api_keys.json
#    (copy from config/api_keys.example.json)

# 3. (Optional) Offline brain
ollama pull gemma2:4b

# 4. Run
python main.py

Requirements:
Windows 10/11, macOS or Linux
Python 3.12 or 3.14
Microphone
Free Gemini API key

J.A.R.V.I.S.
├── main.py                 # Core loop
├── ui.py                   # PyQt6 HUD + sphere
├── sphere_ui.html          # Three.js visual core
├── setup.py
├── actions/
│   ├── system_controller.py
│   ├── gesture_control.py
│   ├── security_scanner.py
│   ├── usb_security.py
│   ├── download_guard.py
│   └── ...
├── config/
│   ├── config.example.json
│   └── api_keys.example.json
├── core/
│   └── prompt.txt
└── requirements.txt

📄 License
Personal and non-commercial use only.
Licensed under Creative Commons BY-NC 4.0.

"It's all easy with Jarvis."