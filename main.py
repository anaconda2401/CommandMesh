import os
import sys
import subprocess
import time

def detect_device():
    """Auto-detects the operating system."""
    print("🤖 Analyzing hardware environment...")
    
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        print("📱 Environment detected: Android (Termux)")
        return "termux"
    else:
        print("💻 Environment detected: Desktop (Windows/Mac/Linux)")
        return "desktop"

def install_dependencies(device_type):
    """Silently installs the required packages for the detected device."""
    # Updated to look inside the specific node's folder!
    req_file = os.path.join("nodes", device_type, "requirements.txt")
    
    if not os.path.exists(req_file):
        print(f"⚠️ Warning: Missing {req_file}. Skipping auto-install.")
        return

    print(f"📦 Verifying dependencies from {req_file}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            check=True
        )
    except subprocess.CalledProcessError:
        print(f"❌ Error: Failed to auto-install dependencies. Try running manually:\n pip install -r {req_file}")
        sys.exit(1)

# ==========================================
# Phase 1: Environment Setup & Installation
# ==========================================
print("="*40)
print(" CommandMesh Node Launcher ".center(40, "="))
print("="*40)

# Detect the hardware and install the correct packages first
device_type = detect_device()
install_dependencies(device_type)

# ==========================================
# Phase 2: Imports & Execution
# ==========================================
# Now that pip install has run, it is safe to import external libraries!
try:
    import paho.mqtt.client as mqtt
    from dotenv import load_dotenv
except ImportError as e:
    print(f"❌ Critical Error: Modules failed to load even after installation. ({e})")
    sys.exit(1)

def check_env():
    """Validates that all required security keys are present in .env."""
    print("🔍 Checking configuration...")
    load_dotenv()
    
    required_keys = ["MQTT_BROKER", "MQTT_PORT", "MQTT_USERNAME", "MQTT_PASSWORD", "MESH_SECRET"]
    missing = [key for key in required_keys if not os.getenv(key)]
    
    if missing:
        print(f"❌ Missing critical .env variables: {', '.join(missing)}")
        sys.exit(1)
    
    print("✅ Configuration loaded.")
    return {
        "broker": os.getenv("MQTT_BROKER"),
        "port": int(os.getenv("MQTT_PORT", 8883)),
        "user": os.getenv("MQTT_USERNAME"),
        "pass": os.getenv("MQTT_PASSWORD")
    }

def test_connection(creds):
    """Performs a live pre-flight check to HiveMQ to verify credentials."""
    print("📡 Testing secure connection to cloud relay...")
    
    connected = False
    error_msg = None

    def on_connect(client, userdata, flags, reason_code, properties=None):
        nonlocal connected, error_msg
        if reason_code == 0:
            connected = True
            print("✅ Cloud relay authentication successful.")
        else:
            error_msg = f"Connection refused (Code: {reason_code})"
        client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.tls_set()
    client.username_pw_set(creds["user"], creds["pass"])
    client.on_connect = on_connect

    try:
        client.connect(creds["broker"], creds["port"], 10)
        client.loop_forever()
    except Exception as e:
        print(f"❌ Network Error: Could not reach HiveMQ server. {e}")
        sys.exit(1)

    if not connected:
        print(f"❌ Authentication Failed: {error_msg}")
        sys.exit(1)

def launch_node(node_type):
    """Executes the specific Python node script in a child process."""
    node_script = os.path.join("nodes", node_type, "node.py")  # nodes/{desktop|termux}/node.py
    
    if not os.path.exists(node_script):
        print(f"❌ Critical Error: Could not find node script at {node_script}")
        sys.exit(1)
        
    print(f"🚀 Handing over to {node_type} module...\n" + "-"*40)
    
    try:
        subprocess.run([sys.executable, node_script])
    except KeyboardInterrupt:
        print("\n🛑 Mesh node shutdown gracefully.")

if __name__ == "__main__":
    creds = check_env()
    test_connection(creds)
    launch_node(device_type)