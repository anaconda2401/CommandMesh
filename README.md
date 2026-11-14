# CommandMesh

CommandMesh is a lightweight, multi-way, peer-to-peer encrypted device control mesh and LLM agent tool suite. It enables secure, bi-directional remote control between desktop computers (Windows, macOS, Linux), low-power devices (such as older Android TVs running Termux), static web applications (Progressive Web App), and Autonomous AI Agents.

The MQTT broker acts strictly as a **dumb TLS relay**—all commands and responses are encrypted end-to-end with **NaCl SecretBox** (`XSalsa20-Poly1305`), ensuring zero plaintext ever reaches the broker.

---

## Key Features

- **Peer-to-Peer Multi-Way Encryption:** Any node can command any other node. All messages and acknowledgments are encrypted symmetrically using **NaCl SecretBox** with keys derived via SHA-256 from a shared `MESH_PASSPHRASE`.
- **Zero Busy-Wait & Low-Power Optimized:** Built with event-driven `paho-mqtt` network loops (`loop_forever()`). Idle CPU usage is near **0.0%**, perfectly optimized for older Android TVs with limited RAM and CPU cores.
- **Progressive Web App (PWA):** Zero-build, 100% static HTML/JS web remote (`pwa/index.html`) that can be hosted on GitHub Pages or run locally. Features a touch D-Pad, media controls, live presence cards, and encrypted ACK toasts via Web Crypto and TweetNaCl.
- **LLM Agent Ready (`tool/`):** Exposes 11 structured function-calling tools (`list_devices`, `dpad`, `media_control`, `run_script`, etc.) for seamless integration with AI agents like Lapis, LangChain, or OpenAI/Anthropic harnesses.
- **Dual CLI Modes:** Run as a continuous background daemon (`python main.py run`) or dispatch one-shot encrypted commands directly from the terminal (`python main.py send <target> <action> [data]`).
- **Directory-as-Allowlist Scripts:** Desktop nodes execute custom local scripts (`.bat`, `.sh`, `.ps1`, `.py`) strictly confined inside `nodes/desktop/scripts/`, secured against path traversal attacks.
- **Android TV Integration:** Run inside Termux with automated wake locks, handling D-Pad navigation, media controls, and YouTube/URL deep links via native root (`su`) or local `adb`.

---

## System Architecture

```
                  +--------------------------------+
                  |       MQTT Broker Relay        |
                  |    (Dumb TLS Cloud Relay)      |
                  +--------------------------------+
                      /      |           |      \
                     /       |           |       \
                    v        v           v        v
        +-----------+  +-----------+  +-----+  +-------------+
        |  Desktop  |  |Android TV |  | PWA |  |  AI Agent   |
        |   Node    |  |  (Termux) |  | UI  |  | (e.g. Lapis)|
        +-----------+  +-----------+  +-----+  +-------------+
```

### MQTT Topic Hierarchy:
- `mesh/cmd/<node_id>` — Point-to-point encrypted commands to a specific node (`retain=False`).
- `mesh/cmd/all` — Broadcast encrypted commands received by all nodes (`retain=False`).
- `mesh/ack/<sender_node_id>` — Encrypted execution results returned to the commander (`retain=False`).
- `mesh/presence/<node_id>` — Online/offline status retained metadata with Last Will & Testament (`retain=True`).

---

## Repository Structure

```text
CommandMesh/
├── lib/                     # Core cryptographic and network primitives
│   ├── security.py          # SecretBox AEAD, SHA-256 key derivation, replay cache, CLI dispatcher
│   └── __init__.py          # Exported security API
├── nodes/                   # Device execution nodes
│   ├── desktop/             # Windows / macOS / Linux node (keyboard, media, scripts)
│   │   ├── node.py          # Desktop node runner with ctypes/pyautogui fallbacks
│   │   ├── scripts/         # Directory-as-Allowlist script repository
│   │   └── requirements.txt # Desktop node package requirements
│   └── termux/              # Android TV / Termux node (root/su, local ADB)
│       ├── node.py          # Termux node runner with wake locks and keyevents
│       └── requirements.txt # Termux lightweight package requirements
├── tool/                    # LLM Agent tool interface
│   ├── client.py            # MeshClient with presence discovery & SecretBox execution
│   ├── tools.py             # High-level CommandMeshTools API
│   ├── schemas.py           # OpenAI/Anthropic/Gemini function schemas
│   └── __init__.py          # Direct module exports
├── pwa/                     # Progressive Web App remote control
│   └── index.html           # 100% static, zero-build web remote (TweetNaCl + Web Crypto)
├── docs/                    # In-depth architectural & setup documentation
│   ├── ARCHITECTURE.md      # Peer-to-peer topology and low-power constraints
│   ├── SECURITY.md          # Cryptography, nonce handling, bounded replay cache
│   ├── PROTOCOL.md          # MQTT topic specs, JSON schemas, sequence diagrams
│   ├── SETUP_DESKTOP.md     # Setup on Windows, macOS, and Linux
│   ├── SETUP_ANDROID_TV.md  # Setup on Android TV / Termux with wake lock
│   ├── PWA_GUIDE.md         # PWA installation, WebSockets MQTT, Web Crypto
│   └── AGENT_INTEGRATION.md # Autonomous LLM agent tool integration
├── tests/                   # Pytest test suite (PyNaCl, cross-language TweetNaCl, tools)
│   ├── test_security.py     # Crypto, replay cache, ±30s window, JS cross-compat
│   └── test_tool.py         # Tool schemas, validation, desktop scripts allowlist
├── main.py                  # Unified CLI entry point (send / run)
├── pyproject.toml           # Package configuration & editable install metadata
├── requirements.txt         # Core runtime dependencies
├── requirements-desktop.txt # Optional desktop automation dependencies
├── requirements-dev.txt     # Test and linter dependencies
├── .env.example             # Configuration template
└── .gitignore               # Clean git exclusions for secrets, caches, and scripts
```

---

## Quickstart

### 1. Installation

Clone the repository and set up a Python virtual environment:

```bash
git clone https://github.com/anaconda2401/CommandMesh.git
cd CommandMesh

python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux / macOS / Termux:
source .venv/bin/activate
```

Install the dependencies:

```bash
# Core dependencies (nodes, tools, CLI):
pip install -r requirements.txt

# Or for desktop automation with pyautogui:
pip install -r requirements-desktop.txt

# Or editable install with all dev/desktop extras:
pip install -e ".[all]"
```

### 2. Configuration (`.env`)

Copy the template configuration:
```bash
cp .env.example .env
```

Edit `.env` with your MQTT broker credentials and a strong master passphrase:

```ini
MQTT_BROKER=your-cluster.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password

# Shared E2E Passphrase across all nodes, PWA, and AI agents
MESH_PASSPHRASE=your_secret_passphrase_here

# Local Node Identity
NODE_ID=laptop
NODE_NAME=Work Laptop
DEVICE_TYPE=pc

# Logging level (WARNING recommended for background daemons)
LOG_LEVEL=WARNING
```

### 3. Start the Node (Daemon Mode)

```bash
python main.py run
# or simply:
python main.py
```

The node connects over TLS, sets up an MQTT Last Will & Testament (LWT) for presence, and waits for peer commands.

---

## CLI Send Mode (One-Shot Commands)

Command any device directly from your terminal:

```bash
# Syntax: python main.py send <target_id> <action> [data]

# Send D-pad navigation to living room TV
python main.py send tv dpad_center

# Increase volume on TV
python main.py send tv vol_up

# Open a URL on your desktop PC
python main.py send laptop open_url https://github.com

# Lock your desktop PC
python main.py send laptop lock_pc

# Execute an allowlisted script on your desktop PC
python main.py send laptop run_script clean_temp.bat
```

---

## Progressive Web App (PWA)

Open `pwa/index.html` directly in your browser, or host it on GitHub Pages.

1. Enter your MQTT Broker details and **Master Passphrase**.
2. Click **Connect**.
3. View live online/offline cards for all discovered mesh nodes.
4. Use the touch D-Pad, Volume controls, Text sender, or Script launcher to control any device.
5. Watch encrypted execution acknowledgments appear as interactive toast notifications.

---

## AI Agent Integration

CommandMesh provides native tools for AI agents (such as Lapis, LangChain, or custom LLM frameworks).

### Link to your agent project:
```bash
cd /path/to/CommandMesh
pip install -e .
```

### Use in Python:
```python
from tool import CommandMeshTools

with CommandMeshTools() as tools:
    # 1. Discover devices
    devices = tools.list_devices()
    print(devices)

    # 2. Control devices
    tools.dpad("tv", "center")
    tools.media_control("tv", "vol_up")
    tools.open_url("laptop", "https://news.ycombinator.com")
```

For full OpenAI/Gemini JSON schemas, use `tool.get_tool_schemas()`.

---

## Testing & Quality

Run the test suite and code quality checks:

```bash
# Run all unit tests (including TweetNaCl/PyNaCl cross-compatibility)
pytest

# Code linter & formatting check
ruff check .
```

---

## Detailed Documentation

For in-depth guides, see the [docs/](docs/README.md) directory:

- [System Architecture](docs/ARCHITECTURE.md)
- [Security Specification](docs/SECURITY.md)
- [MQTT Wire Protocol & Topics](docs/PROTOCOL.md)
- [Desktop Node Setup Guide](docs/SETUP_DESKTOP.md)
- [Android TV & Termux Setup Guide](docs/SETUP_ANDROID_TV.md)
- [Progressive Web App (PWA) Guide](docs/PWA_GUIDE.md)
- [AI Agent Tool Integration](docs/AGENT_INTEGRATION.md)
