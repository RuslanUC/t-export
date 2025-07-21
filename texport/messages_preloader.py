from asyncio import sleep, get_event_loop
from typing import Callable, Awaitable

from pyrogram import Client
from pyrogram.types import Message

from .download.downloader import DownloadTask
from .export_progress import ExportProgressInternal
from .messages_saver import MessageToSave


class Preloader:
    def __init__(
            self, client: Client, progress: ExportProgressInternal, chat_ids: list[int | str],
            media_cb: Callable[[Message], Awaitable[tuple[DownloadTask | None, DownloadTask | None]]]
    ):
        self.client = client
        self.progress = progress
        self.finished = {chat_id: False for chat_id in chat_ids}
        self.messages: dict[..., list[MessageToSave]] = {chat_id: [] for chat_id in chat_ids}
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
                tasks: tuple[DownloadTask | None, DownloadTask | None] = None, None
                if message.media:
                    tasks = await self.media_cb(message)

                self.messages[chat_id].append(MessageToSave(message, *tasks))
                self.messages_loaded += 1

                self.progress.status = "Preloading messages and media..."
                self.progress.messages_loaded = self.messages_loaded
                self.progress.changed()

            self.finished[chat_id] = True

    async def __anext__(self) -> MessageToSave:
        if self._task is None: self._task = get_event_loop().create_task(self._preload())

        while not self.finished[self._current_chat_id] and not self.messages[self._current_chat_id]:
            await sleep(0)

        if self.finished[self._current_chat_id] and not self.messages[self._current_chat_id]:
            raise StopAsyncIteration

        return self.messages[self._current_chat_id].pop(0)

