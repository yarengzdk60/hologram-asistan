"""
WebSocket Component - Handles WebSocket connections and broadcasting
"""
import asyncio
import websockets
import json

# Global client set
clients = set()


# Global mode handler callback
mode_handler = None
voice_control_handler = None
client_disconnect_handler = None


def set_mode_handler(callback):
    """Set callback for mode change messages"""
    global mode_handler
    mode_handler = callback


def set_voice_control_handler(callback):
    """Set callback for voice control messages"""
    global voice_control_handler
    voice_control_handler = callback


def set_client_disconnect_handler(callback):
    """Set callback for client disconnect"""
    global client_disconnect_handler
    client_disconnect_handler = callback


async def handler(ws):
    """Handle new WebSocket connection"""
    print(f"🔌 Client connected (total: {len(clients) + 1})")
    clients.add(ws)
    try:
        async for message in ws:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "mode" and mode_handler:
                    try:
                        mode_handler(data.get("value"))
                    except Exception as e:
                        print(f"⚠️ Mode handler error: {e}")
                elif msg_type == "voice_control" and voice_control_handler:
                    try:
                        voice_control_handler(data.get("action"))
                    except Exception as e:
                        print(f"⚠️ Voice control handler error: {e}")
                else:
                    print(f"⚠️ Unknown message type: {msg_type}")
            except json.JSONDecodeError as e:
                print(f"⚠️ Invalid JSON message: {e}")
            except Exception as e:
                print(f"⚠️ Message handling error: {e}")
                import traceback
                traceback.print_exc()
    except websockets.exceptions.ConnectionClosed:
        print("🔌 Client connection closed normally")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"🔌 Client connection closed with error: {e}")
    except Exception as e:
        print(f"⚠️ WebSocket handler error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            clients.discard(ws)
            print(f"❌ Client disconnected (remaining: {len(clients)})")
            
            # Notify disconnect handler if no clients left
            if len(clients) == 0 and client_disconnect_handler:
                try:
                    client_disconnect_handler()
                except Exception as e:
                    print(f"⚠️ Disconnect handler error: {e}")
        except:
            pass



async def broadcast_action(action_name: str):
    """Broadcast action message to all connected clients"""
    if not clients:
        return
    msg = json.dumps({
        "type": "action",
        "action": action_name
    })
    disconnected = []
    for c in list(clients):
        try:
            await c.send(msg)
        except websockets.exceptions.ConnectionClosed:
            disconnected.append(c)
        except Exception as e:
            print(f"⚠️ Broadcast error: {e}")
            disconnected.append(c)
    
    # Remove disconnected clients
    for c in disconnected:
        clients.discard(c)


async def broadcast_video_frame(frame_base64: str):
    """Broadcast video frame to all connected clients"""
    if not clients:
        return
    msg = json.dumps({
        "type": "video",
        "data": frame_base64
    })
    disconnected = []
    for c in list(clients):
        try:
            await c.send(msg)
        except websockets.exceptions.ConnectionClosed:
            disconnected.append(c)
        except Exception as e:
            # Don't spam errors for video frames
            disconnected.append(c)
    
    # Remove disconnected clients (silently)
    for c in disconnected:
        clients.discard(c)


async def broadcast_speak(audio_path: str, duration: float):
    """Broadcast speak action to all connected clients"""
    if not clients:
        return
    msg = json.dumps({
        "type": "action",
        "action": "speak",
        "audio_path": audio_path,
        "duration": duration
    })
    disconnected = []
    for c in list(clients):
        try:
            await c.send(msg)
        except websockets.exceptions.ConnectionClosed:
            disconnected.append(c)
        except Exception as e:
            print(f"⚠️ Broadcast speak error: {e}")
            disconnected.append(c)
    
    # Remove disconnected clients
    for c in disconnected:
        clients.discard(c)


async def broadcast_error(error_message: str):
    """Broadcast error message to all connected clients"""
    if not clients:
        return
    msg = json.dumps({
        "type": "error",
        "message": error_message
    })
    disconnected = []
    for c in list(clients):
        try:
            await c.send(msg)
        except websockets.exceptions.ConnectionClosed:
            disconnected.append(c)
        except Exception as e:
            print(f"⚠️ Broadcast error: {e}")
            disconnected.append(c)
    
    # Remove disconnected clients
    for c in disconnected:
        clients.discard(c)
