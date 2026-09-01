# CommandMesh

CommandMesh is a secure, private device network for executing remote commands across multiple platforms (Desktop & Android) over MQTT.

The MQTT broker acts as a dumb relay. All commands are cryptographically signed by a client-side Progressive Web App (PWA) and verified locally on the target device using Ed25519 cryptography.

## Features

- **Cross-Platform Nodes:** Run nodes on Windows, macOS, Linux, or Android (via Termux).
- **Progressive Web App (PWA):** Control your entire network from a sleek, mobile-friendly web interface. Includes a D-Pad, media controls, and custom text/script inputs.
- **Cryptographic Security:** Every command is signed using your Master Passphrase. Payload tampering and spoofing are actively prevented via Ed25519 signature verification.
- **Custom Scripts:** Desktop nodes can securely execute whitelisted local scripts (`.bat`, `.sh`, `.ps1`, `.py`).
- **Android Integration:** The Termux node uses ADB or Root (`su`) to control Android TVs or phones (simulate keypresses, open URLs, etc.).

## Architecture

1. **MQTT Broker:** The central relay for all messages (e.g., a free HiveMQ Cloud cluster).
2. **Nodes:** Python clients running on your target devices.
   - **Desktop Node:** Uses `pyautogui` and `subprocess` to control PCs (type text, media controls, lock screen, execute whitelisted scripts).
   - **Termux Node:** Uses `adb` or root (`su`) to control Android devices (launch intents, input keyevents like D-Pad/Volume).
3. **PWA Controller:** A standalone HTML/JS web app (`pwa/index.html`) that generates cryptographic signatures locally using TweetNaCl and sends commands to the MQTT broker.

## Setup

### 1. Configure the node

Clone the repository and create your local configuration:

```bash
git clone https://github.com/anaconda2401/CommandMesh.git
cd CommandMesh
cp .env.example .env
```

Open `.env` and fill in your values:

```
MQTT_BROKER=your-cluster.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
MESH_PUBLIC_KEYS=<hex key from PWA>
NODE_ID=laptop
NODE_NAME=My Laptop
```

### 2. Get your Public Key from the PWA

1. Open `pwa/index.html` in your browser.
2. Enter your MQTT Broker details (URL, username, password).
3. Enter a strong **Master Passphrase**.
4. Click **Generate Node Public Key** and copy the generated hex key.
5. Paste it into `MESH_PUBLIC_KEYS` in your `.env`.

### 3. Start the node

```bash
python main.py
```

On first run, dependencies are installed automatically. The node then connects directly to your configured broker — no browser setup required.

### 4. Desktop Node Scripts (Optional)

Desktop nodes can execute custom scripts remotely. For security, only whitelisted scripts can be executed.

1. Place your scripts inside `nodes/desktop/scripts/`.
2. Add the exact script filename to the `ALLOWED_SCRIPTS` set in `config/allowed_scripts.py`.

### 5. Android Node Setup

On Android, CommandMesh runs inside Termux.

- **Rooted Devices:** Execution is instant. Ensure Magisk/SuperSU is set to 'Always Allow' for Termux.
- **Non-Rooted Devices:** Enable Wireless Debugging in Developer Options and ensure ADB is connected locally (e.g., `adb connect 127.0.0.1:5555`). Set `ADB_TARGET` in `.env` accordingly.

## Security Model

CommandMesh is designed assuming the MQTT broker could be compromised:

```
Transport
   ↓
TLS + MQTT authentication
   ↓
Ed25519 signature verification (PyNaCl)
   ↓
Role authorization
   ↓
Command execution
```

- **Ed25519 Signatures:** Commands are signed in the PWA using the Master Passphrase. The passphrase never leaves the browser.
- **Payload Integrity:** The action, target device ID, payload data, timestamp, and message ID are all included in the signed string, preventing parameter tampering.
- **TLS:** All broker connections use TLS (port 8883 by default).
