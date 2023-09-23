from asyncio import sleep, get_event_loop

from pyrogram import Client
from pyrogram.types import Message as PyroMessage

from .progress_print import ProgressPrint


class Preloader:
    def __init__(self, client: Client, progress: ProgressPrint, media_cb):
        self.client = client
        self.progress = progress
        self.finished = False
        self.messages: list[PyroMessage] = []
        self.messages_loaded = 0
        self.media_cb = media_cb

        self._task = None
        self._pyro_args = ()
        self._pyro_kwargs = {}

    def __call__(self, *pyrogram_args, **pyrogram_kwargs):
        self._pyro_args = pyrogram_args
        self._pyro_kwargs = pyrogram_kwargs
        return self

    def __aiter__(self):
        return self

    async def _preload(self) -> None:
        async for message in self.client.get_chat_history(*self._pyro_args, **self._pyro_kwargs):
            self.messages.append(message)
            self.messages_loaded += 1

            if message.media and self.media_cb:
                await self.media_cb(message)

            with self.progress.update():
                self.progress.status = "Preloading messages and media..."
                self.progress.messages_loaded = self.messages_loaded

        self.finished = True

    async def __anext__(self) -> PyroMessage:
        if self._task is None: self._task = get_event_loop().create_task(self._preload())

        while not self.finished and not self.messages:
            await sleep(.01)

        if self.finished and not self.messages:
            raise StopAsyncIteration

        return self.messages.pop(0)

