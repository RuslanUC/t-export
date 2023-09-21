from typing import Optional

from pyrogram.types import Message as PyroMessage

from .base import BaseComponent
from .media import Media
from .reply import Reply


class MessageBody(BaseComponent):
    def __init__(self, message: PyroMessage, media: Optional[str], media_thumb: Optional[str]):
        self.message = message
        self.media = media
        self.media_thumb = media_thumb

    def to_html(self) -> str:
        text = self.message.text
        if text is None and self.message.caption is not None:
            text = self.message.caption

        return f"""
            {"" if not self.message.media else Media(self.message, self.media, self.media_thumb).to_html()}
            {"" if not self.message.reply_to_message_id else Reply(self.message.reply_to_message_id).to_html()}
            {"" if not text else f'<div class="text">{text}</div>'}
        """
