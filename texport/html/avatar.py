from .base import BaseComponent
from pyrogram.types import Message as PyroMessage


class Avatar(BaseComponent):
    def __init__(self, message: PyroMessage, forward: bool=False):
        self.message = message
        self.is_forward = forward

    def to_html(self) -> str:
        message = self.message
        forward = "" if not self.is_forward else " forwarded"
        name = message.from_user.first_name if not self.is_forward else \
            (message.forward_from.first_name if message.forward_from else message.forward_from_chat.title)

        return f"""
        <div class="pull_left userpic_wrap{forward}">
            <div class="userpic userpic8" style="width: 42px; height: 42px">
                <div class="initials" style="line-height: 42px">{name[0] if name is not None else "N"}</div>
            </div>
        </div>
        """
