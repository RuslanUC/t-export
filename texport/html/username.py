from pyrogram.types import User, Chat
from .base import BaseComponent


class Username(BaseComponent):
    def __init__(self, user: User, chat: Chat):
        self.user = user
        self.chat = chat

    def to_html(self) -> str:
        return f"""<div class="from_name">{self.resolve_author_name(self.user, self.chat, True)}</div>"""
