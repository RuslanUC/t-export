from asyncio import get_running_loop
from os.path import exists
from typing import Union, Optional

from pyrogram.types import Message as PyroMessage

from .export_config import ExportConfig
from .html.base import Export
from .html.message import DateMessage, Message
from .resources import unpack_to


class MessagesSaver:
    def __init__(self, messages: list[PyroMessage], media: dict[Union[int, str], str], config: ExportConfig):
        self.part = 0
        self.messages = messages
        self.media = media
        self.config = config

    def _save(self) -> None:
        out_dir = self.config.output_dir
        if self.messages:
            out_dir = out_dir / str(self.messages[0].chat.id)

        if not exists(out_dir / "js") or not exists(out_dir / "images") or not exists(out_dir / "css"):
            unpack_to(out_dir)

        output = ""
        prev: Optional[PyroMessage] = None
        dates = 0
        while self.messages:
            message = self.messages.pop(0)
            noPrev = prev is None
            sameDay = False if noPrev else prev.date.day == message.date.day
            sameAuthor = False if noPrev else prev.from_user.id == message.from_user.id
            if not sameDay:
                dates -= 1
                output += DateMessage(message.date, dates).to_html()
            media = self.media.pop(message.id, None)
            media_thumb = self.media.pop(f"{message.id}_thumb", None)
            output += Message(message, media, media_thumb, sameAuthor).to_html()
            prev = message

        output = Export(prev.chat.first_name, output).to_html()
        with open(f"{out_dir}/messages{self.part}.html", "w", encoding="utf8") as f:
            f.write(output)
            
        self.part += 1

    async def save(self) -> None:
        loop = get_running_loop()
        await loop.run_in_executor(None, self._save)
