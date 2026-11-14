# Progressive Web App (PWA) Guide

The CommandMesh PWA (`pwa/index.html`) is a static, zero-build web application that transforms any smartphone, tablet, or desktop browser into a responsive physical remote control.

---

## 1. Zero-Build Static Architecture

The PWA is designed to run anywhere with zero build tools (no Node.js, Webpack, Vite, or npm required):
- **Single File:** The entire UI, logic, and cryptography are bundled inside `pwa/index.html`.
- **Hosting Flexibility:** Can be hosted on **GitHub Pages**, Cloudflare Pages, Netlify, or served locally via Python (`python -m http.server`).
- **Offline Capable:** Registered as a Progressive Web App with manifest and service worker compatibility for installation to home screens (iOS Safari, Android Chrome, Windows Edge).

---

## 2. In-Browser Cryptography Pipeline

The PWA achieves 100% binary-level compatibility with PyNaCl using **TweetNaCl.js** and the browser's native **Web Crypto API**:

```
[Master Passphrase]
       ↓ Web Crypto API (crypto.subtle.digest("SHA-256", ...))
[32-byte Symmetric Key]
       ↓
[Generate 24-byte Random Nonce] (crypto.getRandomValues)
       ↓
[Compact JSON Payload]
       ↓ TweetNaCl (nacl.secretbox(payloadBytes, nonce, key))
[Ciphertext (Box + Poly1305 Tag)]
       ↓ Concatenation: Uint8Array([24-byte Nonce, ...Ciphertext])
[Binary Buffer]
       ↓ btoa()
[Base64 Ciphertext] -> Published to MQTT broker over WebSockets
```

### Key Verification Code:
```javascript
// 1. Derive 32-byte key via Web Crypto API
async function deriveKey(passphrase) {
    const enc = new TextEncoder();
    const hash = await crypto.subtle.digest("SHA-256", enc.encode(passphrase));
    return new Uint8Array(hash);
}

// 2. Encrypt compact command
async function encryptPayload(payloadObj, passphrase) {
    const key = await deriveKey(passphrase);
    const nonce = new Uint8Array(24);
    crypto.getRandomValues(nonce);
    const msgBytes = new TextEncoder().encode(JSON.stringify(payloadObj));
    const box = nacl.secretbox(msgBytes, nonce, key);
    
    // Prepend 24-byte nonce to ciphertext (PyNaCl standard format)
    const combined = new Uint8Array(nonce.length + box.length);
    combined.set(nonce, 0);
    combined.set(box, nonce.length);
    
    let binary = "";
    for (let i = 0; i < combined.length; i++) {
        binary += String.fromCharCode(combined[i]);
    }
    return btoa(binary);
}
```

---

## 3. WebSockets MQTT Integration

Browsers cannot open raw TCP sockets to port 8883. Instead, the PWA connects to the MQTT broker using **Secure WebSockets (WSS)**:

- **HiveMQ Cloud WSS Port:** `8884` (path: `/mqtt`)
- **Mosquitto / Local WSS Port:** `9001` or `8083`

The PWA automatically subscribes to:
1. `mesh/presence/#`: Updates live device status cards in real time.
2. `mesh/ack/pwa`: Receives and displays encrypted execution results as floating toast notifications.

---

## 4. Features & Interface

### Touch-Optimized Remote Control
- **D-Pad:** Up, Down, Left, Right, and Center (Select/OK) buttons.
- **Media Controls:** Play/Pause, Volume Up, Volume Down, Home, and Power/Lock.
- **Text Dispatcher:** Send long-form text or search queries directly to TV text boxes or desktop windows.
- **URL & YouTube Intents:** Open websites or launch the YouTube app with a single click.
- **Script Trigger:** Remotely execute allowlisted scripts on Desktop nodes.

### Real-Time Presence Cards
The UI dynamically renders cards for each discovered device, displaying:
- Device ID and friendly name
- Platform icon (PC or TV)
- Online / Offline badge (updated automatically via MQTT LWT)

### Encrypted ACK Feedback
When an action is dispatched, the UI indicates progress. As soon as the target device decrypts and executes the command, the PWA decrypts the incoming response from `mesh/ack/pwa` and shows an interactive status toast (e.g. `[laptop] PC Locked` or `[living_room_tv] Volume Up: 35`).
