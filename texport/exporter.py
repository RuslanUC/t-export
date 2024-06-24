import asyncio
from datetime import date
from typing import Union

from pyrogram import Client
from pyrogram.types import Message as PyroMessage
from pyrogram.utils import zero_datetime

from .export_config import ExportConfig
from .media import MEDIA_TYPES
from .media_downloader import MediaExporter
from .messages_preloader import Preloader
from .messages_saver import MessagesSaver
from .progress_print import ProgressPrint


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
        if media is None or (m.has_size_limit and media.file_size > self._config.size_limit * 1024 * 1024):
            return

        if m.downloadable:
            self._media_downloader.add(media.file_id, f"{self._config.output_dir.absolute()}/{m.dir_name}/", message.id)

            if hasattr(media, "thumbs") and media.thumbs:
                self._media_downloader.add(media.thumbs[0].file_id, f"{self._config.output_dir.absolute()}/thumbs/",
                                           f"{message.id}_thumb")

    async def _write(self, wait_media: list[int]) -> None:
        self.progress.status = "Waiting for all media to be downloaded..."
        await self._media_downloader.wait(wait_media)
        self.progress.status = "Writing messages to file..."
        await self._saver.save()

    async def _export(self, chat_id: Union[int, str]):
        await self._media_downloader.run()

        offset_date = zero_datetime() if self._config.to_date.date() >= date.today() else self._config.to_date
        loaded = 0
        medias = []
        self.progress.approx_messages_count = await self._client.get_chat_history_count(chat_id)
        messages_iter = Preloader(self._client, self.progress, self._export_media) \
            if self._config.preload else self._client.get_chat_history
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
        coro = self._export(self._config.chat_id)
        if block:
            await coro
        else:
            asyncio.get_event_loop().create_task(coro)
