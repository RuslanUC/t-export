from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str


class Audio(HtmlMedia):
    def __init__(self, media_path: str, *args, message: PyroMessage):
        self.path = media_path
        self.audio = audio = message.audio

        duration = audio.duration or 0
        self.minutes = duration // 60
        self.seconds = duration % 60
        self.size = file_size_str(audio.file_size)

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_audio_file">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">{self.audio.file_name or "Audio file"}</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{self.minutes}:{self.seconds}, {self.size}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="media clearfix pull_left block_link media_audio_file" href="{self.path}">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">Audio file</div>
                <div class="status details">{self.minutes}:{self.seconds}</div>
            </div>
        </a>
        """ if self.path else self.no_media()
