import asyncio
from asyncio import sleep
from os.path import relpath
from typing import Union, Optional

from pyrogram import Client
from pyrogram.errors import RPCError

from .export_config import ExportConfig
from .progress_print import ProgressPrint


class MediaExporter:
    def __init__(self, client: Client, config: ExportConfig, media_dict: dict, progress: ProgressPrint):
        self.client = client
        self.config = config
        self.output = media_dict
        self.task = None
        self.queue: list[tuple[str, str, Union[str, int]]] = []
        self.ids: set[Union[str, int]] = set()
        self.all_ids: set[Union[str, int]] = set()
        self.progress = progress

        self._running = False

    def add(self, file_id: str, download_dir: str, out_id: Union[str, int]) -> None:
        if out_id in self.all_ids: return
        self.queue.append((file_id, download_dir, out_id))
        self.ids.add(out_id)
        self.all_ids.add(out_id)
        self._status()

    async def _download(self, file_id: str, download_dir: str, out_id: Union[str, int]) -> None:
        try:
            path = await self.client.download_media(file_id, file_name=download_dir)
        except RPCError:
            return
        path = relpath(path, self.config.output_dir.absolute())
        self.output[out_id] = path

    def _status(self, status: str=None) -> None:
        with self.progress.update():
            self.progress.media_status = status or self.progress.media_status
            self.progress.media_queue = len(self.queue)

    async def _task(self) -> None:
        while self._running:
            if not self.queue:
                self._status("Idle...")
                await sleep(.1)
                continue
            self._status("Downloading...")
            await self._download(*self.queue[0])
            _, _, task_id = self.queue.pop(0)
            self.ids.discard(task_id)

        self._status("Stopped...")

    async def run(self) -> None:
        self._running = True
        self.task = asyncio.get_event_loop().create_task(self._task())

    async def stop(self) -> None:
        await self.wait()
        self._running = False

    async def wait(self, messages: Optional[list[int]]=None) -> None:
        messages = set(messages) if messages is not None else None
        while self._running and self.queue:
            if messages is not None and not messages.intersection(self.ids):
                break
            await sleep(.1)
