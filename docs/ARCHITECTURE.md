# CommandMesh Architecture

CommandMesh is a lightweight, multi-way, peer-to-peer encrypted command execution mesh. It enables secure, bi-directional remote control between desktop computers (Windows, macOS, Linux), low-power devices (such as older Android TVs running Termux), static web applications (Progressive Web App), and Autonomous AI Agents.

---

## High-Level Topology

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

### The "Dumb Relay" Principle

1. **Zero Knowledge on the Broker:**
   The MQTT broker (such as HiveMQ Cloud, Mosquitto, EMQX, or AWS IoT) is treated strictly as an untrusted message pipe. It never sees plaintext commands, parameters, device names, or results.
2. **End-to-End Encryption (E2EE):**
   All payloads are symmetrically encrypted using **NaCl SecretBox** (`XSalsa20-Poly1305`) before leaving the sending device and are decrypted only inside the recipient's memory.
3. **No Central Server or Database:**
   There is no proprietary backend server, no user management database, and no proprietary cloud dependency. The mesh functions anywhere standard MQTT over TLS or WebSockets is accessible.

---

## Mesh Members and Roles

Any device in possession of the shared `MESH_PASSPHRASE` can act as a commander, a receiver, or both:

| Member Type | Implementation | Primary Role | Actions Supported |
|-------------|----------------|--------------|-------------------|
| **Desktop Node** | Python (`nodes/desktop/node.py`) | Execution Layer & CLI Commander | D-Pad navigation, media keys, text typing, keystrokes (`pyautogui` / Windows `ctypes`), URL launch, PC lock, Directory-as-Allowlist scripts (`.bat`, `.sh`, `.ps1`, `.py`). |
| **Android TV / Mobile Node** | Python in Termux (`nodes/termux/node.py`) | Execution Layer & TV Controller | D-Pad navigation, media controls, Android intents (YouTube, Browser), text input via `input text`, wake locks, root (`su`) or local `adb` execution. |
| **PWA Web Controller** | Static HTML/JS (`pwa/index.html`) | Mobile/Desktop Remote UI | Responsive touch D-Pad, volume controls, text dispatcher, script launcher, live device presence cards, ACK toasts. |
| **AI Agent Tool** | Python (`tool/client.py`, `tool/tools.py`) | Autonomous Automation | Exposes 11 structured function-calling tools (`list_devices`, `dpad`, `media_control`, etc.) for LLM agents. |

---

## Multi-Way Interaction Model

Unlike older client-server or master-worker remote architectures, CommandMesh is completely multi-way:

```
[Agent] ----(mesh/cmd/tv)-----> [Android TV Node]
   ^                                   |
   +----------(mesh/ack/agent)---------+

[PWA]  ----(mesh/cmd/laptop)----> [Desktop Node]
   ^                                   |
   +----------(mesh/ack/pwa)-----------+

[Desktop CLI] -(mesh/cmd/tv)----> [Android TV Node]
   ^                                   |
   +-------(mesh/ack/desktop_cli)------+
```

1. **Direct Commands:**
   Sent to `mesh/cmd/<target_node_id>` with an ephemeral `id` and sender `from`.
2. **Direct Acknowledgments (ACKs):**
   The receiving node executes the action and encrypts a canonical response back directly to `mesh/ack/<sender_node_id>` with `in_reply_to: <id>`.
3. **Broadcast Commands:**
   Sent to `mesh/cmd/all` when every online node should act simultaneously (e.g. panic lock or mute).
4. **Presence Management:**
   Every node registers a retained MQTT Last Will and Testament (LWT) on `mesh/presence/<node_id>` with `"status": "offline"`, and publishes `"status": "online"` immediately upon connecting.

---

## Low-CPU & Low-RAM Design Philosophy

Older Android TVs running Termux (such as quad-core Cortex-A53 chips with 1GB–1.5GB of RAM) struggle under heavy Python workloads, busy-wait loops, or verbose stdout spam. CommandMesh is specifically tuned for these hardware constraints:

1. **Zero Busy-Wait (`loop_forever`):**
   Nodes use `paho-mqtt`'s native non-busy socket polling. When idle, CPU consumption is measured at `0.0%`.
2. **Minimal Logging:**
   Log outputs default to `LOG_LEVEL=WARNING`. Routine heartbeats or encrypted payloads are never dumped to stdout, preventing terminal buffer bottlenecks.
3. **Bounded Memory Caches:**
   Replay deduplication uses a fixed `deque(maxlen=128)` coupled with an indexed `set`, guaranteeing constant memory overhead even after months of continuous uptime.
4. **Lazy Module Loading:**
   Bulky GUI libraries (e.g., `pyautogui`) are only imported when a desktop action explicitly demands them and are completely omitted on Termux nodes.
