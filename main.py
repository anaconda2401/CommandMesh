import os
import sys
import subprocess

ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
DEPS_FLAG = os.path.abspath(os.path.join(os.path.dirname(__file__), ".deps_installed"))

def detect_device():
    """Auto-detects the operating system."""
    print("[SYSTEM] Analyzing hardware environment...")
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        print("[INFO] Environment detected: Android (Termux)")
        return "termux"
    else:
        print("[INFO] Environment detected: Desktop (Windows/Mac/Linux)")
        return "desktop"

def install_dependencies(device_type):
    """Silently installs required packages exactly once."""
    if os.path.exists(DEPS_FLAG):
        return

    req_file = os.path.join("nodes", device_type, "requirements.txt")
    if not os.path.exists(req_file):
        print(f"[WARNING] Missing {req_file}. Skipping auto-install.")
        return

    print(f"[INFO] First boot detected. Installing dependencies from {req_file}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            check=True
        )
        open(DEPS_FLAG, 'w').close()
        print("[SUCCESS] Dependencies installed.")
    except subprocess.CalledProcessError:
        print(f"[ERROR] Failed to auto-install dependencies. Run manually:\n pip install -r {req_file}")
        sys.exit(1)

# ==========================================
# Phase 1: Environment Setup & Installation
# ==========================================
print("="*40)
print(" CommandMesh Node Launcher ".center(40, "="))
print("="*40)

device_type = detect_device()
install_dependencies(device_type)

# ==========================================
# Phase 2: Safe Imports
# ==========================================
try:
    import paho.mqtt.client as mqtt
    from dotenv import load_dotenv
except ImportError as e:
    print(f"[ERROR] Critical Error: Modules failed to load. ({e})")
    print("[INFO] Attempting to fix... deleting .deps_installed flag.")
    if os.path.exists(DEPS_FLAG):
        os.remove(DEPS_FLAG)
    sys.exit(1)

# ==========================================
# Phase 3: Core Execution & Logic
# ==========================================
import time

def test_connection(creds):
    print("[SYSTEM] Testing secure connection to cloud relay...")
    connected, error_msg = False, None

    def on_connect(client, userdata, flags, rc, *args):
        nonlocal connected, error_msg
        if rc == 0:
            connected = True
            print("[SUCCESS] Cloud relay authentication successful.")
        else:
            error_msg = f"Connection refused (Code: {rc})"
        client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.tls_set()
    client.username_pw_set(creds["user"], creds["pass"])
    client.on_connect = on_connect

    try:
        client.connect(creds["broker"], 8883, 10)
        client.loop_start()

        timeout = 5
        start_time = time.time()
        while not connected and error_msg is None and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        client.loop_stop()

        if not connected and error_msg is None:
            error_msg = "Connection timed out."

    except Exception as e:
        print(f"[ERROR] Network Error: Could not reach broker. {e}")
        sys.exit(1)

    if not connected:
        print(f"[ERROR] Authentication Failed: {error_msg}")
        sys.exit(1)

def launch_node(node_type):
    node_script = os.path.join("nodes", node_type, "node.py")
    if not os.path.exists(node_script):
        print(f"[ERROR] Critical Error: Could not find {node_script}")
        sys.exit(1)

    print(f"[INFO] Handing over to {node_type} module...\n" + "-"*40)
    try:
        subprocess.run([sys.executable, "-O", node_script])
    except KeyboardInterrupt:
        print("\n[INFO] Mesh node shutdown gracefully.")
        sys.exit(0)

# ==========================================
# Phase 4: Main Boot Sequence
# ==========================================
if __name__ == "__main__":
    load_dotenv(ENV_FILE, override=True)

    creds = {
        "broker": os.getenv("MQTT_BROKER"),
        "user":   os.getenv("MQTT_USERNAME"),
        "pass":   os.getenv("MQTT_PASSWORD"),
    }

    missing = [k for k, v in creds.items() if not v]
    if missing:
        print(f"[ERROR] Missing required configuration: {', '.join(missing)}")
        print("[INFO]  Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    test_connection(creds)
    launch_node(device_type)