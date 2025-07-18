from asyncio import sleep, get_running_loop
from datetime import datetime, UTC
from pathlib import Path

from pyrogram import Client
from pyrogram.file_id import PHOTO_TYPES, FileType, FileId

from .download.downloader import Downloader, DownloadTask
from .export_config import ExportConfig
from .export_progress import ExportProgressInternal


def get_file_name(
        client: Client,
        file_id: str,
        mime_type: str | None,
        date: int | None,
) -> str:
    file_id_obj = FileId.decode(file_id)

    file_type = file_id_obj.file_type
    date = date if isinstance(date, datetime) else datetime.now(UTC)

    guessed_extension = client.guess_extension(mime_type or "")

    if file_type in PHOTO_TYPES:
        extension = ".jpg"
    elif file_type == FileType.VOICE:
        extension = guessed_extension or ".ogg"
    elif file_type in (FileType.VIDEO, FileType.ANIMATION, FileType.VIDEO_NOTE):
        extension = guessed_extension or ".mp4"
    elif file_type == FileType.DOCUMENT:
        extension = guessed_extension or ".zip"
    elif file_type == FileType.STICKER:
        extension = guessed_extension or ".webp"
    elif file_type == FileType.AUDIO:
        extension = guessed_extension or ".mp3"
    else:
        extension = ".unknown"

    return (
        f"{FileType(file_id_obj.file_type).name.lower()}_"
        f"{date.strftime('%Y-%m-%d_%H-%M-%S')}_"
        f"{client.rnd_id()}"
        f"{extension}"
    )

class MediaExporter:
    def __init__(self, client: Client, config: ExportConfig, progress: ExportProgressInternal):
        self.client = client
        self.task = None
        self.ids: set[str | int] = set()
        self.all_ids: set[str | int] = set()
        self.progress = progress
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.failed_bytes = 0

        self._running = False
        self._downloading: dict[str | int, ...] = {}

        self._loop = get_running_loop()
        self._downloader = Downloader(client, config.max_concurrent_downloads)

    async def _wait_for_dl_complete(self, task: DownloadTask, task_id: int | str) -> None:
        await task.done.wait()

        self._downloading.pop(task_id, None)

        self.downloaded_bytes += task.size
        self._status()

    def add(self, file_id: str, download_dir: str, out_id: str | int, size: int, mime: str | None, date: int | None) -> DownloadTask | None:
        if out_id in self.all_ids:
            return self._downloading.get(out_id)

        self.total_bytes += size

        download_dir = Path(download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)
        out_path = download_dir / get_file_name(self.client, file_id, mime, date)

        task = self._downloader.add_task(file_id, 0, out_path, False, size)

        self._downloading[out_id] = task
        self.all_ids.add(out_id)

        self._loop.create_task(self._wait_for_dl_complete(task, out_id))

        self._status()

        return task

    def _status(self, status: str = None) -> None:
        self.progress.media_status = status or self.progress.media_status
        self.progress.media_queue = len(self._downloader._tasks_hi) + len(self._downloader._tasks_lo)
        self.progress.media_bytes = self.total_bytes
        self.progress.media_down_bytes = self.downloaded_bytes
        self.progress.changed()

    async def run(self) -> None:
        self._running = True
        self._downloader.start()

    async def stop(self) -> None:
        while self._downloading:
            await sleep(0)

        await self._downloader.stop()
        self._running = False
