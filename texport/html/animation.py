from typing import Optional
from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str


class Animation(HtmlMedia):
    def __init__(self, media_path: str, media_thumb: Optional[str], message: PyroMessage):
        self.path = media_path
        self.thumb = media_thumb or media_path
        self.message = message

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_video">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">Animation</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{file_size_str(self.message.animation.file_size)}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="animated_wrap clearfix pull_left" href="{self.path}">
            <div class="video_play_bg">
                <div class="gif_play">GIF</div>
            </div>
            <img class="animated" src="{self.thumb}" style="width: 192px; height: auto">
        </a>
        """ if self.path else self.no_media()
