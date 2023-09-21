from pyrogram.types import Message as PyroMessage

from .avatar import Avatar
from .base import BaseComponent
from .message_body import MessageBody


class Forward(BaseComponent):
    def __init__(self, message: PyroMessage, body: MessageBody):
        self.message = message
        self.body = body

    def to_html(self) -> str:
        message = self.message
        name = (message.forward_from.first_name if message.forward_from else message.forward_from_chat.title)
        date = self.message.forward_date.strftime(" %d.%m.%Y %H:%M:%S")

        return f"""
        {Avatar(message, True).to_html()}
        <div class="forwarded body">
            <div class="from_name">{name} <span class="date details">{date}</span></div>
            {self.body.to_html()}
        </div>
        """
