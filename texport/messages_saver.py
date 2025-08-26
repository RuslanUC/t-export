from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from asyncio import get_running_loop, Task, Lock
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from os.path import exists, relpath
from pathlib import Path
from typing import cast

from pyrogram.enums import ChatType
from pyrogram.raw.types import User
from pyrogram.types import Message as PyroMessage, Chat

from .download.downloader import DownloadTask
from .export_config import ExportConfig
from .html.base import EXPORT_FMT_BEFORE_MESSAGES, EXPORT_AFTER_MESSAGES, Export, BaseComponent
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


def _get_chat_type(chat: Chat) -> str:
    # "verification_codes" and "replies" types are not supported for now

    if chat.type is ChatType.PRIVATE:
        raw = getattr(chat, "_raw")
        if isinstance(raw, User) and cast(User, raw).is_self:
            return "saved_messages"
        return "personal_chat"
    elif chat.type is ChatType.BOT:
        return "bot_chat"
    elif chat.type is ChatType.GROUP:
        if chat.is_public:
            # Seems like official Telegram application does not have chat type for public group:
            # https://github.com/telegramdesktop/tdesktop/blob/0cf3325655173a04764d58eb50b6639d295eca62/Telegram/SourceFiles/export/output/export_output_json.cpp#L1562
            return "public_supergroup"
        else:
            return "private_group"
    elif chat.type is ChatType.SUPERGROUP:
        if chat.is_public:
            return "public_supergroup"
        else:
            return "private_supergroup"
    elif chat.type is ChatType.CHANNEL:
        if chat.is_public:
            return "public_channel"
        else:
            return "public_channel"

    return ""


class MessageSaverBase(ABC):
    _SAVER_CLASSES: dict[str, type[MessageSaverBase]] = {}

    def __init__(self, config: ExportConfig):
        self.config = config
        self._loop = get_running_loop()
        self._write_executor = ThreadPoolExecutor(2, thread_name_prefix="ExportWriter")
        self._messages: list[MessageToSave] = []

    @staticmethod
    def _partial_write_sync(path: str | Path, append_str: str, seek_to: int) -> int:
        with open(path, "r+" if seek_to else "w", encoding="utf8") as f:
            f.seek(seek_to)
            f.write(append_str)
            return f.tell()

    async def _partial_write(self, path: str | Path, append_str: str, seek_to: int) -> int:
        return await self._loop.run_in_executor(
            self._write_executor,
            self._partial_write_sync,
            path, append_str, seek_to
        )

    def save_maybe(self, message: MessageToSave) -> Task | None:
        self._messages.append(message)
        if len(self._messages) >= self.config.write_threshold:
            return self.save()

    def save(self) -> Task:
        thr = self.config.write_threshold
        to_write, self._messages = self._messages[:thr], self._messages[thr:]
        return asyncio.ensure_future(self._save(to_write), loop=self._loop)

    @abstractmethod
    async def _save(self, messages: list[MessageToSave]) -> None:
        ...

    @staticmethod
    def register_format(format_name: str, format_cls: type[MessageSaverBase]) -> None:
        classes = MessageSaverBase._SAVER_CLASSES
        format_name = format_name.lower()

        if format_name in classes and classes[format_name] is not format_cls:
            raise RuntimeError(f"Format \"{format_name}\" already registered!")

        classes[format_name] = format_cls

    @staticmethod
    def new_by_format(format_name: str, config: ExportConfig) -> MessageSaverBase:
        classes = MessageSaverBase._SAVER_CLASSES
        format_name = format_name.lower()

        if format_name not in classes:
            raise RuntimeError(f"Format \"{format_name}\" does not exist!")

        return classes[format_name](config)

    @staticmethod
    def registered_formats() -> list[str]:
        return list(MessageSaverBase._SAVER_CLASSES.keys())


class MessageSaverHtml(MessageSaverBase):
    _sub_pos = len(EXPORT_AFTER_MESSAGES)

    def __init__(self, config: ExportConfig):
        super().__init__(config)
        self.parts = defaultdict(lambda: 0)

    async def _save(self, messages: list[MessageToSave]) -> None:
        if not messages:
            return

        chat = messages[0].message.chat

        out_dir = (self.config.output_dir / str(chat.id)).absolute()

        if not exists(out_dir / "js") or not exists(out_dir / "images") or not exists(out_dir / "css"):
            unpack_to(out_dir)

        file_path = out_dir / f"messages{self.parts[chat.id]}.html"
        self.parts[chat.id] += 1

        if self.config.partial_writes:
            header = EXPORT_FMT_BEFORE_MESSAGES.format(title=_get_chat_name(chat))
            header += EXPORT_AFTER_MESSAGES
            pos = await self._partial_write(file_path, header, 0)
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
                pos = await self._partial_write(file_path, to_write, pos)
                pos -= self._sub_pos
                to_write = ""

            message = await task.wait()

            if prev is None or prev.date.day != message.date.day:
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
            await self._partial_write(file_path, to_write, pos)


class MessageSaverJson(MessageSaverBase):
    _FOOTER = " ]\n}"

    def __init__(self, config: ExportConfig) -> None:
        super().__init__(config)
        self._init = False
        self._did_write_messages = False
        self._lock = Lock()
        self._pos = 0

    async def _save(self, messages: list[MessageToSave]) -> None:
        async with self._lock:
            await self._save_real(messages)

    async def _write_messages_json(self, file_path: str | Path, to_write: list[str]) -> None:
        if self._did_write_messages:
            to_write.insert(0, "")

        to_write_str = ",\n".join(to_write) + self._FOOTER
        self._pos = await self._partial_write(file_path, to_write_str, self._pos)
        self._pos -= len(self._FOOTER)
        to_write.clear()

        self._did_write_messages = True

    async def _save_real(self, messages: list[MessageToSave]) -> None:
        if not messages:
            return

        chat = messages[0].message.chat

        out_dir = (self.config.output_dir / str(chat.id)).absolute()
        file_path = out_dir / "result.json"

        if not self._init:
            self._init = True
            self._pos = await self._partial_write(
                file_path,
                "\n".join([
                    "{",
                    f" \"name\": {json.dumps(_get_chat_name(chat))},",
                    f" \"type\": {json.dumps(_get_chat_type(chat))},",
                    f" \"id\": {json.dumps(chat.id)},",
                    f" \"messages\": [",
                    f"",
                ]),
                0,
            )
            await self._partial_write(file_path, self._FOOTER, self._pos)

        to_write = []
        for task in messages:
            if task.need_to_wait() and to_write:
                await self._write_messages_json(file_path, to_write)

            message = await task.wait()

            media_path = relpath(task.media_task.output_path, out_dir) if task.media_task else None
            thumb_path = relpath(task.thumb_task.output_path, out_dir) if task.thumb_task else None

            author_id = 0
            author_type = "unknown"
            if message.from_user:
                author_id = message.from_user.id
                author_type = "user"
            elif message.sender_chat:
                author_id = message.sender_chat.id
                author_type = "chat"

            message_obj = {
                "id": message.id,
                "type": "message",
                "date": message.date.strftime("%Y-%m-%dT%H:%M:%S"),
                "date_unixtime": str(int(message.date.timestamp())),
                "from": BaseComponent.resolve_author_name(message.from_user, message.sender_chat, True),
                "from_id": f"{author_type}{author_id}",
                "text": message.text,
                # TODO: entities
                "text_entities": [
                    {
                        "type": "plain",
                        "text": message.text,
                    }
                ]
            }

            if message.edit_date:
                message_obj["edited"] = message.edit_date.strftime("%Y-%m-%dT%H:%M:%S")
                message_obj["edited_unixtime"] = str(int(message.edit_date.timestamp()))

            # TODO: documents:
            #  file
            #  file_name
            #  file_size
            #  thumbnail
            #  thumbnail_file_size
            #  media_type
            #  sticker_emoji
            #  mime_type
            #  width
            #  height
            #  duration_seconds

            # TODO: photos:
            #  photo
            #  photo_file_size
            #  width
            #  height
            #  self_destruct_period_seconds
            #  media_spoiler

            to_write.append(json.dumps(message_obj, indent=1))

        if to_write:
            await self._write_messages_json(file_path, to_write)

    # TODO: Service message for pinned messages have this structure:
    #  {
    #   "id": {message_id},
    #   "type": "service",
    #   "date": "{date}",
    #   "date_unixtime": "{unix_timestamp}",
    #   "actor": "{from_name}",
    #   "actor_id": "{from_id}",
    #   "action": "pin_message",
    #   "message_id": {pinned_message_ids},
    #   "text": "",
    #   "text_entities": []
    #  }

    # TODO: Service message for calls have this structure:
    #  {
    #   "id": {message_id},
    #   "type": "service",
    #   "date": "{date}",
    #   "date_unixtime": "{unix_timestamp}",
    #   "actor": "{from_name}",
    #   "actor_id": "{from_id}",
    #   "action": "phone_call",
    #   "duration_seconds": {duration},
    #   "discard_reason": "hangup",
    #   "text": "",
    #   "text_entities": []
    #  }


MessageSaverBase.register_format("html", MessageSaverHtml)
MessageSaverBase.register_format("json", MessageSaverJson)
