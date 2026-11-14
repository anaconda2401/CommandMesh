"""OpenAI and agent compatible tool schemas for CommandMesh tools."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_devices",
            "description": (
                "List all discovered CommandMesh devices across the network and "
                "their online status and capabilities."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_status",
            "description": (
                "Get current status and capabilities of a specific CommandMesh device."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of target node (e.g. 'laptop', 'tv_node').",
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dpad",
            "description": (
                "Send directional D-pad input (up, down, left, right, center/ok) to a device."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": [
                            "up",
                            "down",
                            "left",
                            "right",
                            "center",
                            "ok",
                            "enter",
                        ],
                        "description": "Direction to press.",
                    },
                },
                "required": ["device_id", "direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": (
                "Send media playback or volume command (play_pause, vol_up, vol_down) to a device."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "vol_up", "vol_down"],
                        "description": "Media control action to execute.",
                    },
                },
                "required": ["device_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": (
                "Simulate a keyboard shortcut on a desktop PC (e.g. 'ctrl,c', 'alt,tab', 'enter')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target desktop PC.",
                    },
                    "key": {
                        "type": "string",
                        "description": "Comma-separated key combination (e.g. 'ctrl,c' or 'enter').",
                    },
                },
                "required": ["device_id", "key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text on the target device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text characters to type.",
                    },
                },
                "required": ["device_id", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a web URL in the default browser of the target device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                    "url": {
                        "type": "string",
                        "description": "Full URL starting with http:// or https://.",
                    },
                },
                "required": ["device_id", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "home",
            "description": "Return to the home screen or minimize all windows to show desktop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_device",
            "description": "Lock the screen on the target device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_youtube",
            "description": "Open YouTube in the browser or app on the target device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target device.",
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "Execute a whitelisted script located on a desktop PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Unique identifier of the target desktop PC.",
                    },
                    "script_name": {
                        "type": "string",
                        "description": "Exact whitelisted script filename (e.g. 'test.py', 'test_ping.bat').",
                    },
                },
                "required": ["device_id", "script_name"],
            },
        },
    },
]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return list of JSON schema tool definitions for LLMs."""
    return TOOL_SCHEMAS
