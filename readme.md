# 🎵 Logitech Media Server Plugin (Extended)
### 🚀 Release v1.4.0 — Stable Release

This first stable release provides full integration between **Logitech Media Server (LMS)** and **Domoticz**.  
The plugin has been fully rewritten, extended, tested, and is stable on Domoticz 2024+.

---

## 🌟 New Features in v1.4.0

### 🎛️ **Full LMS Remote Control**
- Play / Pause / Stop
- Next / Previous track
- Volume control (dimmer)
- Power On/Off
- Sync / Unsync players

### 📡 **Automatic Player Detection**
- Detects all connected LMS players automatically
- Creates Domoticz devices for each player

### 📊 **Extended Player Information**
- Current track
- Artist
- Album
- Playback status
- Volume
- Online/offline status

### 🎶 **Playlist Support**
- Load playlists per player
- Add tracks to playlist
- Clear playlist
- Start playlists directly via Domoticz or scripts

### 🧠 **Reliable JSON-RPC Communication**
- Full support for `jsonrpc.js`
- Fully tested with Material Skin UI
- Compatible with LMS 8.x

---

## 🛠️ Technical Improvements

- New plugin structure following Domoticz 2024+ standards
- Heartbeat fix (no crashes for missing functions)
- Faster player status parsing
- Reduced API requests → more efficient CPU usage
- Improved error handling + debug logging

---

## 📦 Installation

Clone the plugin into the Domoticz plugin folder:

```bash
cd /home/<user>/domoticz/plugins
git clone https://github.com/MadPatrick/domoticz_LMS.git
sudo systemctl restart domoticz

