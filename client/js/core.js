/**
 * Hologram Assistant - Core Logic
 * Handles global state and WebSocket communication.
 */

// --- Global App State ---
const AppState = {
    _state: {
        mode: null, // "VISION" | "VOICE" | null
        wsStatus: "DISCONNECTED", // "CONNECTED" | "DISCONNECTED" | "RECONNECTING"
        voiceState: "IDLE", // "IDLE" | "REQUESTED" | "LISTENING" | "WAITING" | "PLAYING"
    },

    _listeners: [],

    get mode() { return this._state.mode; },
    get wsStatus() { return this._state.wsStatus; },
    get voiceState() { return this._state.voiceState; },

    // Strict setters
    setMode(value) {
        if (this._state.mode === value) return;
        console.log(`[State] Mode: ${this._state.mode} -> ${value}`);
        this._state.mode = value;
        this._notify();
    },

    setWSStatus(value) {
        if (this._state.wsStatus === value) return;
        console.log(`[State] WS: ${this._state.wsStatus} -> ${value}`);
        this._state.wsStatus = value;
        this._notify();
    },

    setVoiceState(value) {
        if (this._state.voiceState === value) return;
        console.log(`[State] Voice: ${this._state.voiceState} -> ${value}`);
        this._state.voiceState = value;
        this._notify();
    },

    subscribe(callback) {
        this._listeners.push(callback);
        callback(this._state); // Initial call
        return () => {
            this._listeners = this._listeners.filter(l => l !== callback);
        };
    },

    _notify() {
        this._listeners.forEach(l => l(this._state));
    },

    // --- SPA View Manager ---
    showView(viewName) {
        console.log(`[View] Switching to: ${viewName}`);

        // Update AppState
        if (viewName === 'vision') this.setMode('VISION');
        if (viewName === 'voice') this.setMode('VOICE');
        if (viewName === 'portal') this.setMode(null);

        // Update DOM
        const views = document.querySelectorAll('.app-view');
        views.forEach(v => {
            v.classList.remove('active');
            if (v.id === `${viewName}-view`) {
                v.classList.add('active');
            }
        });

        // Sync with backend
        if (this.mode) {
            wsManager.sendMode(this.mode);
        }
    }
};

// --- WebSocket Manager ---
class WSManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.reconnectInterval = 3000;
        this.handlers = new Map();
        this.lastModeSwitch = 0;
        this.modeThrottle = 1000; // 1 second throttle
    }

    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;

        console.log(`[WS] Connecting to ${this.url}...`);
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            AppState.setWSStatus("CONNECTED");
            console.log("%c[WS] Connected", "color: #00ff00; font-weight: bold;");

            // Sync current mode to backend on reconnect (force skip throttle)
            if (AppState.mode) {
                console.log(`[WS] Auto-syncing mode: ${AppState.mode}`);
                this.sendMode(AppState.mode, true);
            }
        };

        this.ws.onclose = (event) => {
            AppState.setWSStatus("DISCONNECTED");
            const wasClean = event.wasClean ? "CLEAN" : "DIRTY";
            console.warn(`%c[WS] Disconnected (${wasClean}) | Code: ${event.code} | Reason: ${event.reason || 'None'}`, "color: #ff4d4d; font-weight: bold;");

            if (event.code === 1006) {
                console.error("[WS] Abnormal Closure - This often means the server crashed, the connection was killed by the OS, or there's a protocol error.");
            }

            setTimeout(() => {
                console.log("[WS] Attempting automatic reconnect...");
                AppState.setWSStatus("RECONNECTING");
                this.connect();
            }, this.reconnectInterval);
        };

        this.ws.onerror = (err) => {
            console.error("%c[WS] Error Detected:", "color: #ff0000; font-weight: bold;", err);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this._routeMessage(data);
            } catch (e) {
                console.error("[WS] Parse error:", e);
            }
        };
    }

    on(type, callback) {
        if (!this.handlers.has(type)) {
            this.handlers.set(type, []);
        }
        this.handlers.get(type).push(callback);
    }

    _routeMessage(data) {
        // Broadcasters
        const listeners = this.handlers.get(data.type) || [];
        listeners.forEach(cb => cb(data));

        // Specialized action routing
        if (data.type === "action") {
            const actionListeners = this.handlers.get(`action:${data.action}`) || [];
            actionListeners.forEach(cb => cb(data));
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
            return true;
        } else {
            console.warn("[WS] Cannot send - connection not open");
            return false;
        }
    }

    sendMode(mode, force = false) {
        const now = Date.now();
        if (!force && (now - this.lastModeSwitch < this.modeThrottle)) {
            console.warn("[WS] Mode switch throttled");
            return;
        }

        if (this.send({ type: "mode", value: mode })) {
            this.lastModeSwitch = now;
        }
    }

    sendVoiceControl(action) {
        // Action: "start" | "stop"
        this.send({ type: "voice_control", action });
    }
}

// --- Connection Overlay Manager ---
function updateOverlay(state) {
    let overlay = document.getElementById('connection-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'connection-overlay';
        overlay.innerHTML = '<div class="spinner"></div><div class="overlay-text">CONNECTING TO BACKEND...</div>';
        document.body.appendChild(overlay);
    }

    if (state.wsStatus === "CONNECTED") {
        overlay.classList.remove('visible');
    } else {
        overlay.classList.add('visible');
    }
}

// Global instance
const wsManager = new WSManager("ws://localhost:8765");
wsManager.connect();

// Auto-sync overlay with state
AppState.subscribe(updateOverlay);

// Export to window for access by other scripts
window.AppState = AppState;
window.wsManager = wsManager;
