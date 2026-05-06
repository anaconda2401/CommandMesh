import os
import time
import json
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

# In-memory protection state
SEEN_SIGNATURES = {}
LAST_CLEANUP = 0
MAX_CACHE_SIZE = 1000

def cleanup_cache(current_time: float, max_age: int):
    """Throttled TTL cleanup to prevent memory leaks and save CPU."""
    global LAST_CLEANUP
    
    # O(1) Fail-safe: Clear cache if overwhelmed (e.g., DDoS of valid signatures)
    if len(SEEN_SIGNATURES) > MAX_CACHE_SIZE:
        SEEN_SIGNATURES.clear()
        LAST_CLEANUP = current_time
        print("[WARNING] Cache limit exceeded. Cleared to prevent memory exhaustion.")
        return

    # Throttle: Only run the O(n) cleanup loop once every 5 seconds
    if current_time - LAST_CLEANUP < 5:
        return
        
    LAST_CLEANUP = current_time
    
    expired = [sig for sig, ts in SEEN_SIGNATURES.items() if (current_time - ts) > max_age]
    for sig in expired:
        del SEEN_SIGNATURES[sig]

def verify_message(data: dict, max_age: int = 10) -> bool:
    if not VERIFIERS:
        print("[ERROR] Missing or invalid MESH_PUBLIC_KEYS in .env")
        return False

    try:
        current_time = time.time()
        time_diff = current_time - data['timestamp']
        
        # 1. Prevent future timestamps while allowing 5s for clock drift
        if time_diff > max_age or time_diff < -5:
            print("[SECURITY] Rejected: Message expired or from the future.")
            return False

        # 2. Clean up old memory (Throttled TTL)
        cleanup_cache(current_time, max_age)

        # 3. Strict Replay Check
        sig = data['signature']
        if sig in SEEN_SIGNATURES:
            print("[SECURITY] Rejected: Replay attack detected.")
            return False

        # 4. Role Authorization
        sender_role = data.get('from')
        if sender_role != REQUIRED_ROLE:
            print(f"[SECURITY] Rejected: Unauthorized role '{sender_role}'")
            return False

        # 5. Cryptographic Construction (Deterministic)
        # If 'data' is a dictionary, we MUST sort keys so the string hash matches the sender perfectly
        raw_data = data.get('data')
        if isinstance(raw_data, dict):
            payload_data = json.dumps(raw_data, sort_keys=True, separators=(',', ':'))
        elif raw_data is not None:
            payload_data = str(raw_data)
        else:
            payload_data = ''
            
        msg_id = str(data.get('msg_id', ''))
        
        # Exact match required against PWA frontend
        msg = f"{data['action']}:{sender_role}:{data['to']}:{payload_data}:{data['timestamp']}:{msg_id}"
        
        msg_bytes = msg.encode('utf-8')
        sig_bytes = bytes.fromhex(sig)

        # 6. Verification
        for verifier in VERIFIERS:
            try:
                verifier.verify(msg_bytes, sig_bytes)
                
                # IMPORTANT: Store `current_time` for accurate TTL, not the payload's timestamp.
                SEEN_SIGNATURES[sig] = current_time
                return True 
                
            except BadSignatureError:
                continue

        print("[SECURITY] Rejected: Invalid Signature! Fake admin detected.")
        return False
        
    except KeyError:
        print("[ERROR] Rejected: Malformed payload.")
        return False