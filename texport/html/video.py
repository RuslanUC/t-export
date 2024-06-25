from typing import Optional

from .base import HtmlMedia
from pyrogram.types import Message as PyroMessage

from .utils import file_size_str


class Video(HtmlMedia):
    def __init__(self, media_path: str, media_thumb: Optional[str], message: PyroMessage):
        self.path = media_path
        self.thumb = media_thumb or media_path
        self.video = video = message.video

        duration = video.duration or 0
        self.minutes = duration // 60
        self.seconds = duration % 60
        self.size = file_size_str(video.file_size)

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_video">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">{self.video.file_name or "Video file"}</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{self.minutes}:{self.seconds}, {self.size}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="video_file_wrap clearfix pull_left" href="{self.path}">
            <div class="video_play_bg">
                <div class="video_play"></div>
            </div>
            <div class="video_duration">{self.minutes}:{self.seconds}</div>
            <img class="video_file" src="{self.thumb}" style="width: 192px; height: auto">
        </a>
        """ if self.path else self.no_media()
