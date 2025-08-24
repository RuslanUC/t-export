from __future__ import annotations

import asyncio
import bisect
from asyncio import Task, sleep, Lock, get_running_loop, Event, Semaphore
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import time
from typing import BinaryIO

from pyrogram import Client
from pyrogram.crypto import aes
from pyrogram.errors import FileReferenceInvalid, FileReferenceExpired, AuthBytesInvalid, VolumeLocNotFound, \
    CDNFileHashMismatch, AuthKeyUnregistered
from pyrogram.file_id import FileId, FileType, ThumbnailSource, FileIdCached
from pyrogram.raw.functions.auth import ExportAuthorization, ImportAuthorization
from pyrogram.raw.functions.upload import GetFile, GetCdnFile, ReuploadCdnFile, GetCdnFileHashes
from pyrogram.raw.types import InputPeerUser, InputPeerChat, InputPeerChannel, \
    InputPeerPhotoFileLocation, InputPhotoFileLocation, InputDocumentFileLocation
from pyrogram.raw.types.upload import File, FileCdnRedirect, CdnFileReuploadNeeded
from pyrogram.session import Session, Auth
from pyrogram.utils import get_channel_id

from texport.media import MEDIA_TYPES

# Whole downloader will break if chunk_size inside pyrogram's get_file changes
CHUNK_SIZE = 1024 * 1024


class DownloadTask:
    __slots__ = (
        "file_id", "message_id", "output_path", "high_priority", "size", "is_thumb", "offset", "lock", "file",
        "active_tasks", "failed_chunks", "done", "wrote_bytes", "task_id", "need_fileref_renew", "_downloader",
    )

    def __init__(
            self, file_id: str, message_id: int, output_path: Path, high_priority: bool, size: int, is_thumb: bool,
            *, task_id: int, downloader: Downloader,
    ) -> None:
        self.task_id = task_id
        # For testing file references renewing
        #if random.randint(0, 100) > 90:
        #    _id = FileId.decode(file_id)
        #    _id.file_reference = urandom(16)
        #    file_id = _id.encode()
        self.file_id = file_id
        self.message_id = message_id
        self.output_path = output_path
        self.high_priority = high_priority
        self.size = size
        self.is_thumb = is_thumb
        self.wrote_bytes = 0
        self.offset = 0
        self.lock = Lock()
        self.file: BinaryIO | None = None
        self.active_tasks = 0
        self.failed_chunks: set[int] = set()
        self.done = Event()

        self.need_fileref_renew = False
        self._downloader = downloader

    def set_priority_high(self, is_high: bool) -> None:
        if is_high == self.high_priority:
            return
        self._downloader.set_task_priority_high(self, is_high)

    def __lt__(self, other: DownloadTask) -> bool:
        return self.task_id < other.task_id


class Downloader:
    def __init__(self, client: Client, max_concurrent_downloads: int) -> None:
        self._client = client
        self._max_concurrent_tasks = max_concurrent_downloads + 1

        self._running = False
        self._loop_task: Task | None = None

        self._tasks_lo: list[DownloadTask] = []
        self._tasks_hi: list[DownloadTask] = []
        self._running_tasks: set[Task] = set()

        self._renewing_tasks: set[DownloadTask] = set()
        self._need_renew_tasks: set[DownloadTask] = set()
        self._last_renew_time = 0
        self._renew_task: Task | None = None

        self._loop = get_running_loop()
        self._write_executor = ThreadPoolExecutor(max_concurrent_downloads, thread_name_prefix="FileWrite")
        self._getfile_sem = Semaphore(max_concurrent_downloads)

        self._id_seq = 0

        self._tasks_changed = Event()

        self.bytes_downloaded = 0

    def add_task(
            self, file_id: str, message_id: int, output_path: Path, high_priority: bool, size: int, is_thumb: bool
    ) -> DownloadTask:
        self._id_seq += 1
        task = DownloadTask(
            file_id, message_id, output_path, high_priority, size, is_thumb, task_id=self._id_seq, downloader=self,
        )
        bisect.insort_left(self._tasks_hi if high_priority else self._tasks_lo, task)
        self._tasks_changed.set()
        return task

    def set_task_priority_high(self, task: DownloadTask, to_high: bool) -> None:
        old_queue = self._tasks_lo if to_high else self._tasks_hi
        new_queue = self._tasks_hi if to_high else self._tasks_lo

        task_idx = bisect.bisect_left(old_queue, task)
        if task_idx >= len(old_queue) or task_idx < 0 or old_queue[task_idx] is not task:
            return

        del old_queue[task_idx]

        task.high_priority = to_high
        bisect.insort_left(new_queue, task)
        self._tasks_changed.set()

    async def _renew_filerefs(self) -> None:
        to_renew_ids: dict[int, list[DownloadTask]] = defaultdict(list)

        while self._need_renew_tasks and len(to_renew_ids) < 100:
            task = self._need_renew_tasks.pop()
            self._renewing_tasks.add(task)
            to_renew_ids[task.message_id].append(task)

        if not to_renew_ids:
            return

        # TODO: pass channel/supergroup id
        for message in await self._client.get_messages(message_ids=list(to_renew_ids.keys()), replies=0):
            if message.id not in to_renew_ids:
                continue

            m = MEDIA_TYPES[message.media]
            media, thumb = m.get_media(message)

            for task in to_renew_ids[message.id]:
                obj = media
                if task.is_thumb:
                    obj = thumb
                if obj is None:
                    task.offset = task.size + 1
                    task.wrote_bytes = task.size
                else:
                    task.file_id = obj.file_id
                task.need_fileref_renew = False
                self._renewing_tasks.discard(task)

        self._need_renew_tasks.update(self._renewing_tasks)
        self._renewing_tasks.clear()

    async def _get_media_session(self, dc_id: int) -> Session:
        session = self._client.media_sessions.get(dc_id)
        if session:
            return session

        storage = self._client.storage

        async with self._client.media_sessions_lock:
            session = self._client.media_sessions[dc_id] = Session(
                self._client, dc_id,
                await Auth(self._client, dc_id, await storage.test_mode()).create()
                if dc_id != await storage.dc_id()
                else await storage.auth_key(),
                await storage.test_mode(),
                is_media=True
            )
            await session.start()

            if dc_id == await storage.dc_id():
                return session

            for _ in range(3):
                exported_auth = await self._client.invoke(ExportAuthorization(dc_id=dc_id))

                try:
                    await session.invoke(
                        ImportAuthorization(
                            id=exported_auth.id,
                            bytes=exported_auth.bytes
                        )
                    )
                except AuthBytesInvalid:
                    continue
                else:
                    break
            else:
                raise AuthBytesInvalid

            return session

    async def _get_file(self, file_id: FileId | FileIdCached, offset: int = 0) -> bytes:
        async with self._getfile_sem:
            file_type = file_id.file_type

            if file_type == FileType.CHAT_PHOTO:
                if file_id.chat_id > 0:
                    peer = InputPeerUser(user_id=file_id.chat_id, access_hash=file_id.chat_access_hash)
                else:
                    if file_id.chat_access_hash == 0:
                        peer = InputPeerChat(chat_id=-file_id.chat_id)
                    else:
                        peer = InputPeerChannel(
                            channel_id=get_channel_id(file_id.chat_id), access_hash=file_id.chat_access_hash
                        )

                location = InputPeerPhotoFileLocation(
                    peer=peer,
                    photo_id=file_id.media_id,
                    big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG
                )
            elif file_type == FileType.PHOTO:
                location = InputPhotoFileLocation(
                    id=file_id.media_id,
                    access_hash=file_id.access_hash,
                    file_reference=file_id.file_reference,
                    thumb_size=file_id.thumbnail_size
                )
            else:
                location = InputDocumentFileLocation(
                    id=file_id.media_id,
                    access_hash=file_id.access_hash,
                    file_reference=file_id.file_reference,
                    thumb_size=file_id.thumbnail_size
                )

            request = GetFile(location=location, offset=offset, limit=CHUNK_SIZE)

            session = await self._get_media_session(file_id.dc_id)

            retries = 5
            for i in range(retries):
                try:
                    r = await session.invoke(request, sleep_threshold=self._client.sleep_threshold)
                    break
                except AuthKeyUnregistered:
                    if i == (retries - 1):
                        raise

            if not isinstance(r, (File, FileCdnRedirect)):
                raise ValueError(f"Expected File or FileCdnRedirect, got {r.__class__.__name__}")

            if isinstance(r, File):
                return r.bytes

            storage = self._client.storage
            cdn_session = Session(
                self._client, r.dc_id, await Auth(self._client, r.dc_id, await storage.test_mode()).create(),
                await storage.test_mode(), is_media=True, is_cdn=True
            )

            try:
                await cdn_session.start()

                while True:
                    r2 = await cdn_session.invoke(
                        GetCdnFile(
                            file_token=r.file_token,
                            offset=offset,
                            limit=CHUNK_SIZE
                        )
                    )

                    if isinstance(r2, CdnFileReuploadNeeded):
                        try:
                            await session.invoke(
                                ReuploadCdnFile(
                                    file_token=r.file_token,
                                    request_token=r2.request_token
                                )
                            )
                        except VolumeLocNotFound:
                            raise
                        else:
                            continue

                    chunk = r2.bytes

                    # https://core.telegram.org/cdn#decrypting-files
                    decrypted_chunk = aes.ctr256_decrypt(
                        chunk,
                        r.encryption_key,
                        bytearray(
                            r.encryption_iv[:-4]
                            + (offset // 16).to_bytes(4, "big")
                        )
                    )

                    hashes = await session.invoke(GetCdnFileHashes(file_token=r.file_token, offset=offset))

                    # https://core.telegram.org/cdn#verifying-files
                    for i, h in enumerate(hashes):
                        cdn_chunk = decrypted_chunk[h.limit * i: h.limit * (i + 1)]
                        CDNFileHashMismatch.check(
                            h.hash == sha256(cdn_chunk).digest(),
                            "h.hash == sha256(cdn_chunk).digest()"
                        )

                    return decrypted_chunk
            except:
                raise
            finally:
                await cdn_session.stop()

            raise RuntimeError("Failed to download file chunk")

    @staticmethod
    def _open_file(path: Path, size: int) -> BinaryIO:
        fp = open(path, "wb")
        fp.truncate(size)
        return fp

    @staticmethod
    def _write_file(file: BinaryIO, offset: int, data: bytes) -> None:
        file.seek(offset)
        file.write(data)

    async def _download_task(self, task: DownloadTask, chunk_offset: int) -> None:
        if chunk_offset > task.size:
            return

        async with task.lock:
            if task.file is None:
                task.file = await self._loop.run_in_executor(
                    self._write_executor, self._open_file,
                    task.output_path, task.size,
                )

        file_id = FileId.decode(task.file_id)
        chunk = await self._get_file(file_id, chunk_offset)

        async with task.lock:
            await self._loop.run_in_executor(
                self._write_executor, self._write_file,
                task.file, chunk_offset, chunk,
            )
            task.wrote_bytes += len(chunk)

    async def _download_task_wrapper(self, task: DownloadTask, chunk_offset: int | None = None) -> None:
        async with task.lock:
            task.active_tasks += 1
            if chunk_offset is None:
                chunk_offset, task.offset = task.offset, task.offset + CHUNK_SIZE
            else:
                task.failed_chunks.discard(chunk_offset)

        try:
            await self._download_task(task, chunk_offset)
        except (FileReferenceInvalid, FileReferenceExpired):
            task.need_fileref_renew = True
            async with task.lock:
                task.failed_chunks.add(chunk_offset)
        except:
            async with task.lock:
                task.failed_chunks.add(chunk_offset)
            raise
        finally:
            async with task.lock:
                task.active_tasks -= 1

        self._tasks_changed.set()

    async def _loop_func(self) -> None:
        idx_hi = 0
        idx_lo = 0

        while self._running or self._tasks_hi or self._tasks_lo or self._running_tasks:
            count_hi = len(self._tasks_hi)
            count_lo = len(self._tasks_lo)

            if (not count_hi and not count_lo) or (len(self._running_tasks) >= self._max_concurrent_tasks):
                try:
                    await asyncio.wait_for(self._tasks_changed.wait(), timeout=0.1)
                except TimeoutError:
                    ...
                else:
                    self._tasks_changed.clear()
                continue

            task = None

            to_check = (
                (self._tasks_hi, count_hi, idx_hi, True),
                (self._tasks_lo, count_lo, idx_lo, False),
            )

            for tasks, count, start_idx, is_high in to_check:
                for idx in range(count):
                    if (idx % 10) == 0:
                        await sleep(0)

                    task_idx = (start_idx + idx) % count
                    task_check = tasks[task_idx]
                    if task_check.offset >= task_check.size and not task_check.failed_chunks:
                        continue
                    if task_check.need_fileref_renew:
                        if task_check not in self._renewing_tasks:
                            if not self._need_renew_tasks:
                                self._last_renew_time = time()
                            self._need_renew_tasks.add(task_check)
                        continue

                    task = task_check
                    if is_high:
                        idx_hi = task_idx
                    else:
                        idx_lo = task_idx

                    break

                if task is not None:
                    break

            if task is not None:
                async with task.lock:
                    chunk_index = task.failed_chunks.pop() if task.failed_chunks else None
                new_task = self._loop.create_task(self._download_task_wrapper(task, chunk_index))
                self._running_tasks.add(new_task)
                new_task.add_done_callback(self._running_tasks.remove)

            if self._need_renew_tasks \
                    and ((time() - self._last_renew_time) > 5 or len(self._need_renew_tasks) >= 100) \
                    and self._renew_task is None:
                self._renew_task = self._loop.create_task(self._renew_filerefs())
                self._renew_task.add_done_callback(lambda _: setattr(self, "_renew_task", None))
                self._last_renew_time = time()

            await sleep(0)

            for tasks, _, _, _ in to_check:
                await sleep(0)
                to_remove = []

                for rem_idx, task in enumerate(tasks):
                    if task.wrote_bytes < task.size or task.active_tasks > 0 or task.failed_chunks or not task.file:
                        continue

                    to_remove.append(rem_idx)

                for rem_idx in reversed(to_remove):
                    await sleep(0)
                    task = tasks.pop(rem_idx)
                    task.file.close()
                    task.done.set()

                if to_remove:
                    self._tasks_changed.set()

    def start(self) -> None:
        if self._running and self._loop_task:
            return
        elif not self._running and self._loop_task:
            self._running = True
            return

        self._running = True
        self._loop_task = self._loop.create_task(self._loop_func())

    async def stop(self) -> None:
        self._running = False
        if self._loop_task is None:
            return
        try:
            await self._loop_task
        except:
            ...
        self._loop_task = None
