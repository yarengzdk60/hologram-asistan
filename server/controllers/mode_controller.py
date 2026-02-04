import logging
import asyncio

logger = logging.getLogger("ModeController")

class ModeController:
    """
    Manages VISION/VOICE modes.
    """
    def __init__(self, task_manager, vision_component, voice_controller):
        self.tm = task_manager
        self.vision = vision_component
        self.vc = voice_controller
        self.current_mode = None
        self._disconnect_timer = None
        self.grace_period = 5.0 # 5 seconds for transient disconnects (page reloads)

    async def handle(self, payload):
        """Handler for 'mode' event."""
        # If we have a pending shutdown, cancel it because a client is back
        if self._disconnect_timer:
            logger.info("Client reconnected, cancelling pending shutdown.")
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

        mode = payload.get("value")
        if self.current_mode == mode:
            # Re-ensure voice is active if it's voice mode (safety)
            if mode == "VOICE":
                await self.vc.start()
            return

        logger.info(f"🔄 Mode Switch: {self.current_mode} -> {mode}")

        # Shutdown outgoing
        if self.current_mode == "VOICE":
            await self.vc.stop()
        elif self.current_mode == "VISION":
            self.vision.stop()

        self.current_mode = mode

        # Startup incoming
        if mode == "VISION":
            loop = asyncio.get_running_loop()
            self.vision.start(loop)
        elif mode == "VOICE":
            await self.vc.start()

    async def handle_disconnect(self, payload=None):
        """Handler for 'internal_disconnect' event."""
        # KALICI COZUM: Client disconnect artik pipeline'i oldurmez.
        # Sadece log yazariz.
        logger.info("Client disconnected. Tasks will continue in background.")
