import shutil

try:
    import colorama
except ImportError:
    ...
else:
    colorama.just_fix_windows_console()

from .export_progress import ExportProgress


class ProgressPrinter:
    @staticmethod
    def _progress(value: int, cols: int, total: int) -> str:
        if total:
            cols_done = int((value / total) * (cols - 2))
            cols_remain = int(cols - 2 - cols_done)
            return f"[{'#' * cols_done}{'-' * cols_remain}]"
        else:
            cols_remain = cols - 2
            return f"[{'-' * cols_remain}]"

    @classmethod
    async def progress_callback(cls, prog: ExportProgress) -> None:
        approx_count = prog.approx_messages_count
        loaded = prog.messages_loaded
        exported = prog.messages_exported
        fail_bytes = prog.media_fail_bytes

        total_mb = prog.media_bytes / 1024 / 1024
        down_mb = prog.media_down_bytes / 1024 / 1024
        fail_mb = fail_bytes / 1024 / 1024

        cols, _ = shutil.get_terminal_size((80, 20))
        exp_progress = cls._progress(exported, cols, approx_count)
        load_progress = cls._progress(loaded, cols, approx_count) if loaded else exp_progress
        media_progress = cls._progress(prog.media_down_bytes + fail_bytes, cols, prog.media_bytes)
        out = [
            f"Current status: {prog.status}",
            f"Current media downloader status: {prog.media_status}",
            f"Media files in media downloader queue: {prog.media_queue}",
            f"Approximate messages count: {approx_count or '?'}",
            f"Media loaded: {down_mb + fail_mb:.2f}MB/{total_mb:.2f}MB"
            + (f"({fail_mb:.2f}MB failed)" if fail_bytes else ""),
            media_progress,
            f"Messages loaded: {loaded if loaded else exported}",
            load_progress,
            f"Messages exported: {exported}",
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
