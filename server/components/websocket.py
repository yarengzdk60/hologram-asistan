"""
WebSocket Component - Minimalist handler.
Parses JSON and forwards to EventRouter.
FIXED: type + action routing & debug support
"""

import asyncio
import websockets
import json
import logging

logger = logging.getLogger("WebSocket")
clients = set()
event_router = None


def set_event_router(router):
    global event_router
    event_router = router


async def handler(ws):
    """Handle new WebSocket connection"""
    logger.info(f"🔌 Connection attempt... Total: {len(clients)}")
    clients.add(ws)

    try:
        async for message in ws:
            try:
                data = json.loads(message)

                msg_type = data.get("type")
                action = data.get("action")

                logger.info(
                    f"[WS IN] type={msg_type} action={action} payload={data}"
                )

                if not event_router:
                    logger.error("EventRouter not initialized!")
                    continue

                # 🔑 CRITICAL FIX
                # voice_control + start  -> voice_control:start
                if action:
                    event_name = f"{msg_type}:{action}"
                else:
                    event_name = msg_type

                asyncio.create_task(
                    event_router.dispatch(event_name, data)
                )

            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {message}")
                await broadcast_error("Invalid JSON")
            except Exception as e:
                logger.exception("WebSocket message handling error")
                await broadcast_error(str(e))

    except websockets.exceptions.ConnectionClosed:
        pass

    finally:
        clients.discard(ws)
        logger.info(f"❌ Disconnected. Remaining: {len(clients)}")

        if not clients and event_router:
            asyncio.create_task(
                event_router.dispatch("internal_disconnect", {})
            )


# =========================
# BROADCAST HELPERS
# =========================

async def broadcast_message(message_dict: dict):
    if not clients:
        return

    msg = json.dumps(message_dict)
    disconnected = []

    for c in list(clients):
        try:
            await c.send(msg)
        except Exception:
            disconnected.append(c)

    for c in disconnected:
        clients.discard(c)


async def broadcast_action(action_name: str):
    await broadcast_message({
        "type": "action",
        "action": action_name
    })


async def broadcast_state(value: str):
    await broadcast_message({
        "type": "state",
        "value": value
    })


async def broadcast_speak(audio_path: str, duration: float, text: str = None):
    await broadcast_message({
        "type": "action",
        "action": "speak",
        "audio_path": audio_path,
        "duration": duration,
        "text": text
    })


async def broadcast_error(error_message: str):
    await broadcast_message({
        "type": "error",
        "message": error_message
    })


async def broadcast_debug(message: str):
    """🔥 Frontend debug viewer için"""
    await broadcast_message({
        "type": "debug",
        "message": message
    })


async def broadcast_video_frame(frame_base64: str):
    if not clients:
        return

    msg = json.dumps({
        "type": "video",
        "data": frame_base64
    })

    for c in list(clients):
        try:
            await c.send(msg)
        except:
            clients.discard(c)
