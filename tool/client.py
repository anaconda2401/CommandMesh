"""CommandMesh MQTT client for executing agent tool calls using SecretBox encryption."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Self

from dotenv import load_dotenv

# Ensure root 'lib' is discoverable
_root_dir = Path(__file__).resolve().parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

# Ensure local venv site-packages is discoverable if present
_venv_site = _root_dir / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))

import paho.mqtt.client as mqtt

from lib.security import (
    create_command_payload,
    decrypt_payload,
    encrypt_payload,
)

logger = logging.getLogger("commandmesh.tool.client")

# Load .env configurations gracefully
_mesh_env = _root_dir / ".env"
if _mesh_env.is_file():
    load_dotenv(_mesh_env)
_cwd_env = Path.cwd() / ".env"
if _cwd_env.is_file() and _cwd_env.resolve() != _mesh_env.resolve():
    load_dotenv(_cwd_env)

# Static capabilities for discovery fallbacks
STATIC_CAPABILITIES: dict[str, list[str]] = {
    "pc": [
        "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad_center",
        "vol_up", "vol_down", "play_pause", "type_text", "press_keys",
        "open_url", "open_youtube", "home", "lock_pc", "run_script",
    ],
    "tv": [
        "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad_center",
        "vol_up", "vol_down", "play_pause", "type_text", "open_url",
        "open_youtube", "home", "lock_device",
    ],
}

DESKTOP_ONLY_ACTIONS = frozenset({"press_keys", "run_script"})


class MeshClient:
    """MQTT Client for peer-to-peer encrypted mesh interactions."""

    def __init__(
        self,
        broker: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        passphrase: str | None = None,
        private_key: str | None = None,
        sender_id: str | None = None,
        role: str | None = None,
        ack_timeout: float = 5.0,
    ) -> None:
        self.broker = broker or os.getenv("MQTT_BROKER", "localhost").strip()
        self.port = int(port or os.getenv("MQTT_PORT", "8883"))
        self.username = username or os.getenv("MQTT_USERNAME", "").strip()
        self.password = password or os.getenv("MQTT_PASSWORD", "").strip()

        # Support both MESH_PASSPHRASE and legacy private_key parameter alias
        self.passphrase = (
            passphrase
            or private_key
            or os.getenv("MESH_PASSPHRASE")
            or os.getenv("MESH_PRIVATE_KEY")
            or os.getenv("MESH_SECRET")
            or ""
        ).strip()

        self.sender_id = (
            sender_id
            or role
            or os.getenv("NODE_ID")
            or "mesh_agent"
        ).strip()
        self.role = self.sender_id
        self.ack_timeout = ack_timeout

        self._devices: dict[str, dict[str, Any]] = {}
        self._pending: dict[str, threading.Event] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._client: mqtt.Client | None = None
        self._connected = False
        self._connect_event = threading.Event()

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected to MQTT broker."""
        return self._connected

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the MQTT broker using TLS."""
        if self._connected:
            return True

        if not self.broker or not self.username or not self.password:
            logger.error("Missing MQTT broker credentials (MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD).")
            return False

        if not self.passphrase:
            logger.error("Missing MESH_PASSPHRASE for SecretBox encryption.")
            return False

        self._connect_event.clear()

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
        )
        client.tls_set()
        client.username_pw_set(self.username, self.password)
        client.reconnect_delay_set(min_delay=1, max_delay=60)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        try:
            client.connect(self.broker, self.port, keepalive=60)
            client.loop_start()
            if self._connect_event.wait(timeout=timeout):
                self._client = client
                self._connected = True
                return True
            logger.warning("Connection to MQTT broker timed out after %ss", timeout)
            client.loop_stop()
            client.disconnect()
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Error connecting to MQTT broker: %s", exc)
            return False

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: Any,
        *args: Any,
    ) -> None:
        if rc == 0:
            logger.info("Connected to CommandMesh broker as '%s'", self.sender_id)
            self._connected = True
            self._connect_event.set()

            # Subscribe to direct ACKs for this client and presence discovery
            ack_topic = f"mesh/ack/{self.sender_id}"
            presence_topic = "mesh/presence/#"
            client.subscribe([(ack_topic, 1), (presence_topic, 1)])
        else:
            logger.error("Failed to connect to broker (rc=%s)", rc)
            self._connect_event.set()

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: Any,
        *args: Any,
    ) -> None:
        self._connected = False
        logger.debug("Disconnected from MQTT broker (rc=%s)", rc)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        topic = msg.topic
        payload_bytes = msg.payload

        # 1. Handle presence updates (retained JSON)
        if topic.startswith("mesh/presence/"):
            try:
                info = json.loads(payload_bytes.decode("utf-8"))
                dev_id = info.get("id") or topic.split("/")[-1]
                if dev_id:
                    status = info.get("status", "unknown")
                    is_online = status == "online"
                    dev_type = info.get("type", "unknown")

                    caps = info.get("capabilities") or STATIC_CAPABILITIES.get(dev_type, [])

                    with self._lock:
                        self._devices[dev_id] = {
                            "id": dev_id,
                            "name": info.get("name", dev_id),
                            "type": dev_type,
                            "online": is_online,
                            "status": status,
                            "capabilities": caps,
                            "ts": info.get("ts", time.time()),
                        }
            except Exception as exc:  # noqa: BLE001
                logger.debug("Malformed presence payload on %s: %s", topic, exc)
            return

        # 2. Handle encrypted ACKs (mesh/ack/<sender_id>)
        expected_ack_topic = f"mesh/ack/{self.sender_id}"
        if topic == expected_ack_topic:
            try:
                b64_str = payload_bytes.decode("ascii")
                data = decrypt_payload(b64_str, self.passphrase, replay_cache=None)
                if not data:
                    return

                in_reply_to = data.get("in_reply_to") or data.get("msg_id")
                if not in_reply_to:
                    return

                with self._lock:
                    if in_reply_to in self._pending:
                        self._results[in_reply_to] = data
                        self._pending[in_reply_to].set()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error handling ACK message: %s", exc)

    def disconnect(self) -> None:
        """Disconnect and stop client loop."""
        with self._lock:
            client = self._client
            self._client = None
            self._connected = False
            self._connect_event.clear()
            if client is not None:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Error during MQTT disconnect: %s", exc)

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.disconnect()

    def ensure_connected(self) -> bool:
        """Ensure client is connected, connecting lazily if needed."""
        if not self._connected:
            return self.connect()
        return True

    def list_devices(self, wait_if_empty: float = 1.0) -> list[dict[str, Any]]:
        """Return list of all discovered devices and their status."""
        self.ensure_connected()
        if wait_if_empty > 0:
            deadline = time.time() + wait_if_empty
            while time.time() < deadline:
                with self._lock:
                    if self._devices:
                        return list(self._devices.values())
                time.sleep(0.05)
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str, timeout: float = 1.5) -> dict[str, Any] | None:
        """Retrieve status of a single device from discovery cache."""
        self.ensure_connected()
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                dev = self._devices.get(device_id)
                if dev is not None:
                    return dev
            time.sleep(0.05)
        with self._lock:
            return self._devices.get(device_id)

    def execute_command(
        self,
        device_id: str,
        action: str,
        data: Any = None,
        desktop_only: bool = False,
    ) -> dict[str, Any]:
        """Dispatch a validated, encrypted SecretBox command to a node and await ACK."""
        if not self.ensure_connected():
            return {
                "success": False,
                "device": device_id,
                "action": action,
                "error": "mqtt_unavailable",
                "message": "Cannot reach MQTT broker.",
            }

        if not self.passphrase:
            return {
                "success": False,
                "device": device_id,
                "action": action,
                "error": "missing_passphrase",
                "message": "No MESH_PASSPHRASE configured for encryption.",
            }

        # Allow 'all' broadcast target without requiring discovery entry
        if device_id != "all":
            device = self.get_device(device_id)
            if device is None:
                return {
                    "success": False,
                    "device": device_id,
                    "action": action,
                    "error": "device_not_found",
                    "message": f"Device '{device_id}' was not found in discovery cache.",
                }

            if not device.get("online", False):
                return {
                    "success": False,
                    "device": device_id,
                    "action": action,
                    "error": "device_offline",
                    "message": f"Device '{device_id}' is currently offline.",
                }

            dev_type = device.get("type", "unknown")
            if (desktop_only or action in DESKTOP_ONLY_ACTIONS) and dev_type != "pc":
                return {
                    "success": False,
                    "device": device_id,
                    "action": action,
                    "error": "invalid_command",
                    "message": (
                        f"Action '{action}' is desktop-only, but device "
                        f"'{device_id}' has type '{dev_type}'."
                    ),
                }

        # Validate plain filename for run_script
        if action == "run_script":
            script_name = str(data or "").strip()
            safe_name = Path(script_name).name
            if not safe_name or safe_name != script_name or ".." in script_name:
                return {
                    "success": False,
                    "device": device_id,
                    "action": action,
                    "error": "invalid_parameter",
                    "message": "Script name must be a plain filename without path separators.",
                }
            data = safe_name

        # Construct and encrypt payload
        cmd_payload = create_command_payload(
            sender_id=self.sender_id,
            target=device_id,
            action=action,
            data=data,
        )
        msg_id = cmd_payload["id"]

        try:
            b64_ciphertext = encrypt_payload(cmd_payload, self.passphrase)
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "device": device_id,
                "action": action,
                "error": "encryption_failed",
                "message": f"Failed to encrypt command: {exc}",
            }

        # Setup pending ACK event
        event = threading.Event()
        with self._lock:
            self._pending[msg_id] = event

        topic = f"mesh/cmd/{device_id}"
        try:
            if self._client is not None:
                self._client.publish(topic, b64_ciphertext, qos=1, retain=False)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._pending.pop(msg_id, None)
            return {
                "success": False,
                "device": device_id,
                "action": action,
                "error": "publish_failed",
                "message": str(exc),
            }

        # Await ACK
        got_ack = event.wait(timeout=self.ack_timeout)
        with self._lock:
            self._pending.pop(msg_id, None)
            ack = self._results.pop(msg_id, None)

        if not got_ack or ack is None:
            return {
                "success": False,
                "device": device_id,
                "action": action,
                "error": "device_timeout",
                "message": f"Device '{device_id}' did not acknowledge within {self.ack_timeout}s.",
            }

        is_ok = ack.get("status") == "success"
        output_msg = ack.get("output") or ack.get("message") or ("Success" if is_ok else "Command failed")

        result_payload = {
            "success": is_ok,
            "device": device_id,
            "action": action,
            "status": ack.get("status", "unknown"),
            "message": output_msg,
            "result": output_msg,
            "raw": ack,
        }
        if not is_ok:
            result_payload["error"] = ack.get("error") or "device_rejected"

        return result_payload
