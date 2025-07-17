from __future__ import annotations

import bisect
from asyncio import Task, sleep, Lock, get_running_loop, Event
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO

from pyrogram import Client
from pyrogram.file_id import FileId


# Whole downloader will break if chunk_size inside pyrogram's get_file changes
CHUNK_SIZE = 1024 * 1024


class DownloadTask:
    def __init__(self, file_id: str, message_id: int, output_path: Path, priority: int, size: int) -> None:
        self.file_id = file_id
        self.message_id = message_id
        self.output_path = output_path
        self.priority = priority
        self.size = size
        self.offset = 0
        self.lock = Lock()
        self.file: BinaryIO | None = None
        self.active_tasks = 0
        self.failed_chunks: set[int] = set()
        self.done = Event()

    # TODO: add method to change priority


class Downloader:
    def __init__(self, client: Client, max_concurrent_downloads: int) -> None:
        self._client = client
        self._max_concurrent_downloads = max_concurrent_downloads

        self._running = False
        self._loop_task: Task | None = None

        self._tasks: list[DownloadTask] = []
        self._running_tasks: set[Task] = set()

        self._dc_init = set()
        self._dc_lock = Lock()

        self._loop = get_running_loop()
        self._write_executor = ThreadPoolExecutor(max_concurrent_downloads, thread_name_prefix="FileWrite")

    def add_task(self, file_id: str, message_id: int, output_path: Path, priority: int, size: int) -> DownloadTask:
        task = DownloadTask(file_id, message_id, output_path, priority, size)
        bisect.insort_right(self._tasks, task, key=lambda t: t.priority)
        return task

    @staticmethod
    def _open_file(path: Path, size: int) -> BinaryIO:
        fp = open(path, "wb")
        fp.truncate(size)
        return fp

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

    async def _loop_func(self) -> None:
        idx = 0
        while self._running or (self._tasks or self._running_tasks):
            if not self._tasks or len(self._running_tasks) > self._max_concurrent_downloads:
                await sleep(.1)
                continue

            base_priority = self._tasks[0].priority

            if idx >= len(self._tasks) or self._tasks[idx].priority > base_priority:
                idx = 0

            task = self._tasks[idx]
            async with task.lock:
                chunk_index = task.failed_chunks.pop() if task.failed_chunks else None


            new_task = self._loop.create_task(self._download_task_wrapper(task, chunk_index))
            self._running_tasks.add(new_task)
            new_task.add_done_callback(self._running_tasks.remove)

            idx += 1

            to_remove = []
            for rem_idx, task in enumerate(self._tasks):
                if task.priority > base_priority:
                    break
                async with task.lock:
                    if task.offset < task.size or task.active_tasks > 0 or task.failed_chunks:
                        continue

                to_remove.append(rem_idx)

            for rem_idx in reversed(to_remove):
                task = self._tasks.pop(rem_idx)
                task.file.close()
                task.done.set()

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






