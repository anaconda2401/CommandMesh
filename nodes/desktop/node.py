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

# 2. Import the shared script whitelist
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

SECRET = os.getenv("MESH_SECRET")
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
    
    print(f"⚙️ Executing: {action} | Params: {params}")
    
    # --- METHOD 1: PARAMETERIZED ACTIONS ---
    if action == "open_url" and params:
        if params.startswith("http://") or params.startswith("https://"):
            webbrowser.open(params)
            
    elif action == "type_text" and params and pyautogui:
        pyautogui.write(params)
        
    elif action == "press_keys" and params and pyautogui:
        keys = [k.strip() for k in params.split(',')]
        pyautogui.hotkey(*keys)

    # --- METHOD 2: SECURE SCRIPT EXECUTION (WHITELISTED) ---
    elif action == "run_script" and params:
        safe_name = os.path.basename(params)
        
        # Security: Reject if not in config/allowed_scripts.py
        if safe_name not in ALLOWED_SCRIPTS:
            print(f"🚫 Security Block: Script '{safe_name}' is not in the whitelist.")
            return
            
        script_path = os.path.join(SCRIPTS_DIR, safe_name)
        
        if os.path.exists(script_path):
            print(f"🚀 Launching secure script: {safe_name}")
            try:
                # SAFE EXECUTION: shell=False prevents command injection
                if safe_name.endswith('.py'):
                    subprocess.Popen([sys.executable, script_path], shell=False)
                elif safe_name.endswith('.bat') or safe_name.endswith('.cmd'):
                    subprocess.Popen(["cmd.exe", "/c", script_path], shell=False)
                elif safe_name.endswith('.ps1'):
                    subprocess.Popen(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script_path], shell=False)
            except Exception as e:
                print(f"❌ Failed to run script: {e}")
        else:
            print(f"❌ Script not found in nodes/desktop/scripts/: {safe_name}")

    # --- STANDARD SYSTEM & MEDIA COMMANDS ---
    elif action == "open_youtube":
        subprocess.run(["cmd.exe", "/c", "start", "https://youtube.com"], shell=False, check=False)
    elif action == "lock_pc":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], shell=False, check=False)
    elif action == "home" and pyautogui:
        pyautogui.hotkey('win', 'd')
        
    elif action == "play_pause" and pyautogui:
        pyautogui.press('playpause')
    elif action == "vol_up" and pyautogui:
        pyautogui.press('volumeup', presses=2)
    elif action == "vol_down" and pyautogui:
        pyautogui.press('volumedown', presses=2)
        
    # --- D-PAD CONTROLS ---
    elif action == "dpad_up" and pyautogui:
        pyautogui.press('up')
    elif action == "dpad_down" and pyautogui:
        pyautogui.press('down')
    elif action == "dpad_left" and pyautogui:
        pyautogui.press('left')
    elif action == "dpad_right" and pyautogui:
        pyautogui.press('right')
    elif action == "dpad_center" and pyautogui:
        pyautogui.press('enter')

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"✅ Node '{DEVICE_ID}' connected.")
        client.subscribe(TOPIC_INBOX)
        status_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "online"})
        client.publish(TOPIC_DISCOVERY, status_payload, retain=True)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if data.get("to") != DEVICE_ID: return
        
        # Passes the whole payload to security check (which validates the 'mesh_admin' role)
        if not verify_message(SECRET, data): return
        
        execute_action(data)
    except Exception as e:
        print(f"Error processing message: {e}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
client.tls_set()
client.username_pw_set(USER, PASS)

lwt_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "offline"})
client.will_set(TOPIC_DISCOVERY, lwt_payload, retain=True)

client.on_connect = on_connect
client.on_message = on_message

print(f"🚀 Booting Node: {DEVICE_ID}...")
client.connect(BROKER, PORT, 60)
client.loop_forever()