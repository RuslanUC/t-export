def file_size_str(size: int) -> str:
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.2f} GB"
    elif size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    elif size >= 1024:
        return f"{size/1024:.2f} KB"
    return f"{size} B"
