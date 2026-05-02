import os
import sys
import json
import subprocess
from urllib.parse import urlparse
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Allow importing from the root 'lib' directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib.security import verify_message

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# --- TV / PHONE CONFIGURATION ---
DEVICE_ID = "living_room_tv"
DEVICE_NAME = "Android Smart TV"
DEVICE_TYPE = "tv"

SECRET = os.getenv("MESH_SECRET")
BROKER = os.getenv("MQTT_BROKER")
PORT = int(os.getenv("MQTT_PORT", 8883))
USER = os.getenv("MQTT_USERNAME")
PASS = os.getenv("MQTT_PASSWORD")

TOPIC_INBOX = f"commandmesh/{DEVICE_ID}/in"
TOPIC_DISCOVERY = f"commandmesh/discovery/{DEVICE_ID}"

def execute_action(payload_data):
    action = payload_data.get("action")
    params = payload_data.get("data")
    
    print(f"⚙️ Executing Android Action: {action} | Params: {params}")
    
    # --- SECURE PARAMETERIZED ACTIONS ---
    if action == "open_url" and params:
        parsed = urlparse(params)
        if parsed.scheme in ("http", "https"):
            # SAFE: Passed as a list to subprocess without shell=True
            subprocess.run(
                ["am", "start", "-a", "android.intent.action.VIEW", "-d", params],
                shell=False, check=False
            )
            
    elif action == "type_text" and params:
        # SAFE: Cannot break out of the string context
        subprocess.run(["input", "text", str(params)], shell=False, check=False)

    # --- STANDARD SYSTEM COMMANDS ---
    elif action == "home":
        subprocess.run(["input", "keyevent", "3"], shell=False, check=False)
    elif action == "lock_pc":
        subprocess.run(["input", "keyevent", "26"], shell=False, check=False)
    elif action == "open_youtube":
        # SAFE: Passed as a list, no shell interpolation
        subprocess.run(
            ["am", "start", "-a", "android.intent.action.VIEW", "-d", "https://www.youtube.com"],
            shell=False, check=False
        )
        
    # --- MEDIA CONTROLS ---
    elif action == "vol_up":
        subprocess.run(["input", "keyevent", "24"], shell=False, check=False)
    elif action == "vol_down":
        subprocess.run(["input", "keyevent", "25"], shell=False, check=False)
    elif action == "play_pause":
        subprocess.run(["input", "keyevent", "85"], shell=False, check=False)
        
    # --- D-PAD CONTROLS ---
    elif action == "dpad_up":
        subprocess.run(["input", "keyevent", "19"], shell=False, check=False)
    elif action == "dpad_down":
        subprocess.run(["input", "keyevent", "20"], shell=False, check=False)
    elif action == "dpad_left":
        subprocess.run(["input", "keyevent", "21"], shell=False, check=False)
    elif action == "dpad_right":
        subprocess.run(["input", "keyevent", "22"], shell=False, check=False)
    elif action == "dpad_center":
        subprocess.run(["input", "keyevent", "66"], shell=False, check=False)

    # --- SECURITY EXCLUSION ---
    elif action == "run_script":
        print("🛡️ Security Block: Scripts are not permitted on this device.")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"✅ Termux Node '{DEVICE_ID}' connected.")
        client.subscribe(TOPIC_INBOX)
        
        status_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "online"})
        client.publish(TOPIC_DISCOVERY, status_payload, retain=True)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if data.get("to") != DEVICE_ID: return
        
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

print(f"🚀 Booting Android Termux Node: {DEVICE_ID}...")
# Prevents Android from killing Termux in the background
os.system("termux-wake-lock") 

client.connect(BROKER, PORT, 60)
client.loop_forever()