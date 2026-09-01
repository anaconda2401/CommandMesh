import os
import json

# ──────────────────────────────────────────────────────────────────────────────
# Signature Verification Toggle
# Controlled via SIGNATURE_VERIFICATION=true|false in the .env file.
# Default: enabled (true) — set to 'false' only on trusted private networks.
# ──────────────────────────────────────────────────────────────────────────────
_sig_env = os.getenv("SIGNATURE_VERIFICATION", "true").strip().lower()
SIGNATURE_VERIFICATION_ENABLED = _sig_env not in ("false", "0", "no", "off")

REQUIRED_ROLE = os.getenv("REQUIRED_ROLE", "mesh_admin")

# Only load PyNaCl / public keys when verification is actually enabled.
VERIFIERS = []
if SIGNATURE_VERIFICATION_ENABLED:
    try:
        from nacl.signing import VerifyKey
        from nacl.encoding import HexEncoder
        from nacl.exceptions import BadSignatureError as _BadSigError
    except ImportError:
        print("[WARNING] PyNaCl not installed. Signature verification will be disabled.")
        SIGNATURE_VERIFICATION_ENABLED = False
        _BadSigError = Exception  # fallback so the module still loads

    if SIGNATURE_VERIFICATION_ENABLED:
        PUB_KEYS_STR = os.getenv("MESH_PUBLIC_KEYS", "")
        for pk_hex in PUB_KEYS_STR.split(","):
            pk_hex = pk_hex.strip()
            if pk_hex:
                try:
                    VERIFIERS.append(VerifyKey(pk_hex, encoder=HexEncoder))
                except Exception as e:
                    print(f"[WARNING] Could not load a public key: {e}")
else:
    _BadSigError = Exception  # fallback reference so the function body is valid

# Boot-time status line so the operator knows what mode is active.
if SIGNATURE_VERIFICATION_ENABLED:
    print(f"[SECURITY] Ed25519 signature verification: ENABLED ({len(VERIFIERS)} key(s) loaded)")
else:
    print("[SECURITY] !! Ed25519 signature verification: DISABLED (trust-all mode) !!")


def verify_message(data: dict) -> bool:
    """
    Validate an incoming MQTT command payload.

    When SIGNATURE_VERIFICATION_ENABLED is True  → full Ed25519 check (PyNaCl).
    When SIGNATURE_VERIFICATION_ENABLED is False → role-only check, no crypto.
    """
    # ── 1. Role Authorization (always enforced) ───────────────────────────────
    sender_role = data.get('from')
    if sender_role != REQUIRED_ROLE:
        print(f"[SECURITY] Rejected: Unauthorized role '{sender_role}'")
        return False

    # ── 2. Skip cryptography when feature is disabled ────────────────────────
    if not SIGNATURE_VERIFICATION_ENABLED:
        return True

    # ── 3. Require at least one loaded public key ─────────────────────────────
    if not VERIFIERS:
        print("[ERROR] Missing or invalid MESH_PUBLIC_KEYS in .env")
        return False

    try:
        # 4. Reconstruct the canonical message string (must match PWA exactly)
        raw_data = data.get('data')
        if isinstance(raw_data, dict):
            payload_data = json.dumps(raw_data, sort_keys=True, separators=(',', ':'))
        elif raw_data is not None:
            payload_data = str(raw_data)
        else:
            payload_data = ''

        msg_id = str(data.get('msg_id', ''))
        msg = f"{data['action']}:{sender_role}:{data['to']}:{payload_data}:{data['timestamp']}:{msg_id}"

        msg_bytes = msg.encode('utf-8')
        sig_bytes = bytes.fromhex(data['signature'])

        # 5. Try each registered public key
        for verifier in VERIFIERS:
            try:
                verifier.verify(msg_bytes, sig_bytes)
                return True
            except _BadSigError:
                continue

        print("[SECURITY] Rejected: Invalid Signature! Fake admin detected.")
        return False

    except KeyError:
        print("[ERROR] Rejected: Malformed payload (missing required field).")
        return False