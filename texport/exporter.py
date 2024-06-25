import asyncio
from asyncio import sleep
from datetime import date
from typing import Union, TypeVar, Callable, Optional

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message as PyroMessage
from pyrogram.utils import zero_datetime

from . import ExportConfig, MediaExporter, Preloader, MessagesSaver, ProgressPrint
from .media import MEDIA_TYPES


T = TypeVar("T")


async def _flood_wait(func: Callable[[...], T], *args, **kwargs) -> Optional[T]:
    for i in range(5):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await sleep(e.value + 1)


class Exporter:
    def __init__(self, client: Client, export_config: ExportConfig=None):
        self._config = export_config or ExportConfig()
        self._client = client
        self._task = None
        self.progress: ProgressPrint = ProgressPrint(disabled=not self._config.print)
        self._messages: list[PyroMessage] = []
        self._media: dict[Union[int, str], str] = {}
        self._saver = MessagesSaver(self._messages, self._media, export_config)
        self._media_downloader = MediaExporter(client, export_config, self._media, self.progress)
        self._excluded_media = self._config.excluded_media()

    async def _export_media(self, message: PyroMessage) -> None:
        if message.media not in MEDIA_TYPES or message.media in self._excluded_media:
            return
        m = MEDIA_TYPES[message.media]
        media = m.get_media(message)
        if media is None or (m.has_size_limit and (
                media.file_size is None or media.file_size > self._config.size_limit * 1024 * 1024)):
            return

        if m.downloadable:
            chat_output_dir = (self._config.output_dir / f"{message.chat.id}").absolute()

            self._media_downloader.add(media.file_id, f"{chat_output_dir}/{m.dir_name}/", message.id)
            if hasattr(media, "thumbs") and media.thumbs:
                self._media_downloader.add(media.thumbs[0].file_id, f"{chat_output_dir}/thumbs/", f"{message.id}_thumb")

    async def _write(self, wait_media: list[int]) -> None:
        self.progress.status = "Waiting for all media to be downloaded..."
        await self._media_downloader.wait(wait_media)
        self.progress.status = "Writing messages to file..."
        await self._saver.save()

    async def _export(self):
        await self._media_downloader.run()

        offset_date = zero_datetime() if self._config.to_date.date() >= date.today() else self._config.to_date
        loaded = 0
        medias = []
        for chat_id in self._config.chat_ids:
            self.progress.approx_messages_count += await _flood_wait(self._client.get_chat_history_count, chat_id) or 0
        messages_iter = Preloader(self._client, self.progress, self._config.chat_ids, self._export_media) \
            if self._config.preload else self._client.get_chat_history

        for chat_id in self._config.chat_ids:
            async for message in messages_iter(chat_id, offset_date=offset_date):
                if message.date < self._config.from_date:
                    break

                loaded += 1
                with self.progress.update():
                    self.progress.status = "Exporting messages..."
                    self.progress.messages_exported = loaded

                if message.media:
                    medias.append(message.id)
                    medias.append(f"{message.id}_thumb")
                    await self._export_media(message)

                if not message.text and not message.caption and message.media not in MEDIA_TYPES:
                    continue

                self._messages.append(message)
                if len(self._messages) > 1000:
                    await self._write(medias)

            if self._messages:
                await self._write(medias)

        self._task = None

        self.progress.status = "Stopping media downloader..."
        await self._media_downloader.stop()
        self.progress.status = "Done!"

    async def export(self, block: bool=True) -> None:
        if self._task is not None:
            return
        coro = self._export()
        if block:
            await coro
        else:
            asyncio.get_event_loop().create_task(coro)
