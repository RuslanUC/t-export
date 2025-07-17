from __future__ import annotations

from asyncio import Event


class ExportProgress:
    __slots__ = (
        "status", "approx_messages_count", "messages_exported", "messages_loaded", "media_status", "media_queue",
        "media_bytes", "media_down_bytes", "media_fail_bytes", "changed",
    )

    def __init__(self, progress: ExportProgress | None = None) -> None:
        self.status = progress.status if progress is not None else "Initializing..."
        self.approx_messages_count = progress.approx_messages_count if progress is not None else 0
        self.messages_exported = progress.messages_exported if progress is not None else 0
        self.messages_loaded = progress.messages_loaded if progress is not None else 0
        self.media_status = progress.media_status if progress is not None else "Idle..."
        self.media_queue = progress.media_queue if progress is not None else 0
        self.media_bytes = progress.media_bytes if progress is not None else 0
        self.media_down_bytes = progress.media_down_bytes if progress is not None else 0
        self.media_fail_bytes = progress.media_fail_bytes if progress is not None else 0


class ExportProgressInternal(ExportProgress):
    __slots__ = ("_changed", "_stopped",)

    def __init__(self) -> None:
        super().__init__(None)
        self._changed = Event()
        self._stopped = False

    def changed(self) -> None:
        self._changed.set()

    def stop(self) -> None:
        self._stopped = True
        self.changed()

    def start(self) -> None:
        self._stopped = False

    async def wait(self) -> ExportProgress | None:
        if self._stopped:
            return None

        await self._changed.wait()
        self._changed.clear()
        return ExportProgress(self)
