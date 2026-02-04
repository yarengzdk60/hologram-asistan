/**
 * vision.js
 * Motion-Reactive Hologram Mode: Camera detects any movement in bg, Lottie robot reacts.
 */
(function () {
    const container = document.getElementById('hologram-container');
    if (!container) return;

    let hologramAnim = lottie.loadAnimation({
        container: container,
        renderer: 'svg',
        loop: true,
        autoplay: true,
        path: 'anim.json'
    });

    let isReacting = false;

    // Handle Motion Action
    wsManager.on('action:motion_detected', () => {
        // Only react if we are in vision mode
        if (AppState.mode !== 'VISION') return;
        if (isReacting) return; // UI side cooldown safety

        console.log("[Hologram] Movement detected! Awakening...");
        isReacting = true;

        // 1. Visual reaction in hologram: Speed up
        hologramAnim.setSpeed(2.2);

        // 2. Add temporary intensity to the glow effect
        container.classList.add('reactive-glow');

        // Reset after reaction period
        setTimeout(() => {
            hologramAnim.setSpeed(1.0);
            container.classList.remove('reactive-glow');
            isReacting = false;
        }, 1200);
    });

    console.log("[Vision] Motion-reactive Hologram initialized");
})();
