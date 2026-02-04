/**
 * Voice Logic - Hands-free Version
 * Strictly handles audio playback and reflects state from backend.
 * No manual button trigger required.
 */

const debugLog = document.getElementById("debug-log");

function logDebug(message, data = null) {
    const t = new Date().toLocaleTimeString();
    let line = `[${t}] ${message}`;
    if (data) line += " → " + JSON.stringify(data);
    if (debugLog) {
        debugLog.textContent += "\n" + line;
        debugLog.scrollTop = debugLog.scrollHeight;
    }
}

(function () {
    const micBtn = document.getElementById('mic-btn');
    const statusText = document.getElementById('voice-status');
    const transcribedText = document.getElementById('voice-text');

    if (!micBtn || !statusText || !transcribedText) {
        console.warn("[Voice] Elements not found, skipping init");
        return;
    }

    let currentAudio = null;

    // --- State Mapping ---
    const STATE_COLORS = {
        IDLE: '#00f2ff',
        REQUESTED: '#ffaa00',
        LISTENING: '#ff0088',
        WAITING: '#8800ff',
        PLAYING: '#00ff88'
    };

    AppState.subscribe(state => {
        if (state.mode !== 'VOICE') return;

        // Button State (Purely Visual)
        micBtn.style.borderColor = STATE_COLORS[state.voiceState] || '#fff';
        statusText.textContent = state.voiceState;
        statusText.style.color = STATE_COLORS[state.voiceState] || '#fff';

        if (state.voiceState === 'LISTENING') {
            micBtn.classList.add('listening');
        } else {
            micBtn.classList.remove('listening');
        }

        // Visual feedback based on state
        if (state.voiceState === 'PLAYING' || state.voiceState === 'REQUESTED' || state.voiceState === 'WAITING') {
            micBtn.style.boxShadow = `0 0 40px ${STATE_COLORS[state.voiceState]}`;
        } else {
            micBtn.style.boxShadow = '';
        }
    });

    // --- Message Listeners ---

    // Handle incoming audio
    wsManager.on('action:speak', (msg) => {
        if (AppState.mode !== 'VOICE') return;

        console.log("[Voice] Received audio:", msg.audio_path);

        // Interrupt existing audio
        if (currentAudio) {
            currentAudio.pause();
            currentAudio = null;
        }

        // Create new audio instance
        currentAudio = new Audio(msg.audio_path);

        currentAudio.onplay = () => {
            AppState.setVoiceState('PLAYING');
            transcribedText.textContent = msg.text || "";
        };

        currentAudio.onended = () => {
            AppState.setVoiceState('IDLE');
        };

        currentAudio.onerror = (e) => {
            console.error("[Voice] Audio playback error:", e);
            AppState.setVoiceState('IDLE');
        };

        // play() works because user interaction happened (Portals)
        currentAudio.play().catch(err => {
            console.warn("[Voice] Autoplay blocked, likely no interaction yet", err);
            statusText.textContent = "TAP UI TO ENABLE AUDIO";
            document.body.onclick = () => {
                currentAudio.play();
                document.body.onclick = null;
            };
        });
    });

    // Handle transcription updates
    wsManager.on('transcribe', (msg) => {
        if (AppState.mode !== 'VOICE') return;
        transcribedText.textContent = msg.text;
    });

    // Handle generic state updates from backend
    wsManager.on('state', (msg) => {
        if (AppState.mode !== 'VOICE') return;
        logDebug("BACKEND STATE → " + msg.value);
        AppState.setVoiceState(msg.value);
    });

    // Handle errors
    wsManager.on('error', (msg) => {
        if (AppState.mode !== 'VOICE') return;
        console.error("[Voice] Backend error:", msg.message);
        transcribedText.textContent = "Error: " + msg.message;
        AppState.setVoiceState('IDLE');
    });

    // Removing manual click handler as requested
    micBtn.onclick = null;
    micBtn.style.cursor = 'default';

    console.log("[Voice] Hands-free Logic initialized");
})();
