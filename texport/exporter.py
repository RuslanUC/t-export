import asyncio
from asyncio import sleep, Task
from time import time
from typing import TypeVar, Callable, ParamSpec

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.raw.functions.account import InitTakeoutSession
from pyrogram.raw.functions.messages import GetHistory
from pyrogram.raw.types.messages import Messages, MessagesSlice
from pyrogram.types import Message as PyroMessage

from . import ExportConfig, MediaExporter, Preloader, MessagesSaver, ProgressPrint
from .media import MEDIA_TYPES
from .messages_saver import MessageToSave

T = TypeVar("T")
P = ParamSpec("P")


async def _flood_wait(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T | None:
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
        self._media: dict[int | str, str] = {}
        self._saver = MessagesSaver(self._media, export_config)
        self._media_downloader = MediaExporter(client, export_config, self._media, self.progress)
        self._excluded_media = self._config.excluded_media()
        self._loop = asyncio.get_running_loop()
        self._write_tasks: set[Task] = set()

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

            self._media_downloader.add(media.file_id, f"{chat_output_dir}/{m.dir_name}/", message.id, media.file_size)
            if hasattr(media, "thumbs") and media.thumbs:
                thumb = media.thumbs[0]
                self._media_downloader.add(thumb.file_id, f"{chat_output_dir}/thumbs/", f"{message.id}_thumb", thumb.file_size)

    async def _write(self, messages: list[MessageToSave]) -> None:
        #self.progress.status = "Waiting for all media to be downloaded..."
        #await self._media_downloader.wait(wait_media)
        self.progress.status = "Writing messages to file..."
        task = self._loop.create_task(self._saver.save(messages))
        self._write_tasks.add(task)
        task.add_done_callback(self._write_tasks.remove)

    async def _get_min_max_ids(self, chat_id: int | str) -> tuple[int, int]:
        from_date = int(self._config.from_date.timestamp())
        to_date = int(self._config.to_date.timestamp())

        date_offset_min = (from_date - 1) if from_date > 0 else 0
        date_offset_max = (to_date + 86400) if to_date < time() else 0

        peer = await self._client.resolve_peer(chat_id)
        min_messages: Messages | MessagesSlice = await self._client.invoke(GetHistory(
            peer=peer, offset_date=date_offset_min, offset_id=0, add_offset=0, limit=1, max_id=0, min_id=0, hash=0,
        ))
        max_messages: Messages | MessagesSlice = await self._client.invoke(GetHistory(
            peer=peer, offset_date=date_offset_max, offset_id=0, add_offset=0, limit=1, max_id=0, min_id=0, hash=0,
        ))

        min_messages: list[PyroMessage] = min_messages.messages
        max_messages: list[PyroMessage] = max_messages.messages

        min_message_id = min_messages[0].id if min_messages else 0
        max_message_id = max_messages[0].id if max_messages else 0

        return min_message_id, max_message_id


    async def _export(self):
        if self._config.use_takeout_api and not await self._client.storage.is_bot() and not self._client.takeout_id:
            self._client.takeout_id = (await self._client.invoke(InitTakeoutSession(
                message_users=True,
                message_chats=True,
                message_megagroups=True,
                message_channels=True,
                files=True,
                file_max_size=1024 * 1024 * 1024 * 4,
            ))).id

        await self._media_downloader.run()

        loaded = 0
        messages: list[MessageToSave] = []

        message_ranges: dict[int | str, tuple[int, int]] = {}
        counts: dict[int | str, int] = {}
        for chat_id in self._config.chat_ids:
            message_ranges[chat_id] = await self._get_min_max_ids(chat_id)
            min_id, max_id = message_ranges[chat_id]
            id_diff = (max_id - min_id) if min_id > 0 and max_id > 0 else (2 ** 31 - 1)

            if not self._config.count_messages:
                continue

            resp = await _flood_wait(self._client.invoke, GetHistory(
                peer=await self._client.resolve_peer(chat_id),
                offset_id=max_id,
                offset_date=0,
                add_offset=0,
                limit=1,
                max_id=0,
                min_id=min_id,
                hash=0,
            ))

            if resp is None:
                count = 0
            elif isinstance(resp, Messages):
                count = min(len(resp.messages), id_diff)
            else:
                count = min(resp.count, id_diff)

            counts[chat_id] = count
            self.progress.approx_messages_count += count

        messages_iter = Preloader(self._client, self.progress, self._config.chat_ids, self._export_media) \
            if self._config.preload else self._client.get_chat_history

        for chat_id, (min_id, max_id) in message_ranges.items():
            loaded_start = loaded
            async for message in messages_iter(chat_id, min_id=min_id, max_id=max_id):
                loaded += 1
                with self.progress.update():
                    self.progress.status = "Exporting messages..."
                    self.progress.messages_exported = loaded

                if not message.text and not message.caption and message.media not in MEDIA_TYPES:
                    continue

                if message.media:
                    messages.append(MessageToSave(message, self._media_downloader))
                    await self._export_media(message)
                else:
                    messages.append(MessageToSave(message, None))

                if len(messages) >= self._config.write_threshold:
                    await self._write(messages)
                    messages = []

            if messages:
                await self._write(messages)
                messages = []

            if chat_id in counts:
                old_count = counts[chat_id]
                real_count = loaded - loaded_start
                with self.progress.update():
                    self.progress.approx_messages_count -= old_count
                    self.progress.approx_messages_count += real_count

                counts[chat_id] = real_count

        self.progress.status = "Waiting for all messages to be saved..."
        while self._write_tasks:
            await sleep(0)

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
            self._loop.create_task(coro)
