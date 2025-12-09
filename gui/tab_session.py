"""
Tab session management for multi-tab terminal support.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from gui.terminal_widget import TerminalWidget
    from core.ssh_session import SSHSession, SSHConfig


@dataclass
class ChatState:
    """In-memory chat state for a tab."""
    conversation_id: Optional[str] = None  # Current conversation ID (None = new)
    display_messages: List[Tuple[str, bool]] = field(default_factory=list)  # [(text, is_user), ...]
    web_search_enabled: bool = False  # Web search checkbox state per conversation

    def clear(self) -> None:
        """Clear the chat state for a new conversation."""
        self.conversation_id = None
        self.display_messages.clear()
        self.web_search_enabled = False


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
    chat_state: ChatState = field(default_factory=ChatState)
    # Additional host metadata for AI context
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None
    functions: Optional[List[str]] = None
    groups: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    port_knocking: Optional[List[dict]] = None
    # Fallback hosts for connection retry
    fallback_hosts: List[str] = field(default_factory=list)
    current_host_index: int = 0
    # SFTP state
    sftp_current_path: str = "~"
    sftp_history: List[str] = field(default_factory=list)
    sftp_history_index: int = -1

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
