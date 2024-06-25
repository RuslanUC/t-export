from typing import Optional

from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str


class VideoNote(HtmlMedia):
    def __init__(self, media_path: str, media_thumb: Optional[str], message: PyroMessage):
        self.path = media_path
        self.thumb = media_thumb
        self.video_note = video_note = message.video_note

        duration = video_note.duration or 0
        self.minutes = duration // 60
        self.seconds = duration % 60
        self.size = file_size_str(video_note.file_size)

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_video">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">Voice message</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{self.minutes}:{self.seconds}, {self.size}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="media clearfix pull_left block_link media_video" href="{self.path}">
            <img class="thumb pull_left" src="{self.thumb}">
            <div class="body">
                <div class="title bold">Video message</div>
                <div class="status details">{self.minutes}:{self.seconds}</div>
            </div>
        </a>
        """ if self.path else self.no_media()
