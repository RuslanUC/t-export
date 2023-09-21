from datetime import datetime
from typing import Optional

from pyrogram.types import Message as PyroMessage

from .avatar import Avatar
from .base import BaseMessage
from .forward import Forward
from .message_body import MessageBody
from .username import Username


class Message(BaseMessage):
    def __init__(self, message: PyroMessage, media: Optional[str], media_thumb: Optional[str], joined: bool):
        self.message = message
        self.media = media
        self.media_thumb = media_thumb
        self.joined = joined
        super().__init__(message.id)

    def to_html(self) -> str:
        forward = self.message.forward_from or self.message.forward_from_chat

        time = self.message.date.strftime("%H:%M")
        joined = " joined" if self.joined else ""

        body = MessageBody(self.message, self.media, self.media_thumb)
        if forward:
            body = Forward(self.message, body)

        return f"""
        <div class="message default clearfix{joined}" id="message{self.message_id}">
            {"" if self.joined else Avatar(self.message).to_html()}
            <div class="body">
                <div class="pull_right date details">{time}</div>
                {"" if self.joined else Username(self.message.from_user).to_html()}
                {body.to_html()}
            </div>
        </div>
        """


class DateMessage(BaseMessage):
    def __init__(self, dt: datetime, message_id: int):
        self.dt = dt
        super().__init__(message_id)

    def to_html(self) -> str:
        date = self.dt.strftime("%-d %B %Y")
        return f"""
        <div class="message service" id="message{self.message_id}">
            <div class="body details">
                {date}
            </div>
        </div>
        """
