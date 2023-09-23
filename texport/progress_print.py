import shutil
from contextlib import contextmanager
from contextvars import ContextVar

import colorama

colorama.init()  # Fix windows


class ProgressPrint:
    def __init__(self, disabled: bool=False):
        self._status = "Initializing..."
        self._approx_messages_count = 0
        self._messages_exported = 0
        self._messages_loaded = 0
        self._media_status = "Idle..."
        self._media_queue = 0

        self._disabled = disabled

        self.do_update = ContextVar('do_update')
        self.do_update.set(True)

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        if self._status == value: return

        self._status = value
        if self.do_update.get():
            self._update()

    @property
    def approx_messages_count(self) -> int:
        return self._approx_messages_count

    @approx_messages_count.setter
    def approx_messages_count(self, value: int) -> None:
        if self._approx_messages_count == value: return

        self._approx_messages_count = value
        if self.do_update.get():
            self._update()

    @property
    def messages_exported(self) -> int:
        return self._messages_exported

    @messages_exported.setter
    def messages_exported(self, value: int) -> None:
        if self._messages_exported == value: return

        self._messages_exported = value
        if self.do_update.get():
            self._update()

    @property
    def messages_loaded(self) -> int:
        return self._messages_loaded

    @messages_loaded.setter
    def messages_loaded(self, value: int) -> None:
        if self._messages_loaded == value: return

        self._messages_loaded = value
        if self.do_update.get():
            self._update()

    @property
    def media_status(self) -> str:
        return self._media_status

    @media_status.setter
    def media_status(self, value: str) -> None:
        if self._media_status == value: return

        self._media_status = value
        if self.do_update.get():
            self._update()

    @property
    def media_queue(self) -> int:
        return self._media_queue

    @media_queue.setter
    def media_queue(self, value: int) -> None:
        if self._media_queue == value: return

        self._media_queue = value
        if self.do_update.get():
            self._update()

    def _progress(self, value: int, cols: int) -> str:
        if self._approx_messages_count:
            cols_done = int((value / self._approx_messages_count) * (cols - 2))
            cols_remain = int(cols - 2 - cols_done)
            return f"[{'#' * cols_done}{'-' * cols_remain}]"
        else:
            cols_remain = cols - 2
            return f"[{'-' * cols_remain}]"

    def _update(self) -> None:
        if self._disabled: return

        cols, _ = shutil.get_terminal_size((80, 20))
        exp_progress = self._progress(self._messages_exported, cols)
        load_progress = self._progress(self._messages_loaded, cols) if self._messages_loaded else exp_progress
        out = [
            f"Current status: {self._status}",
            f"Current media downloader status: {self._media_status}",
            f"Media files in media downloader queue: {self._media_queue}",
            f"Approximately messages count: {self._approx_messages_count or '?'}",
            f"Messages loaded: {self._messages_loaded if self._messages_loaded else self._messages_exported}",
            load_progress,
            f"Messages exported: {self._messages_exported}",
            exp_progress,
        ]
        for idx, line in enumerate(out):
            if len(line) > cols:
                out[idx] = f"{line[:cols - 3]}..."
            else:
                out[idx] = line.ljust(cols, " ")

        lines = len(out)
        out = "".join(out)
        print(f"\x1B[{lines}A{out}", end="", flush=True)

    @contextmanager
    def update(self):
        self.do_update.set(False)
        yield
        self.do_update.set(True)
        self._update()


if __name__ == '__main__':
    from time import sleep

    p = ProgressPrint()
    for i in range(100):
        with p.update():
            p.status = "Downloading messages..."
            p.messages_exported = i
            p.approx_messages_count = 99
        sleep(.1)
