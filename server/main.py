"""
Hologram Assistant - Main Server
Component-based architecture
"""
import asyncio
import websockets
import sys
import io
from pathlib import Path
from aiohttp import web
import aiohttp_cors

# Fix Windows terminal encoding for emoji
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from server.components.websocket import handler, set_mode_handler, set_voice_control_handler, set_client_disconnect_handler
from server.components.vision import VisionComponent
from server.components.voice import VoiceComponent


HOST = "localhost"
PORT = 8765


async def main():
    print("🚀 Hologram Assistant Server starting...")

    loop = asyncio.get_running_loop()

    # Initialize components
    vision = VisionComponent()
    voice = VoiceComponent()

    # Don't auto-start any mode - wait for frontend to send mode message
    # Voice component starts but remains inactive
    voice.start(loop)

    # Global mode state
    current_mode = None  # Start with no mode active

    # Mode change handler with guard
    def handle_mode_change(mode):
        nonlocal current_mode
        
        # MODE GUARD: Prevent spam - if already in this mode, do nothing
        if current_mode == mode:
            print(f"⚠️ Already in {mode} mode - ignoring redundant switch")
            return
        
        try:
            if mode == "VOICE":
                # Check if HuggingFace API key is available
                if not voice.hf_api_key:
                    print("⚠️ Cannot switch to VOICE mode - HuggingFace API key not set")
                    return
                
                # Stop Vision mode completely
                if current_mode == "VISION":
                    vision.stop()
                    print("🛑 Vision mode stopped")
                
                # Activate Voice mode
                current_mode = "VOICE"
                voice.set_active(True)
                print("🔄 Switched to VOICE mode")
                
            elif mode == "VISION":
                # Stop Voice mode completely
                if current_mode == "VOICE":
                    voice.set_active(False)
                    print("🛑 Voice mode stopped")
                
                # Start Vision mode
                current_mode = "VISION"
                if not vision.running:
                    vision.start(loop)
                print("🔄 Switched to VISION mode")
            else:
                print(f"⚠️ Unknown mode: {mode}")
        except Exception as e:
            print(f"⚠️ Mode change error: {e}")
            import traceback
            traceback.print_exc()

    set_mode_handler(handle_mode_change)
    
    # Voice control handler
    def handle_voice_control(action):
        try:
            if action == "start":
                voice.set_active(True)
                print("🎤 Voice recording started")
            elif action == "stop":
                voice.set_active(False)
                print("🎤 Voice recording stopped")
        except Exception as e:
            print(f"⚠️ Voice control error: {e}")
            import traceback
            traceback.print_exc()
    
    set_voice_control_handler(handle_voice_control)
    
    # Client disconnect handler
    def handle_client_disconnect():
        """Handle all clients disconnecting"""
        nonlocal current_mode
        try:
            if current_mode == "VOICE":
                print("🔌 All clients disconnected - deactivating Voice mode")
                voice.set_active(False)
        except Exception as e:
            print(f"⚠️ Disconnect handler error: {e}")
    
    set_client_disconnect_handler(handle_client_disconnect)

    # HTTP Server for serving audio files
    async def serve_audio(request):
        file_path = request.match_info.get('path', '')
        audio_file = Path("audio_output") / file_path
        
        print(f"[HTTP] Audio request: {file_path}")
        
        if audio_file.exists() and audio_file.suffix in ['.mp3', '.wav']:
            print(f"[HTTP] ✅ Serving: {audio_file}")
            # Explicit CORS headers
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': '*',
                'Cache-Control': 'no-cache'
            }
            return web.FileResponse(audio_file, headers=headers)
        
        print(f"[HTTP] ❌ File not found: {audio_file}")
        return web.Response(status=404, text="File not found")
    
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    app.router.add_get('/audio/{path:.*}', serve_audio)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, 8090)
    await site.start()
    print(f"🌐 HTTP Server running on http://{HOST}:8090")

    # Start WebSocket Server
    try:
        async with websockets.serve(handler, HOST, PORT, ping_interval=20, ping_timeout=10):
            print(f"🔌 WebSocket Server running on ws://{HOST}:{PORT}")
            print("✅ Server ready - waiting for connections...")
            try:
                await asyncio.Future()  # run forever
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")
            finally:
                vision.stop()
                voice.stop()
    except Exception as e:
        print(f"❌ Server startup error: {e}")
        import traceback
        traceback.print_exc()
        vision.stop()
        voice.stop()
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Server stopped")
