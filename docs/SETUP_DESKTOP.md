# Desktop Node Setup Guide

The CommandMesh Desktop Node runs on **Windows**, **macOS**, and **Linux**. It acts as a secure execution layer capable of handling mouse/keyboard simulation, media controls, browser automation, and allowlisted local script execution.

---

## 1. Prerequisites

- Python 3.10 or later
- An active MQTT broker (e.g. HiveMQ Cloud, Mosquitto, EMQX) with TLS support on port 8883.

---

## 2. Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/anaconda2401/CommandMesh.git
   cd CommandMesh
   ```

2. **Create and activate a virtual environment:**
   - **Windows:**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install paho-mqtt pynacl python-dotenv
   ```
   *(Optional)* For advanced desktop keyboard/mouse automation:
   ```bash
   pip install pyautogui
   ```
   > [!NOTE]
   > On Windows, if `pyautogui` is not installed, CommandMesh automatically falls back to native Windows `ctypes.windll.user32.keybd_event` calls for standard media keys and typing.

---

## 3. Configuration

Copy the template `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your broker details and shared passphrase:

```ini
# MQTT Broker Settings
MQTT_BROKER=your-cluster.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=your_mqtt_username
MQTT_PASSWORD=your_mqtt_password

# E2E Shared Passphrase (identical across all nodes, PWA, and agents)
MESH_PASSPHRASE=your_secret_passphrase_here

# Local Node Identity
NODE_ID=laptop
NODE_NAME=Work Laptop
DEVICE_TYPE=pc

# Logging Level (WARNING recommended for background daemon)
LOG_LEVEL=WARNING
```

---

## 4. Running the Node

### A. Daemon Mode (Continuous Background Listener)
To start the node listening for incoming peer commands:

```bash
python main.py run
# or simply:
python main.py
```

Expected startup output:
```text
========================================
 MODE: [*] DESKTOP EXECUTION LAYER
 NODE: laptop (Windows)
========================================
[MQTT] [*] Node 'laptop' (Windows) connected successfully.
```

### B. One-Shot CLI Dispatch Mode
Any Desktop node can also act as a CLI commander to send encrypted actions to any other peer without opening a browser or writing code:

```bash
# Format: python main.py send <target_id> <action> [data]

# Turn up volume on TV
python main.py send tv vol_up

# Navigate D-pad center on TV
python main.py send tv dpad_center

# Open YouTube on TV
python main.py send tv open_youtube

# Lock another PC
python main.py send desktop_pc lock_pc

# Open a website on another PC
python main.py send laptop open_url https://github.com
```

---

## 5. Directory-as-Allowlist Scripts

Desktop nodes can safely execute local scripts without exposing remote arbitrary shell command vulnerabilities.

### How to Add Scripts:
1. Navigate to `nodes/desktop/scripts/`.
2. Drop your script into the folder:
   - Windows: `.bat`, `.cmd`, `.ps1`, `.py`
   - Linux / macOS: `.sh`, `.py`
3. Trigger the script remotely by specifying its filename:
   ```bash
   python main.py send laptop run_script clean_temp.bat
   ```

### Security Enforcement:
- Path traversal (`../`, absolute paths) is strictly blocked using `Path.resolve().is_relative_to()`.
- Subprocesses execute with `shell=False`, preventing command injection.

---

## 6. Autostart on Boot

### Windows (Task Scheduler or Startup Folder)
1. Press `Win + R`, type `shell:startup`, and press Enter.
2. Create a shortcut or batch file (e.g., `start_mesh.bat`):
   ```cmd
   @echo off
   cd /d "D:\projects\CommandMesh"
   call .venv\Scripts\activate.bat
   start /min python main.py run
   ```

### Linux (systemd User Service)
Create `~/.config/systemd/user/commandmesh.service`:
```ini
[Unit]
Description=CommandMesh Desktop Node
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/user/CommandMesh
ExecStart=/home/user/CommandMesh/.venv/bin/python main.py run
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```
Enable and start the service:
```bash
systemctl --user enable --now commandmesh
```
