"""Agent-ready tool functions and CommandMeshTools class."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Self

from .client import MeshClient
from .schemas import get_tool_schemas

logger = logging.getLogger(__name__)

_VALID_DPAD = frozenset({"up", "down", "left", "right", "center"})
_DPAD_ALIASES = {"ok": "center", "enter": "center"}
_VALID_MEDIA = frozenset({"play_pause", "vol_up", "vol_down"})


class CommandMeshTools:
    """High-level tool provider for AI agents to control CommandMesh devices."""

    def __init__(
        self,
        client: MeshClient | None = None,
        broker: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        passphrase: str | None = None,
        private_key: str | None = None,
        role: str | None = None,
        ack_timeout: float = 5.0,
    ) -> None:
        self.client = client or MeshClient(
            broker=broker,
            port=port,
            username=username,
            password=password,
            passphrase=passphrase or private_key,
            role=role,
            ack_timeout=ack_timeout,
        )

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the mesh."""
        return self.client.connect(timeout=timeout)

    def disconnect(self) -> None:
        """Disconnect from the mesh."""
        self.client.disconnect()

    def __enter__(self) -> Self:
        """Context manager support."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Context manager cleanup."""
        self.disconnect()

    # ── Tool Definitions ──────────────────────────────────────────────────────

    def list_devices(self) -> dict[str, Any]:
        """List all discovered CommandMesh devices and their status."""
        devices = self.client.list_devices()
        return {"success": True, "devices": devices}

    def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Get status and capabilities of a specific CommandMesh device."""
        device = self.client.get_device(device_id)
        if device is None:
            return {
                "success": False,
                "device": device_id,
                "error": "device_not_found",
                "message": f"Device '{device_id}' was not found in discovery cache.",
            }
        return {"success": True, "device": device}

    def dpad(self, device_id: str, direction: str) -> dict[str, Any]:
        """Send D-pad input (up, down, left, right, center/ok) to target device."""
        direction_clean = direction.strip().lower()
        direction_norm = _DPAD_ALIASES.get(direction_clean, direction_clean)
        if direction_norm not in _VALID_DPAD:
            return {
                "success": False,
                "device": device_id,
                "action": f"dpad_{direction}",
                "error": "invalid_parameter",
                "message": (
                    f"Invalid D-pad direction '{direction}'. "
                    f"Must be one of: {sorted(_VALID_DPAD)}"
                ),
            }
        return self.client.execute_command(
            device_id=device_id,
            action=f"dpad_{direction_norm}",
            data=None,
        )

    def media_control(self, device_id: str, action: str) -> dict[str, Any]:
        """Send media playback or volume control command (play_pause, vol_up, vol_down)."""
        action_clean = action.strip().lower()
        if action_clean not in _VALID_MEDIA:
            return {
                "success": False,
                "device": device_id,
                "action": action,
                "error": "invalid_parameter",
                "message": (
                    f"Invalid media action '{action}'. "
                    f"Must be one of: {sorted(_VALID_MEDIA)}"
                ),
            }
        return self.client.execute_command(
            device_id=device_id,
            action=action_clean,
            data=None,
        )

    def press_key(self, device_id: str, key: str) -> dict[str, Any]:
        """Simulate a keyboard shortcut on a desktop PC (e.g. 'ctrl,c', 'alt,tab')."""
        key_clean = key.strip()
        if not key_clean:
            return {
                "success": False,
                "device": device_id,
                "action": "press_keys",
                "error": "invalid_parameter",
                "message": "Key parameter cannot be empty.",
            }
        return self.client.execute_command(
            device_id=device_id,
            action="press_keys",
            data=key_clean,
            desktop_only=True,
        )

    def type_text(self, device_id: str, text: str) -> dict[str, Any]:
        """Type arbitrary text characters on the target device."""
        if text is None:
            return {
                "success": False,
                "device": device_id,
                "action": "type_text",
                "error": "invalid_parameter",
                "message": "Text parameter cannot be null.",
            }
        return self.client.execute_command(
            device_id=device_id,
            action="type_text",
            data=text,
        )

    def open_url(self, device_id: str, url: str) -> dict[str, Any]:
        """Open a web URL in the default browser of the target device."""
        url_clean = url.strip()
        if not url_clean.startswith(("http://", "https://")):
            return {
                "success": False,
                "device": device_id,
                "action": "open_url",
                "error": "invalid_parameter",
                "message": "URL must begin with 'http://' or 'https://'.",
            }
        return self.client.execute_command(
            device_id=device_id,
            action="open_url",
            data=url_clean,
        )

    def home(self, device_id: str) -> dict[str, Any]:
        """Return to the home screen or minimize all windows to show desktop."""
        return self.client.execute_command(
            device_id=device_id,
            action="home",
            data=None,
        )

    def lock_device(self, device_id: str) -> dict[str, Any]:
        """Lock the target device screen."""
        return self.client.execute_command(
            device_id=device_id,
            action="lock_pc",
            data=None,
        )

    def open_youtube(self, device_id: str) -> dict[str, Any]:
        """Open YouTube on the target device."""
        return self.client.execute_command(
            device_id=device_id,
            action="open_youtube",
            data=None,
        )

    def run_script(self, device_id: str, script_name: str) -> dict[str, Any]:
        """Execute a whitelisted script located on a desktop PC node."""
        return self.client.execute_command(
            device_id=device_id,
            action="run_script",
            data=script_name.strip(),
            desktop_only=True,
        )

    def get_tools(self) -> list[Callable[..., Any]]:
        """Return list of bound callable tool functions for LLM frameworks."""
        return [
            self.list_devices,
            self.get_device_status,
            self.dpad,
            self.media_control,
            self.press_key,
            self.type_text,
            self.open_url,
            self.home,
            self.lock_device,
            self.open_youtube,
            self.run_script,
        ]

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI/Anthropic function calling schemas."""
        return get_tool_schemas()


# ── Global Default Instance & Convenience Functions ──────────────────────────

_default_instance: CommandMeshTools | None = None


def get_default_tools() -> CommandMeshTools:
    """Return or create singleton CommandMeshTools instance."""
    global _default_instance
    if _default_instance is None:
        _default_instance = CommandMeshTools()
    return _default_instance


def list_devices() -> dict[str, Any]:
    """List all discovered CommandMesh devices across the network."""
    return get_default_tools().list_devices()


def get_device_status(device_id: str) -> dict[str, Any]:
    """Get status and capabilities of a specific CommandMesh device."""
    return get_default_tools().get_device_status(device_id=device_id)


def dpad(device_id: str, direction: str) -> dict[str, Any]:
    """Send D-pad input (up, down, left, right, center/ok) to a device."""
    return get_default_tools().dpad(device_id=device_id, direction=direction)


def media_control(device_id: str, action: str) -> dict[str, Any]:
    """Send media playback or volume command (play_pause, vol_up, vol_down) to a device."""
    return get_default_tools().media_control(device_id=device_id, action=action)


def press_key(device_id: str, key: str) -> dict[str, Any]:
    """Simulate a keyboard shortcut on a desktop PC (e.g. 'ctrl,c', 'alt,tab')."""
    return get_default_tools().press_key(device_id=device_id, key=key)


def type_text(device_id: str, text: str) -> dict[str, Any]:
    """Type arbitrary text characters on the target device."""
    return get_default_tools().type_text(device_id=device_id, text=text)


def open_url(device_id: str, url: str) -> dict[str, Any]:
    """Open a web URL in the default browser of the target device."""
    return get_default_tools().open_url(device_id=device_id, url=url)


def home(device_id: str) -> dict[str, Any]:
    """Return to the home screen or minimize all windows to show desktop."""
    return get_default_tools().home(device_id=device_id)


def lock_device(device_id: str) -> dict[str, Any]:
    """Lock the target device screen."""
    return get_default_tools().lock_device(device_id=device_id)


def open_youtube(device_id: str) -> dict[str, Any]:
    """Open YouTube on the target device."""
    return get_default_tools().open_youtube(device_id=device_id)


def run_script(device_id: str, script_name: str) -> dict[str, Any]:
    """Execute a whitelisted script located on a desktop PC node."""
    return get_default_tools().run_script(device_id=device_id, script_name=script_name)


def get_tools() -> list[Callable[..., Any]]:
    """Return list of callable tool functions for LLM frameworks."""
    return get_default_tools().get_tools()
