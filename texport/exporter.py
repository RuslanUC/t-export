import asyncio
from asyncio import sleep, Task
from time import time
from typing import TypeVar, Callable, ParamSpec, Awaitable, cast

from pyrogram import Client
from pyrogram.errors import FloodWait, PeerIdInvalid
from pyrogram.raw.base import InputPeer
from pyrogram.raw.functions.account import InitTakeoutSession
from pyrogram.raw.functions.messages import GetHistory
from pyrogram.raw.types import InputChannel, InputUser
from pyrogram.raw.types.messages import Messages, MessagesSlice
from pyrogram.types import Message as PyroMessage

from . import ExportConfig, MediaExporter, Preloader, ExportProgress
from .download.downloader import DownloadTask
from .export_progress import ExportProgressInternal
from .media import MEDIA_TYPES, ExpiredMedia
from .messages_saver import MessageToSave, MessageSaverBase

T = TypeVar("T")
P = ParamSpec("P")


async def _flood_wait(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T | None:
    for i in range(5):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await sleep(e.value + 1)


ProgressCallback = Callable[[ExportProgress], Awaitable]


class Exporter:
    def __init__(self, client: Client, export_config: ExportConfig=None):
        self._config = export_config or ExportConfig()
        self._client = client
        self._task = None
        self._progress_task = None
        self._progress = ExportProgressInternal()
        self._media_downloader = MediaExporter(client, export_config, self._progress)
        self._excluded_media = self._config.excluded_media()
        self._loop = asyncio.get_running_loop()
        self._write_tasks: set[Task] = set()

        self._progress_callbacks: set[ProgressCallback] = set()

    def add_progress_callback(self, func: ProgressCallback) -> ProgressCallback:
        self._progress_callbacks.add(func)
        return func

    def remove_progress_callback(self, func: ProgressCallback) -> None:
        self._progress_callbacks.add(func)

    def _add_downloader_task(self, message_id: int, media: ..., out_dir: str, is_thumb: bool) -> DownloadTask | None:
        if media is None:
            return None

        mime = getattr(media, "mime_type", None)
        date = getattr(media, "date", None)
        return self._media_downloader.add(media.file_id, out_dir, message_id, is_thumb, media.file_size, mime, date)

    async def _export_media(self, message: PyroMessage) -> tuple[DownloadTask | None, DownloadTask | None]:
        if message.media not in MEDIA_TYPES or message.media in self._excluded_media:
            return None, None

        m = MEDIA_TYPES[message.media]
        media, thumb = m.get_media(message)
        if media is None \
                or isinstance(media, ExpiredMedia) \
                or (m.has_size_limit and ((media.file_size or 0) > self._config.size_limit * 1024 * 1024)):
            return None, None

        if not m.downloadable:
            return None, None

        chat_output_dir = (self._config.output_dir / f"{message.chat.id}").absolute()

        media_task = self._add_downloader_task(message.id, media, f"{chat_output_dir}/{m.dir_name}/", False)
        thumb_task = self._add_downloader_task(message.id, thumb, f"{chat_output_dir}/thumbs/", True)

        return media_task, thumb_task

    def _enqueue_save(self, savers: list[MessageSaverBase], message: MessageToSave | None) -> None:
        tasks = []

        for saver in savers:
            if message is not None:
                task = saver.save_maybe(message)
            else:
                task = saver.save()

            if task is not None:
                tasks.append(task)

        for task in tasks:
            self._write_tasks.update(tasks)
            task.add_done_callback(self._write_tasks.remove)

        if tasks:
            self._progress.status = "Writing messages to file..."
            self._progress.changed()

    async def _get_history(
            self, peer: InputPeer | InputUser | InputChannel, offset_date: int, offset_id: int, limit: int, min_id: int,
    ) -> Messages | MessagesSlice:
        return await self._client.invoke(GetHistory(
            peer=peer,
            offset_date=offset_date,
            offset_id=offset_id,
            add_offset=0,
            limit=limit,
            max_id=0,
            min_id=min_id,
            hash=0,
        ))

    async def _get_min_max_ids(self, chat_id: int | str) -> tuple[int, int]:
        from_date = int(self._config.from_date.timestamp())
        to_date = int(self._config.to_date.timestamp())

        date_offset_min = (from_date - 1) if from_date > 0 else 1
        date_offset_max = (to_date + 86400) if to_date < time() else int(time())

        peer = await self._client.resolve_peer(chat_id)
        min_messages = await self._get_history(peer, date_offset_min, 0, 1, 0)
        max_messages = await self._get_history(peer, date_offset_max, 0, 1, 0)

        min_messages = cast(list[PyroMessage], min_messages.messages)
        max_messages = cast(list[PyroMessage], max_messages.messages)

        min_message_id = (min_messages[0].id - 1) if min_messages else 0
        max_message_id = (max_messages[0].id + 1) if max_messages else 0

        return min_message_id, max_message_id

    async def _progress_func(self) -> None:
        while (new_progress := await self._progress.wait()) is not None:
            for callback in self._progress_callbacks:
                await callback(new_progress)

    async def _try_fix_peer_id(
            self, peer_id: str | int,
    ) -> str | int:
        try:
            await self._client.resolve_peer(peer_id)
            return peer_id
        except PeerIdInvalid:
            pass

        if not isinstance(peer_id, int):
            try:
                peer_id = int(peer_id)
                await self._client.resolve_peer(peer_id)
                return peer_id
            except ValueError:
                pass

        raise PeerIdInvalid

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

        if not self._config.formats:
            raise ValueError("Expected at least one format to be exported.")

        savers = [
            MessageSaverBase.new_by_format(fmt, self._config)
            for fmt in self._config.formats
        ]

        await self._media_downloader.run()

        self._progress.start()
        self._progress_task = self._loop.create_task(self._progress_func())

        loaded = 0
        chat_ids = []

        message_ranges: dict[int | str, tuple[int, int]] = {}
        counts: dict[int | str, int] = {}
        for chat_id in self._config.chat_ids:
            chat_id = await self._try_fix_peer_id(chat_id)
            chat_ids.append(chat_id)

            message_ranges[chat_id] = await self._get_min_max_ids(chat_id)
            min_id, max_id = message_ranges[chat_id]
            id_diff = (max_id - min_id) if min_id > 0 and max_id > 0 else (2 ** 31 - 1)

            if not self._config.count_messages:
                continue

            resp = await _flood_wait(
                self._get_history,
                peer=await self._client.resolve_peer(chat_id),
                offset_date=0,
                offset_id=max_id,
                limit=1,
                min_id=min_id,
            )

            if resp is None:
                count = 0
            elif isinstance(resp, Messages):
                count = min(len(resp.messages), id_diff)
            else:
                count = min(resp.count, id_diff)

            counts[chat_id] = count
            self._progress.approx_messages_count += count
            self._progress.changed()

        if self._config.preload:
            messages_iter = Preloader(self._client, self._progress, chat_ids, self._export_media)
        else:
            messages_iter = self._client.get_chat_history

        for chat_id, (min_id, max_id) in message_ranges.items():
            loaded_start = loaded
            message: MessageToSave | PyroMessage
            async for message in messages_iter(chat_id, min_id=min_id, max_id=max_id):
                message_to_save: MessageToSave
                if not self._config.preload:
                    message_to_save = MessageToSave(message, None, None)
                else:
                    message_to_save = message
                    message = message.message

                loaded += 1
                self._progress.status = "Exporting messages..."
                self._progress.messages_exported = loaded
                self._progress.changed()

                if not message.text and not message.caption and message.media not in MEDIA_TYPES:
                    continue

                if message.media and not self._config.preload:
                    message_to_save.media_task, message_to_save.thumb_task = await self._export_media(message)

                self._enqueue_save(savers, message_to_save)

            self._enqueue_save(savers, None)

            if chat_id in counts:
                old_count = counts[chat_id]
                real_count = loaded - loaded_start
                self._progress.approx_messages_count -= old_count
                self._progress.approx_messages_count += real_count
                self._progress.changed()

                counts[chat_id] = real_count

        self._progress.status = "Waiting for all messages to be saved..."
        self._progress.changed()

        while self._write_tasks:
            await sleep(0)

        self._task = None

        self._progress.status = "Stopping media downloader..."
        self._progress.changed()

        await self._media_downloader.stop()

        self._progress.status = "Done!"
        self._progress.changed()

        if self._progress_task is not None:
            self._progress.stop()
            await self._progress_task
            self._progress_task = None

    async def export(self, block: bool=True) -> None:
        if self._task is not None:
            return
        coro = self._export()
        if block:
            await coro
        else:
            self._loop.create_task(coro)
