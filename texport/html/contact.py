from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia


class Contact(HtmlMedia):
    def __init__(self, *args, message: PyroMessage):
        self.contact = message.contact

    def no_media(self) -> str:
        return ""

    def to_html(self) -> str:
        last_name = "" if not self.contact.last_name else self.contact.last_name

        return f"""
        <div class="media clearfix pull_left media_contact">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">{self.contact.first_name} {last_name}</div>
                <div class="status details">{self.contact.phone_number}</div>
            </div>
        </div>
        """
