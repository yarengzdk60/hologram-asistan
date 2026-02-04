from server.components.websocket import handler, set_event_router
from server.components.vision import VisionComponent
from server.controllers.mode_controller import ModeController
from server.controllers.voice_controller import VoiceController
from server.core.task_manager import TaskManager
from server.core.event_router import EventRouter
import websockets
import aiohttp_cors
from aiohttp import web
import logging
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# 1. SETUP ENVIRONMENT & PATHS (MUST BE FIRST)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env from project root
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

# Audio output directory (Hidden to prevent Live Server reload)
AUDIO_OUTPUT_DIR = project_root / ".audio_cache"
AUDIO_OUTPUT_DIR.mkdir(exist_ok=True)

# 2. IMPORTS (After path setup)


# Logging Config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Main")

# Config
HOST = "localhost"
WS_PORT = 8765
HTTP_PORT = 8090


async def main():
    logger.info("Initializing Hologram Assistant Backend...")

    # 1. Initialize Core Infrastructure
    router = EventRouter()
    tm = TaskManager()

    # 2. Initialize Components
    vision = VisionComponent()
    vc = VoiceController(tm, AUDIO_OUTPUT_DIR)
    mc = ModeController(tm, vision, vc)

    # 3. Register Correct Event Handlers
    router.register("voice_control:start", vc.start)
    router.register("voice_control:stop", vc.stop)
    router.register("mode", mc.handle)
    router.register("internal_disconnect", mc.handle_disconnect)

    set_event_router(router)

    # 4. HTTP Server (Audio Serving)
    async def serve_audio(request):
        filename = request.match_info.get('path', '')
        filepath = AUDIO_OUTPUT_DIR / filename
        if filepath.exists():
            return web.FileResponse(filepath, headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache"
            })
        return web.Response(status=404)

    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })
    app.router.add_get('/audio/{path:.*}', serve_audio)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, HOST, HTTP_PORT).start()
    logger.info(f"🌐 HTTP Server: http://{HOST}:{HTTP_PORT}")

    # 5. WebSocket Server
    try:
        async with websockets.serve(handler, HOST, WS_PORT, ping_interval=20):
            logger.info(f"🔌 WebSocket Server: ws://{HOST}:{WS_PORT}")
            await asyncio.Future()  # Keep alive
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutdown initiated...")
        await tm.cancel_all()
        vision.stop()
        await runner.cleanup()
        logger.info("Cleanup complete. Goodbye.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
