import asyncio
from datetime import date
from os.path import relpath
from typing import Union, Optional

from pyrogram import Client
from pyrogram.types import Message as PyroMessage
from pyrogram.utils import zero_datetime

from texport.export_config import ExportConfig
from texport.media import MEDIA_TYPES
from texport.messages_saver import MessagesSaver
from texport.progress_print import ProgressPrint


class ExportStatus:
    def __init__(self):
        self.approx_messages_count = None
        self.last_message_id = None
        self.last_date = None


class Exporter:
    def __init__(self, client: Client, export_config: ExportConfig=None):
        self._config = export_config or ExportConfig()
        self._client = client
        self._task = None
        self.status: Optional[ExportStatus] = None
        self._progress: ProgressPrint = ProgressPrint(disabled=not self._config.print)
        self._messages: list[PyroMessage] = []
        self._media: dict[Union[int, str], str] = {}
        self._saver = MessagesSaver(self._messages, self._media, export_config)
        self._excluded_media = self._config.excluded_media()

    async def _export_media(self, message: PyroMessage) -> None:
        if message.media not in MEDIA_TYPES or message.media in self._excluded_media:
            return
        m = MEDIA_TYPES[message.media]
        media = m.get_media(message)
        if media.file_size > self._config.size_limit * 1024 * 1024:
            return

        path = await message.download(file_name=f"{self._config.output_dir.absolute()}/{m.dir_name}/")
        path = relpath(path, self._config.output_dir.absolute())
        self._media[message.id] = path

        if hasattr(media, "thumbs") and media.thumbs:
            path = await self._client.download_media(media.thumbs[0].file_id,
                                                     file_name=f"{self._config.output_dir.absolute()}/thumbs/")
            path = relpath(path, self._config.output_dir.absolute())
            self._media[f"{message.id}_thumb"] = path

    async def _export(self, chat_id: Union[int, str]):
        offset_date = zero_datetime() if self._config.to_date.date() >= date.today() else self._config.to_date
        loaded = 0
        self._progress.approx_messages_count = await self._client.get_chat_history_count(chat_id)
        async for message in self._client.get_chat_history(chat_id, offset_date=offset_date):
            if message.date < self._config.from_date:
                break

            loaded += 1
            with self._progress.update():
                self._progress.status = "Exporting messages..."
                self._progress.messages_exported = loaded

            if self.status.approx_messages_count is None:
                self.status.approx_messages_count = message.id
            self.status.last_message_id = message.id
            self.status.last_date = message.date

            if message.media:
                self._progress.status = "Downloading media..."
                await self._export_media(message)

            if not message.text and not message.caption and message.id not in self._media:
                continue

            self._messages.append(message)
            if len(self._messages) > 5000:
                self._progress.status = "Writing messages to file..."
                await self._saver.save()

        if self._messages:
            self._progress.status = "Writing messages to file..."
            await self._saver.save()
        self.status = self._task = None

        self._progress.status = "Done!"

    async def export(self, block: bool=True) -> None:
        if self._task is not None or self.status is not None:
            return
        self.status = ExportStatus()
        coro = self._export(self._config.chat_id)
        if block:
            await coro
        else:
            asyncio.get_event_loop().create_task(coro)
