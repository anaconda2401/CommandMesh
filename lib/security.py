"""CommandMesh symmetric end-to-end encryption and replay protection.

Uses NaCl SecretBox (XSalsa20-Poly1305) with 24-byte random nonces and 32-byte
symmetric keys derived via SHA-256 from a shared MESH_PASSPHRASE.
Includes bounded replay protection (deque + set) and a +/-30s timestamp window.
"""

from __future__ import annotations

import base64
import collections
import hashlib
import json
import logging
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure local dependencies are discoverable
try:
    import nacl.secret
    import nacl.utils
except ImportError:
    _mesh_site_packages = Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages"
    if _mesh_site_packages.exists() and str(_mesh_site_packages) not in sys.path:
        sys.path.insert(0, str(_mesh_site_packages))
    import nacl.secret
    import nacl.utils

# Load .env configurations gracefully
_root_env = Path(__file__).resolve().parent.parent / ".env"
if _root_env.is_file():
    load_dotenv(_root_env)
_cwd_env = Path.cwd() / ".env"
if _cwd_env.is_file() and _cwd_env.resolve() != _root_env.resolve():
    load_dotenv(_cwd_env)

logger = logging.getLogger("commandmesh.security")

TIMESTAMP_WINDOW_SECONDS = 30.0
DEFAULT_REPLAY_CACHE_SIZE = 128


class ReplayCache:
    """Bounded, memory-safe message ID replay cache.

    Combines collections.deque(maxlen=N) and set to achieve O(1) lookups
    while guaranteeing RAM overhead stays capped at ~5 KB regardless of uptime.
    """

    def __init__(self, maxlen: int = DEFAULT_REPLAY_CACHE_SIZE) -> None:
        self.maxlen = maxlen
        self._deque: collections.deque[str] = collections.deque(maxlen=maxlen)
        self._set: set[str] = set()
        self._lock = threading.Lock()

    def check_and_add(self, msg_id: str) -> bool:
        """Check if message ID is fresh.

        Returns True if fresh (and records it); returns False if replayed.
        """
        if not msg_id:
            return False
        with self._lock:
            if msg_id in self._set:
                return False
            if len(self._deque) == self.maxlen:
                oldest = self._deque.popleft()
                self._set.discard(oldest)
            self._deque.append(msg_id)
            self._set.add(msg_id)
            return True

    def __contains__(self, msg_id: str) -> bool:
        with self._lock:
            return msg_id in self._set

    def __len__(self) -> int:
        with self._lock:
            return len(self._set)

    def clear(self) -> None:
        """Clear all cached IDs."""
        with self._lock:
            self._deque.clear()
            self._set.clear()


# Default singleton replay cache for node runtime
default_replay_cache = ReplayCache()


def derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte symmetric key via SHA-256 from a master passphrase."""
    cleaned = (passphrase or "").strip().encode("utf-8")
    return hashlib.sha256(cleaned).digest()


def encrypt_payload(payload: dict[str, Any], passphrase: str) -> str:
    """Encrypt a compact JSON payload using NaCl SecretBox with a random 24-byte nonce.

    Returns a Base64-encoded string representing (24-byte nonce + ciphertext + MAC).
    """
    key = derive_key(passphrase)
    box = nacl.secret.SecretBox(key)
    nonce = nacl.utils.random(24)

    # Compact JSON serialization without redundant spaces
    raw_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    encrypted_msg = box.encrypt(raw_json, nonce)
    return base64.b64encode(encrypted_msg).decode("ascii")


def decrypt_payload(
    b64_ciphertext: str,
    passphrase: str,
    replay_cache: ReplayCache | None = default_replay_cache,
    now: float | None = None,
    enforce_window: bool = True,
) -> dict[str, Any] | None:
    """Decrypt and authenticate a Base64 ciphertext with SecretBox.

    Enforces:
    1. Authenticated decryption (MAC check via XSalsa20-Poly1305).
    2. Timestamp freshness window (+/- 30 seconds).
    3. Bounded replay cache check against duplicate message IDs.

    Returns dict if authentic and fresh; returns None if invalid or replayed.
    """
    if not b64_ciphertext or not passphrase:
        return None

    try:
        raw_encrypted = base64.b64decode(b64_ciphertext.strip().encode("ascii"), validate=True)
        key = derive_key(passphrase)
        box = nacl.secret.SecretBox(key)
        plaintext = box.decrypt(raw_encrypted)
        data = json.loads(plaintext.decode("utf-8"))
    except Exception:  # noqa: BLE001
        logger.debug("Failed to decrypt or authenticate incoming payload")
        return None

    if not isinstance(data, dict):
        return None

    # 1. Enforce +/- 30s timestamp window
    if enforce_window:
        msg_ts = data.get("ts")
        if not isinstance(msg_ts, (int, float)):
            return None
        current_time = time.time() if now is None else now
        if abs(current_time - float(msg_ts)) > TIMESTAMP_WINDOW_SECONDS:
            logger.debug("Dropped message with expired timestamp: %s (now: %s)", msg_ts, current_time)
            return None

    # 2. Check and record message ID in bounded replay cache
    msg_id = data.get("id") or data.get("msg_id")
    if replay_cache is not None and (not msg_id or not replay_cache.check_and_add(str(msg_id))):
        logger.debug("Dropped replayed or missing message ID: %s", msg_id)
        return None

    return data


def create_command_payload(
    sender_id: str,
    target: str,
    action: str,
    data: Any = None,
) -> dict[str, Any]:
    """Build a compact canonical command payload."""
    ts = int(time.time())
    msg_id = f"cmd_{int(ts * 1000)}_{random.randint(1000, 9999)}"
    payload: dict[str, Any] = {
        "from": str(sender_id).strip(),
        "to": str(target).strip(),
        "action": str(action).strip(),
        "ts": ts,
        "id": msg_id,
    }
    if data is not None:
        payload["data"] = data
    return payload


def create_ack_payload(
    sender_id: str,
    target: str = "",
    in_reply_to: str = "",
    action: str = "",
    status: str = "success",
    output: str = "",
) -> dict[str, Any]:
    """Build a compact canonical acknowledgment payload."""
    ts = int(time.time())
    msg_id = f"ack_{int(ts * 1000)}_{random.randint(1000, 9999)}"
    return {
        "from": str(sender_id).strip(),
        "to": str(target).strip(),
        "in_reply_to": str(in_reply_to).strip(),
        "action": str(action).strip(),
        "status": str(status).strip(),
        "output": str(output).strip(),
        "ts": ts,
        "id": msg_id,
    }


def send_command(
    broker: str,
    port: int,
    username: str,
    password: str,
    passphrase: str,
    sender_id: str,
    target: str,
    action: str,
    data: Any = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """One-shot command dispatch to any node in the mesh.

    Publishes encrypted command to mesh/cmd/<target>, waits for encrypted ACK
    on mesh/ack/<sender_id>, and returns result dictionary.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        _mesh_site_packages = Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages"
        if _mesh_site_packages.exists() and str(_mesh_site_packages) not in sys.path:
            sys.path.insert(0, str(_mesh_site_packages))
        import paho.mqtt.client as mqtt

    cmd_payload = create_command_payload(
        sender_id=sender_id,
        target=target,
        action=action,
        data=data,
    )
    cmd_id = cmd_payload["id"]
    encrypted_body = encrypt_payload(cmd_payload, passphrase)

    cmd_topic = f"mesh/cmd/{target}"
    ack_topic = f"mesh/ack/{sender_id}"

    ack_event = threading.Event()
    result_box: dict[str, Any] = {}

    def on_connect(client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
        if rc == 0:
            client.subscribe(ack_topic, qos=1)
            client.publish(cmd_topic, encrypted_body, qos=1, retain=False)

    def on_message(client: Any, userdata: Any, msg: Any) -> None:
        try:
            b64_str = msg.payload.decode("ascii")
            ack = decrypt_payload(b64_str, passphrase, replay_cache=None)
            if ack and ack.get("in_reply_to") == cmd_id:
                result_box.update(ack)
                ack_event.set()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed parsing response message: %s", exc)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.tls_set()
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(broker, port, keepalive=60)
        client.loop_start()
        got_ack = ack_event.wait(timeout=timeout)
        client.loop_stop()
        client.disconnect()
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "target": target,
            "action": action,
            "error": "connection_failed",
            "message": str(exc),
        }

    if not got_ack:
        return {
            "success": False,
            "target": target,
            "action": action,
            "error": "timeout",
            "message": f"Command timed out after {timeout}s without ACK.",
        }

    is_ok = result_box.get("status") == "success"
    return {
        "success": is_ok,
        "target": target,
        "action": action,
        "status": result_box.get("status", "unknown"),
        "output": result_box.get("output", ""),
        "raw": result_box,
    }
