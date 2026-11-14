# CommandMesh Documentation Index

Welcome to the technical documentation for **CommandMesh** — a lightweight, peer-to-peer encrypted IoT and device control mesh for Desktops, Android TVs, Web PWAs, and AI Agents.

---

## Documentation Guides

1. **[System Architecture](ARCHITECTURE.md)**
   - High-level topology and peer-to-peer design.
   - The "Dumb Broker" relay model.
   - Multi-way communication patterns (commander $\leftrightarrow$ target).
   - Low-power and low-RAM design principles.

2. **[Security Specification](SECURITY.md)**
   - End-to-end symmetric encryption via NaCl SecretBox (`XSalsa20-Poly1305`).
   - SHA-256 key derivation from `MESH_PASSPHRASE`.
   - 24-byte random nonces and wire format.
   - $\pm 30$ second timestamp freshness window.
   - Bounded replay attack cache (`deque(maxlen=128)` + `set`).
   - Desktop Directory-as-Allowlist script execution security boundary.

3. **[Wire Protocol & Topics](PROTOCOL.md)**
   - Topic hierarchy (`mesh/cmd/*`, `mesh/ack/*`, `mesh/presence/*`).
   - Canonical JSON schemas for commands, acknowledgments, and presence.
   - Retained Last Will & Testament (LWT) lifecycle.
   - Complete message sequence diagrams.

4. **[Desktop Node Setup Guide](SETUP_DESKTOP.md)**
   - Setup on Windows, macOS, and Linux.
   - Virtual environments, dependencies, and native Windows `ctypes` fallback.
   - Daemon listener mode vs. one-shot CLI commands.
   - Directory-as-Allowlist custom script configuration.
   - System boot autostart (Task Scheduler / systemd).

5. **[Android TV & Termux Setup Guide](SETUP_ANDROID_TV.md)**
   - Installing and running CommandMesh on Android TV and mobile devices via Termux.
   - Termux wake locks (`termux-wake-lock`) to survive TV sleep/standby.
   - Execution modes: Native root (`su`) vs. local ADB loopback.
   - Zero-CPU idle optimizations (`loop_forever`) and terminal buffer management.
   - Automatic boot startup via Termux:Boot.

6. **[Progressive Web App (PWA) Guide](PWA_GUIDE.md)**
   - Static, zero-build web app architecture (`pwa/index.html`).
   - Browser cryptography with TweetNaCl and Web Crypto API.
   - WebSockets MQTT client (WSS).
   - Real-time device presence cards and encrypted ACK toast notifications.

7. **[AI Agent Tool Integration](AGENT_INTEGRATION.md)**
   - Integrating CommandMesh with autonomous LLM agents (Lapis, LangChain, etc.).
   - Tool Suite overview (`tool/client.py`, `tool/tools.py`).
   - The 11 core function-calling tools and schema generation (`tool/schemas.py`).
   - Parameter pre-validation and safety boundaries.
