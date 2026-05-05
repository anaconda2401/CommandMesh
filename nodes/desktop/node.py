import os
import sys
import json
import subprocess
import webbrowser
import platform
import threading
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
DEVICE_ID = os.getenv("NODE_ID", "desktop_fallback")
DEVICE_NAME = os.getenv("NODE_NAME", "Unnamed PC")
DEVICE_TYPE = "pc"

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 8883))
USER = os.getenv("MQTT_USERNAME", "")
PASS = os.getenv("MQTT_PASSWORD", "")

TOPIC_INBOX = f"commandmesh/{DEVICE_ID}/in"
TOPIC_OUTBOX = f"commandmesh/{DEVICE_ID}/out" # NEW: ACK Outbox
TOPIC_DISCOVERY = f"commandmesh/discovery/{DEVICE_ID}"

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)

OS_NAME = platform.system()

# ==========================================
# COMMAND EXECUTION ROUTER
# ==========================================
def execute_action(payload_data):
    """Returns a tuple (success_boolean, detail_message) for the optional ACK."""
    action = payload_data.get("action")
    params = payload_data.get("data")
    
    # --- METHOD 1: URL ACTIONS (Non-blocking) ---
    if action == "open_url" and params:
        if params.startswith("http://") or params.startswith("https://"):
            threading.Thread(target=webbrowser.open, args=(params,), daemon=True).start()
            return True, "URL Opened"

    # --- METHOD 2: SECURE SCRIPT EXECUTION (WHITELISTED) ---
    elif action == "run_script" and params:
        safe_name = os.path.basename(params)
        
        if safe_name not in ALLOWED_SCRIPTS:
            return False, f"Security Block: '{safe_name}' not in whitelist."
            
        script_path = os.path.join(SCRIPTS_DIR, safe_name)
        
        if os.path.exists(script_path):
            # kwargs to prevent memory leaks from capturing huge text outputs in the background
            sb_kwargs = {"shell": False, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            try:
                if safe_name.endswith('.py'):
                    subprocess.Popen([sys.executable, script_path], **sb_kwargs)
                elif safe_name.endswith(('.bat', '.cmd')) and OS_NAME == "Windows":
                    subprocess.Popen(["cmd.exe", "/c", script_path], **sb_kwargs)
                elif safe_name.endswith('.ps1'):
                    ps_exe = "powershell.exe" if OS_NAME == "Windows" else "pwsh"
                    subprocess.Popen([ps_exe, "-ExecutionPolicy", "Bypass", "-File", script_path], **sb_kwargs)
                elif safe_name.endswith('.sh') and OS_NAME in ["Linux", "Darwin"]:
                    subprocess.Popen(["bash", script_path], **sb_kwargs)
                else:
                    return False, f"OS mismatch for script '{safe_name}'"
                
                return True, f"Script '{safe_name}' launched"
            except Exception as e:
                return False, f"Script error: {e}"
        else:
            return False, f"File not found: '{safe_name}'"

    # --- STANDARD SYSTEM & MEDIA COMMANDS ---
    elif action == "open_youtube":
        threading.Thread(target=webbrowser.open, args=("https://youtube.com",), daemon=True).start()
        return True, "YouTube Opened"
        
    elif action == "lock_pc":
        try:
            sb_kwargs = {"shell": False, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "timeout": 5}
            if OS_NAME == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], **sb_kwargs)
            elif OS_NAME == "Darwin":
                subprocess.run(["pmset", "displaysleepnow"], **sb_kwargs)
            elif OS_NAME == "Linux":
                subprocess.run(["xdg-screensaver", "lock"], **sb_kwargs)
            return True, "PC Locked"
        except subprocess.TimeoutExpired:
            return False, "Lock command timed out"
        except Exception:
            return False, "Lock command failed"
        
    # --- PYAUTOGUI DEPENDENT ACTIONS ---
    elif action in ["type_text", "press_keys", "home", "play_pause", "vol_up", "vol_down", 
                    "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad_center"]:
        
        if not pyautogui:
            return False, "pyautogui library missing"
            
        if OS_NAME == "Linux" and "DISPLAY" not in os.environ:
             return False, "Linux headless mode detected. GUI actions disabled."

        try:
            if action == "type_text" and params:
                pyautogui.write(params)
            elif action == "press_keys" and params:
                keys = [k.strip() for k in params.split(',')]
                pyautogui.hotkey(*keys)
            elif action == "home":
                if OS_NAME == "Windows": pyautogui.hotkey('win', 'd')
                elif OS_NAME == "Darwin": pyautogui.hotkey('command', 'f3')
                elif OS_NAME == "Linux": pyautogui.hotkey('ctrl', 'super', 'd')
            elif action == "play_pause": pyautogui.press('playpause')
            elif action == "vol_up": pyautogui.press('volumeup', presses=2)
            elif action == "vol_down": pyautogui.press('volumedown', presses=2)
            elif action == "dpad_up": pyautogui.press('up')
            elif action == "dpad_down": pyautogui.press('down')
            elif action == "dpad_left": pyautogui.press('left')
            elif action == "dpad_right": pyautogui.press('right')
            elif action == "dpad_center": pyautogui.press('enter')
            
            return True, "Key executed"
        except Exception as e:
            return False, f"GUI error: {e}"

    return False, f"Unknown action: {action}"

# ==========================================
# MQTT SETUP (WITH HYBRID ACK)
# ==========================================
def on_connect(client, userdata, flags, rc, *args):
    if rc == 0:
        print(f"[MQTT] [*] Node '{DEVICE_ID}' ({OS_NAME}) connected successfully.")
        client.subscribe(TOPIC_INBOX)
        status_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "online"})
        client.publish(TOPIC_DISCOVERY, status_payload, retain=True)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if data.get("to") != DEVICE_ID: return
        if not verify_message(data): return
        
        success, detail = execute_action(data)
        
        # HYBRID ACK SYSTEM: Only reply if the sender attached a msg_id
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
            # Minimal quiet logging
            print(f"[ACK] Sent for {msg_id}")
            
    except json.JSONDecodeError:
        pass # Silently drop garbage payloads
    except Exception as e:
        print(f"[ERR] Fault in message processing: {e}")

# Downgraded to MQTTv311 to match launcher and save RAM
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
client.tls_set()
client.username_pw_set(USER, PASS)

lwt_payload = json.dumps({"id": DEVICE_ID, "name": DEVICE_NAME, "type": DEVICE_TYPE, "status": "offline"})
client.will_set(TOPIC_DISCOVERY, lwt_payload, retain=True)

client.on_connect = on_connect
client.on_message = on_message

print("\n" + "="*40)
print(f" NODE: {DEVICE_NAME} ({OS_NAME})")
print("="*40)
print(f" MODE: [*] DESKTOP EXECUTION LAYER")
print(f" MQTT: Connecting to broker...")
print("="*40 + "\n")

try:
    client.connect(BROKER, PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print(f"\n[INFO] Shutting down '{DEVICE_ID}'...")
    client.publish(TOPIC_DISCOVERY, lwt_payload, retain=True)
    client.loop_write() 
    client.disconnect()
    print("[OK] Disconnected cleanly.")