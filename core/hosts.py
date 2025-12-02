"""
Host management module.
Provides CRUD operations for SSH hosts with encrypted password storage.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

from core.crypto import CryptoManager, get_config_dir

logger = logging.getLogger(__name__)


@dataclass
class Host:
    """Represents a saved SSH host."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    password_encrypted: Optional[str] = None
    terminal_type: str = "xterm"
    device_type: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Host":
        """Create Host from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            host=data.get("host", ""),
            port=data.get("port", 22),
            username=data.get("username", ""),
            password_encrypted=data.get("password_encrypted"),
            terminal_type=data.get("terminal_type", "xterm"),
            device_type=data.get("device_type"),
            created_at=data.get("created_at", datetime.now().isoformat())
        )


class HostsManager:
    """
    Manages host storage and retrieval.

    Hosts are stored in a JSON file with passwords encrypted using Fernet.
    """

    def __init__(self):
        """Initialize hosts manager."""
        self._config_dir = get_config_dir()
        self._hosts_file = self._config_dir / "hosts.json"
        self._crypto = CryptoManager(self._config_dir)
        self._hosts: list[Host] = []
        self._load()

    def _load(self) -> None:
        """Load hosts from JSON file."""
        self._config_dir.mkdir(parents=True, exist_ok=True)

        if not self._hosts_file.exists():
            logger.info("No hosts file found, starting with empty list")
            self._hosts = []
            return

        try:
            with open(self._hosts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._hosts = [Host.from_dict(h) for h in data.get("hosts", [])]
            logger.info(f"Loaded {len(self._hosts)} hosts")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in hosts file: {e}")
            self._hosts = []
        except Exception as e:
            logger.error(f"Failed to load hosts: {e}")
            self._hosts = []

    def _save(self) -> None:
        """Save hosts to JSON file."""
        try:
            data = {"hosts": [h.to_dict() for h in self._hosts]}
            with open(self._hosts_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Hosts saved to file")
        except Exception as e:
            logger.error(f"Failed to save hosts: {e}")
            raise

    def get_all(self) -> list[Host]:
        """Get all hosts."""
        return self._hosts.copy()

    def get_by_id(self, host_id: str) -> Optional[Host]:
        """Get host by ID."""
        for host in self._hosts:
            if host.id == host_id:
                return host
        return None

    def add(
        self,
        name: str,
        host: str,
        port: int = 22,
        username: str = "",
        password: Optional[str] = None,
        terminal_type: str = "xterm",
        device_type: Optional[str] = None
    ) -> Host:
        """
        Add a new host.

        Args:
            name: Display name for the host
            host: IP address or hostname
            port: SSH port (default 22)
            username: SSH username
            password: SSH password (will be encrypted, None = prompt on connect)
            terminal_type: Terminal type (xterm or vt100)
            device_type: Type of device (Linux, MikroTik, Huawei, Cisco, or custom)

        Returns:
            The created Host object
        """
        password_encrypted = None
        if password:
            password_encrypted = self._crypto.encrypt(password)

        new_host = Host(
            name=name,
            host=host,
            port=port,
            username=username,
            password_encrypted=password_encrypted,
            terminal_type=terminal_type,
            device_type=device_type if device_type else None
        )

        self._hosts.append(new_host)
        self._save()
        logger.info(f"Added new host: {name} ({host})")
        return new_host

    def update(
        self,
        host_id: str,
        name: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        terminal_type: Optional[str] = None,
        device_type: Optional[str] = None,
        clear_password: bool = False
    ) -> Optional[Host]:
        """
        Update an existing host.

        Args:
            host_id: ID of the host to update
            name: New display name (None = keep current)
            host: New IP/hostname (None = keep current)
            port: New port (None = keep current)
            username: New username (None = keep current)
            password: New password (None = keep current, empty string = clear)
            terminal_type: New terminal type (None = keep current)
            device_type: New device type (None = keep current)
            clear_password: If True, remove saved password

        Returns:
            Updated Host object or None if not found
        """
        existing = self.get_by_id(host_id)
        if not existing:
            logger.warning(f"Host not found for update: {host_id}")
            return None

        if name is not None:
            existing.name = name
        if host is not None:
            existing.host = host
        if port is not None:
            existing.port = port
        if username is not None:
            existing.username = username
        if terminal_type is not None:
            existing.terminal_type = terminal_type
        if device_type is not None:
            existing.device_type = device_type if device_type else None

        if clear_password:
            existing.password_encrypted = None
        elif password is not None:
            if password:
                existing.password_encrypted = self._crypto.encrypt(password)
            else:
                existing.password_encrypted = None

        self._save()
        logger.info(f"Updated host: {existing.name}")
        return existing

    def delete(self, host_id: str) -> bool:
        """
        Delete a host.

        Args:
            host_id: ID of the host to delete

        Returns:
            True if deleted, False if not found
        """
        for i, host in enumerate(self._hosts):
            if host.id == host_id:
                deleted = self._hosts.pop(i)
                self._save()
                logger.info(f"Deleted host: {deleted.name}")
                return True
        logger.warning(f"Host not found for deletion: {host_id}")
        return False

    def get_password(self, host_id: str) -> Optional[str]:
        """
        Get decrypted password for a host.

        Args:
            host_id: ID of the host

        Returns:
            Decrypted password or None if no password saved
        """
        host = self.get_by_id(host_id)
        if not host or not host.password_encrypted:
            return None

        try:
            return self._crypto.decrypt(host.password_encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt password for host {host_id}: {e}")
            return None

    def has_password(self, host_id: str) -> bool:
        """Check if host has a saved password."""
        host = self.get_by_id(host_id)
        return host is not None and host.password_encrypted is not None
