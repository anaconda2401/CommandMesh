import os
import hmac
import hashlib
import time

# Load the required role (defaults to mesh_admin)
REQUIRED_ROLE = os.getenv("REQUIRED_ROLE", "mesh_admin")

def verify_message(secret: str, data: dict, max_age: int = 10) -> bool:
    try:
        # 1. Replay Attack Prevention
        if (time.time() - data['timestamp']) > max_age:
            print("🧟 Rejected: Message expired.")
            return False

        # 2. ROLE-BASED AUTHORIZATION (The Fix)
        # Instead of checking WHO sent it, we check if they are claiming the Admin Role
        sender_role = data.get('from')
        if sender_role != REQUIRED_ROLE:
            print(f"🚫 Rejected: Sender does not have the '{REQUIRED_ROLE}' role.")
            return False

        # 3. Cryptographic Signature Validation
        # If they don't actually have the MESH_SECRET, this math will fail, 
        # proving they are a fake admin.
        msg = f"{data['action']}:{sender_role}:{data['to']}:{data['timestamp']}"
        expected_sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(expected_sig, data['signature']):
            return True
            
        print("🛑 Rejected: Invalid Signature! Fake admin detected.")
        return False
        
    except KeyError:
        print("⚠️ Rejected: Malformed payload.")
        return False