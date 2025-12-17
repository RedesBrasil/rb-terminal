"""
Connection Manager - Handles SSH connections.
Extracted from main_window.py for better separation of concerns.
"""

import asyncio
import logging
import socket
from typing import Optional, Callable, List

from PySide6.QtCore import QObject, Signal

import asyncssh

from core.ssh_session import SSHSession, SSHConfig
from core.agent import create_agent, UsageStats
from gui.tab_session import TabSession

logger = logging.getLogger(__name__)


class ConnectionManager(QObject):
    """
    Manages SSH connections for terminal sessions.

    Responsibilities:
    - Establishing SSH connections
    - Handling connection failures and retries
    - Managing port knocking
    - Creating AI agents for sessions
    - Handling disconnections
    """

    # Signals
    connection_started = Signal(TabSession)
    connection_success = Signal(TabSession)
    connection_failed = Signal(TabSession, str)  # session, error message
    disconnected = Signal(TabSession)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Callbacks (set by MainWindow)
        self._on_ssh_output: Optional[Callable] = None
        self._on_unexpected_disconnect: Optional[Callable] = None
        self._on_command_executed: Optional[Callable] = None
        self._on_thinking: Optional[Callable] = None
        self._on_usage_update: Optional[Callable] = None

    def set_callbacks(
        self,
        on_ssh_output: Callable,
        on_unexpected_disconnect: Callable,
        on_command_executed: Callable = None,
        on_thinking: Callable = None,
        on_usage_update: Callable = None
    ) -> None:
        """Set callbacks for connection events."""
        self._on_ssh_output = on_ssh_output
        self._on_unexpected_disconnect = on_unexpected_disconnect
        self._on_command_executed = on_command_executed
        self._on_thinking = on_thinking
        self._on_usage_update = on_usage_update

    async def perform_port_knock(self, host: str, sequence: List[dict]) -> None:
        """Execute port knocking sequence (fire and forget)."""
        for entry in sequence:
            try:
                protocol = entry.get("protocol", "tcp")
                port = entry.get("port")
                if not port:
                    continue
                sock_type = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
                sock = socket.socket(socket.AF_INET, sock_type)
                sock.settimeout(0.1)
                if protocol == "tcp":
                    try:
                        sock.connect((host, port))
                    except (socket.timeout, ConnectionRefusedError, OSError):
                        pass
                else:
                    sock.sendto(b"", (host, port))
                sock.close()
            except Exception:
                pass  # Fire and forget - ignore all errors
        logger.debug(f"Port knocking completed for {host}: {sequence}")

    def _create_disconnect_callback(self, session: TabSession) -> Callable:
        """Create a disconnect callback for a specific session."""
        def callback():
            if self._on_unexpected_disconnect:
                self._on_unexpected_disconnect(session.id)
        return callback

    def _create_output_callback(self, session: TabSession) -> Callable:
        """Create an output callback for a specific session."""
        def callback(data: str):
            if self._on_ssh_output:
                self._on_ssh_output(session, data)
        return callback

    def create_agent_for_session(
        self,
        session: TabSession,
        on_command_executed: Callable = None,
        on_thinking: Callable = None,
        on_usage_update: Callable = None
    ) -> None:
        """Create AI agent for a session's SSH connection."""
        if not session.ssh_session or not session.terminal:
            return

        async def execute_command(cmd: str) -> str:
            if session.ssh_session and session.ssh_session.is_connected:
                return await session.ssh_session.execute_command(cmd)
            raise RuntimeError("Not connected")

        def _normalize_for_terminal(text: str) -> str:
            # Convert lone LF or CR into CRLF so the terminal cursor resets to column 0.
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            return text.replace("\n", "\r\n")

        def cmd_callback(cmd: str, output: str) -> None:
            # Ensure injected command lines respect carriage return
            if session.terminal:
                session.terminal.append_output(f"\r\n$ {cmd}\r\n")
                session.terminal.append_output(_normalize_for_terminal(output) + "\r\n")

            # Send Enter to PTY to force shell to show prompt again
            if session.ssh_session and session.ssh_session.is_connected:
                asyncio.create_task(session.ssh_session.send_input("\r"))

            if on_command_executed:
                on_command_executed(cmd, output)

        # Get connection info from config
        host_address = session.config.host if session.config else None
        host_port = session.config.port if session.config else None
        username = session.config.username if session.config else None

        session.agent = create_agent(
            execute_command=execute_command,
            on_command_executed=cmd_callback,
            on_thinking=on_thinking,
            on_usage_update=on_usage_update,
            # Host connection info
            host_name=session.host_name,
            host_address=host_address,
            host_port=host_port,
            username=username,
            # Device metadata
            device_type=session.device_type,
            manufacturer=session.manufacturer,
            os_version=session.os_version,
            functions=session.functions,
            groups=session.groups,
            tags=session.tags,
            notes=session.notes
        )

    async def connect(self, session: TabSession, config: SSHConfig) -> bool:
        """
        Establish SSH connection for a session.

        Returns:
            True if connection successful, False otherwise
        """
        if not session.terminal:
            return False

        session.connection_status = "connecting"
        self.connection_started.emit(session)

        # Port knocking before SSH connection
        if session.port_knocking:
            await self.perform_port_knock(config.host, session.port_knocking)

        try:
            session.ssh_session = SSHSession(
                config,
                self._create_output_callback(session),
                self._create_disconnect_callback(session)
            )
            await session.ssh_session.connect()

            # Success - clear pending connection and save for reconnection
            session.pending_connection = None
            session.config = config
            session.connection_status = "connected"
            session.terminal.clear()
            session.terminal.set_focus()

            # Send terminal size after connection
            cols, rows = session.terminal.get_terminal_size()
            await session.ssh_session.resize_terminal(cols, rows)

            self.connection_success.emit(session)
            return True

        except asyncssh.PermissionDenied:
            logger.warning(f"Authentication failed for {config.username}@{config.host}")
            session.ssh_session = None
            session.connection_status = "disconnected"

            # Store connection data for retry (keep username)
            cols, rows = session.terminal.get_terminal_size()
            session.pending_connection = {
                "host": config.host,
                "port": config.port,
                "username": config.username,
                "terminal_type": config.terminal_type,
                "term_width": cols,
                "term_height": rows,
            }

            # Show error and prompt for password again
            session.terminal.append_output("Access denied\r\n")
            session.terminal.start_prelogin(need_username=False, need_password=True)

            self.connection_failed.emit(session, "Access denied")
            return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            session.ssh_session = None

            # Check if we have fallback hosts to try
            if session.fallback_hosts and session.current_host_index < len(session.fallback_hosts) - 1:
                session.current_host_index += 1
                next_ip = session.fallback_hosts[session.current_host_index]
                logger.info(f"Trying fallback IP: {next_ip}")

                # Create new config with next IP
                new_config = SSHConfig(
                    host=next_ip,
                    port=config.port,
                    username=config.username,
                    password=config.password,
                    terminal_type=config.terminal_type,
                    term_width=config.term_width,
                    term_height=config.term_height,
                )
                # Retry with next IP
                return await self.connect(session, new_config)

            # No more fallback hosts - connection failed
            session.pending_connection = None
            session.connection_status = "disconnected"
            session.fallback_hosts = []
            session.current_host_index = 0

            self.connection_failed.emit(session, str(e))
            return False

    async def disconnect(self, session: TabSession, agent_task: asyncio.Task = None) -> None:
        """Disconnect a session."""
        if agent_task and not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass

        if session.agent:
            await session.agent.close()
            session.agent = None

        if session.ssh_session:
            await session.ssh_session.disconnect()
            session.ssh_session = None

        session.connection_status = "disconnected"
        self.disconnected.emit(session)

    def handle_unexpected_disconnect(self, session: TabSession, agent_task: asyncio.Task = None) -> None:
        """Handle unexpected disconnection from SSH session."""
        logger.info(f"Unexpected disconnect detected for session {session.id}")

        # Clean up session state
        if agent_task and not agent_task.done():
            agent_task.cancel()
        session.agent = None
        session.ssh_session = None
        session.connection_status = "disconnected"

        # Clear any pending output buffer
        session.output_buffer.clear()

        # Show disconnected message in terminal
        if session.terminal:
            session.terminal.show_disconnected_message()

        self.disconnected.emit(session)
