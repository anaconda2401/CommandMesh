# Android TV & Termux Setup Guide

CommandMesh runs seamlessly inside [Termux](https://termux.dev/) on Android TV boxes, streaming sticks (e.g. Chromecast with Google TV, Fire TV), and Android smartphones.

It provides hardware-level remote control (D-Pad navigation, media controls, volume, launching YouTube, and deep-link URLs) with near-zero battery and CPU consumption.

---

## 1. Prerequisites & Termux Installation

1. Install **Termux** (prefer F-Droid or GitHub Releases, never the outdated Google Play Store build).
2. On Android TV devices without a touchscreen, use an air-mouse, ADB over Wi-Fi, or an app like *scrcpy* to assist with initial setup.

---

## 2. Package Installation in Termux

Open Termux and execute:

```bash
# Update package repositories
pkg update -y && pkg upgrade -y

# Install Python and build dependencies for PyNaCl
pkg install -y python git clang libffi openssl

# Clone the CommandMesh repository
git clone https://github.com/anaconda2401/CommandMesh.git
cd CommandMesh

# Install required Python packages
pip install paho-mqtt pynacl python-dotenv
```

---

## 3. Execution Modes: Root (`su`) vs. Local ADB

The Termux node supports two execution strategies depending on whether your Android device is rooted:

### Mode A: Rooted Android TV (`su`) — Recommended
If your TV box has Magisk, SuperSU, or LineageOS root:
1. Open Termux and run `su`.
2. Grant "Always Allow" root permissions to Termux.
3. CommandMesh will automatically detect `su` and execute keyevents and intents via native root shell. No ADB configuration is required.

### Mode B: Non-Rooted Android TV (Local ADB Loopback)
If the device is not rooted:
1. Go to **Settings $\rightarrow$ Device Preferences $\rightarrow$ Developer Options**.
2. Enable **USB Debugging** and **Wireless Debugging** (or Network ADB).
3. In Termux, install ADB:
   ```bash
   pkg install -y android-tools
   ```
4. Connect ADB to localhost:
   ```bash
   adb connect 127.0.0.1:5555
   ```
   *(Accept the "Always allow from this computer" prompt on your TV screen).*

---

## 4. Configuration

Create your `.env` file inside `CommandMesh/`:

```ini
# MQTT Broker Settings
MQTT_BROKER=your-cluster.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=your_mqtt_username
MQTT_PASSWORD=your_mqtt_password

# E2E Shared Passphrase (must match your Desktop and PWA)
MESH_PASSPHRASE=your_secret_passphrase_here

# TV Node Identity
NODE_ID=living_room_tv
NODE_NAME=Living Room TV
DEVICE_TYPE=tv

# ADB Target (used only if not rooted)
ADB_TARGET=127.0.0.1:5555

# Minimal output to protect old TV terminal buffers
LOG_LEVEL=WARNING
```

---

## 5. Critical Android TV Optimizations

### 1. Acquire Termux Wake Lock
Android TV power management aggressively suspends background apps when the screen is off or in standby. To prevent the MQTT client from dropping:

```bash
termux-wake-lock
```
This acquires a low-power CPU wake lock so CommandMesh can respond instantly to power-on and wake commands.

### 2. Zero-CPU Idle Architecture
Older TVs (e.g. quad-core Cortex-A53 chips) quickly heat up or lag if background tasks spin.
- CommandMesh uses `client.loop_forever()`, ensuring the process sleeps natively until an MQTT packet arrives over the socket.
- Idle CPU usage remains under **0.1%**.

### 3. Preventing Terminal Buffer Slowdowns
Old Android Termux terminals experience significant performance degradation when stdout output accumulates in memory.
- `LOG_LEVEL=WARNING` suppresses routine keepalives, ping logs, and payload dumps.
- Standard logs are concise single-line entries produced only on startup, reconnection, or fatal errors.

---

## 6. Running the Node

Run the node daemon:

```bash
python main.py run
```

Output:
```text
========================================
 MODE: [*] TERMUX EXECUTION LAYER
 NODE: living_room_tv (Root Mode: True)
========================================
[MQTT] [*] Node 'living_room_tv' connected successfully.
```

---

## 7. Autostart on TV Boot (Termux:Boot)

To ensure CommandMesh starts automatically when the TV turns on:
1. Install the **Termux:Boot** add-on app.
2. Launch the Termux:Boot app once to register Android boot permissions.
3. Create the startup directory and script inside Termux:
   ```bash
   mkdir -p ~/.termux/boot
   cat << 'EOF' > ~/.termux/boot/start-commandmesh.sh
   #!/data/data/com.termux/files/usr/bin/bash
   termux-wake-lock
   cd ~/CommandMesh
   python main.py run > /dev/null 2>&1 &
   EOF
   chmod +x ~/.termux/boot/start-commandmesh.sh
   ```
4. Now, every time the Android TV boots or restarts, CommandMesh launches in the background automatically.
