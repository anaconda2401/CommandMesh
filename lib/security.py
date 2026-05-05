import os
import time
from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError

REQUIRED_ROLE = os.getenv("REQUIRED_ROLE", "mesh_admin")
PUB_KEYS_STR = os.getenv("MESH_PUBLIC_KEYS", "")

VERIFIERS = []
for pk_hex in PUB_KEYS_STR.split(","):
    pk_hex = pk_hex.strip()
    if pk_hex:
        try:
            VERIFIERS.append(VerifyKey(pk_hex, encoder=HexEncoder))
        except Exception as e:
            print(f"[WARNING] Could not load a public key: {e}")

# F-03 Fix: Temporary cache to track and reject reused signatures
SEEN_SIGNATURES = {}

def verify_message(data: dict, max_age: int = 10) -> bool:
    if not VERIFIERS:
        print("[ERROR] Missing or invalid MESH_PUBLIC_KEYS in .env")
        return False

    try:
        current_time = time.time()
        time_diff = current_time - data['timestamp']
        
        # F-04 Fix: Prevent future timestamps while allowing 5s for clock drift
        if time_diff > max_age or time_diff < -5:
            print("[SECURITY] Rejected: Message expired or from the future.")
            return False

        # F-03 Fix: Strict Replay Check
        sig = data['signature']
        if sig in SEEN_SIGNATURES:
            print("[SECURITY] Rejected: Replay attack detected. Signature already processed.")
            return False

        # Memory Management: Clean up cache older than max_age
        keys_to_delete = [k for k, ts in SEEN_SIGNATURES.items() if (current_time - ts) > max_age]
        for k in keys_to_delete:
            del SEEN_SIGNATURES[k]

        sender_role = data.get('from')
        if sender_role != REQUIRED_ROLE:
            print(f"[SECURITY] Rejected: Unauthorized role '{sender_role}'")
            return False

        # F-01 Fix: Payload Tampering Prevention
        # Convert data to string securely, defaulting to empty string if None
        payload_data = str(data.get('data', '')) if data.get('data') is not None else ''
        
        # The math now strictly includes the payload data
        msg = f"{data['action']}:{sender_role}:{data['to']}:{payload_data}:{data['timestamp']}"
        msg_bytes = msg.encode('utf-8')
        sig_bytes = bytes.fromhex(sig)

        for verifier in VERIFIERS:
            try:
                verifier.verify(msg_bytes, sig_bytes)
                # Success: Record this signature to prevent it from being used again
                SEEN_SIGNATURES[sig] = data['timestamp']
                return True 
            except BadSignatureError:
                continue

        print("[SECURITY] Rejected: Invalid Signature! Fake admin detected.")
        return False
        
    except KeyError:
        print("[ERROR] Rejected: Malformed payload.")
        return False