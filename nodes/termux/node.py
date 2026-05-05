import os
import sys
import json
import subprocess
import shutil
import shlex
from urllib.parse import urlparse
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# 1. Allow importing from the root 'lib' directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.security import verify_message

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# --- TV / PHONE CONFIGURATION ---
DEVICE_ID = os.getenv("NODE_ID", "android_fallback")
DEVICE_NAME = os.getenv("NODE_NAME", "Unnamed Android")
DEVICE_TYPE = "tv"

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 8883))
USER = os.getenv("MQTT_USERNAME", "")
PASS = os.getenv("MQTT_PASSWORD", "")
ADB_TARGET = os.getenv("ADB_TARGET", "127.0.0.1:5555")

TOPIC_INBOX = f"commandmesh/{DEVICE_ID}/in"
TOPIC_OUTBOX = f"commandmesh/{DEVICE_ID}/out"
TOPIC_DISCOVERY = f"commandmesh/discovery/{DEVICE_ID}"

ANDROID_KEYCODES = {
    "home": "3", "lock_pc": "26", "vol_up": "24", "vol_down": "25",
    "play_pause": "85", "dpad_up": "19", "dpad_down": "20",
    "dpad_left": "21", "dpad_right": "22", "dpad_center": "66"
}

# ==========================================
# AUTO-DETECT EXECUTION MODE
# ==========================================
def detect_termux_mode():
    """Checks for root access first, falls back to normal ADB."""
    env_mode = os.getenv("TERMUX_MODE", "").lower()
    if env_mode in ["root", "adb"]:
        return env_mode
    
    if shutil.which("su"):
        try:
            test = subprocess.run(["su", "-c", "id"], capture_output=True, text=True, timeout=2)
            if test.returncode == 0:
                return "root"
        except Exception:
            pass
            
    if shutil.which("adb"):
        return "adb"
        
    print("\n[FATAL] System cannot execute commands!")
    print(" -> FIX 1: If rooted, ensure Magisk/SuperSU granted permission to Termux.")
    print(" -> FIX 2: If normal, run 'pkg install android-tools' in Termux.")
    sys.exit(1)

TERMUX_MODE = detect_termux_mode()

# ==========================================
# PRE-FLIGHT CHECKS & DIAGNOSTICS
# ==========================================
IS_ANDROID = "ANDROID_ROOT" in os.environ
has_wakelock = False

if shutil.which("termux-wake-lock"):
    os.system("termux-wake-lock")
    has_wakelock = True

# Mode-specific setup & hints
mode_display = ""
hints = []

if TERMUX_MODE == "root":
    mode_display = "[*] ROOTED MODE (su)"
    hints.append("[HINT] Root mode is active. Execution will be instant with no network drops.")
    hints.append("[HINT] Ensure Magisk/SuperSU is set to 'Always Allow' for Termux.")
else:
    mode_display = f"[*] NORMAL MODE (ADB) -> Target: {ADB_TARGET}"
    hints.append("[HINT] Normal mode uses ADB. Keep WiFi on and connected.")
    hints.append(f"[HINT] Ensure 'Wireless Debugging' is enabled for {ADB_TARGET}.")
    
    # Attempt initial ADB connection
    res = subprocess.run(["adb", "connect", ADB_TARGET], capture_output=True, text=True)
    if "cannot connect" in res.stdout.lower() or "connection refused" in res.stdout.lower():
        hints.append(f"[WARNING] Initial ADB connection to {ADB_TARGET} failed!")

# PRINT BOOT DASHBOARD
print("\n" + "="*50)
print(f" COMMANDMESH ANDROID NODE : {DEVICE_NAME}")
print("="*50)
print(f" Node ID   : {DEVICE_ID}")
print(f" Mode      : {mode_display}")
print(f" Wakelock  : {'[OK] Active (Safe in background)' if has_wakelock else '[FAIL] Missing (Run: pkg install termux-api)'}")
print(f" Android   : {'[YES]' if IS_ANDROID else '[NO] (Testing on PC?)'}")
print(f" Broker    : Connecting to {BROKER}:{PORT}...")
print("-" * 50)
for hint in hints:
    print(hint)
print("="*50 + "\n")

# ==========================================
# COMMAND EXECUTION ROUTER
# ==========================================
def run_android_cmd(cmd_list):
    try:
        if TERMUX_MODE == "root":
            safe_cmd_str = shlex.join(cmd_list)
            res = subprocess.run(["su", "-c", safe_cmd_str], capture_output=True, text=True)
        else:
            res = subprocess.run(["adb", "-s", ADB_TARGET, "shell"] + cmd_list, capture_output=True, text=True)
            output_str = (res.stdout + res.stderr).lower()
            if "device offline" in output_str or "not found" in output_str:
                print(f"[WARNING] ADB offline. Auto-reconnecting to {ADB_TARGET}...")
                subprocess.run(["adb", "connect", ADB_TARGET], capture_output=True)
                res = subprocess.run(["adb", "-s", ADB_TARGET, "shell"] + cmd_list, capture_output=True, text=True)

        if res.returncode != 0:
            error_msg = res.stderr.strip() or res.stdout.strip()
            print(f"[ERROR] Cmd failed: {error_msg}")
            return False, error_msg
            
        return True, "Success"
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        return False, str(e)

# ==========================================
# ACTION HANDLER
# ==========================================
def execute_action(payload_data):
    action = payload_data.get("action")
    params = payload_data.get("data")
    
    print(f"[CMD] {action} {('-> ' + str(params)) if params else ''}")
    
    if action == "open_url" and params:
        parsed = urlparse(params)
        if parsed.scheme in ("http", "https"):
            return run_android_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", params])
            
    elif action == "type_text" and params:
        safe_text = str(params).replace(" ", "%s")
        return run_android_cmd(["input", "text", safe_text])

    elif action == "open_youtube":
        return run_android_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", "https://www.youtube.com"])

    elif action in ANDROID_KEYCODES:
        return run_android_cmd(["input", "keyevent", ANDROID_KEYCODES[action]])

    elif action == "run_script":
        print("[BLOCK] Scripts are disabled on Android.")
        return False, "Security block: Scripts not permitted"
        
    return False, f"Unknown action: {action}"

# ==========================================
# MQTT SETUP
# ==========================================
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[MQTT] [OK] Connected to mesh successfully.")
        client.subscribe(TOPIC_INBOX)
        
        status_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "online"})
        client.publish(TOPIC_DISCOVERY, status_payload, retain=True)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if data.get("to") != DEVICE_ID: return
        
        if not verify_message(data): return 
            
        success, detail = execute_action(data)
        
        ack_payload = {
            "id": DEVICE_ID,
            "action": data.get("action"),
            "status": "success" if success else "error",
            "message": detail
        }
        client.publish(TOPIC_OUTBOX, json.dumps(ack_payload))
        
    except Exception as e:
        print(f"[ERROR] Processing message: {e}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
client.tls_set()
client.username_pw_set(USER, PASS)

lwt_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "offline"})
client.will_set(TOPIC_DISCOVERY, lwt_payload, retain=True)

client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(BROKER, PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print(f"\n[INFO] Shutting down...")
    client.publish(TOPIC_DISCOVERY, lwt_payload, retain=True)
    client.loop_write() 
    client.disconnect()
    
    if has_wakelock:
        os.system("termux-wake-unlock")
        
    print("[SUCCESS] Disconnected cleanly.")