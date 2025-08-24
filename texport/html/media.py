from pyrogram.types import Message as PyroMessage

from .base import BaseComponent
from ..media import MEDIA_TYPES


class Media(BaseComponent):
    def __init__(self, message: PyroMessage, media_path: str, media_thumb: str | None, media_args: dict=None):
        self.message = message
        self.media_path = media_path
        self.media_thumb = media_thumb
        self.media_args = media_args or {}

    def to_html(self) -> str:
        if self.message.media not in MEDIA_TYPES: return ""
        media_element = MEDIA_TYPES[self.message.media].html_media_type
        return f"""
        <div class="media_wrap clearfix">
            {media_element(self.media_path, self.media_thumb, message=self.message).to_html()}
        </div>
        """


# TODO: phone call messages have following media html:
#  <div class="media clearfix pull_left media_call success">
#      <div class="fill pull_left"></div>
#      <div class="body">
#          <div class="title bold">{author}</div>
#          <div class="status details">{Incoming/Outgoing} ({seconds} seconds)</div>
#      </div>
#  </div>
