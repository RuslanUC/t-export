from dataclasses import dataclass
from typing import Literal

from pyrogram.enums import MessageMediaType
from pyrogram.types import Message as PyroMessage, Object as PyroObject, Thumbnail

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


class ExpiredMedia(PyroObject):
    ...


@dataclass
class Media:
    attr_name: str
    dir_name: str
    html_media_type: type[HtmlMedia]
    has_thumbs: bool = True
    has_size_limit: bool = True
    downloadable: bool = True

    def __post_init__(self):
        if not self.downloadable:
            self.has_size_limit = False

    @staticmethod
    def _get_thumbs(media, attr_name: Literal["sizes", "thumbs"]) -> list[Thumbnail] | None:
        thumbs = getattr(media, attr_name)
        return sorted(thumbs or [], key=lambda th: th.width)

    def get_media(self, message: PyroMessage) -> tuple[PyroObject | None, Thumbnail | None]:
        # TODO: something is wrong with thumbs, probably in this method (not all messages have them for some reason)

        media = getattr(message, self.attr_name)
        thumb = None

        if media and self.has_thumbs:
            thumbs = self._get_thumbs(media, "thumbs")
            thumb = thumbs[0] if thumbs else None

        if media and self.attr_name == "photo":
            sizes = self._get_thumbs(media, "sizes")
            media = sizes[-1] if sizes else None

        if media is None:
            raw = getattr(message, "_raw")
            raw_media = getattr(raw, "media")
            ttl = getattr(raw_media, "ttl_seconds")
            if ttl:
                return ExpiredMedia(), None

        return media, thumb


MEDIA_TYPES = {
    MessageMediaType.PHOTO: Media("photo", "photos", Photo),
    MessageMediaType.AUDIO: Media("audio", "audios", Audio),
    MessageMediaType.VOICE: Media("voice", "voices", Voice, False),
    MessageMediaType.DOCUMENT: Media("document", "documents", Document),
    MessageMediaType.STICKER: Media("sticker", "stickers", Sticker),
    MessageMediaType.VIDEO: Media("video", "videos", Video),
    MessageMediaType.ANIMATION: Media("animation", "animations", Animation),
    MessageMediaType.VIDEO_NOTE: Media("video_note", "video_notes", VideoNote),
    MessageMediaType.POLL: Media("poll", "_", Poll, False, False, False),
    MessageMediaType.CONTACT: Media("contact", "_", Contact, False, False, False),
}
