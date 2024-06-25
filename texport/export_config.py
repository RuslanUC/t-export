from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Union

from pyrogram.enums import MessageMediaType

EXPORT_MEDIA = {
    "photos": MessageMediaType.PHOTO,
    "videos": MessageMediaType.VIDEO,
    "voice": MessageMediaType.VOICE,
    "video_notes": MessageMediaType.VIDEO_NOTE,
    "stickers": MessageMediaType.STICKER,
    "gifs": MessageMediaType.ANIMATION,
    "files": MessageMediaType.DOCUMENT,
}


@dataclass
class ExportConfig:
    chat_ids: list[Union[str, int]] = field(default_factory=lambda: ["me"])
    output_dir: Path = Path("./telegram_export")
    export_photos: bool = True
    export_videos: bool = True
    export_voice: bool = True
    export_video_notes: bool = True
    export_stickers: bool = True
    export_gifs: bool = True
    export_files: bool = True
    size_limit: int = 32  # In megabytes
    from_date: datetime = datetime(1970, 1, 1)
    to_date: datetime = datetime.now()
    print: bool = False
    preload: bool = False
    max_concurrent_downloads: int = 4

    def excluded_media(self) -> set[MessageMediaType]:
        result = set()
        for media_type in EXPORT_MEDIA:
            if not getattr(self, f"export_{media_type}"):
                result.add(EXPORT_MEDIA[media_type])
        return result

    def __post_init__(self):
        if self.max_concurrent_downloads <= 0:
            self.max_concurrent_downloads = 4
