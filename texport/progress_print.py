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

        self._disabled = disabled

        self.do_update = ContextVar('do_update')
        self.do_update.set(True)

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        self._status = value
        if self.do_update.get():
            self._update()

    @property
    def approx_messages_count(self) -> int:
        return self._approx_messages_count

    @approx_messages_count.setter
    def approx_messages_count(self, value: int) -> None:
        self._approx_messages_count = value
        if self.do_update.get():
            self._update()

    @property
    def messages_exported(self) -> int:
        return self._messages_exported

    @messages_exported.setter
    def messages_exported(self, value: int) -> None:
        self._messages_exported = value
        if self.do_update.get():
            self._update()

    def _update(self) -> None:
        if self._disabled: return

        cols, _ = shutil.get_terminal_size((80, 20))
        if self._approx_messages_count:
            cols_done = int((self._messages_exported / self._approx_messages_count) * (cols - 2))
            cols_remain = int(cols - 2 - cols_done)
            progress = f"[{'#' * cols_done}{'-' * cols_remain}]"
        else:
            cols_remain = cols - 2
            progress = f"[{'-' * cols_remain}]"
        out = [
            f"Current status: {self._status}",
            f"Messages exported so far: {self._messages_exported}",
            f"Approximately messages count: {self._approx_messages_count or '?'}",
            progress
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
