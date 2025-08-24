from asyncio import get_running_loop
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from os.path import exists, relpath

from pyrogram.enums import ChatType
from pyrogram.types import Message as PyroMessage, Chat

from .download.downloader import DownloadTask
from .export_config import ExportConfig
from .html.base import EXPORT_FMT_BEFORE_MESSAGES, EXPORT_AFTER_MESSAGES, Export
from .html.message import DateMessage, Message
from .resources import unpack_to


class MessageToSave:
    __slots__ = ("message", "media_task", "thumb_task",)

    def __init__(
            self, message: PyroMessage, media_task: DownloadTask | None, thumb_task: DownloadTask | None,
    ) -> None:
        self.message = message
        self.media_task = media_task
        self.thumb_task = thumb_task

    def need_to_wait(self) -> bool:
        return (self.media_task is not None and not self.media_task.done.is_set()) \
            or (self.thumb_task is not None and not self.thumb_task.done.is_set())

    async def wait(self) -> PyroMessage:
        if self.media_task is not None:
            self.media_task.set_priority_high(True)
        if self.thumb_task is not None:
            self.thumb_task.set_priority_high(True)

        if self.media_task is not None:
            await self.media_task.done.wait()
        if self.thumb_task is not None:
            await self.thumb_task.done.wait()

        return self.message


def _get_chat_name(chat: Chat) -> str:
    if chat.type in (ChatType.PRIVATE, ChatType.BOT):
        if chat.last_name:
            return f"{chat.first_name} {chat.last_name}"
        return chat.first_name
    elif chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        return chat.title

    return "Unknown"


class MessagesSaver:
    _sub_pos = len(EXPORT_AFTER_MESSAGES)

    def __init__(self, config: ExportConfig):
        self.parts = defaultdict(lambda: 0)
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

        out_dir = (self.config.output_dir / str(chat.id)).absolute()

        if not exists(out_dir / "js") or not exists(out_dir / "images") or not exists(out_dir / "css"):
            unpack_to(out_dir)

        file_path = f"{out_dir}/messages{self.parts[chat.id]}.html"
        self.parts[chat.id] += 1


        if self.config.partial_writes:
            header = EXPORT_FMT_BEFORE_MESSAGES.format(title=_get_chat_name(chat))
            header += EXPORT_AFTER_MESSAGES
            pos = await self._loop.run_in_executor(self._write_executor, self._write, file_path, header, 0)
            pos -= self._sub_pos
        else:
            pos = 0

        prev: PyroMessage | None = None
        prev_author_id: int = 0
        dates = 0
        to_write = ""
        for task in messages:
            if task.need_to_wait() and self.config.partial_writes and to_write:
                to_write += EXPORT_AFTER_MESSAGES
                pos = await self._loop.run_in_executor(self._write_executor, self._write, file_path, to_write, pos)
                pos -= self._sub_pos
                to_write = ""

            message = await task.wait()

            if prev is not None and prev.date.day != message.date.day:
                dates -= 1
                to_write += DateMessage(message.date, dates).to_html()

            media_path = relpath(task.media_task.output_path, out_dir) if task.media_task else None
            thumb_path = relpath(task.thumb_task.output_path, out_dir) if task.thumb_task else None

            author_id = 0
            if message.from_user:
                author_id = message.from_user.id
            elif message.sender_chat:
                author_id = message.sender_chat.id

            to_write += Message(
                message, media_path, thumb_path, prev is not None and prev_author_id == author_id
            ).to_html()

            prev = message
            prev_author_id = author_id

        if not self.config.partial_writes:
            to_write = Export(_get_chat_name(chat), to_write).to_html()
        else:
            to_write += EXPORT_AFTER_MESSAGES

        if to_write:
            await self._loop.run_in_executor(
                self._write_executor, self._write, file_path, to_write, pos,
            )
