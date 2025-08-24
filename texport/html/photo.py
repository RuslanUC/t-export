from pyrogram.enums import MessageMediaType
from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str
from .. import media


class Photo(HtmlMedia):
    def __init__(self, media_path: str, media_thumb: str | None, message: PyroMessage):
        self.path = media_path
        self.thumb = media_thumb or media_path

        photo, _ = media.MEDIA_TYPES[MessageMediaType.PHOTO].get_media(message)
        self.photo = photo

        if photo is not None and not isinstance(photo, media.ExpiredMedia):
            self.size = file_size_str(photo.file_size)
        else:
            self.size = 0

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

    @staticmethod
    def expired() -> str:
        return f"""
            <div class="media clearfix pull_left media_photo">
                <div class="fill pull_left"></div>
                <div class="body">
                    <div class="title bold">Self-destructing photo</div>
                    <div class="status details">Expired</div>
                </div>
            </div>
        """

    def to_html(self) -> str:
        if isinstance(self.photo, media.ExpiredMedia):
            return self.expired()
        elif self.path:
            return f"""
                <a class="photo_wrap clearfix pull_left" href="{self.path}">
                    <img class="photo" src="{self.thumb}" style="width: 192px; height: audo">
                </a>
            """

        return self.no_media()
