# AI Agent Tool Integration Guide

CommandMesh includes a native, ready-to-use LLM tool interface located in `tool/`. It exposes 11 structured function-calling tools that allow AI agents (such as Lapis, LangChain, AutoGen, or custom OpenAI/Anthropic/Gemini agents) to autonomously control real-world devices across the mesh.

---

## 1. Connecting CommandMesh to an Agent Harness

CommandMesh can be linked directly to your agent environment via an editable pip installation without copying files or duplicating core logic:

```bash
# In your agent's virtual environment:
cd /path/to/CommandMesh
pip install -e .
```

---

## 2. Core Tool Definitions

CommandMesh exposes **11 granular tools** with parameter validation and device discovery awareness:

| Tool Function | Name in Schema | Parameters | Description |
|---------------|----------------|------------|-------------|
| `list_devices()` | `mesh_list_devices` | *None* | Discovers all online mesh devices and their capabilities. |
| `get_device_status(device_id)` | `mesh_device_status` | `device_id` (`str`) | Fetches detailed status, OS type, and online state of a specific device. |
| `dpad(device_id, direction)` | `mesh_dpad` | `device_id` (`str`), `direction` (`up\|down\|left\|right\|center\|ok`) | Sends directional D-Pad inputs to a target device. |
| `media_control(device_id, action)` | `mesh_media_control` | `device_id` (`str`), `action` (`play_pause\|vol_up\|vol_down`) | Controls media playback and volume. |
| `press_key(device_id, key)` | `mesh_press_key` | `device_id` (`str`), `key` (`str`) | *(Desktop only)* Simulates keyboard hotkeys (e.g. `ctrl,c`, `enter`, `f11`). |
| `type_text(device_id, text)` | `mesh_type_text` | `device_id` (`str`), `text` (`str`) | Types a string into active inputs or search boxes. |
| `home(device_id)` | `mesh_home` | `device_id` (`str`) | Returns to the home screen on Android TV or minimizes windows on Desktop. |
| `lock_device(device_id)` | `mesh_lock_device` | `device_id` (`str`) | Locks the PC screen or turns off TV display. |
| `open_youtube(device_id)` | `mesh_open_youtube` | `device_id` (`str`) | Launches YouTube in the browser (Desktop) or YouTube app (Android TV). |
| `open_url(device_id, url)` | `mesh_open_url` | `device_id` (`str`), `url` (`str`) | Opens an HTTP/HTTPS URL in the default browser. |
| `run_script(device_id, script_name)` | `mesh_run_script` | `device_id` (`str`), `script_name` (`str`) | *(Desktop only)* Safely executes an allowlisted script from `scripts/`. |

---

## 3. Schema Generation

CommandMesh exports standard JSON schemas compatible with OpenAI Function Calling, Gemini Function Declarations, and Anthropic Tools:

```python
from tool.schemas import get_tool_schemas

# Returns a list of 11 function schemas
schemas = get_tool_schemas()
```

Sample generated schema snippet:
```json
{
  "type": "function",
  "function": {
    "name": "mesh_dpad",
    "description": "Send D-pad navigation input (up, down, left, right, center/ok) to a target CommandMesh device.",
    "parameters": {
      "type": "object",
      "properties": {
        "device_id": {
          "type": "string",
          "description": "Unique identifier of the target device."
        },
        "direction": {
          "type": "string",
          "enum": ["up", "down", "left", "right", "center", "ok"],
          "description": "Directional input or center select."
        }
      },
      "required": ["device_id", "direction"]
    }
  }
}
```

---

## 4. Agent Tool Provider Example

Here is how an agent integrates `CommandMeshTools` within its execution loop:

```python
from tool.tools import CommandMeshTools

# 1. Initialize tools using credentials from .env
mesh_tools = CommandMeshTools()

# 2. Connect to the mesh
mesh_tools.connect()

# 3. Example agent execution flow:
# Query: "Check if my TV is online and increase the volume"

# Step A: Discover devices
devices_response = mesh_tools.list_devices()
print(devices_response)
# Output: {"success": True, "devices": [{"id": "tv", "status": "online", "type": "tv"}]}

# Step B: Adjust volume
volume_response = mesh_tools.media_control(device_id="tv", action="vol_up")
print(volume_response)
# Output: {"success": True, "device": "tv", "action": "vol_up", "message": "Volume Increased"}

# 4. Graceful shutdown
mesh_tools.disconnect()
```

Alternatively, use Python's `with` context manager for scoped sessions:

```python
with CommandMeshTools() as tools:
    tools.dpad("tv", "center")
```

---

## 5. Security Safeguards for Agents

1. **Parameter Pre-Validation:**
   `tool/client.py` strictly validates arguments (e.g. blocking script path traversal `../` and checking desktop-only constraints) before publishing any packets.
2. **Offline Device Protection:**
   Commands to offline devices are rejected immediately without publishing unnecessary broker traffic.
3. **Deterministic Error Codes:**
   Tool execution returns consistent machine-readable error codes (`device_offline`, `device_not_found`, `invalid_command`, `device_timeout`) allowing the LLM to explain failures accurately to the user.
