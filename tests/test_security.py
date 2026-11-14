"""Unit tests for lib/security.py: SecretBox encryption, replay protection, and cross-language tests."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from lib.security import (
    ReplayCache,
    create_ack_payload,
    create_command_payload,
    decrypt_payload,
    derive_key,
    encrypt_payload,
)

PASSPHRASE = "mesh_test_secret_passphrase_2026"


def test_derive_key_length_and_determinism():
    """Verify SHA-256 key derivation produces exactly 32 bytes deterministically."""
    key1 = derive_key(PASSPHRASE)
    key2 = derive_key(PASSPHRASE)
    assert len(key1) == 32
    assert key1 == key2

    # Different passphrases yield different keys
    key3 = derive_key("another_passphrase")
    assert key1 != key3


def test_secretbox_encrypt_decrypt_roundtrip():
    """Verify standard encrypt and decrypt roundtrip preserves compact payload."""
    cache = ReplayCache()
    payload = {
        "from": "laptop",
        "to": "tv",
        "action": "vol_up",
        "data": 25,
        "ts": int(time.time()),
        "id": "cmd_test_001",
    }
    b64_cipher = encrypt_payload(payload, PASSPHRASE)
    assert isinstance(b64_cipher, str)
    assert len(b64_cipher) > 32

    decrypted = decrypt_payload(b64_cipher, PASSPHRASE, replay_cache=cache)
    assert decrypted is not None
    assert decrypted["from"] == "laptop"
    assert decrypted["to"] == "tv"
    assert decrypted["action"] == "vol_up"
    assert decrypted["data"] == 25
    assert decrypted["id"] == "cmd_test_001"


def test_decrypt_with_wrong_passphrase_fails():
    """Verify wrong passphrase cannot authenticate or decrypt SecretBox ciphertext."""
    payload = {
        "from": "node_a",
        "to": "node_b",
        "action": "ping",
        "ts": int(time.time()),
        "id": "cmd_test_002",
    }
    b64_cipher = encrypt_payload(payload, PASSPHRASE)
    decrypted = decrypt_payload(b64_cipher, "wrong_passphrase", replay_cache=None)
    assert decrypted is None


def test_decrypt_tampered_ciphertext_fails():
    """Verify Poly1305 MAC check rejects tampered bytes."""
    payload = {
        "from": "node_a",
        "to": "node_b",
        "action": "ping",
        "ts": int(time.time()),
        "id": "cmd_test_003",
    }
    b64_cipher = encrypt_payload(payload, PASSPHRASE)

    # Flip characters in the Base64 ciphertext
    tampered = b64_cipher[:-4] + "AAAA"
    decrypted = decrypt_payload(tampered, PASSPHRASE, replay_cache=None)
    assert decrypted is None

    # Corrupt with garbage text
    assert decrypt_payload("not_even_base64!!!", PASSPHRASE, replay_cache=None) is None


def test_timestamp_freshness_window():
    """Verify +/- 30s timestamp window strictly rejects expired or skewed packets."""
    now = 1731580000.0

    # 1. Message within window (-10s) -> allowed
    payload_valid = {"from": "a", "to": "b", "action": "ok", "ts": now - 10, "id": "ts_1"}
    b64 = encrypt_payload(payload_valid, PASSPHRASE)
    assert decrypt_payload(b64, PASSPHRASE, replay_cache=None, now=now) is not None

    # 2. Expired message (-35s) -> dropped
    payload_expired = {"from": "a", "to": "b", "action": "ok", "ts": now - 35, "id": "ts_2"}
    b64_exp = encrypt_payload(payload_expired, PASSPHRASE)
    assert decrypt_payload(b64_exp, PASSPHRASE, replay_cache=None, now=now) is None

    # 3. Skewed future message (+35s) -> dropped
    payload_future = {"from": "a", "to": "b", "action": "ok", "ts": now + 35, "id": "ts_3"}
    b64_fut = encrypt_payload(payload_future, PASSPHRASE)
    assert decrypt_payload(b64_fut, PASSPHRASE, replay_cache=None, now=now) is None


def test_bounded_replay_cache():
    """Verify bounded replay cache drops duplicates and caps RAM overhead at maxlen."""
    cache = ReplayCache(maxlen=5)

    # Adding unique IDs
    for i in range(5):
        assert cache.check_and_add(f"id_{i}") is True
    assert len(cache) == 5

    # Duplicates rejected
    assert cache.check_and_add("id_2") is False

    # Eviction: adding 6th item evicts oldest (id_0)
    assert cache.check_and_add("id_5") is True
    assert len(cache) == 5
    assert "id_0" not in cache
    assert "id_5" in cache

    # Now id_0 can be re-added because it was evicted from both deque and set
    assert cache.check_and_add("id_0") is True


def test_decrypt_drops_replayed_message():
    """Verify decrypt_payload silently drops duplicate message IDs using ReplayCache."""
    cache = ReplayCache(maxlen=10)
    payload = {
        "from": "node_a",
        "to": "node_b",
        "action": "ping",
        "ts": int(time.time()),
        "id": "replay_msg_999",
    }
    b64_cipher = encrypt_payload(payload, PASSPHRASE)

    # First attempt: valid
    res1 = decrypt_payload(b64_cipher, PASSPHRASE, replay_cache=cache)
    assert res1 is not None

    # Replay attempt: dropped
    res2 = decrypt_payload(b64_cipher, PASSPHRASE, replay_cache=cache)
    assert res2 is None


def test_payload_builder_helpers():
    """Verify create_command_payload and create_ack_payload formatting."""
    cmd = create_command_payload(
        sender_id="pwa",
        target="laptop",
        action="open_url",
        data="https://youtube.com",
    )
    assert cmd["from"] == "pwa"
    assert cmd["to"] == "laptop"
    assert cmd["action"] == "open_url"
    assert cmd["data"] == "https://youtube.com"
    assert "ts" in cmd
    assert cmd["id"].startswith("cmd_")

    ack = create_ack_payload(
        sender_id="laptop",
        target="pwa",
        in_reply_to="cmd_123",
        action="open_url",
        status="success",
        output="URL Opened",
    )
    assert ack["from"] == "laptop"
    assert ack["to"] == "pwa"
    assert ack["in_reply_to"] == "cmd_123"
    assert ack["status"] == "success"
    assert ack["output"] == "URL Opened"
    assert ack["id"].startswith("ack_")


def test_cross_language_tweetnacl_interoperability():
    """Verify cross-language byte compatibility between PyNaCl and TweetNaCl (JavaScript)."""
    nacl_js = Path(__file__).resolve().parent / "tweetnacl.min.js"
    if not nacl_js.exists():
        pytest.skip("tweetnacl.min.js not available for cross-language test")

    # 1. Python encrypts -> JavaScript decrypts
    py_payload = {
        "from": "python_unit_test",
        "to": "js_node",
        "action": "home",
        "data": "minimize",
        "ts": int(time.time()),
        "id": "cross_lang_01",
    }
    py_b64 = encrypt_payload(py_payload, PASSPHRASE)

    node_script = f"""
    const nacl = require('./tests/tweetnacl.min.js');
    const crypto = require('crypto');
    const key = crypto.createHash('sha256').update('{PASSPHRASE}').digest();
    const raw = Buffer.from('{py_b64}', 'base64');
    const nonce = raw.subarray(0, 24);
    const box = raw.subarray(24);
    const opened = nacl.secretbox.open(box, nonce, key);
    if (!opened) process.exit(1);
    const jsonStr = Buffer.from(opened).toString('utf-8');
    const parsed = JSON.parse(jsonStr);
    if (parsed.action !== 'home' || parsed.id !== 'cross_lang_01') process.exit(2);

    // Now JavaScript encrypts a response
    const jsNonce = nacl.randomBytes(24);
    const jsMsg = Buffer.from(JSON.stringify({{
        from: 'js_node',
        to: 'python_unit_test',
        in_reply_to: 'cross_lang_01',
        action: 'home',
        status: 'success',
        output: 'Desktop Shown',
        ts: Math.floor(Date.now() / 1000),
        id: 'ack_cross_02'
    }}));
    const jsBox = nacl.secretbox(jsMsg, jsNonce, key);
    const combined = Buffer.concat([Buffer.from(jsNonce), Buffer.from(jsBox)]);
    console.log('JS_CIPHER:' + combined.toString('base64'));
    """

    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=True)
    js_cipher = ""
    for line in res.stdout.splitlines():
        if line.startswith("JS_CIPHER:"):
            js_cipher = line.split("JS_CIPHER:")[1].strip()

    assert js_cipher != ""
    # 2. Python decrypts JavaScript ciphertext
    decrypted_js = decrypt_payload(js_cipher, PASSPHRASE, replay_cache=None)
    assert decrypted_js is not None
    assert decrypted_js["from"] == "js_node"
    assert decrypted_js["status"] == "success"
    assert decrypted_js["in_reply_to"] == "cross_lang_01"
    assert decrypted_js["output"] == "Desktop Shown"
