# CommandMesh

<div align="center">

**A secure, cloud-relayed, cross-platform remote command network.**

Control your PC and Android devices from your phone — through the internet, on any network, with zero port forwarding.

[![GitHub Repo](https://img.shields.io/badge/GitHub-CommandMesh-00ffaa?style=flat-square&logo=github&logoColor=white)](https://github.com/anaconda2401/CommandMesh)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![MQTT](https://img.shields.io/badge/Broker-HiveMQ-purple?style=flat-square)](https://www.hivemq.com/)
[![PWA](https://img.shields.io/badge/Frontend-PWA-orange?style=flat-square)](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)

</div>

---

## What is CommandMesh?

CommandMesh is a **private device control mesh network**. Run lightweight Python nodes on your PC or Android (Termux), then control them from a **Progressive Web App (PWA)** on your phone — from anywhere in the world.

All communication is relayed through a **HiveMQ cloud MQTT broker** over TLS, meaning:
- ✅ No port forwarding required
- ✅ Works across different Wi-Fi networks and mobile data
- ✅ All commands are cryptographically signed with HMAC-SHA256
- ✅ Replay attacks are blocked by a 10-second timestamp window

---

## Architecture

```
┌──────────────┐        TLS/MQTT         ┌───────────────────┐
│  PWA (Phone) │ ──── HiveMQ Cloud ────► │  Python Node (PC) │
│              │ ◄───── Discovery ─────── │  Python Node (TV) │
└──────────────┘                          └───────────────────┘
```

1. **Each device** runs `main.py`, which detects its environment (Desktop or Termux/Android) and boots the correct node.
2. **Each node** connects to HiveMQ and publishes its presence to the discovery topic.
3. **The PWA** (hosted locally or on GitHub Pages) subscribes to the discovery topic, auto-discovers all live nodes, and lets you select a device to control.
4. Every command is **HMAC-signed** by the PWA and **verified** by the receiving node before execution.

---

## Project Structure

```
CommandMesh/
├── main.py                       # Universal entry point — auto-detects device & boots node
│
├── core/
│   └── security.py               # HMAC-SHA256 signature verification & replay attack prevention
│
├── nodes/
│   ├── desktop/
│   │   ├── node.py               # Desktop node (Windows/Mac/Linux)
│   │   ├── requirements-desktop.txt
│   │   └── mesh_scripts/         # (gitignored) Place your .bat/.sh scripts here
│   │
│   └── termux/
│       ├── node.py               # Android node (Termux / Smart TV)
│       └── requirements-termux.txt
│
├── pwa/
│   ├── index.html                # Full PWA controller UI (single file, no build step)
│   ├── manifest.json             # PWA install manifest
│   ├── config.js                 # (gitignored) Your live HiveMQ WebSocket URL
│   └── config.example.js         # Template — copy and rename to config.js
│
├── .env                          # (gitignored) Your secrets — NEVER commit this
├── .env.example                  # Template — copy and rename to .env
└── .gitignore
```

---

## Setup Guide

### Prerequisites

- Python 3.8+ installed on each device you want to control
- A free [HiveMQ Cloud](https://www.hivemq.com/cloud/) account (the free tier is sufficient)

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/anaconda2401/CommandMesh.git
cd CommandMesh
```

### Step 2: Configure Secrets

Copy the environment variable template and fill in your HiveMQ credentials:

```bash
cp .env.example .env
```

Open `.env` and fill in your details:

```env
MQTT_BROKER=YOUR_CLUSTER_ID.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=your_hivemq_username
MQTT_PASSWORD=your_hivemq_password
MESH_SECRET=choose_a_strong_secret_key
```

> **Important:** `MESH_SECRET` is a shared key between the PWA and all nodes. It must be the same everywhere. Choose something long and random.

### Step 3: Configure Each Device Node

Open the node file for your device and set its identity:

**`nodes/desktop/node.py`** (for your PC):
```python
DEVICE_ID   = "my_gaming_pc"    # Unique ID for this device (no spaces)
DEVICE_NAME = "Gaming PC"       # Display name shown in the PWA
DEVICE_TYPE = "pc"
```

**`nodes/termux/node.py`** (for your Android / TV):
```python
DEVICE_ID   = "living_room_tv"
DEVICE_NAME = "Android Smart TV"
DEVICE_TYPE = "tv"
```

### Step 4: Run the Node

On each device, simply run:

```bash
python main.py
```

`main.py` will automatically:
1. Detect if it's running on Desktop or Termux (Android)
2. Install the correct dependencies from `requirements-{device}.txt`
3. Validate your `.env` configuration
4. Run a live pre-flight TLS connection test to HiveMQ
5. Boot the correct node script

### Step 5: Configure and Open the PWA

Copy the PWA config template:

```bash
cp pwa/config.example.js pwa/config.js
```

Open `pwa/config.js` and enter your HiveMQ **WebSocket** URL (browsers use a different port than Python nodes):

```javascript
const CONFIG = {
    // Note: Browsers use WebSockets port (8884), NOT the standard MQTT port (8883)
    BROKER_URL: "wss://YOUR_CLUSTER_ID.s1.eu.hivemq.cloud:8884/mqtt",
    BASE_TOPIC: "commandmesh",
    DISCOVERY_TOPIC: "commandmesh/discovery/#"
};
```

Open `pwa/index.html` in your phone's browser (or any browser). On first launch, enter your HiveMQ **username**, **password**, and **Mesh Secret**. These are saved in `localStorage` — you won't need to enter them again.

---

## Security Model

CommandMesh uses a **dual-layer security system**:

| Layer | Mechanism | Protection Against |
|---|---|---|
| **Transport** | TLS 1.2+ (HiveMQ enforced) | Eavesdropping, MITM attacks |
| **Payload** | HMAC-SHA256 signature | Command tampering, forged messages |
| **Timestamp** | 10-second expiry window | Replay / zombie attacks |

Every command payload includes:
```json
{
  "action": "lock_pc",
  "from": "pwa_admin",
  "to": "desktop_main",
  "timestamp": 1746123456,
  "signature": "a3f9c2..."
}
```

The node verifies the signature **before** executing any action. A message with an invalid signature or one older than 10 seconds is silently dropped.

---

## Supported Commands

### Media & System
| Command | PC (Desktop) | Android (Termux) |
|---|---|---|
| `play_pause` | `pyautogui` media key | `keyevent 85` |
| `vol_up` | `pyautogui` volume up | `keyevent 24` |
| `vol_down` | `pyautogui` volume down | `keyevent 25` |
| `home` | Win+D (show desktop) | `keyevent 3` (Home) |
| `lock_pc` | `LockWorkStation` | `keyevent 26` (Power) |
| `open_youtube` | Opens in browser | Opens via intent |

### Navigation (D-Pad)
`dpad_up`, `dpad_down`, `dpad_left`, `dpad_right`, `dpad_center`

### Advanced Tools (Parameterized)
| Command | Description | PC | Android |
|---|---|---|---|
| `open_url` | Opens a URL | `webbrowser.open()` | Android intent |
| `type_text` | Types text at cursor | `pyautogui.write()` | `input text` |
| `run_script` | Executes a script file | ✅ (from `mesh_scripts/`) | 🚫 Blocked |

### Custom Scripts (PC Only)

Place any `.bat` or `.sh` script inside `nodes/desktop/mesh_scripts/`. From the PWA's **Advanced Tools** section, type the filename (e.g., `launch_obs.bat`) and tap **Run Script**.

> Scripts in `mesh_scripts/` are gitignored by default to keep your automations private.

---

## Extending CommandMesh

Adding a new command is a two-step process:

1. **Add the action handler** in the relevant `nodes/<device>/node.py` inside `execute_action()`:
   ```python
   elif action == "my_new_command":
       # your code here
   ```

2. **Add a button** in `pwa/index.html`:
   ```html
   <button onclick="sendCommand('my_new_command')">My New Command</button>
   ```

---

## Troubleshooting

**`❌ Missing critical .env variables`**
→ Ensure `.env` exists in the root directory and all 5 keys are filled in.

**`❌ Authentication Failed`**
→ Double-check your HiveMQ username and password in `.env`. Ensure the cluster is active.

**`❌ Script not found in mesh_scripts/`**
→ Place the script file inside `nodes/desktop/mesh_scripts/` and use only the filename, not a path.

**PWA shows "🔴 Connection Error"**
→ Verify `pwa/config.js` uses the **WebSocket URL** (`wss://...`) on **port 8884**, not 8883.

**Commands are rejected on the node**
→ Ensure `MESH_SECRET` in `.env` matches exactly what you entered in the PWA login screen.

---

## License

This project is open-source. Feel free to fork, modify, and build on it.

---

<div align="center">
Made with ☕ | <a href="https://github.com/anaconda2401/CommandMesh">github.com/anaconda2401/CommandMesh</a>
</div>
