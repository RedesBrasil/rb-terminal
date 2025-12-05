"""
SFTP Manager - Wrapper for asyncssh SFTP operations.
Provides a clean async interface for file operations over SSH.
"""

import asyncio
import logging
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, List, Optional

import asyncssh

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Information about a remote file or directory."""
    name: str
    path: str
    is_dir: bool
    is_link: bool
    size: int
    modified: datetime
    permissions: str
    owner: str
    group: str
    link_target: Optional[str] = None

    @property
    def extension(self) -> str:
        """Get file extension (lowercase, without dot)."""
        if self.is_dir:
            return ""
        ext = os.path.splitext(self.name)[1].lower()
        return ext[1:] if ext else ""

    @property
    def is_hidden(self) -> bool:
        """Check if file is hidden (starts with dot)."""
        return self.name.startswith('.')


def _format_permissions(mode: int) -> str:
    """Convert numeric mode to rwx string."""
    perms = []
    for who in range(2, -1, -1):
        shift = who * 3
        perms.append('r' if mode & (4 << shift) else '-')
        perms.append('w' if mode & (2 << shift) else '-')
        perms.append('x' if mode & (1 << shift) else '-')
    return ''.join(perms)


def _parse_attrs(name: str, path: str, attrs: asyncssh.SFTPAttrs) -> FileInfo:
    """Parse SFTP attributes into FileInfo."""
    is_dir = stat.S_ISDIR(attrs.permissions) if attrs.permissions else False
    is_link = stat.S_ISLNK(attrs.permissions) if attrs.permissions else False

    modified = datetime.fromtimestamp(attrs.mtime) if attrs.mtime else datetime.now()
    permissions = _format_permissions(attrs.permissions & 0o777) if attrs.permissions else "---------"

    return FileInfo(
        name=name,
        path=path,
        is_dir=is_dir,
        is_link=is_link,
        size=attrs.size or 0,
        modified=modified,
        permissions=permissions,
        owner=str(attrs.uid) if attrs.uid is not None else "?",
        group=str(attrs.gid) if attrs.gid is not None else "?",
    )


class SFTPManager:
    """
    Manages SFTP operations over an existing SSH connection.

    Usage:
        manager = SFTPManager()
        await manager.connect(ssh_session)
        files = await manager.list_dir("/home/user")
        await manager.download("/remote/file.txt", "/local/file.txt")
        await manager.disconnect()
    """

    def __init__(self):
        self._sftp: Optional[asyncssh.SFTPClient] = None
        self._home_dir: str = "/"
        self._current_path: str = "/"

    @property
    def is_connected(self) -> bool:
        """Check if SFTP client is connected."""
        return self._sftp is not None

    @property
    def current_path(self) -> str:
        """Get current working directory."""
        return self._current_path

    @property
    def home_dir(self) -> str:
        """Get user's home directory."""
        return self._home_dir

    async def connect(self, ssh_conn: asyncssh.SSHClientConnection) -> None:
        """
        Initialize SFTP client from SSH connection.

        Args:
            ssh_conn: Active asyncssh SSH connection
        """
        if self._sftp:
            await self.disconnect()

        try:
            self._sftp = await ssh_conn.start_sftp_client()

            # Get home directory
            try:
                self._home_dir = await self._sftp.getcwd() or "/"
            except Exception:
                self._home_dir = "/"

            self._current_path = self._home_dir
            logger.info(f"SFTP connected, home: {self._home_dir}")

        except Exception as e:
            logger.error(f"Failed to start SFTP: {e}")
            raise

    async def disconnect(self) -> None:
        """Close SFTP client."""
        if self._sftp:
            try:
                self._sftp.exit()
            except Exception as e:
                logger.warning(f"Error closing SFTP: {e}")
            finally:
                self._sftp = None
                logger.info("SFTP disconnected")

    def _resolve_path(self, path: str) -> str:
        """
        Resolve path to absolute path.
        Handles ~, ., .. and relative paths.
        """
        if not path:
            return self._current_path

        # Handle home directory
        if path.startswith("~"):
            path = self._home_dir + path[1:]

        # Make absolute if relative
        if not path.startswith("/"):
            path = str(PurePosixPath(self._current_path) / path)

        # Normalize path (resolve . and ..)
        parts = []
        for part in path.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)

        return "/" + "/".join(parts)

    async def list_dir(
        self,
        path: str = ".",
        show_hidden: bool = True,
        sort_by: str = "name",
        dirs_first: bool = True
    ) -> List[FileInfo]:
        """
        List directory contents.

        Args:
            path: Directory path (default: current directory)
            show_hidden: Include hidden files (starting with .)
            sort_by: Sort key: "name", "size", "modified"
            dirs_first: Show directories before files

        Returns:
            List of FileInfo objects
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)
        files: List[FileInfo] = []

        try:
            entries = await self._sftp.readdir(abs_path)

            for entry in entries:
                name = entry.filename

                # Skip . and ..
                if name in (".", ".."):
                    continue

                # Filter hidden files
                if not show_hidden and name.startswith('.'):
                    continue

                full_path = str(PurePosixPath(abs_path) / name)

                try:
                    # Get full attributes (follows symlinks)
                    attrs = entry.attrs

                    # Check if it's a symlink
                    is_link = False
                    link_target = None
                    if attrs.permissions and stat.S_ISLNK(attrs.permissions):
                        is_link = True
                        try:
                            link_target = await self._sftp.readlink(full_path)
                            # Get target attributes
                            target_attrs = await self._sftp.stat(full_path)
                            attrs = target_attrs
                        except Exception:
                            pass

                    file_info = _parse_attrs(name, full_path, attrs)
                    file_info.is_link = is_link
                    file_info.link_target = link_target
                    files.append(file_info)

                except Exception as e:
                    logger.warning(f"Error getting attrs for {name}: {e}")
                    # Create basic entry
                    files.append(FileInfo(
                        name=name,
                        path=full_path,
                        is_dir=False,
                        is_link=False,
                        size=0,
                        modified=datetime.now(),
                        permissions="---------",
                        owner="?",
                        group="?",
                    ))

            # Sort files
            def sort_key(f: FileInfo):
                if sort_by == "size":
                    return (not f.is_dir if dirs_first else False, f.size, f.name.lower())
                elif sort_by == "modified":
                    return (not f.is_dir if dirs_first else False, f.modified, f.name.lower())
                else:  # name
                    return (not f.is_dir if dirs_first else False, f.name.lower())

            files.sort(key=sort_key)
            return files

        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"Directory not found: {abs_path}")
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_path}")
        except Exception as e:
            logger.error(f"Error listing directory: {e}")
            raise

    async def change_dir(self, path: str) -> str:
        """
        Change current directory.

        Args:
            path: New directory path

        Returns:
            New absolute path
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        # Verify it's a directory
        try:
            attrs = await self._sftp.stat(abs_path)
            if not stat.S_ISDIR(attrs.permissions):
                raise NotADirectoryError(f"Not a directory: {abs_path}")
        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"Directory not found: {abs_path}")

        self._current_path = abs_path
        logger.debug(f"Changed directory to: {abs_path}")
        return abs_path

    async def get_file_info(self, path: str) -> FileInfo:
        """
        Get information about a file or directory.

        Args:
            path: File path

        Returns:
            FileInfo object
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)
        name = PurePosixPath(abs_path).name or "/"

        try:
            attrs = await self._sftp.stat(abs_path)
            return _parse_attrs(name, abs_path, attrs)
        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"File not found: {abs_path}")

    async def download(
        self,
        remote_path: str,
        local_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> None:
        """
        Download a file from remote to local.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
            progress_callback: Optional callback(bytes_transferred, total_bytes)
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_remote = self._resolve_path(remote_path)

        try:
            # Get file size for progress
            attrs = await self._sftp.stat(abs_remote)
            total_size = attrs.size or 0

            # Create progress handler for asyncssh
            def progress_handler(srcpath, dstpath, bytes_copied, total_bytes):
                if progress_callback:
                    progress_callback(bytes_copied, total_bytes or total_size)

            # Download file
            await self._sftp.get(
                abs_remote,
                local_path,
                progress_handler=progress_handler if progress_callback else None
            )

            logger.info(f"Downloaded: {abs_remote} -> {local_path}")

        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"Remote file not found: {abs_remote}")
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_remote}")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> None:
        """
        Upload a file from local to remote.

        Args:
            local_path: Local file path
            remote_path: Remote destination path
            progress_callback: Optional callback(bytes_transferred, total_bytes)
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_remote = self._resolve_path(remote_path)

        # Get local file size
        local_file = Path(local_path)
        if not local_file.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        total_size = local_file.stat().st_size

        try:
            # Create progress handler for asyncssh
            def progress_handler(srcpath, dstpath, bytes_copied, total_bytes):
                if progress_callback:
                    progress_callback(bytes_copied, total_bytes or total_size)

            # Upload file
            await self._sftp.put(
                local_path,
                abs_remote,
                progress_handler=progress_handler if progress_callback else None
            )

            logger.info(f"Uploaded: {local_path} -> {abs_remote}")

        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_remote}")
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise

    async def mkdir(self, path: str) -> str:
        """
        Create a directory.

        Args:
            path: Directory path to create

        Returns:
            Absolute path of created directory
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        try:
            await self._sftp.mkdir(abs_path)
            logger.info(f"Created directory: {abs_path}")
            return abs_path
        except asyncssh.SFTPFailure as e:
            if "exists" in str(e).lower():
                raise FileExistsError(f"Directory already exists: {abs_path}")
            raise
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_path}")

    async def create_file(self, path: str) -> str:
        """
        Create an empty file.

        Args:
            path: File path to create

        Returns:
            Absolute path of created file
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        try:
            # Check if file already exists
            try:
                await self._sftp.stat(abs_path)
                raise FileExistsError(f"File already exists: {abs_path}")
            except asyncssh.SFTPNoSuchFile:
                pass  # File doesn't exist, we can create it

            # Create empty file by opening in write mode
            async with self._sftp.open(abs_path, "w") as f:
                pass  # Just create empty file

            logger.info(f"Created file: {abs_path}")
            return abs_path
        except FileExistsError:
            raise
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_path}")
        except Exception as e:
            logger.error(f"Error creating file: {e}")
            raise

    async def rename(self, old_path: str, new_path: str) -> str:
        """
        Rename/move a file or directory.

        Args:
            old_path: Current path
            new_path: New path (can be just filename for rename in same dir)

        Returns:
            New absolute path
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_old = self._resolve_path(old_path)

        # If new_path doesn't contain /, assume same directory
        if "/" not in new_path:
            parent = str(PurePosixPath(abs_old).parent)
            abs_new = str(PurePosixPath(parent) / new_path)
        else:
            abs_new = self._resolve_path(new_path)

        try:
            await self._sftp.rename(abs_old, abs_new)
            logger.info(f"Renamed: {abs_old} -> {abs_new}")
            return abs_new
        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"File not found: {abs_old}")
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied")

    async def delete(self, path: str, recursive: bool = False) -> None:
        """
        Delete a file or directory.

        Args:
            path: Path to delete
            recursive: If True, delete directory contents recursively
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        try:
            attrs = await self._sftp.stat(abs_path)
            is_dir = stat.S_ISDIR(attrs.permissions) if attrs.permissions else False

            if is_dir:
                if recursive:
                    await self._delete_recursive(abs_path)
                else:
                    await self._sftp.rmdir(abs_path)
            else:
                await self._sftp.remove(abs_path)

            logger.info(f"Deleted: {abs_path}")

        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"File not found: {abs_path}")
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_path}")
        except asyncssh.SFTPFailure as e:
            if "not empty" in str(e).lower():
                raise OSError(f"Directory not empty: {abs_path}")
            raise

    async def _delete_recursive(self, path: str) -> None:
        """Recursively delete directory contents."""
        entries = await self._sftp.readdir(path)

        for entry in entries:
            if entry.filename in (".", ".."):
                continue

            full_path = str(PurePosixPath(path) / entry.filename)

            if entry.attrs.permissions and stat.S_ISDIR(entry.attrs.permissions):
                await self._delete_recursive(full_path)
            else:
                await self._sftp.remove(full_path)

        await self._sftp.rmdir(path)

    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        try:
            await self._sftp.stat(abs_path)
            return True
        except asyncssh.SFTPNoSuchFile:
            return False

    async def read_text(self, path: str, max_size: int = 1024 * 1024) -> str:
        """
        Read text file contents.

        Args:
            path: Remote file path
            max_size: Maximum bytes to read (default 1MB)

        Returns:
            File contents as string
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        try:
            # Check file size first
            attrs = await self._sftp.stat(abs_path)
            if attrs.size and attrs.size > max_size:
                raise ValueError(f"File too large: {attrs.size} bytes (max {max_size})")

            async with self._sftp.open(abs_path, 'r') as f:
                content = await f.read(max_size)
                return content.decode('utf-8', errors='replace')

        except asyncssh.SFTPNoSuchFile:
            raise FileNotFoundError(f"File not found: {abs_path}")
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_path}")

    async def write_text(self, path: str, content: str) -> None:
        """
        Write text content to file.

        Args:
            path: Remote file path
            content: Text content to write
        """
        if not self._sftp:
            raise RuntimeError("SFTP not connected")

        abs_path = self._resolve_path(path)

        try:
            async with self._sftp.open(abs_path, 'w') as f:
                await f.write(content.encode('utf-8'))
            logger.info(f"Wrote {len(content)} bytes to: {abs_path}")
        except asyncssh.SFTPPermissionDenied:
            raise PermissionError(f"Permission denied: {abs_path}")
