"""
File Browser Utilities - Icons, formatters, and helper functions.
Extracted from file_browser.py for better separation of concerns.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.sftp_manager import FileInfo


# File type icons (using unicode symbols for simplicity)
FILE_ICONS = {
    "folder": "\U0001F4C1",  # 📁
    "folder_open": "\U0001F4C2",  # 📂
    "file": "\U0001F4C4",  # 📄
    "image": "\U0001F5BC",  # 🖼
    "video": "\U0001F3AC",  # 🎬
    "audio": "\U0001F3B5",  # 🎵
    "archive": "\U0001F4E6",  # 📦
    "code": "\U0001F4DD",  # 📝
    "text": "\U0001F4C3",  # 📃
    "pdf": "\U0001F4D5",  # 📕
    "link": "\U0001F517",  # 🔗
}

# Extension to icon mapping
EXT_ICONS = {
    # Images
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "bmp": "image", "svg": "image", "ico": "image", "webp": "image",
    # Video
    "mp4": "video", "avi": "video", "mkv": "video", "mov": "video",
    "wmv": "video", "flv": "video", "webm": "video",
    # Audio
    "mp3": "audio", "wav": "audio", "flac": "audio", "ogg": "audio",
    "aac": "audio", "wma": "audio", "m4a": "audio",
    # Archives
    "zip": "archive", "tar": "archive", "gz": "archive", "bz2": "archive",
    "xz": "archive", "7z": "archive", "rar": "archive",
    # Code
    "py": "code", "js": "code", "ts": "code", "java": "code",
    "c": "code", "cpp": "code", "h": "code", "hpp": "code",
    "cs": "code", "go": "code", "rs": "code", "rb": "code",
    "php": "code", "html": "code", "css": "code", "scss": "code",
    "json": "code", "xml": "code", "yaml": "code", "yml": "code",
    "sh": "code", "bash": "code", "ps1": "code", "bat": "code",
    "sql": "code", "md": "code", "rst": "code",
    # Text
    "txt": "text", "log": "text", "ini": "text", "cfg": "text",
    "conf": "text", "config": "text",
    # PDF
    "pdf": "pdf",
}


def get_file_icon(file_info: "FileInfo") -> str:
    """Get icon for file based on type/extension."""
    if file_info.is_link:
        return FILE_ICONS["link"]
    if file_info.is_dir:
        return FILE_ICONS["folder"]

    ext = file_info.extension
    icon_type = EXT_ICONS.get(ext, "file")
    return FILE_ICONS.get(icon_type, FILE_ICONS["file"])


def format_size(size: int) -> str:
    """Format file size in human readable format."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def format_bytes_progress(name: str, done: int, total: int, action: str = "Transferindo") -> str:
    """
    Format progress as KB/MB with percentage.

    Args:
        name: File name
        done: Bytes transferred
        total: Total bytes
        action: Action verb (e.g., "Enviando", "Baixando")

    Returns:
        Formatted progress string
    """
    if total <= 0:
        return f"{action} {name}..."
    percent = (done / total) * 100
    if total < 1024 * 1024:
        done_kb = done / 1024
        total_kb = total / 1024
        return f"{action} {name}: {done_kb:.1f}/{total_kb:.1f} KB ({percent:.0f}%)"
    else:
        done_mb = done / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        return f"{action} {name}: {done_mb:.2f}/{total_mb:.2f} MB ({percent:.0f}%)"


def format_folder_progress(name: str, files_done: int, total_files: int, action: str = "Transferindo") -> str:
    """
    Format folder progress as file count with percentage.

    Args:
        name: Folder name
        files_done: Files completed
        total_files: Total files
        action: Action verb (e.g., "Enviando", "Baixando")

    Returns:
        Formatted progress string
    """
    if total_files <= 0:
        return f"{action} {name}..."
    percent = (files_done / total_files) * 100
    return f"{action} {name}: {files_done}/{total_files} arquivos ({percent:.0f}%)"
