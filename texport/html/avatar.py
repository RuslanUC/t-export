from .base import BaseComponent
from pyrogram.types import Message as PyroMessage


class Avatar(BaseComponent):
    def __init__(self, message: PyroMessage, forward: bool=False):
        self.message = message
        self.is_forward = forward

    def to_html(self) -> str:
        message = self.message
        forward = "" if not self.is_forward else " forwarded"
        if self.is_forward:
            name = self.resolve_forward_origin_name(message.forward_origin)
        else:
            name = message.from_user.first_name

        return f"""
        <div class="pull_left userpic_wrap{forward}">
            <div class="userpic userpic8" style="width: 42px; height: 42px">
                <div class="initials" style="line-height: 42px">{name[0] if name is not None else "N"}</div>
            </div>
        </div>
        """
