from typing import Optional

from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str


class Photo(HtmlMedia):
    def __init__(self, media_path: str, media_thumb: Optional[str], message: PyroMessage):
        self.path = media_path
        self.thumb = media_thumb or media_path
        self.photo = photo = message.photo

        self.size = file_size_str(photo.file_size if photo is not None else 0)

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_photo">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">Photo</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{self.size}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="photo_wrap clearfix pull_left" href="{self.path}">
            <img class="photo" src="{self.thumb}" style="width: 192px; height: audo">
        </a>
        """ if self.path else self.no_media()
