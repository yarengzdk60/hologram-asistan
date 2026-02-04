/**
 * Hologram Assistant - Client Application
 */
const log = document.getElementById("log");
const cameraImg = document.getElementById("camera");
const testWaveButton = document.getElementById("testWaveButton");
const lottieContainer = document.getElementById("lottie-container");

// WebSocket connection
const WS_URL = "ws://localhost:8765";
let socket = null;
let animation = null;
let waveStopTimeout = null;
const WAVE_DURATION_MS = 3000;
let currentMode = null; // Track current mode to prevent spam
let lastModeSwitch = 0; // Throttle mode switches
const MODE_SWITCH_THROTTLE = 1000; // ms

// Log helper
const appendLog = (text) => {
    if (!log) return;
    log.innerHTML += "<br>" + text;
    log.scrollTop = log.scrollHeight;
};

// Lottie animation setup
async function initAnimation() {
    if (!window.lottie) {
        console.error("Lottie library not loaded");
        return;
    }
    if (!lottieContainer) {
        console.error("Lottie container not found");
        return;
    }

    try {
        // Fetch the JSON animation file
        const response = await fetch('animasyon.json');
        const animationData = await response.json();

        animation = window.lottie.loadAnimation({
            container: lottieContainer,
            renderer: "svg",
            loop: true,
            autoplay: false,
            animationData: animationData
        });

        animation.addEventListener("DOMLoaded", () => {
            animation.goToAndStop(0, true);
        });
    } catch (error) {
        console.error("Failed to load animation:", error);
    }
}

// Animation controls
function playWave() {
    if (!animation) return;

    if (waveStopTimeout) {
        clearTimeout(waveStopTimeout);
    }

    animation.stop();
    animation.play();

    waveStopTimeout = setTimeout(() => {
        animation.stop();
    }, WAVE_DURATION_MS);
}

// WebSocket connection
function connectWebSocket() {
    try {
        socket = new WebSocket(WS_URL);

        socket.onopen = () => {
            appendLog("✅ Server'a bağlanıldı<br>Waiting for stream...");

            // THROTTLE + MODE GUARD
            const now = Date.now();
            if (currentMode !== "VISION" && (now - lastModeSwitch) > MODE_SWITCH_THROTTLE) {
                socket.send(JSON.stringify({
                    type: "mode",
                    value: "VISION"
                }));
                currentMode = "VISION";
                lastModeSwitch = now;
                console.log("[MODE] Switched to VISION");
            }
        };

        socket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);

                if (message.type === "video" && cameraImg) {
                    cameraImg.src = "data:image/jpeg;base64," + message.data;
                } else if (message.type === "action" && message.action === "wave") {
                    playWave();
                    appendLog("👋 Wave Detected!");
                }
            } catch (error) {
                console.error("Message parsing error:", error);
            }
        };

        socket.onerror = () => {
            appendLog("❌ WebSocket hatası (Backend çalışıyor mu?)");
        };

        socket.onclose = () => {
            appendLog("⚠️ Bağlantı kesildi");
            // Auto-reconnect after 3 seconds
            setTimeout(() => {
                if (socket?.readyState === WebSocket.CLOSED) {
                    connectWebSocket();
                }
            }, 3000);
        };
    } catch (error) {
        console.error("WebSocket connection error:", error);
    }
}

// Test button
if (testWaveButton) {
    testWaveButton.addEventListener("click", () => {
        playWave();
        appendLog("🧪 Test Wave Triggered (butondan)");
    });
}

// Initialize
initAnimation();
connectWebSocket();
