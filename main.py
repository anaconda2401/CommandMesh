import os
import sys
import subprocess
import time
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))

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
    """Silently installs the required packages for the detected device."""
    req_file = os.path.join("nodes", device_type, "requirements.txt")
    if not os.path.exists(req_file):
        print(f"[WARNING] Missing {req_file}. Skipping auto-install.")
        return

    print(f"[INFO] Verifying dependencies from {req_file}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            check=True
        )
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
    from dotenv import load_dotenv, set_key
except ImportError as e:
    print(f"[ERROR] Critical Error: Modules failed to load. ({e})")
    sys.exit(1)

# ==========================================
# Phase 3: Web Dashboard Server
# ==========================================
import html
import secrets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

# F-02 Fix: Generate a secure, randomized CSRF token for this session
CSRF_TOKEN = secrets.token_hex(16)

class ConfigDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        load_dotenv(ENV_FILE, override=True)
        
        # F-06 Fix: Neutralize Stored XSS by escaping environment variables
        broker = html.escape(os.getenv("MQTT_BROKER", ""))
        username = html.escape(os.getenv("MQTT_USERNAME", ""))
        public_keys = html.escape(os.getenv("MESH_PUBLIC_KEYS", ""))

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>CommandMesh Setup</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {{ --bg: #0f0f0f; --surface: #1e1e1e; --primary: #00ffaa; --text: #ffffff; }}
                body {{ font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); display: flex; justify-content: center; padding: 20px; margin: 0; }}
                .container {{ background: var(--surface); padding: 30px; border-radius: 10px; width: 100%; max-width: 400px; border: 1px solid #333; }}
                h2 {{ color: var(--primary); text-align: center; margin-top: 0; }}
                label {{ font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
                input {{ width: 100%; padding: 12px; margin: 8px 0 20px; background: #222; color: #fff; border: 1px solid #333; border-radius: 8px; box-sizing: border-box; font-size: 14px; }}
                button {{ width: 100%; padding: 15px; background: #333; color: var(--text); border: 1px solid #444; border-radius: 10px; font-size: 15px; cursor: pointer; transition: 0.2s; }}
                button:hover {{ background: var(--primary); color: #000; border-color: var(--primary); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Node Setup</h2>
                <form method="POST">
                    <!-- F-02 Fix: Inject CSRF Token -->
                    <input type="hidden" name="csrf_token" value="{CSRF_TOKEN}">
                    
                    <label>MQTT Broker URL</label>
                    <input type="text" name="MQTT_BROKER" value="{broker}" placeholder="e.g., wss://cluster.hivemq.cloud:8884/mqtt" required>

                    <label>MQTT Username</label>
                    <input type="text" name="MQTT_USERNAME" value="{username}" required>

                    <label>MQTT Password</label>
                    <input type="password" name="MQTT_PASSWORD" placeholder="Enter password to update">

                    <label>Mesh Public Keys (VIP List)</label>
                    <input type="text" name="MESH_PUBLIC_KEYS" value="{public_keys}" placeholder="Paste your public hex key here" required>
                    
                    <button type="submit">Save & Boot Node</button>
                </form>
            </div>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        parsed_data = parse_qs(post_data)

        # F-02 Fix: Strictly validate the CSRF token
        submitted_token = parsed_data.get("csrf_token", [""])[0]
        if not secrets.compare_digest(submitted_token, CSRF_TOKEN):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Security Block: CSRF token validation failed.")
            print("[SECURITY] CSRF Attack Blocked.")
            return

        if not os.path.exists(ENV_FILE):
            open(ENV_FILE, 'a').close()

        valid_keys = ["MQTT_BROKER", "MQTT_USERNAME", "MQTT_PASSWORD", "MESH_PUBLIC_KEYS"]
        for key in valid_keys:
            if key in parsed_data and parsed_data[key][0].strip():
                set_key(ENV_FILE, key, parsed_data[key][0].strip())

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        success_html = """
        <div style="font-family: system-ui, sans-serif; background: #0f0f0f; color: #fff; text-align: center; padding: 50px;">
            <h2 style="color: #00ffaa;">✅ Saved & Secured!</h2>
            <p style="color: #888;">Configuration applied. The local server is shutting down.</p>
        </div>
        """
        self.wfile.write(success_html.encode('utf-8'))
        
        # F-05 Fix: Terminate the dashboard thread cleanly after a successful setup
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        pass

def run_dashboard():
    host, port = '127.0.0.1', 8080
    server = HTTPServer((host, port), ConfigDashboardHandler)
    server.serve_forever()
    
# ==========================================
# Phase 4: Core Execution & Logic
# ==========================================
def get_missing_keys():
    load_dotenv(ENV_FILE, override=True)
    required = ["MQTT_BROKER", "MQTT_USERNAME", "MQTT_PASSWORD", "MESH_PUBLIC_KEYS"]
    return [k for k in required if not os.getenv(k)]

def test_connection(creds):
    print("[SYSTEM] Testing secure connection to cloud relay...")
    connected, error_msg = False, None

    def on_connect(client, userdata, flags, reason_code, properties=None):
        nonlocal connected, error_msg
        if reason_code == 0:
            connected = True
            print("[SUCCESS] Cloud relay authentication successful.")
        else:
            error_msg = f"Connection refused (Code: {reason_code})"
        client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.tls_set()
    client.username_pw_set(creds["user"], creds["pass"])
    client.on_connect = on_connect

    try:
        client.connect(creds["broker"], 8883, 10)
        client.loop_forever()
    except Exception as e:
        print(f"[ERROR] Network Error: Could not reach HiveMQ server. {e}")
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
        subprocess.run([sys.executable, node_script])
    except KeyboardInterrupt:
        print("\n[INFO] Mesh node shutdown gracefully.")
        sys.exit(0)

# ==========================================
# Phase 5: Main Boot Sequence
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--dashboard", action="store_true", help="Force launch the config dashboard")
    args = parser.parse_args()

    missing_keys = get_missing_keys()

    # If keys are missing OR the user forced the dashboard with '-d'
    if missing_keys or args.dashboard:
        if not os.path.exists(ENV_FILE):
            open(ENV_FILE, 'w').close()
            print("[INFO] Created new empty .env file.")
            
        print("\n[SYSTEM] Launching Setup Dashboard...")
        print("[INFO] GO TO: http://127.0.0.1:8080 in your browser to configure.")
        
        threading.Thread(target=run_dashboard, daemon=True).start()
        
        # Pause the script until the user saves the form and all keys exist
        while get_missing_keys():
            time.sleep(1)
        print("\n[SUCCESS] Configuration received! Proceeding...")

    # Load final confirmed credentials
    load_dotenv(ENV_FILE, override=True)
    creds = {
        "broker": os.getenv("MQTT_BROKER"),
        "user": os.getenv("MQTT_USERNAME"),
        "pass": os.getenv("MQTT_PASSWORD")
    }
    
    test_connection(creds)
    launch_node(device_type)