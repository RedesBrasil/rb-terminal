"""
Remote File Editor - Manages remote file editing via SFTP.
Downloads files to temp, opens with default editor, monitors for changes, uploads back.
Extracted from file_browser.py for better separation of concerns.
"""

import asyncio
import logging
import os
import subprocess
import sys
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional, Callable, Dict

from PySide6.QtCore import QTimer

from core.sftp_manager import SFTPManager

logger = logging.getLogger(__name__)


@dataclass
class EditingFile:
    """Represents a file being edited remotely."""
    remote_path: str
    local_path: str
    last_modified: float  # timestamp of last known modification
    uploading: bool = False


class RemoteFileEditor:
    """
    Manages remote file editing.

    Downloads files to temp, opens with default editor,
    monitors for changes, and uploads back to server.
    """

    file_changed = None  # Will be set to Signal
    file_uploaded = None  # Will be set to Signal

    def __init__(self, sftp_manager: SFTPManager, status_callback: Callable[[str], None] = None):
        self._sftp = sftp_manager
        self._status_callback = status_callback
        self._editing_files: Dict[str, EditingFile] = {}  # local_path -> EditingFile
        self._temp_dir: Optional[Path] = None
        self._watch_timer: Optional[QTimer] = None
        self._check_interval = 1000  # Check every 1 second

    def _ensure_temp_dir(self) -> Path:
        """Ensure temp directory exists."""
        if self._temp_dir is None or not self._temp_dir.exists():
            self._temp_dir = Path(tempfile.mkdtemp(prefix="rb_terminal_edit_"))
        return self._temp_dir

    def _set_status(self, message: str) -> None:
        """Set status message."""
        if self._status_callback:
            self._status_callback(message)
        logger.info(message)

    async def open_file(self, remote_path: str) -> bool:
        """
        Download and open a remote file for editing.

        Args:
            remote_path: Remote file path

        Returns:
            True if file was opened successfully
        """
        if not self._sftp or not self._sftp.is_connected:
            self._set_status("SFTP não conectado")
            return False

        try:
            # Create temp directory structure to preserve filename
            temp_dir = self._ensure_temp_dir()
            filename = PurePosixPath(remote_path).name
            local_path = temp_dir / filename

            # If file already being edited, just focus it
            for ef in self._editing_files.values():
                if ef.remote_path == remote_path:
                    self._open_with_default_app(ef.local_path)
                    self._set_status(f"Arquivo já aberto: {filename}")
                    return True

            # Download file
            self._set_status(f"Baixando {filename}...")
            await self._sftp.download(remote_path, str(local_path))

            # Record the file
            mtime = local_path.stat().st_mtime
            editing_file = EditingFile(
                remote_path=remote_path,
                local_path=str(local_path),
                last_modified=mtime
            )
            self._editing_files[str(local_path)] = editing_file

            # Open with default application
            self._open_with_default_app(str(local_path))
            self._set_status(f"Editando: {filename}")

            # Start watching for changes
            self._start_watching()

            return True

        except Exception as e:
            logger.error(f"Failed to open file for editing: {e}")
            self._set_status(f"Erro ao abrir arquivo: {e}")
            return False

    def _open_with_default_app(self, local_path: str) -> None:
        """Open file with the system's default application."""
        try:
            if sys.platform == "win32":
                os.startfile(local_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", local_path], check=True)
            else:
                subprocess.run(["xdg-open", local_path], check=True)
        except Exception as e:
            logger.error(f"Failed to open file with default app: {e}")
            raise

    def _start_watching(self) -> None:
        """Start watching for file changes."""
        if self._watch_timer is None:
            self._watch_timer = QTimer()
            self._watch_timer.timeout.connect(self._check_for_changes)

        if not self._watch_timer.isActive():
            self._watch_timer.start(self._check_interval)

    def _stop_watching(self) -> None:
        """Stop watching for file changes."""
        if self._watch_timer and self._watch_timer.isActive():
            self._watch_timer.stop()

    def _check_for_changes(self) -> None:
        """Check if any editing files have been modified."""
        files_to_upload = []

        for local_path, editing_file in list(self._editing_files.items()):
            if editing_file.uploading:
                continue

            try:
                path = Path(local_path)
                if not path.exists():
                    # File was deleted, remove from tracking
                    del self._editing_files[local_path]
                    continue

                current_mtime = path.stat().st_mtime
                if current_mtime > editing_file.last_modified:
                    # File was modified, schedule upload
                    files_to_upload.append(editing_file)
                    editing_file.last_modified = current_mtime

            except Exception as e:
                logger.error(f"Error checking file {local_path}: {e}")

        # Upload changed files
        for editing_file in files_to_upload:
            asyncio.ensure_future(self._upload_changes(editing_file))

    async def _upload_changes(self, editing_file: EditingFile) -> None:
        """Upload changes to the remote file."""
        if editing_file.uploading:
            return

        editing_file.uploading = True
        filename = Path(editing_file.local_path).name

        try:
            self._set_status(f"Salvando {filename}...")
            await self._sftp.upload(editing_file.local_path, editing_file.remote_path)
            self._set_status(f"Salvo: {filename}")

            # Update mtime after successful upload
            editing_file.last_modified = Path(editing_file.local_path).stat().st_mtime

        except Exception as e:
            logger.error(f"Failed to upload changes: {e}")
            self._set_status(f"Erro ao salvar {filename}: {e}")
        finally:
            editing_file.uploading = False

    def get_editing_count(self) -> int:
        """Get number of files being edited."""
        return len(self._editing_files)

    def close_file(self, remote_path: str) -> None:
        """Stop tracking a file for editing."""
        to_remove = None
        for local_path, ef in self._editing_files.items():
            if ef.remote_path == remote_path:
                to_remove = local_path
                break

        if to_remove:
            del self._editing_files[to_remove]
            # Try to delete the temp file
            try:
                Path(to_remove).unlink(missing_ok=True)
            except Exception:
                pass

        if not self._editing_files:
            self._stop_watching()

    def close_all(self) -> None:
        """Close all editing files and cleanup."""
        self._stop_watching()
        self._editing_files.clear()

        # Cleanup temp directory
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_dir = None
