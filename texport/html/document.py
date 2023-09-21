from pyrogram.types import Message as PyroMessage

from .base import HtmlMedia
from .utils import file_size_str


class Document(HtmlMedia):
    def __init__(self, media_path: str, *args, message: PyroMessage):
        self.path = media_path
        self.name = message.document.file_name
        self.doc = message.document
        self.size = file_size_str(self.doc.file_size)

    def no_media(self) -> str:
        return f"""
        <div class="media clearfix pull_left media_file">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">{self.doc.file_name or "Document"}</div>
                <div class="description">Not included, change data exporting settings to download.</div>
                <div class="status details">{self.size}</div>
            </div>
        </div>
        """

    def to_html(self) -> str:
        return f"""
        <a class="media clearfix pull_left block_link media_file" href="{self.path}">
            <div class="fill pull_left"></div>
            <div class="body">
                <div class="title bold">{self.name}</div>
                <div class="status details">{self.size}</div>
            </div>
        </a>
        """ if self.path else self.no_media()
