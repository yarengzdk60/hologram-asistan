import asyncio
import logging

logger = logging.getLogger("TaskManager")

class TaskManager:
    def __init__(self):
        self.tasks = {}

    async def start(self, name, coro_func):
        """Starts a task, cancelling any existing one with the same name."""
        await self.cancel(name)
        
        # Check if coro_func is a function or already a coroutine
        # The user's example shows passing self.voice.voice_loop (the method itself)
        if asyncio.iscoroutinefunction(coro_func):
            task = asyncio.create_task(coro_func())
        else:
            task = asyncio.create_task(coro_func)
            
        self.tasks[name] = task
        logger.info(f"Started task: {name}")

    async def cancel(self, name):
        """Cancels a task by name."""
        task = self.tasks.get(name)
        if task and not task.done():
            logger.info(f"Cancelling task: {name}")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks.pop(name, None)

    async def cancel_all(self):
        for name in list(self.tasks.keys()):
            await self.cancel(name)
