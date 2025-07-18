from __future__ import annotations

import asyncio
import bisect
from asyncio import Task, sleep, Lock, get_running_loop, Event, Semaphore
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO

from pyrogram import Client
from pyrogram.file_id import FileId

# Whole downloader will break if chunk_size inside pyrogram's get_file changes
CHUNK_SIZE = 1024 * 1024


class DownloadTask:
    __slots__ = (
        "file_id", "message_id", "output_path", "high_priority", "size", "offset", "lock", "file", "active_tasks",
        "failed_chunks", "done", "task_id", "_downloader",
    )

    def __init__(
            self, file_id: str, message_id: int, output_path: Path, high_priority: bool, size: int,
            *, task_id: int, downloader: Downloader,
    ) -> None:
        self.task_id = task_id
        self.file_id = file_id
        self.message_id = message_id  # TODO: implement file_id (file_reference) renewing when expired
        self.output_path = output_path
        self.high_priority = high_priority
        self.size = size
        self.offset = 0
        self.lock = Lock()
        self.file: BinaryIO | None = None
        self.active_tasks = 0
        self.failed_chunks: set[int] = set()
        self.done = Event()

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
        self._max_concurrent_tasks = max_concurrent_downloads * 2

        self._running = False
        self._loop_task: Task | None = None

        self._tasks_lo: list[DownloadTask] = []
        self._tasks_hi: list[DownloadTask] = []
        self._running_tasks: set[Task] = set()

        self._dc_init = set()
        self._dc_lock = Lock()

        self._loop = get_running_loop()
        self._write_executor = ThreadPoolExecutor(max_concurrent_downloads, thread_name_prefix="FileWrite")
        self._old_sem = client.get_file_semaphore
        client.get_file_semaphore = Semaphore(max_concurrent_downloads)

        self._id_seq = 0

        self._tasks_changed = Event()

        self.bytes_downloaded = 0

    def add_task(
            self, file_id: str, message_id: int, output_path: Path, high_priority: bool, size: int,
    ) -> DownloadTask:
        self._id_seq += 1
        task = DownloadTask(
            file_id, message_id, output_path, high_priority, size, task_id=self._id_seq, downloader=self,
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

    @staticmethod
    def _open_file(path: Path, size: int) -> BinaryIO:
        fp = open(path, "wb")
        fp.truncate(size)
        return fp

    # TODO: sometimes, for some reason, this function raises error because file is closed ???
    @staticmethod
    def _write_file(file: BinaryIO, offset: int, data: bytes) -> None:
        file.seek(offset)
        file.write(data)

    async def _download_task(self, task: DownloadTask, chunk_index: int) -> None:
        if (chunk_index * CHUNK_SIZE) > task.size:
            return

        async with task.lock:
            if task.file is None:
                task.file = await self._loop.run_in_executor(
                    self._write_executor, self._open_file,
                    task.output_path, task.size,
                )

        file_id = FileId.decode(task.file_id)
        get_file_tup = (file_id, 0, 1, chunk_index, None, ())
        chunk = None

        dc_was_initialized = False
        async with self._dc_lock:
            if file_id.dc_id in self._dc_init:
                dc_was_initialized = True
            else:
                chunk = await anext(self._client.get_file(*get_file_tup))

        if dc_was_initialized:
            chunk = await anext(self._client.get_file(*get_file_tup))

        async with task.lock:
            await self._loop.run_in_executor(
                self._write_executor, self._write_file,
                task.file, chunk_index * CHUNK_SIZE, chunk,
            )

    async def _download_task_wrapper(self, task: DownloadTask, chunk_index: int | None = None) -> None:
        async with task.lock:
            task.active_tasks += 1
            if chunk_index is None:
                this_offset, task.offset = task.offset, task.offset + CHUNK_SIZE
                chunk_index = this_offset // CHUNK_SIZE
            else:
                if chunk_index in task.failed_chunks:
                    task.failed_chunks.remove(chunk_index)

        try:
            await self._download_task(task, chunk_index)
        except:
            async with task.lock:
                task.failed_chunks.add(chunk_index)
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

            if (not count_hi and not count_lo) or len(self._running_tasks) > self._max_concurrent_tasks:
                try:
                    await asyncio.wait_for(self._tasks_changed.wait(), timeout=0.1)
                except TimeoutError:
                    continue
                else:
                    self._tasks_changed.clear()

            task = None

            to_check = (
                (self._tasks_hi, count_hi, idx_hi, True),
                (self._tasks_lo, count_lo, idx_lo, False),
            )

            for tasks, count, start_idx, is_high in to_check:
                await sleep(0)
                for idx in range(count):
                    task_idx = (start_idx + idx) % count
                    task_check = tasks[task_idx]
                    async with task_check.lock:
                        if task_check.offset > task_check.size and not task_check.failed_chunks:
                            continue

                    task = task_check
                    if is_high:
                        idx_hi = task_idx
                    else:
                        idx_lo = task_idx

                    break

            if task is not None:
                async with task.lock:
                    chunk_index = task.failed_chunks.pop() if task.failed_chunks else None
                    new_task = self._loop.create_task(self._download_task_wrapper(task, chunk_index))
                    self._running_tasks.add(new_task)
                    new_task.add_done_callback(self._running_tasks.remove)

            await sleep(0)

            for tasks, _, _, _ in to_check:
                await sleep(0)
                to_remove = []

                for rem_idx, task in enumerate(tasks):
                    async with task.lock:
                        if task.offset < task.size or task.active_tasks > 0 or task.failed_chunks:
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






