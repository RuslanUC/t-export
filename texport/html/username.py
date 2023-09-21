from pyrogram.types import User as PyroUser
from .base import BaseComponent


class Username(BaseComponent):
    def __init__(self, user: PyroUser):
        self.user = user

    def to_html(self) -> str:
        last_name = self.user.last_name
        last_name = last_name if last_name is not None else ""
        return f"""<div class="from_name">{self.user.first_name} {last_name}</div>"""
