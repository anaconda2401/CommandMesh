// config.example.js
// Instructions: Rename this file to config.js and enter your HiveMQ WebSocket URL.

const CONFIG = {
    // Note: Browsers require the WebSockets port (usually 8884), NOT the standard MQTT port (8883)
    BROKER_URL: "wss://YOUR_CLUSTER_ID.s1.eu.hivemq.cloud:8884/mqtt",
    
    // The base topic for the mesh network
    BASE_TOPIC: "commandmesh",
    
    // The topic the PWA listens to for device auto-discovery
    DISCOVERY_TOPIC: "commandmesh/discovery/#"
};