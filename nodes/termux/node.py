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

# --- CONFIGURATION ---
DEVICE_ID = os.getenv("NODE_ID", "tv_node")
DEVICE_NAME = os.getenv("NODE_NAME", "Android TV")
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
# EXECUTION MODE DETECTION
# ==========================================
try:
    IS_NATIVE_ROOT = os.geteuid() == 0
except AttributeError:
    IS_NATIVE_ROOT = False

ROOT_SHELL = None

def init_persistent_shell():
    
    global ROOT_SHELL
    try:
        ROOT_SHELL = subprocess.Popen(
            ["su"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1
        )
    except Exception as e:
        print(f"[FATAL] Failed to start persistent root shell: {e}")
        sys.exit(1)

def detect_termux_mode():
    if IS_NATIVE_ROOT: return "native_root"
    if shutil.which("su"): return "su_wrapper"
    if shutil.which("adb"): return "adb"
    print("\n[FATAL] No execution method found!")
    sys.exit(1)

TERMUX_MODE = detect_termux_mode()

if TERMUX_MODE == "su_wrapper":
    init_persistent_shell()

# ==========================================
# BOOT DIAGNOSTICS (ASCII ONLY)
# ==========================================
print("\n" + "="*40)
print(f" NODE: {DEVICE_NAME}")
print("="*40)

if TERMUX_MODE == "native_root":
    print(" MODE: [OK] NATIVE ROOT (0-Latency)")
elif TERMUX_MODE == "su_wrapper":
    print(" MODE: [*] SU PERSISTENT SHELL (Ultra-Fast)")
else:
    print(f" MODE: [*] ADB -> {ADB_TARGET}")

if shutil.which("termux-wake-lock"):
    os.system("termux-wake-lock")
    print(" WAKE: [OK] Background lock active")
else:
    print(" WAKE: [FAIL] termux-api missing")

print(f" MQTT: Connecting to broker...")
print("="*40 + "\n")

# ==========================================
# COMMAND ROUTER (MEMORY OPTIMIZED & SAFE)
# ==========================================
def run_android_cmd(cmd_list):
    global ROOT_SHELL
    try:
        if TERMUX_MODE == "native_root":
            res = subprocess.run(cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            return res.returncode == 0, "Executed"
            
        elif TERMUX_MODE == "su_wrapper":
            # 1. Check if the shell unexpectedly died. Restart if necessary.
            if ROOT_SHELL.poll() is not None:
                print("[WARNING] Root shell died. Restarting...")
                init_persistent_shell()
                
            # 2. Format safely and pipe instantly into the open shell
            safe_cmd_str = shlex.join(cmd_list)
            ROOT_SHELL.stdin.write(f"{safe_cmd_str}\n")
            ROOT_SHELL.stdin.flush()
            
            # Fire-and-forget successful write
            return True, "Executed (Piped)"
            
        else:
            # ADB Mode
            res = subprocess.run(["adb", "-s", ADB_TARGET, "shell"] + cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            if res.returncode != 0:
                subprocess.run(["adb", "connect", ADB_TARGET], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                res = subprocess.run(["adb", "-s", ADB_TARGET, "shell"] + cmd_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            return res.returncode == 0, "Executed"

    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, f"Error: {str(e)}"

# ==========================================
# ACTION HANDLER
# ==========================================
def execute_action(payload_data):
    action = payload_data.get("action")
    params = payload_data.get("data")
    
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
        return False, "Blocked"
        
    return False, "Unknown"

# ==========================================
# MQTT SETUP
# ==========================================
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[MQTT] [OK] Connected!")
        client.subscribe(TOPIC_INBOX)
        
        status_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "online"})
        client.publish(TOPIC_DISCOVERY, status_payload, retain=True)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if data.get("to") != DEVICE_ID: return
        if not verify_message(data): return 
            
        success, detail = execute_action(data)
        
        msg_id = data.get("msg_id")
        if msg_id:
            ack_payload = {
                "id": DEVICE_ID,
                "msg_id": msg_id,
                "action": data.get("action"),
                "status": "success" if success else "error",
                "message": detail
            }
            client.publish(TOPIC_OUTBOX, json.dumps(ack_payload))
            print(f"[ACK] {msg_id}")
            
    except json.JSONDecodeError:
        pass 
    except Exception as e:
        print(f"[ERR] {e}")

# Downgraded to MQTTv311 for lower memory footprint
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
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
    
    # Safely close the persistent shell pipe
    if ROOT_SHELL is not None and ROOT_SHELL.poll() is None:
        try:
            ROOT_SHELL.stdin.close()
            ROOT_SHELL.terminate()
        except Exception:
            pass
            
    client.publish(TOPIC_DISCOVERY, lwt_payload, retain=True)
    client.loop_write() 
    client.disconnect()
    
    if shutil.which("termux-wake-lock"):
        os.system("termux-wake-unlock")
        
    print("[OK] Disconnected.")