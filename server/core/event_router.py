import asyncio
import inspect
import logging

logger = logging.getLogger("EventRouter")

class EventRouter:
    def __init__(self):
        self.handlers = {}

    def register(self, event_name, handler):
        self.handlers[event_name] = handler
        logger.info(f"Registered handler for: {event_name}")

    async def dispatch(self, event_name, payload):
        handler = self.handlers.get(event_name)

        if not handler:
            logger.warning(f"No handlers registered for message type: {event_name}")
            return

        try:
            logger.info(f"Dispatching {event_name}")
            if inspect.iscoroutinefunction(handler):
                await handler(payload)
            else:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, handler, payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Handler error for event {event_name}: {e}")
