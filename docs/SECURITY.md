# CommandMesh Security Specification

CommandMesh is built on a zero-trust model relative to network infrastructure and MQTT brokers. All data confidentiality, integrity, authenticity, and freshness are enforced cryptographically at the endpoints.

---

## 1. Cryptographic Primitive: NaCl SecretBox

CommandMesh uses **NaCl SecretBox** (`crypto_secretbox_xsalsa20poly1305`):
- **Stream Cipher:** XSalsa20 with a 256-bit (32-byte) key and a 192-bit (24-byte) random nonce.
- **Authentication:** Poly1305 One-Time MAC (128-bit / 16-byte tag).

### Why SecretBox over AES-GCM or Asymmetric Signatures?
1. **Authenticated Encryption with Associated Data (AEAD):**
   SecretBox guarantees both **confidentiality** and **integrity**. Any tampering with the ciphertext, nonce, or key causes decryption to fail immediately with zero execution.
2. **Speed on Low-Power ARM CPUs:**
   XSalsa20 and Poly1305 require no hardware AES-NI or cryptographic coprocessors. On older Cortex-A53 Android TVs, XSalsa20 executes in a fraction of the CPU cycles required for software AES.
3. **No Key Management Overhead:**
   Unlike asymmetric schemes (such as Ed25519) requiring public-key registries or certificates on every node, all mesh peers share a single master passphrase from which the 32-byte key is derived.

---

## 2. Key Derivation

The 32-byte encryption key is deterministically derived from the UTF-8 encoded passphrase using single-iteration **SHA-256**:

$$\text{Key} = \text{SHA-256}(\text{MESH\_PASSPHRASE})$$

### Cross-Language Compatibility
- **Python (`lib/security.py`):**
  ```python
  import hashlib
  key = hashlib.sha256(passphrase.encode("utf-8")).digest()
  ```
- **Web App / JavaScript (`pwa/index.html`):**
  ```javascript
  const enc = new TextEncoder();
  const hashBuffer = await crypto.subtle.digest("SHA-256", enc.encode(passphrase));
  const key = new Uint8Array(hashBuffer);
  ```

---

## 3. Wire Format & Nonce Handling

Every command or acknowledgment message is serialized to compact JSON, encrypted, and Base64-encoded:

```
+--------------------------------------------------------------------------+
| 24-byte Random Nonce | Ciphertext (Compact JSON) | 16-byte Poly1305 Tag  |
+--------------------------------------------------------------------------+
|<------------------------------ Base64 ---------------------------------->|
```

1. **Nonce Generation:**
   A fresh 24-byte cryptographically secure random nonce is generated for **every single transmission**:
   - Python: `nacl.utils.random(24)`
   - Browser: `crypto.getRandomValues(new Uint8Array(24))` or `nacl.randomBytes(24)`
2. **Prepended Nonce:**
   The 24-byte nonce is concatenated to the front of the ciphertext. The receiver slices the first 24 bytes as the nonce and passes the remaining bytes to the SecretBox opening routine.
3. **Nonce Collision Risk:**
   With 192 bits of entropy, the probability of a nonce collision is practically zero ($2^{-96}$ birthday bound), even across millions of messages.

---

## 4. Freshness & Replay Attack Defense

Every decrypted payload contains an integer Unix timestamp (`ts`) and a unique message identifier (`id`):

```json
{
  "from": "laptop",
  "to": "tv",
  "action": "vol_up",
  "data": null,
  "ts": 1794659100,
  "id": "cmd_1794659100000_1234"
}
```

When a message is received, it must pass two strict freshness checks before execution:

### 1. The $\pm 30$ Second Clock Window
$$\left| \text{timestamp}_{\text{payload}} - \text{timestamp}_{\text{system}} \right| \le 30$$

If the message's timestamp is more than 30 seconds in the past or 30 seconds into the future, the message is dropped silently. This prevents attackers from storing encrypted packets and replaying them hours or days later.

### 2. Bounded Replay Cache (Sliding Window)
Even within the 30-second window, an eavesdropper might attempt to repeat an encrypted command multiple times (e.g., repeating a volume-up command 50 times).

To prevent this without leaking memory, nodes maintain a dual-structure replay cache:
- A FIFO circular queue: `collections.deque(maxlen=128)`
- A hash set for $O(1)$ lookups: `set[str]`

```python
class ReplayCache:
    def __init__(self, maxlen: int = 128) -> None:
        self.seen_set: set[str] = set()
        self.seen_deque: collections.deque[str] = collections.deque(maxlen=maxlen)

    def is_replayed(self, msg_id: str) -> bool:
        if not msg_id or msg_id in self.seen_set:
            return True
        if len(self.seen_deque) == self.seen_deque.maxlen:
            oldest = self.seen_deque[0]
            self.seen_set.discard(oldest)
        self.seen_deque.append(msg_id)
        self.seen_set.add(msg_id)
        return False
```

- When the cache reaches 128 elements, the oldest message ID is evicted from both the queue and the set.
- Because messages older than 30 seconds are rejected by the timestamp check, an evicted ID cannot be successfully replayed.
- **Memory footprint:** Constant size (~15 KB maximum). Zero RAM leaks over months of continuous operation.

---

## 5. Desktop Node Security: Directory-as-Allowlist

Desktop nodes allow remote script launching via the `run_script` action. To prevent arbitrary code execution, CommandMesh enforces strict directory containment:

1. **Dedicated Directory:**
   Scripts must reside strictly inside `nodes/desktop/scripts/`.
2. **Path Traversal Protection:**
   The requested script path is resolved using Python's `Path.resolve()` and tested against `SCRIPTS_DIR`:
   ```python
   target_path = (SCRIPTS_DIR / raw_name).resolve()
   if not target_path.is_relative_to(SCRIPTS_DIR) or target_path == SCRIPTS_DIR:
       return False, "Security Block: Traversal detected"
   ```
   Attempts to pass `../`, `../../`, or absolute paths (`C:\Windows\...`, `/etc/passwd`) are rejected before filesystem access.
3. **No Shell Invocation (`shell=False`):**
   Subprocesses are invoked with explicit arguments and `shell=False`. Command strings are never passed to an OS command interpreter shell, eliminating shell injection vectors.
4. **Supported Extensions Only:**
   Only verified file types (`.bat`, `.cmd`, `.ps1` on Windows; `.sh` on POSIX; `.py` cross-platform) are permitted.
