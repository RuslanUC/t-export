import json
from asyncio import get_event_loop
from datetime import datetime
from os import makedirs
from os.path import exists
from pathlib import Path
from shutil import copy

import click
from pyrogram import Client

from .export_config import ExportConfig
from .exporter import Exporter


async def _main(session_name: str, api_id: int, api_hash: str, config: ExportConfig) -> None:
    async with Client(
            f"{Path.home()}/.texport/{session_name}",
            api_id=api_id,
            api_hash=api_hash,
            no_updates=True,
    ) as client:
        exporter = Exporter(client, config)
        await exporter.export()
        if config.print:
            print("Export complete!")


@click.command()
@click.option("--api-id", type=click.INT, default=None,
              help="Telegram api id. Saved in ~/.texport/config.json file.")
@click.option("--api-hash", type=click.STRING, default=None,
              help="Telegram api hash. Saved in ~/.texport/config.json file.")
@click.option("--session-name", "-s", type=click.STRING, default="main",
              help="Pyrogram session name or path to existing file. Saved in ~/.texport/<session_name>.session file.")
@click.option("--chat-id", "-c", type=click.STRING, default=["me"], multiple=True,
              help="Chat id or username or phone number. \"me\" or \"self\" to export saved messages.")
@click.option("--output", "-o", type=click.STRING, default="./telegram_export",
              help="Output directory.")
@click.option("--size-limit", "-l", type=click.INT, default=32,
              help="Media size limit in megabytes.")
@click.option("--from-date", "-f", type=click.STRING, default="01.01.1970",
              help="Date from which messages will be saved.")
@click.option("--to-date", "-t", type=click.STRING, default=datetime.now().strftime("%d.%m.%Y"),
              help="Date to which messages will be saved.")
@click.option("--photos/--no-photos", default=True, help="Download photos or not.")
@click.option("--videos/--no-videos", default=True, help="Download videos or not.")
@click.option("--voice/--no-voice", default=True, help="Download voice messages or not.")
@click.option("--video-notes/--no-video-notes", default=True, help="Download video messages or not.")
@click.option("--stickers/--no-stickers", default=True, help="Download stickers or not.")
@click.option("--gifs/--no-gifs", default=True, help="Download gifs or not.")
@click.option("--documents/--no-documents", default=True, help="Download documents or not.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Do not print progress to console.")
@click.option("--no-preload", is_flag=True, default=False, help="Do not preload all messages.")
@click.option("--max-concurrent-downloads", "-d", type=click.INT, default=4,
              help="Number of concurrent media downloads.")
def main(
        session_name: str, api_id: int, api_hash: str, chat_id: list[str], output: str, size_limit: int, from_date: str,
        to_date: str, photos: bool, videos: bool, voice: bool, video_notes: bool, stickers: bool, gifs: bool,
        documents: bool, quiet: bool, no_preload: bool, max_concurrent_downloads: int,
) -> None:
    home = Path.home()
    texport_dir = home / ".texport"
    makedirs(texport_dir, exist_ok=True)
    makedirs(output, exist_ok=True)

    config = ExportConfig(
        chat_ids=chat_id,
        output_dir=Path(output),
        size_limit=size_limit,
        from_date=datetime.strptime(from_date, "%d.%m.%Y"),
        to_date=datetime.strptime(to_date, "%d.%m.%Y"),
        export_photos=photos,
        export_videos=videos,
        export_voice=voice,
        export_video_notes=video_notes,
        export_stickers=stickers,
        export_gifs=gifs,
        export_files=documents,
        print=not quiet,
        preload=not no_preload,
        max_concurrent_downloads=max_concurrent_downloads,
    )

    if session_name.endswith(".session"):
        name = Path(session_name).name
        copy(session_name, home / ".texport" / name)
        session_name = name[:8]

    if (api_id is None or api_hash is None) and not exists(home / ".texport" / f"{session_name}.session"):
        if not exists(texport_dir / "config.json"):
            print("You should specify \"--api-id\" and \"--api-hash\" arguments or import existing pyrogram session "
                  "file by passing it's path to \"--session\" argument!")
            return
        with open(texport_dir / "config.json", "r", encoding="utf8") as f:
            conf = json.load(f)
        api_id, api_hash = conf["api_id"], conf["api_hash"]
    elif api_id is not None and api_hash is not None:
        with open(texport_dir / "config.json", "w", encoding="utf8") as f:
            json.dump({"api_id": api_id, "api_hash": api_hash}, f)

    get_event_loop().run_until_complete(_main(session_name, api_id, api_hash, config))


if __name__ == "__main__":
    main()
