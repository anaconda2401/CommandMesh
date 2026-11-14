"""CommandMesh unified CLI entry point: run node daemon or send one-shot commands."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ENV_FILE = Path(__file__).resolve().parent / ".env"
DEPS_FLAG = Path(__file__).resolve().parent / ".deps_installed"


def detect_device() -> str:
    """Auto-detect operating system platform."""
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        return "termux"
    return "desktop"


def install_dependencies(device_type: str, quiet: bool = False) -> None:
    """Silently install required node packages on first boot."""
    if DEPS_FLAG.exists():
        return

    req_file = Path(__file__).resolve().parent / "nodes" / device_type / "requirements.txt"
    if not req_file.exists():
        return

    if not quiet:
        print(f"[INFO] First boot detected. Installing dependencies from {req_file.name}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"],
            check=True,
        )
        DEPS_FLAG.touch()
        if not quiet:
            print("[SUCCESS] Dependencies installed.")
    except subprocess.CalledProcessError:
        print(f"[ERROR] Failed to auto-install dependencies. Run manually:\n pip install -r {req_file}")
        sys.exit(1)


def load_config() -> dict[str, str]:
    """Load configuration from environment and .env."""
    from dotenv import load_dotenv

    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=True)

    broker = os.getenv("MQTT_BROKER", "").strip()
    port = os.getenv("MQTT_PORT", "8883").strip()
    user = os.getenv("MQTT_USERNAME", "").strip()
    password = os.getenv("MQTT_PASSWORD", "").strip()
    passphrase = os.getenv("MESH_PASSPHRASE", "").strip()
    node_id = os.getenv("NODE_ID", "").strip()

    return {
        "broker": broker,
        "port": port,
        "user": user,
        "pass": password,
        "passphrase": passphrase,
        "node_id": node_id,
    }


def cmd_send(args: argparse.Namespace) -> None:
    """Handle 'python main.py send <target> <action> [data]'."""
    from lib.security import send_command

    cfg = load_config()
    missing = [k for k in ["broker", "user", "pass", "passphrase"] if not cfg.get(k)]
    if missing:
        print(f"[ERROR] Missing required configuration in .env: {', '.join(missing)}")
        print("[INFO]  Ensure MQTT credentials and MESH_PASSPHRASE are set.")
        sys.exit(1)

    sender_id = cfg.get("node_id") or "cli_admin"
    port = int(cfg.get("port") or 8883)

    target = args.target.strip()
    action = args.action.strip()
    data = args.data

    if not args.quiet:
        print(f"[CMD] Dispatching '{action}' -> '{target}'...")

    res = send_command(
        broker=cfg["broker"],
        port=port,
        username=cfg["user"],
        password=cfg["pass"],
        passphrase=cfg["passphrase"],
        sender_id=sender_id,
        target=target,
        action=action,
        data=data,
        timeout=args.timeout,
    )

    if res.get("success"):
        output = res.get("output", "")
        status = res.get("status", "success")
        msg = f"[OK] Device '{target}' ACK ({status})"
        if output:
            msg += f": {output}"
        print(msg)
        sys.exit(0)
    else:
        err = res.get("error", "failed")
        msg = res.get("message") or res.get("output") or err
        print(f"[ERROR] '{target}' execution failed ({err}): {msg}", file=sys.stderr)
        sys.exit(1)


def test_connection(creds: dict[str, str], quiet: bool = False) -> None:
    """Verify connectivity and TLS authentication to MQTT broker."""
    import paho.mqtt.client as mqtt

    if not quiet:
        print("[SYSTEM] Testing secure connection to cloud relay...")
    connected = False
    error_msg = None

    def on_connect(client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
        nonlocal connected, error_msg
        if rc == 0:
            connected = True
        else:
            error_msg = f"Connection refused (code: {rc})"
        client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.tls_set()
    client.username_pw_set(creds["user"], creds["pass"])
    client.on_connect = on_connect

    try:
        client.connect(creds["broker"], int(creds.get("port") or 8883), 10)
        client.loop_start()

        timeout = 5.0
        start_time = time.time()
        while not connected and error_msg is None and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        client.loop_stop()
        if not connected and error_msg is None:
            error_msg = "Connection timed out."
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Network Error: Could not reach broker: {exc}", file=sys.stderr)
        sys.exit(1)

    if not connected:
        print(f"[ERROR] Authentication Failed: {error_msg}", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print("[SUCCESS] Cloud relay authentication successful.")


def cmd_run(args: argparse.Namespace) -> None:
    """Handle running the node daemon (default)."""
    device_type = detect_device()
    install_dependencies(device_type, quiet=args.quiet)

    cfg = load_config()
    missing = [k for k in ["broker", "user", "pass", "passphrase"] if not cfg.get(k)]
    if missing:
        print(f"[ERROR] Missing required configuration: {', '.join(missing)}")
        print("[INFO]  Copy .env.example to .env and fill in your credentials and MESH_PASSPHRASE.")
        sys.exit(1)

    if not args.quiet:
        print("=" * 40)
        print(" CommandMesh Node Launcher ".center(40, "="))
        print("=" * 40)
        print(f"[INFO] Environment detected: {device_type.capitalize()}")

    test_connection(cfg, quiet=args.quiet)

    node_script = Path(__file__).resolve().parent / "nodes" / device_type / "node.py"
    if not node_script.exists():
        print(f"[ERROR] Could not find {node_script}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"[INFO] Handing over to {device_type} module...\n" + "-" * 40)

    env = os.environ.copy()
    if args.quiet:
        env["LOG_LEVEL"] = "WARNING"

    try:
        subprocess.run([sys.executable, "-O", str(node_script)], env=env, check=False)
    except KeyboardInterrupt:
        if not args.quiet:
            print("\n[INFO] Mesh node shutdown gracefully.")
        sys.exit(0)


def main() -> None:
    """Main CLI argument dispatcher."""
    parser = argparse.ArgumentParser(
        prog="commandmesh",
        description="CommandMesh: Lightweight, peer-to-peer encrypted IoT device mesh.",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output (minimal logging)")

    subparsers = parser.add_subparsers(dest="command")

    # 'run' subcommand (also default)
    run_parser = subparsers.add_parser("run", help="Launch the local device node in daemon mode")
    run_parser.add_argument("-q", "--quiet", action="store_true", help="Minimal logging")

    # 'send' subcommand
    send_parser = subparsers.add_parser("send", help="Send a one-shot command to a remote mesh node")
    send_parser.add_argument("target", help="Target node ID (e.g. 'laptop', 'tv', 'all')")
    send_parser.add_argument("action", help="Action to execute (e.g. 'vol_up', 'home', 'open_youtube')")
    send_parser.add_argument("data", nargs="?", default=None, help="Optional data parameter (e.g. URL, text)")
    send_parser.add_argument("-t", "--timeout", type=float, default=5.0, help="ACK timeout in seconds (default: 5.0)")
    send_parser.add_argument("-q", "--quiet", action="store_true", help="Minimal logging")

    args = parser.parse_args()

    if args.command == "send":
        cmd_send(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
