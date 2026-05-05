# CommandMesh

CommandMesh is a secure, private device network that allows you to execute remote commands across multiple platforms (Desktop & Android) over MQTT. 

Built with security first, the project ensures that the MQTT broker acts only as a dumb relay. All commands are cryptographically signed by a client-side Progressive Web App (PWA) and verified locally on the target device using Ed25519 cryptography.

## Features

- **Cross-Platform Nodes:** Run nodes on Windows, macOS, Linux, or Android (via Termux).
- **Progressive Web App (PWA):** Control your entire network from a sleek, mobile-friendly web interface. Includes a D-Pad, media controls, and custom text/script inputs.
- **Cryptographic Security:** Every command is signed using your Master Passphrase. Payload tampering, spoofing, and replay attacks are actively prevented.
- **Zero-Config Setup:** Nodes auto-detect their environment, install dependencies, and provide a local web dashboard (port 8080) for easy initial configuration.
- **Custom Scripts:** Desktop nodes can securely execute whitelisted local scripts (`.bat`, `.sh`, `.ps1`, `.py`).
- **Android Integration:** The Termux node uses ADB or Root (`su`) to control Android TVs or phones (simulate keypresses, open URLs, etc.).

## Architecture

1. **MQTT Broker:** The central relay for all messages (e.g., a free HiveMQ Cloud cluster).
2. **Nodes:** Python clients running on your target devices.
   - **Desktop Node:** Uses `pyautogui` and `subprocess` to control PCs (type text, media controls, lock screen, execute whitelisted scripts).
   - **Termux Node:** Uses `adb` or root (`su`) to control Android devices (launch intents, input keyevents like D-Pad/Volume).
3. **PWA Controller:** A standalone HTML/JS web app (`pwa/index.html`) that generates cryptographic signatures locally using TweetNaCl and sends commands to the MQTT broker.

## Setup Instructions

### 1. The PWA Controller
The PWA requires no backend and can be hosted anywhere (GitHub Pages, Vercel, Netlify) or just opened locally.
1. Open `pwa/index.html` in your browser.
2. Enter your MQTT Broker details (e.g., HiveMQ URL, username, and password).
3. Enter a strong **Master Passphrase**. 
4. Click **Generate Node Public Key** and copy the generated hex key. You will need this for your nodes.

### 2. Node Installation
Clone the repository on the target device:
```bash
git clone https://github.com/anaconda2401/CommandMesh.git
cd CommandMesh
python main.py
```
On first run, the node will:
1. Detect your OS environment (Termux vs Desktop).
2. Install required Python dependencies automatically.
3. Launch a local setup server at `http://127.0.0.1:8080`.
4. Open the local dashboard in your browser and paste your MQTT credentials and the **Public Key** you generated in the PWA.
5. The node will save to `.env` and connect to the mesh!

### 3. Desktop Node Scripts (Optional)
Desktop nodes can execute custom scripts remotely. For security, only whitelisted scripts can be executed.
1. Place your scripts inside `nodes/desktop/scripts/`.
2. Add the exact script filename to the `ALLOWED_SCRIPTS` list inside `config/allowed_scripts.py`.

### 4. Android Node Setup
On Android, CommandMesh runs inside Termux.
- **Rooted Devices:** Execution is instant. Ensure Magisk/SuperSU is set to 'Always Allow' for Termux.
- **Non-Rooted Devices:** Enable Wireless Debugging in Developer Options and ensure ADB is connected locally (e.g., `adb connect 127.0.0.1:5555`).

## Security Details

CommandMesh is designed assuming the MQTT broker could be compromised:
- **Ed25519 Signatures:** Uses PyNaCl to verify that commands came from the holder of the Master Passphrase. The Master Passphrase never leaves the PWA.
- **Anti-Replay Windows:** Timestamps are embedded in the signed message. Messages older than 10 seconds (or from the future) are rejected.
- **Signature Caching:** Nodes remember recently seen signatures to block strict replay attacks within the 10-second window.
- **Payload Integrity:** The command action, target ID, and payload data are all included in the signature hash, preventing man-in-the-middle parameter tampering.
