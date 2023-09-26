from dataclasses import dataclass

from pyrogram.enums import MessageMediaType
from pyrogram.types import Message as PyroMessage

from .html.animation import Animation
from .html.audio import Audio
from .html.base import HtmlMedia
from .html.contact import Contact
from .html.document import Document
from .html.photo import Photo
from .html.poll import Poll
from .html.sticker import Sticker
from .html.video import Video
from .html.video_note import VideoNote
from .html.voice import Voice


@dataclass
class Media:
    attr_name: str
    dir_name: str
    html_media_type: type[HtmlMedia]
    has_size_limit: bool = True
    downloadable: bool = True

    def __post_init__(self):
        if not self.downloadable:
            self.has_size_limit = False

    def get_media(self, message: PyroMessage):
        return getattr(message, self.attr_name)


MEDIA_TYPES = {
    MessageMediaType.PHOTO: Media("photo", "photos", Photo),
    MessageMediaType.AUDIO: Media("audio", "audios", Audio),
    MessageMediaType.VOICE: Media("voice", "voices", Voice),
    MessageMediaType.DOCUMENT: Media("document", "documents", Document),
    MessageMediaType.STICKER: Media("sticker", "stickers", Sticker),
    MessageMediaType.VIDEO: Media("video", "videos", Video),
    MessageMediaType.ANIMATION: Media("animation", "animations", Animation),
    MessageMediaType.VIDEO_NOTE: Media("video_note", "video_notes", VideoNote),
    MessageMediaType.POLL: Media("poll", "_", Poll, False, False),
    MessageMediaType.CONTACT: Media("contact", "_", Contact, False, False),
}
