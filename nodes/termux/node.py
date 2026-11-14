"""CommandMesh Android / Termux Node (Android TV, Phones, Tablets).

Optimized for low-RAM, low-CPU unattended operation on older Android TVs.
Features persistent root shell / ADB / native root execution, zero busy-wait CPU,
automatic exponential reconnect backoff, bounded replay cache, and encrypted
peer-to-peer SecretBox messaging over MQTT.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

# Ensure root 'lib' is discoverable
_root_dir = Path(__file__).resolve().parent.parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

# Ensure local venv site-packages is discoverable if present
_venv_site = _root_dir / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))

import paho.mqtt.client as mqtt

from lib.security import (
    ReplayCache,
    create_ack_payload,
    decrypt_payload,
    encrypt_payload,
)

# Load secrets from root .env file
_env_path = _root_dir / ".env"
if _env_path.is_file():
    load_dotenv(_env_path)

# --- LOGGING CONFIGURATION ---
_log_level_name = os.getenv("LOG_LEVEL", "WARNING").strip().upper()
_log_level = getattr(logging, _log_level_name, logging.WARNING)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("commandmesh.node.termux")

# --- NODE CONFIGURATION ---
DEVICE_ID = os.getenv("NODE_ID", "tv_node").strip()
DEVICE_NAME = os.getenv("NODE_NAME", "Android TV").strip()
DEVICE_TYPE = "tv"

BROKER = os.getenv("MQTT_BROKER", "localhost").strip()
PORT = int(os.getenv("MQTT_PORT", "8883").strip())
USER = os.getenv("MQTT_USERNAME", "").strip()
PASS = os.getenv("MQTT_PASSWORD", "").strip()
ADB_TARGET = os.getenv("ADB_TARGET", "127.0.0.1:5555").strip()
PASSPHRASE = os.getenv("MESH_PASSPHRASE", "").strip()

TOPIC_CMD_DIRECT = f"mesh/cmd/{DEVICE_ID}"
TOPIC_CMD_ALL = "mesh/cmd/all"
TOPIC_ACK_INBOX = f"mesh/ack/{DEVICE_ID}"
TOPIC_PRESENCE = f"mesh/presence/{DEVICE_ID}"

ANDROID_KEYCODES: dict[str, str] = {
    "home": "3",
    "lock_pc": "26",
    "lock_device": "26",
    "vol_up": "24",
    "vol_down": "25",
    "play_pause": "85",
    "dpad_up": "19",
    "dpad_down": "20",
    "dpad_left": "21",
    "dpad_right": "22",
    "dpad_center": "66",
}

replay_cache = ReplayCache(maxlen=128)

# ==========================================
# EXECUTION MODE DETECTION
# ==========================================
try:
    IS_NATIVE_ROOT = os.geteuid() == 0
except AttributeError:
    IS_NATIVE_ROOT = False

ROOT_SHELL: subprocess.Popen[str] | None = None


def init_persistent_shell() -> None:
    """Start persistent su pipe for high-throughput zero-latency writes."""
    global ROOT_SHELL
    try:
        ROOT_SHELL = subprocess.Popen(
            ["su"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to start persistent root shell: %s", exc)
        sys.exit(1)


def detect_termux_mode() -> str:
    """Identify the optimal command execution strategy."""
    if IS_NATIVE_ROOT:
        return "native_root"
    if shutil.which("su"):
        return "su_wrapper"
    if shutil.which("adb"):
        return "adb"
    logger.error("No Android execution method found (su or adb missing)")
    sys.exit(1)


TERMUX_MODE = detect_termux_mode()
if TERMUX_MODE == "su_wrapper":
    init_persistent_shell()


def run_android_cmd(cmd_list: list[str]) -> tuple[bool, str]:
    """Execute raw Android command list via native root, su shell, or ADB."""
    try:
        if TERMUX_MODE == "native_root":
            res = subprocess.run(cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            return res.returncode == 0, "Executed"

        elif TERMUX_MODE == "su_wrapper":
            if ROOT_SHELL is None or ROOT_SHELL.poll() is not None:
                init_persistent_shell()

            if ROOT_SHELL and ROOT_SHELL.stdin:
                safe_cmd_str = shlex.join(cmd_list)
                ROOT_SHELL.stdin.write(f"{safe_cmd_str}\n")
                ROOT_SHELL.stdin.flush()
                return True, "Executed (Piped)"
            return False, "Root shell unavailable"

        else:
            # ADB Mode
            adb_cmd = ["adb", "-s", ADB_TARGET, "shell", *cmd_list]
            res = subprocess.run(adb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            if res.returncode != 0:
                subprocess.run(["adb", "connect", ADB_TARGET], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
                res = subprocess.run(adb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            return res.returncode == 0, "Executed"

    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as exc:  # noqa: BLE001
        return False, f"Execution error: {exc}"


def execute_action(action: str, params: Any = None) -> tuple[bool, str]:
    """Route device actions to Android intents and keyevents."""
    action_clean = str(action or "").strip()

    if action_clean == "open_url" and params:
        url_str = str(params).strip()
        parsed = urlparse(url_str)
        if parsed.scheme in ("http", "https"):
            return run_android_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", url_str])
        return False, "Invalid URL scheme"

    elif action_clean == "type_text" and params:
        safe_text = str(params).replace(" ", "%s")
        return run_android_cmd(["input", "text", safe_text])

    elif action_clean == "open_youtube":
        return run_android_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", "https://www.youtube.com"])

    elif action_clean in ANDROID_KEYCODES:
        return run_android_cmd(["input", "keyevent", ANDROID_KEYCODES[action_clean]])

    elif action_clean == "run_script":
        return False, "Arbitrary script execution blocked on Android"

    return False, f"Unknown action: {action_clean}"


# ==========================================
# MQTT CLIENT EVENT HANDLERS
# ==========================================
def on_connect(client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
    """Called on initial connect and every automatic reconnect."""
    if rc == 0:
        print(f"[MQTT] [*] Node '{DEVICE_ID}' (Android TV) connected.")

        # Re-subscribe to all required topics on every reconnect
        client.subscribe([(TOPIC_CMD_DIRECT, 1), (TOPIC_CMD_ALL, 1), (TOPIC_ACK_INBOX, 1)])

        # Publish retained presence
        presence_payload = json.dumps({
            "id": DEVICE_ID,
            "name": DEVICE_NAME,
            "type": DEVICE_TYPE,
            "status": "online",
            "capabilities": [
                "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad_center",
                "vol_up", "vol_down", "play_pause", "type_text", "open_url",
                "open_youtube", "home", "lock_device",
            ],
            "ts": int(time.time()),
        })
        client.publish(TOPIC_PRESENCE, presence_payload, qos=1, retain=True)
    else:
        logger.warning("MQTT connection refused with code %s", rc)


def on_message(client: Any, userdata: Any, msg: Any) -> None:
    """Handle incoming encrypted command messages."""
    topic = msg.topic
    if not (topic == TOPIC_CMD_DIRECT or topic == TOPIC_CMD_ALL):
        return

    try:
        b64_ciphertext = msg.payload.decode("ascii")
        data = decrypt_payload(b64_ciphertext, PASSPHRASE, replay_cache=replay_cache)
        if not data:
            return  # Silently drop unauthenticated or expired packets

        target = data.get("to")
        if target not in (DEVICE_ID, "all"):
            return

        action = data.get("action", "")
        params = data.get("data")
        sender_id = data.get("from")
        cmd_id = data.get("id", "")

        success, detail = execute_action(action, params)

        # Send encrypted ACK back to sender
        if sender_id and cmd_id:
            ack_topic = f"mesh/ack/{sender_id}"
            ack_payload = create_ack_payload(
                sender_id=DEVICE_ID,
                target=sender_id,
                in_reply_to=cmd_id,
                action=action,
                status="success" if success else "error",
                output=detail,
            )
            encrypted_ack = encrypt_payload(ack_payload, PASSPHRASE)
            client.publish(ack_topic, encrypted_ack, qos=1, retain=False)
            if _log_level <= logging.INFO:
                print(f"[ACK] -> '{sender_id}' for {cmd_id} ({action})")

    except Exception as exc:  # noqa: BLE001
        logger.debug("Fault in message processing: %s", exc)


def main() -> None:
    """Node runner using blocking loop_forever with exponential reconnect."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.tls_set()
    client.username_pw_set(USER, PASS)

    # Automatic exponential reconnect backoff for mobile/TV Wi-Fi stability
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    # Last Will and Testament
    lwt_payload = json.dumps({
        "id": DEVICE_ID,
        "name": DEVICE_NAME,
        "type": DEVICE_TYPE,
        "status": "offline",
        "ts": int(time.time()),
    })
    client.will_set(TOPIC_PRESENCE, lwt_payload, qos=1, retain=True)

    client.on_connect = on_connect
    client.on_message = on_message

    print("\n" + "=" * 40)
    print(f" NODE: {DEVICE_NAME} (Android TV)")
    print("=" * 40)
    print(f" MODE: [*] {TERMUX_MODE.upper()} EXECUTION LAYER (SecretBox)")
    print(" MQTT: Connecting to broker...")
    print("=" * 40 + "\n")

    if shutil.which("termux-wake-lock"):
        os.system("termux-wake-lock")

    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[INFO] Shutting down '{DEVICE_ID}'...")
        if ROOT_SHELL is not None and ROOT_SHELL.poll() is None:
            try:
                if ROOT_SHELL.stdin:
                    ROOT_SHELL.stdin.close()
                ROOT_SHELL.terminate()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error closing root shell: %s", exc)

        client.publish(TOPIC_PRESENCE, lwt_payload, qos=1, retain=True)
        client.loop_write()
        client.disconnect()

        if shutil.which("termux-wake-unlock"):
            os.system("termux-wake-unlock")
        print("[OK] Disconnected cleanly.")


if __name__ == "__main__":
    main()
