import os
import sys
import json
import subprocess
import webbrowser
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# 1. Allow importing from the root 'lib' and 'config' directories
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.security import verify_message
from config.allowed_scripts import ALLOWED_SCRIPTS

try:
    import pyautogui
except ImportError:
    pyautogui = None

# Load secrets from the root .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# --- CONFIGURATION ---
DEVICE_ID = "desktop_main"
DEVICE_NAME = "My Laptop"
DEVICE_TYPE = "pc"

BROKER = os.getenv("MQTT_BROKER")
PORT = int(os.getenv("MQTT_PORT", 8883))
USER = os.getenv("MQTT_USERNAME")
PASS = os.getenv("MQTT_PASSWORD")

TOPIC_INBOX = f"commandmesh/{DEVICE_ID}/in"
TOPIC_DISCOVERY = f"commandmesh/discovery/{DEVICE_ID}"

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)

def execute_action(payload_data):
    action = payload_data.get("action")
    params = payload_data.get("data")
    
    print(f"[INFO] Executing: {action} | Params: {params}")
    
    # --- METHOD 1: URL ACTIONS ---
    if action == "open_url" and params:
        if params.startswith("http://") or params.startswith("https://"):
            webbrowser.open(params)

    # --- METHOD 2: SECURE SCRIPT EXECUTION (WHITELISTED) ---
    elif action == "run_script" and params:
        safe_name = os.path.basename(params)
        
        # Security: Reject if not in config/allowed_scripts.py
        if safe_name not in ALLOWED_SCRIPTS:
            print(f"[SECURITY] Block: Script '{safe_name}' is not in the whitelist.")
            return
            
        script_path = os.path.join(SCRIPTS_DIR, safe_name)
        
        if os.path.exists(script_path):
            print(f"[INFO] Launching secure script: {safe_name}")
            try:
                # SAFE EXECUTION: shell=False prevents command injection
                if safe_name.endswith('.py'):
                    subprocess.Popen([sys.executable, script_path], shell=False)
                elif safe_name.endswith('.bat') or safe_name.endswith('.cmd'):
                    subprocess.Popen(["cmd.exe", "/c", script_path], shell=False)
                elif safe_name.endswith('.ps1'):
                    subprocess.Popen(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script_path], shell=False)
            except Exception as e:
                print(f"[ERROR] Failed to run script: {e}")
        else:
            print(f"[ERROR] Script not found in nodes/desktop/scripts/: {safe_name}")

    # --- STANDARD SYSTEM & MEDIA COMMANDS ---
    elif action == "open_youtube":
        subprocess.run(["cmd.exe", "/c", "start", "https://youtube.com"], shell=False, check=False)
    elif action == "lock_pc":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], shell=False, check=False)
        
    # --- PYAUTOGUI DEPENDENT ACTIONS ---
    # We group all GUI actions together to handle the missing dependency cleanly
    elif action in ["type_text", "press_keys", "home", "play_pause", "vol_up", "vol_down", 
                    "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad_center"]:
        
        if not pyautogui:
            print(f"[WARNING] Cannot execute '{action}' — pyautogui is not installed on this system.")
            return

        if action == "type_text" and params:
            pyautogui.write(params)
        elif action == "press_keys" and params:
            keys = [k.strip() for k in params.split(',')]
            pyautogui.hotkey(*keys)
        elif action == "home":
            pyautogui.hotkey('win', 'd')
        elif action == "play_pause":
            pyautogui.press('playpause')
        elif action == "vol_up":
            pyautogui.press('volumeup', presses=2)
        elif action == "vol_down":
            pyautogui.press('volumedown', presses=2)
        elif action == "dpad_up":
            pyautogui.press('up')
        elif action == "dpad_down":
            pyautogui.press('down')
        elif action == "dpad_left":
            pyautogui.press('left')
        elif action == "dpad_right":
            pyautogui.press('right')
        elif action == "dpad_center":
            pyautogui.press('enter')

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[SUCCESS] Node '{DEVICE_ID}' connected.")
        client.subscribe(TOPIC_INBOX)
        status_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "online"})
        client.publish(TOPIC_DISCOVERY, status_payload, retain=True)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if data.get("to") != DEVICE_ID: return
        
        # Passes the payload to security check (no secret passed!)
        if not verify_message(data): return
        
        execute_action(data)
    except Exception as e:
        print(f"Error processing message: {e}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
client.tls_set()
client.username_pw_set(USER, PASS)

# Setup Last Will and Testament for unexpected drops (e.g., losing wifi)
lwt_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "offline"})
client.will_set(TOPIC_DISCOVERY, lwt_payload, retain=True)

client.on_connect = on_connect
client.on_message = on_message

print(f"[INFO] Booting Node: {DEVICE_ID}...")

# Graceful Disconnect Handling
try:
    client.connect(BROKER, PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print(f"\n[INFO] Shutting down '{DEVICE_ID}'. Broadcasting offline status...")
    # Manually publish offline payload and force flush the network buffer
    client.publish(TOPIC_DISCOVERY, lwt_payload, retain=True)
    client.loop_write() 
    client.disconnect()
    print("[SUCCESS] Disconnected cleanly.")