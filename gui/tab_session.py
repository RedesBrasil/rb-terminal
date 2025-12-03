"""
Tab session management for multi-tab terminal support.
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from gui.terminal_widget import TerminalWidget
    from core.ssh_session import SSHSession, SSHConfig


@dataclass
class TabSession:
    """Encapsulates all state for a single terminal tab."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    terminal: Optional["TerminalWidget"] = None
    ssh_session: Optional["SSHSession"] = None
    agent: Optional[object] = None  # SSHAgent type
    config: Optional["SSHConfig"] = None
    pending_connection: Optional[dict] = None
    host_id: Optional[str] = None
    host_name: Optional[str] = None  # Display name from saved host
    device_type: Optional[str] = None
    output_buffer: list = field(default_factory=list)
    connection_status: str = "disconnected"  # disconnected, connecting, connected

    @property
    def is_connected(self) -> bool:
        """Check if the session is connected."""
        return self.ssh_session is not None and self.ssh_session.is_connected

    @property
    def display_name(self) -> str:
        """Get display name for tab title."""
        if self.connection_status == "connecting":
            return "Conectando..."
        if self.is_connected and self.config:
            if self.host_name:
                return self.host_name
            if self.config.username:
                return f"{self.config.username}@{self.config.host}"
            return self.config.host
        # Return empty string for disconnected tabs
        return ""

    def clear_session(self) -> None:
        """Clear session data but keep terminal."""
        self.ssh_session = None
        self.agent = None
        self.connection_status = "disconnected"
        self.output_buffer.clear()
