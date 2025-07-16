from asyncio import get_running_loop
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from os.path import exists

from pyrogram.types import Message as PyroMessage

from . import MediaExporter
from .export_config import ExportConfig
from .html.base import EXPORT_FMT_BEFORE_MESSAGES, EXPORT_AFTER_MESSAGES, Export
from .html.message import DateMessage, Message
from .resources import unpack_to


class MessageToSave:
    __slots__ = ("message", "media_ids", "downloader",)

    def __init__(
            self, message: PyroMessage, downloader: MediaExporter | None,
    ) -> None:
        self.message = message
        self.downloader = downloader

    async def wait(self) -> PyroMessage:
        if self.downloader:
            await self.downloader.wait([self.message.id, f"{self.message.id}_thumb"])
        return self.message

class MessagesSaver:
    _sub_pos = len(EXPORT_AFTER_MESSAGES)

    def __init__(self, media: dict[int | str, str], config: ExportConfig):
        self.parts = defaultdict(lambda: 0)
        self.media = media
        self.config = config

        self._loop = get_running_loop()
        self._write_executor = ThreadPoolExecutor(2, thread_name_prefix="ExportWriter")

    @staticmethod
    def _write(path: str, append_str: str, seek_to: int) -> int:
        with open(path, "a" if seek_to else "w", encoding="utf8") as f:
            f.seek(seek_to)
            f.write(append_str)
            return f.tell()

    async def save(self, messages: list[MessageToSave]) -> None:
        if not messages:
            return

        chat = messages[0].message.chat

        out_dir = self.config.output_dir / str(chat.id)

        if not exists(out_dir / "js") or not exists(out_dir / "images") or not exists(out_dir / "css"):
            unpack_to(out_dir)

        file_path = f"{out_dir}/messages{self.parts[chat.id]}.html"
        self.parts[chat.id] += 1

        header = EXPORT_FMT_BEFORE_MESSAGES.format(title=chat.first_name)
        if self.config.partial_writes:
            pos = await self._loop.run_in_executor(self._write_executor, self._write, file_path, header, 0)
        else:
            pos = 0

        prev: PyroMessage | None = None
        dates = 0
        to_write = ""
        for message in messages:
            message = await message.wait()

            if prev is not None and prev.date.day != message.date.day:
                dates -= 1
                to_write += DateMessage(message.date, dates).to_html()

            media = self.media.pop(message.id, None)
            media_thumb = self.media.pop(f"{message.id}_thumb", None)

            to_write += Message(
                message, media, media_thumb, prev is not None and prev.from_user.id == message.from_user.id
            ).to_html()

            prev = message

            if self.config.partial_writes:
                pos = await self._loop.run_in_executor(self._write_executor, self._write, file_path, to_write, pos)
                pos -= self._sub_pos
                to_write = ""

        if not self.config.partial_writes:
            await self._loop.run_in_executor(
                self._write_executor, self._write, file_path, Export(chat.first_name, to_write).to_html(), 0,
            )

