from asyncio import sleep, get_event_loop

from pyrogram import Client
from pyrogram.types import Message

from .progress_print import ProgressPrint


class Preloader:
    def __init__(self, client: Client, progress: ProgressPrint, chat_ids: list, media_cb):
        self.client = client
        self.progress = progress
        self.finished = {chat_id: False for chat_id in chat_ids}
        self.messages: dict[..., list[Message]] = {chat_id: [] for chat_id in chat_ids}
        self.messages_loaded = 0
        self.media_cb = media_cb
        self._chat_ids = chat_ids

        self._task = None
        self._pyro_args = ()
        self._pyro_kwargs = {}
        self._current_chat_id = None

    def __call__(self, chat_id, *pyrogram_args, **pyrogram_kwargs):
        self._current_chat_id = chat_id
        self._pyro_args = pyrogram_args
        self._pyro_kwargs = pyrogram_kwargs
        return self

    def __aiter__(self):
        return self

    async def _preload(self) -> None:
        for chat_id in self._chat_ids:
            async for message in self.client.get_chat_history(chat_id, *self._pyro_args, **self._pyro_kwargs):
                self.messages[chat_id].append(message)
                self.messages_loaded += 1

                if message.media and self.media_cb:
                    await self.media_cb(message)

                with self.progress.update():
                    self.progress.status = "Preloading messages and media..."
                    self.progress.messages_loaded = self.messages_loaded

            self.finished[chat_id] = True

    async def __anext__(self) -> Message:
        if self._task is None: self._task = get_event_loop().create_task(self._preload())

        while not self.finished[self._current_chat_id] and not self.messages[self._current_chat_id]:
            await sleep(.01)

        if self.finished[self._current_chat_id] and not self.messages[self._current_chat_id]:
            raise StopAsyncIteration

        return self.messages[self._current_chat_id].pop(0)

