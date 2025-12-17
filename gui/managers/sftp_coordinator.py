"""
SFTP Coordinator - Handles file browser and terminal directory sync.
Extracted from main_window.py for better separation of concerns.
"""

import asyncio
import logging
import re
from pathlib import PurePosixPath
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, QTimer

from gui.tab_session import TabSession
from gui.file_browser import FileBrowser

logger = logging.getLogger(__name__)


class SFTPCoordinator(QObject):
    """
    Coordinates SFTP file browser and terminal directory sync.

    Responsibilities:
    - Connecting SFTP browser to SSH sessions
    - Syncing file browser with terminal CWD
    - Tracking cd commands from terminal input
    - Managing follow terminal mode
    """

    # Signals
    status_message = Signal(str)
    directory_changed = Signal(str)

    def __init__(self, sftp_browser: FileBrowser, parent=None):
        super().__init__(parent)
        self._sftp_browser = sftp_browser
        self._sftp_sync_timer: Optional[QTimer] = None
        self._visible = False

        # Connect browser signals
        self._sftp_browser.directory_changed.connect(self._on_directory_changed)

    @property
    def visible(self) -> bool:
        """Check if SFTP panel is visible."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        """Set SFTP panel visibility."""
        self._visible = value

    @property
    def follow_terminal(self) -> bool:
        """Check if follow terminal mode is enabled."""
        return self._sftp_browser.follow_terminal

    @property
    def current_path(self) -> str:
        """Get current SFTP path."""
        return self._sftp_browser.current_path

    async def connect_for_session(self, session: TabSession) -> bool:
        """Connect SFTP browser to the session's SSH connection."""
        if not session.ssh_session or not session.ssh_session.is_connected:
            return False

        try:
            # Get the underlying SSH connection
            ssh_conn = session.ssh_session._conn
            if ssh_conn:
                await self._sftp_browser.connect(ssh_conn)
                logger.info("SFTP connected for session")

                # Sync with terminal cwd if follow mode is enabled
                if self._sftp_browser.follow_terminal:
                    await self.sync_with_terminal_cwd(session)
                return True
        except Exception as e:
            logger.error(f"Failed to connect SFTP: {e}")
            self.status_message.emit(f"Erro SFTP: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect SFTP browser."""
        await self._sftp_browser.disconnect()
        self._sftp_browser.clear()

    def clear(self) -> None:
        """Clear SFTP browser."""
        self._sftp_browser.clear()

    async def sync_with_terminal_cwd(self, session: TabSession) -> None:
        """Sync SFTP browser with terminal's current working directory."""
        if not self._visible:
            logger.debug("SFTP sync skipped: panel not visible")
            return
        if not self._sftp_browser.follow_terminal:
            logger.debug("SFTP sync skipped: follow terminal disabled")
            return

        if not session or not session.is_connected or not session.ssh_session:
            logger.debug("SFTP sync skipped: no active session")
            return

        try:
            # Get current working directory from terminal
            cwd = await session.ssh_session.execute_command("pwd", timeout=5.0)
            cwd = cwd.strip()
            logger.debug(f"Terminal cwd: {cwd}")

            if cwd and cwd.startswith("/"):
                # Update file browser if path changed
                if cwd != self._sftp_browser.current_path:
                    logger.debug(f"Navigating SFTP to: {cwd}")
                    self._sftp_browser.set_path(cwd)
        except Exception as e:
            logger.debug(f"Could not get terminal cwd: {e}")

    def trigger_follow_sync(self, session: TabSession) -> None:
        """Trigger SFTP sync after a short delay (debounced)."""
        if not self._sftp_sync_timer:
            self._sftp_sync_timer = QTimer()
            self._sftp_sync_timer.setSingleShot(True)
            self._sftp_sync_timer.timeout.connect(
                lambda: asyncio.ensure_future(self.sync_with_terminal_cwd(session))
            )

        # Debounce: wait 500ms after last input before syncing
        self._sftp_sync_timer.start(500)

    def track_terminal_input(self, session: TabSession, data: str) -> None:
        """Track terminal input to detect cd commands."""
        # Initialize input buffer if needed
        if not hasattr(session, '_input_buffer'):
            session._input_buffer = ""
            session._current_cwd = "~"  # Start at home

        # Handle special characters
        if data == '\x7f' or data == '\b':  # Backspace
            if session._input_buffer:
                session._input_buffer = session._input_buffer[:-1]
            return
        elif data == '\x03':  # Ctrl+C
            session._input_buffer = ""
            return
        elif data == '\x15':  # Ctrl+U (clear line)
            session._input_buffer = ""
            return

        # Check for Enter key
        if '\r' in data or '\n' in data:
            command = session._input_buffer.strip()
            session._input_buffer = ""

            # Detect cd command
            if command:
                self._process_cd_command(session, command)
        else:
            # Accumulate input
            session._input_buffer += data

    def _process_cd_command(self, session: TabSession, command: str) -> None:
        """Process a command to detect cd and update SFTP path."""
        # Match cd commands: cd, cd -, cd ~, cd /path, cd path, cd "path with spaces"
        cd_pattern = r'^cd\s*(.*)$'
        match = re.match(cd_pattern, command)

        if not match:
            return

        path_arg = match.group(1).strip()

        # Remove quotes if present
        if path_arg.startswith('"') and path_arg.endswith('"'):
            path_arg = path_arg[1:-1]
        elif path_arg.startswith("'") and path_arg.endswith("'"):
            path_arg = path_arg[1:-1]

        # Determine new path
        current = getattr(session, '_current_cwd', '~')

        if not path_arg or path_arg == '~':
            new_path = '~'
        elif path_arg == '-':
            # cd - : go to previous directory (not tracked, skip)
            return
        elif path_arg.startswith('/'):
            # Absolute path
            new_path = path_arg
        elif path_arg == '..':
            # Parent directory
            if current == '~' or current == '/':
                new_path = '/'
            else:
                new_path = str(PurePosixPath(current).parent)
        elif path_arg.startswith('~/'):
            # Home-relative path
            new_path = path_arg
        else:
            # Relative path
            if current == '~':
                new_path = f"~/{path_arg}"
            else:
                new_path = str(PurePosixPath(current) / path_arg)

        # Normalize path (remove . and ..)
        if new_path not in ('~', '/') and not new_path.startswith('~/'):
            parts = []
            for part in new_path.split('/'):
                if part == '..':
                    if parts:
                        parts.pop()
                elif part and part != '.':
                    parts.append(part)
            new_path = '/' + '/'.join(parts) if parts else '/'

        logger.debug(f"Detected cd to: {new_path}")

        # Update SFTP browser if follow mode is enabled
        self._trigger_path_update(new_path)

    def _trigger_path_update(self, path: str) -> None:
        """Update SFTP browser to the given path if follow mode is enabled."""
        if not self._visible:
            return
        if not self._sftp_browser.follow_terminal:
            return

        # Update file browser path
        if path != self._sftp_browser.current_path:
            logger.debug(f"Navigating SFTP to: {path}")
            self._sftp_browser.set_path(path)

    def _on_directory_changed(self, path: str) -> None:
        """Handle SFTP directory change."""
        self.directory_changed.emit(path)

    async def download_files(self, files, dest_dir: str, progress_callback: Callable = None) -> int:
        """Download files to local directory."""
        return await self._sftp_browser.download_files(
            files,
            dest_dir,
            progress_callback=progress_callback
        )

    async def upload_files(self, local_files: list, remote_dir: str, progress_callback: Callable = None) -> int:
        """Upload files to remote directory."""
        return await self._sftp_browser.upload_files(
            local_files,
            remote_dir,
            progress_callback=progress_callback
        )
