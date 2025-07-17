import asyncio
from asyncio import sleep, Task, Semaphore, create_task
from functools import partial
from os.path import relpath
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import RPCError

from .export_config import ExportConfig
from .export_progress import ExportProgressInternal


class MediaExporter:
    def __init__(self, client: Client, config: ExportConfig, media_dict: dict, progress: ExportProgressInternal):
        self.client = client
        self.config = config
        self.output = media_dict
        self.task = None
        self.queue: list[tuple[str, str, str | int, int]] = []
        self.ids: set[str | int] = set()
        self.all_ids: set[str | int] = set()
        self.progress = progress
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.failed_bytes = 0

        self._running = False
        self._downloading: dict[str | int, ...] = {}
        self._sem = Semaphore(self.config.max_concurrent_downloads)

    def add(self, file_id: str, download_dir: str, out_id: str | int, size: int) -> None:
        if out_id in self.all_ids: return
        self.total_bytes += size
        self.queue.append((file_id, download_dir, out_id, size))
        self.ids.add(out_id)
        self.all_ids.add(out_id)
        self._status()

    def _download_done(self, _: Task[None], task_id: int | str) -> None:
        self._downloading.pop(task_id, None)
        self.ids.discard(task_id)

    async def _download(self, file_id: str, download_dir: str, out_id: str | int, size: int) -> None:
        async with self._sem:
            try:
                path = await self.client.download_media(file_id, file_name=download_dir)
            except RPCError:
                self.failed_bytes += size
                return

        self.downloaded_bytes += size
        self.output[out_id] = relpath(path, Path(download_dir).parent.absolute())

    def _status(self, status: str = None) -> None:
        self.progress.media_status = status or self.progress.media_status
        self.progress.media_queue = len(self.queue) + len(self._downloading)
        self.progress.media_bytes = self.total_bytes
        self.progress.media_down_bytes = self.downloaded_bytes
        self.progress.media_fail_bytes = self.failed_bytes
        self.progress.changed()

    async def _task(self) -> None:
        # use create_task and semaphore
        downloading: dict[str | int, Task] = {}
        while self._running:
            if not self.queue and not downloading:
                self._status("Idle...")
                await sleep(.1)
                continue
            self._status("Downloading...")
            *args, task_id = self.queue.pop(0)
            task = create_task(self._download(*args, task_id))
            self._downloading[task_id] = task
            task.add_done_callback(partial(self._download_done, task_id=task_id))

        self._status("Stopped...")

    async def run(self) -> None:
        self._running = True
        self.task = asyncio.get_event_loop().create_task(self._task())

    async def stop(self) -> None:
        await self.wait()
        self._running = False

    async def wait(self, messages: list[int] | None = None) -> None:
        messages = set(messages) if messages is not None else None
        while self._running and (self.queue or self._downloading):
            if messages is not None and not messages.intersection(self.ids):
                break
            await sleep(.1)
