"""CommandMesh Desktop Node (Windows / macOS / Linux).

Listens on MQTT for peer-to-peer encrypted commands using NaCl SecretBox.
Features automatic reconnect with exponential backoff, zero busy-wait CPU,
bounded replay cache, Directory-as-Allowlist script execution, and native
Windows fallbacks when GUI automation libraries are not installed.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure root 'lib' is discoverable
_root_dir = Path(__file__).resolve().parent.parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

# Also ensure virtual environment site-packages is discoverable if present
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
logger = logging.getLogger("commandmesh.node.desktop")

# --- NODE CONFIGURATION ---
DEVICE_ID = os.getenv("NODE_ID", "desktop_fallback").strip()
DEVICE_NAME = os.getenv("NODE_NAME", "Unnamed PC").strip()
DEVICE_TYPE = "pc"

BROKER = os.getenv("MQTT_BROKER", "localhost").strip()
PORT = int(os.getenv("MQTT_PORT", "8883").strip())
USER = os.getenv("MQTT_USERNAME", "").strip()
PASS = os.getenv("MQTT_PASSWORD", "").strip()
PASSPHRASE = os.getenv("MESH_PASSPHRASE", "").strip()

TOPIC_CMD_DIRECT = f"mesh/cmd/{DEVICE_ID}"
TOPIC_CMD_ALL = "mesh/cmd/all"
TOPIC_ACK_INBOX = f"mesh/ack/{DEVICE_ID}"
TOPIC_PRESENCE = f"mesh/presence/{DEVICE_ID}"

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

OS_NAME = platform.system()
replay_cache = ReplayCache(maxlen=128)

# Lazy import holder for pyautogui
_pyautogui: Any = None
_pyautogui_checked: bool = False


def get_pyautogui() -> Any:
    """Lazy-load pyautogui only when GUI actions are invoked."""
    global _pyautogui, _pyautogui_checked
    if not _pyautogui_checked:
        _pyautogui_checked = True
        try:
            import pyautogui as pag
            _pyautogui = pag
        except ImportError:
            _pyautogui = None
    return _pyautogui


def _send_windows_vk(vk_code: int, count: int = 1) -> None:
    """Send native Windows virtual keycode event via standard ctypes."""
    import ctypes
    for _ in range(count):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP


def execute_action(action: str, params: Any = None) -> tuple[bool, str]:
    """Route and execute device actions safely."""
    action_clean = str(action or "").strip()

    # --- 1. URL OPENING ---
    if action_clean == "open_url" and params:
        url_str = str(params).strip()
        if url_str.startswith(("http://", "https://")):
            threading.Thread(target=webbrowser.open, args=(url_str,), daemon=True).start()
            return True, "URL Opened"
        return False, "Invalid URL scheme"

    # --- 2. ALLOWLISTED SCRIPTS (Directory-as-Allowlist) ---
    elif action_clean == "run_script" and params:
        raw_name = str(params).strip()
        target_path = (SCRIPTS_DIR / raw_name).resolve()

        try:
            if not target_path.is_relative_to(SCRIPTS_DIR) or target_path == SCRIPTS_DIR:
                return False, f"Security Block: Traversal detected for '{raw_name}'"
        except (ValueError, AttributeError):
            return False, f"Security Block: Invalid script path for '{raw_name}'"

        if not target_path.is_file():
            return False, f"Script not found: '{target_path.name}'"

        safe_name = target_path.name
        script_path = str(target_path)
        sb_kwargs = {"shell": False, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

        try:
            if safe_name.endswith(".py"):
                subprocess.Popen([sys.executable, script_path], **sb_kwargs)
            elif safe_name.endswith((".bat", ".cmd")) and OS_NAME == "Windows":
                subprocess.Popen(["cmd.exe", "/c", script_path], **sb_kwargs)
            elif safe_name.endswith(".ps1"):
                ps_exe = "powershell.exe" if OS_NAME == "Windows" else "pwsh"
                subprocess.Popen([ps_exe, "-ExecutionPolicy", "Bypass", "-File", script_path], **sb_kwargs)
            elif safe_name.endswith(".sh") and OS_NAME in ("Linux", "Darwin"):
                subprocess.Popen(["bash", script_path], **sb_kwargs)
            else:
                return False, f"OS mismatch or unsupported script format: '{safe_name}'"
            return True, f"Script '{safe_name}' launched"
        except Exception as exc:  # noqa: BLE001
            return False, f"Script execution error: {exc}"

    # --- 3. SYSTEM & MEDIA ACTIONS ---
    elif action_clean == "open_youtube":
        threading.Thread(target=webbrowser.open, args=("https://youtube.com",), daemon=True).start()
        return True, "YouTube Opened"

    elif action_clean in ("lock_pc", "lock_device"):
        try:
            sb_kwargs = {"shell": False, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "timeout": 5}
            if OS_NAME == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False, **sb_kwargs)
            elif OS_NAME == "Darwin":
                subprocess.run(["pmset", "displaysleepnow"], check=False, **sb_kwargs)
            elif OS_NAME == "Linux":
                subprocess.run(["xdg-screensaver", "lock"], check=False, **sb_kwargs)
            return True, "PC Locked"
        except Exception as exc:  # noqa: BLE001
            return False, f"Lock command failed: {exc}"

    # --- 4. KEYBOARD / DPAD / VOLUME ACTIONS ---
    elif action_clean in (
        "type_text", "press_keys", "home", "play_pause", "vol_up", "vol_down",
        "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad_center",
    ):
        pag = get_pyautogui()
        if pag is None and OS_NAME != "Windows":
            return False, "pyautogui library missing on non-Windows host"

        if OS_NAME == "Linux" and "DISPLAY" not in os.environ:
            return False, "Linux headless mode detected. GUI actions disabled."

        try:
            if pag is not None:
                if action_clean == "type_text" and params:
                    pag.write(str(params))
                elif action_clean == "press_keys" and params:
                    keys = [k.strip() for k in str(params).split(",")]
                    pag.hotkey(*keys)
                elif action_clean == "home":
                    if OS_NAME == "Windows":
                        pag.hotkey("win", "d")
                    elif OS_NAME == "Darwin":
                        pag.hotkey("command", "f3")
                    elif OS_NAME == "Linux":
                        pag.hotkey("ctrl", "super", "d")
                elif action_clean == "play_pause":
                    pag.press("playpause")
                elif action_clean == "vol_up":
                    pag.press("volumeup", presses=2)
                elif action_clean == "vol_down":
                    pag.press("volumedown", presses=2)
                elif action_clean == "dpad_up":
                    pag.press("up")
                elif action_clean == "dpad_down":
                    pag.press("down")
                elif action_clean == "dpad_left":
                    pag.press("left")
                elif action_clean == "dpad_right":
                    pag.press("right")
                elif action_clean == "dpad_center":
                    pag.press("enter")
                return True, "Key executed"
            elif OS_NAME == "Windows":
                import ctypes

                if action_clean == "vol_up":
                    _send_windows_vk(0xAF, 2)
                elif action_clean == "vol_down":
                    _send_windows_vk(0xAE, 2)
                elif action_clean == "play_pause":
                    _send_windows_vk(0xB3)
                elif action_clean == "dpad_up":
                    _send_windows_vk(0x26)
                elif action_clean == "dpad_down":
                    _send_windows_vk(0x28)
                elif action_clean == "dpad_left":
                    _send_windows_vk(0x25)
                elif action_clean == "dpad_right":
                    _send_windows_vk(0x27)
                elif action_clean == "dpad_center":
                    _send_windows_vk(0x0D)
                elif action_clean == "home":
                    ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)
                    ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
                elif action_clean == "type_text" and params:
                    for ch in str(params):
                        ctypes.windll.user32.keybd_event(0, ord(ch), 0x0004, 0)
                        ctypes.windll.user32.keybd_event(0, ord(ch), 0x0004 | 0x0002, 0)
                elif action_clean == "press_keys" and params:
                    return False, "pyautogui library required for complex multi-key combinations"
                return True, "Key executed (native Windows)"
        except Exception as exc:  # noqa: BLE001
            return False, f"GUI error: {exc}"

    return False, f"Unknown action: {action_clean}"


# ==========================================
# MQTT CLIENT EVENT HANDLERS
# ==========================================
def on_connect(client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
    """Called on initial connect and every automatic reconnect."""
    if rc == 0:
        print(f"[MQTT] [*] Node '{DEVICE_ID}' ({OS_NAME}) connected successfully.")

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
                "vol_up", "vol_down", "play_pause", "type_text", "press_keys",
                "open_url", "open_youtube", "home", "lock_pc", "run_script",
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
            return  # Silently drop unauthenticated, replayed, or expired packets

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
                print(f"[ACK] -> '{sender_id}' for {cmd_id} ({action}: {detail})")

    except Exception as exc:  # noqa: BLE001
        logger.debug("Fault in message processing: %s", exc)


def main() -> None:
    """Node runner using blocking loop_forever with exponential reconnect."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.tls_set()
    client.username_pw_set(USER, PASS)

    # Automatic exponential backoff for uninterrupted reliability (1s to 60s)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    # Last Will and Testament for instantaneous offline status
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
    print(f" NODE: {DEVICE_NAME} ({OS_NAME})")
    print("=" * 40)
    print(" MODE: [*] DESKTOP EXECUTION LAYER (SecretBox)")
    print(" MQTT: Connecting to broker...")
    print("=" * 40 + "\n")

    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[INFO] Shutting down '{DEVICE_ID}'...")
        client.publish(TOPIC_PRESENCE, lwt_payload, qos=1, retain=True)
        client.loop_write()
        client.disconnect()
        print("[OK] Disconnected cleanly.")


if __name__ == "__main__":
    main()
