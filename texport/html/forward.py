from pyrogram.types import Message as PyroMessage

from .avatar import Avatar
from .base import BaseComponent
from .message_body import MessageBody


class Forward(BaseComponent):
    def __init__(self, message: PyroMessage, body: MessageBody):
        self.message = message
        self.body = body

    def to_html(self) -> str:
        origin = self.message.forward_origin
        date = origin.date.strftime(" %d.%m.%Y %H:%M:%S") if origin.date else "Unknown"
        name = self.resolve_forward_origin_name(origin)

        return f"""
        {Avatar(self.message, True).to_html()}
        <div class="forwarded body">
            <div class="from_name">{name} <span class="date details">{date}</span></div>
            {self.body.to_html()}
        </div>
        """
