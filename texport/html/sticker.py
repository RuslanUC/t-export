from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str


class Sticker(HtmlMedia):
    def __init__(self, media_path: str, media_thumb: str | None, message: PyroMessage):
        self.path = media_path
        self.thumb = media_thumb or media_path
        self.sticker = sticker = message.sticker

        self.size = file_size_str(sticker.file_size)

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_photo">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">Sticker</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{self.sticker.emoji}, {self.size}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="sticker_wrap clearfix pull_left" href="{self.path}">
            <img class="sticker" src="{self.thumb}" style="width: 192px; height: auto">
        </a>
        """ if self.path else self.no_media()
