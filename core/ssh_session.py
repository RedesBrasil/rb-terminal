"""
SSH Session wrapper using asyncssh.
Provides a clean interface for SSH connections with PTY support.
Designed to be reusable by the AI agent in future stages.
"""

import asyncio
import logging
import re
from typing import Callable, Optional, Tuple, List
from dataclasses import dataclass

import asyncssh

logger = logging.getLogger(__name__)


class CursorTracker:
    """
    Tracks virtual cursor position based on terminal control sequences.

    MikroTik tests terminal capabilities by moving cursor and querying position.
    This tracker intercepts movement commands and responds with correct positions,
    allowing MikroTik to enable colors without the ~10 second detection timeout.
    """

    def __init__(self, width: int = 120, height: int = 30):
        self.x = 1  # Column (1-indexed)
        self.y = 1  # Row (1-indexed)
        self.width = width
        self.height = height

    def process_sequence(self, sequence: str) -> Optional[bytes]:
        """
        Process a CSI sequence and return response if needed.

        Args:
            sequence: CSI parameter string (e.g., "6n", "9999B")

        Returns:
            Response bytes to send, or None if no response needed
        """
        # Device Attributes (ESC[c or ESC[0c)
        if sequence in ['c', '0c']:
            return b'\x1b[?62;1;2;6;7;8;9c'  # VT220 with features

        # Cursor Position Report (ESC[6n) - most important for MikroTik
        if sequence == '6n':
            response = f'\x1b[{self.y};{self.x}R'
            return response.encode('ascii')

        # Device Status Report (ESC[5n)
        if sequence == '5n':
            return b'\x1b[0n'  # Terminal OK

        # Cursor movement commands - update tracked position
        # ESC[<n>A - Cursor Up
        match = re.match(r'(\d*)A', sequence)
        if match:
            n = int(match.group(1) or 1)
            self.y = max(1, self.y - n)
            return None

        # ESC[<n>B - Cursor Down (important: MikroTik uses ESC[9999B)
        match = re.match(r'(\d*)B', sequence)
        if match:
            n = int(match.group(1) or 1)
            self.y = min(self.height, self.y + n)
            return None

        # ESC[<n>C - Cursor Forward (Right)
        match = re.match(r'(\d*)C', sequence)
        if match:
            n = int(match.group(1) or 1)
            self.x = min(self.width, self.x + n)
            return None

        # ESC[<n>D - Cursor Back (Left)
        match = re.match(r'(\d*)D', sequence)
        if match:
            n = int(match.group(1) or 1)
            self.x = max(1, self.x - n)
            return None

        # ESC[<row>;<col>H or ESC[<row>;<col>f - Cursor Position
        match = re.match(r'(\d*);?(\d*)H', sequence) or re.match(r'(\d*);?(\d*)f', sequence)
        if match:
            row = int(match.group(1) or 1)
            col = int(match.group(2) or 1)
            self.y = max(1, min(self.height, row))
            self.x = max(1, min(self.width, col))
            return None

        # ESC[<n>d - Line Position Absolute
        match = re.match(r'(\d*)d', sequence)
        if match:
            row = int(match.group(1) or 1)
            self.y = max(1, min(self.height, row))
            return None

        return None

    def reset(self):
        """Reset cursor to home position."""
        self.x = 1
        self.y = 1


# Legacy terminal query patterns (kept for backward compatibility)
# Note: For MikroTik, use CursorTracker with proactive_terminal_response=True instead
TERMINAL_QUERIES = {
    # Primary Device Attributes (DA1) - ESC[c or ESC[0c
    re.compile(rb'\x1b\[0?c(?!\?)'): b'\x1b[?62;1;2;6;8c',

    # Secondary Device Attributes (DA2) - ESC[>c or ESC[>0c
    re.compile(rb'\x1b\[>0?c'): b'\x1b[>1;10;0c',

    # DECID (ESC Z) - legacy terminal ID request
    re.compile(rb'\x1bZ'): b'\x1b[?62;1;2;6;8c',

    # Cursor Position Report (DSR 6) - ESC[6n
    # Note: This is a fixed response. For accurate position, use CursorTracker
    re.compile(rb'\x1b\[6n'): b'\x1b[1;1R',

    # Device Status Report (DSR 5) - ESC[5n
    re.compile(rb'\x1b\[5n'): b'\x1b[0n',
}


@dataclass
class SSHConfig:
    """SSH connection configuration."""
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    terminal_type: str = "xterm"
    term_width: int = 80
    term_height: int = 24
    proactive_terminal_response: bool = False  # Enable for MikroTik to get colors without delay


class InteractiveAuthHandler:
    """
    Handler for keyboard-interactive authentication.
    Collects credentials via terminal prompts.
    """

    def __init__(
        self,
        output_callback: Callable[[str], None],
        input_future_setter: Callable[[asyncio.Future], None]
    ):
        self._output_callback = output_callback
        self._input_future_setter = input_future_setter
        self._pending_responses: List[asyncio.Future] = []

    async def get_response(self, prompt: str, echo: bool) -> str:
        """Get response from user for a prompt."""
        # Show prompt in terminal
        self._output_callback(prompt)

        # Create future for response
        response_future: asyncio.Future = asyncio.Future()
        self._input_future_setter(response_future)

        # Wait for user input
        try:
            response = await asyncio.wait_for(response_future, timeout=120.0)
            if not echo:
                # For password, just show newline (don't echo the password)
                self._output_callback("\r\n")
            return response
        except asyncio.TimeoutError:
            self._output_callback("\r\nTimeout waiting for input\r\n")
            return ""


class SSHSession:
    """
    Async SSH session with PTY support.

    Provides methods for:
    - Connecting/disconnecting
    - Sending input to the terminal
    - Receiving output via callback
    - Resizing terminal
    - Executing commands (for AI agent use)
    """

    def __init__(
        self,
        config: SSHConfig,
        output_callback: Callable[[str], None],
        disconnect_callback: Optional[Callable[[], None]] = None
    ):
        """
        Initialize SSH session.

        Args:
            config: SSH connection configuration
            output_callback: Function called with terminal output data
            disconnect_callback: Function called when connection is lost unexpectedly
        """
        self.config = config
        self._output_callback = output_callback
        self._disconnect_callback = disconnect_callback
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._process: Optional[asyncssh.SSHClientProcess] = None
        self._connected = False
        self._read_task: Optional[asyncio.Task] = None
        self._manual_disconnect = False
        self._auth_input_future: Optional[asyncio.Future] = None
        self._waiting_for_auth_input = False
        self._cursor_tracker: Optional[CursorTracker] = None

    @property
    def is_connected(self) -> bool:
        """Check if session is connected."""
        return self._connected and self._conn is not None

    def _set_auth_input_future(self, future: asyncio.Future) -> None:
        """Set the future for receiving auth input."""
        self._auth_input_future = future
        self._waiting_for_auth_input = True

    async def _keyboard_interactive_auth(
        self,
        name: str,
        instructions: str,
        prompts: List[Tuple[str, bool]]
    ) -> List[str]:
        """
        Handle keyboard-interactive authentication.
        Shows prompts in terminal and collects responses.
        """
        handler = InteractiveAuthHandler(
            self._output_callback,
            self._set_auth_input_future
        )

        if name:
            self._output_callback(f"{name}\r\n")
        if instructions:
            self._output_callback(f"{instructions}\r\n")

        responses = []
        for prompt, echo in prompts:
            response = await handler.get_response(prompt, echo)
            responses.append(response)

        self._waiting_for_auth_input = False
        return responses

    def provide_auth_input(self, data: str) -> bool:
        """
        Provide input during authentication phase.
        Returns True if input was consumed for auth.
        """
        if self._waiting_for_auth_input and self._auth_input_future:
            if not self._auth_input_future.done():
                # Remove trailing newline/return
                clean_data = data.rstrip('\r\n')
                self._auth_input_future.set_result(clean_data)
                return True
        return False

    @property
    def waiting_for_auth(self) -> bool:
        """Check if session is waiting for authentication input."""
        return self._waiting_for_auth_input

    async def connect(self) -> None:
        """
        Establish SSH connection with PTY.

        Raises:
            asyncssh.Error: On connection failure
            Exception: On other errors
        """
        logger.info(f"Connecting to {self.config.host}:{self.config.port}")
        self._manual_disconnect = False

        try:
            # Username is required - should be collected before calling connect()
            if not self.config.username:
                raise ValueError("Username is required for SSH connection")

            # Build connection options
            connect_options = {
                "host": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "known_hosts": None,  # Skip host key verification for simplicity
            }

            # Add password if provided, otherwise use keyboard-interactive for password
            if self.config.password:
                connect_options["password"] = self.config.password
            else:
                # No password saved - use keyboard-interactive to prompt for password
                connect_options["kbdint_auth"] = self._keyboard_interactive_auth

            self._conn = await asyncssh.connect(**connect_options)

            # Start interactive shell with PTY
            logger.info(f"Creating PTY with term_type={self.config.terminal_type}")

            self._process = await self._conn.create_process(
                term_type=self.config.terminal_type,
                term_size=(self.config.term_width, self.config.term_height),
                encoding=None,  # Binary mode for raw terminal data
            )

            self._connected = True
            logger.info(f"SSH connection established (terminal: {self.config.terminal_type})")

            # Initialize cursor tracker for proactive terminal response (MikroTik)
            if self.config.proactive_terminal_response:
                self._cursor_tracker = CursorTracker(
                    width=self.config.term_width,
                    height=self.config.term_height
                )
                logger.info("Proactive terminal response enabled (for MikroTik colors)")

            # Start reading output in background
            self._read_task = asyncio.create_task(self._read_output())

        except asyncssh.PermissionDenied:
            logger.error("Authentication failed")
            raise
        except asyncssh.HostKeyNotVerifiable:
            logger.error("Host key verification failed")
            raise
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def _read_output(self) -> None:
        """Background task to read and forward terminal output."""
        unexpected_disconnect = False
        connection_start = asyncio.get_event_loop().time()

        try:
            # CSI sequence pattern for extracting control sequences
            csi_pattern = re.compile(rb'\x1b\[([^a-zA-Z]*[a-zA-Z])')
            query_response_window = 5.0  # Only respond to queries in first 5 seconds

            while self._connected and self._process:
                try:
                    # Check if process has exited
                    if self._process.exit_status is not None:
                        logger.info(f"SSH process exited with status {self._process.exit_status}")
                        self._connected = False
                        unexpected_disconnect = not self._manual_disconnect
                        break

                    # Read with a short timeout to allow event loop to process
                    data = await asyncio.wait_for(
                        self._process.stdout.read(8192),
                        timeout=0.05
                    )
                    if data:
                        # Handle terminal queries
                        elapsed = asyncio.get_event_loop().time() - connection_start
                        if elapsed < query_response_window:
                            if self._cursor_tracker:
                                # Use CursorTracker for accurate position tracking
                                await self._respond_with_cursor_tracker(data, csi_pattern)
                            else:
                                # Fall back to legacy query response (no duplicate tracking)
                                await self._respond_to_terminal_queries_legacy(data)

                        # Send raw bytes to terminal - pyte can handle bytes directly
                        # This preserves ANSI escape sequences perfectly
                        if isinstance(data, bytes):
                            # Decode as latin-1 (preserves all bytes 0-255 as-is)
                            text = data.decode('latin-1')
                        else:
                            text = data
                        self._output_callback(text)
                    else:
                        # EOF - connection closed (empty bytes or None)
                        logger.info("SSH connection closed by remote (EOF)")
                        self._connected = False
                        unexpected_disconnect = not self._manual_disconnect
                        break
                except asyncio.TimeoutError:
                    # Check if process exited during timeout
                    if self._process and self._process.exit_status is not None:
                        logger.info(f"SSH process exited with status {self._process.exit_status}")
                        self._connected = False
                        unexpected_disconnect = not self._manual_disconnect
                        break
                    # Yield to allow other tasks to run
                    await asyncio.sleep(0)
                    continue
                except (asyncssh.ConnectionLost, asyncssh.ProcessError, BrokenPipeError):
                    # Channel/connection closed - normal termination (e.g., exit command)
                    logger.info("SSH channel closed")
                    self._connected = False
                    unexpected_disconnect = not self._manual_disconnect
                    break
                except Exception as e:
                    if self._connected:
                        logger.error(f"Error reading output: {e}")
                        unexpected_disconnect = not self._manual_disconnect
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            # Notify about unexpected disconnection
            if unexpected_disconnect and self._disconnect_callback:
                self._disconnect_callback()

    def _filter_terminal_queries(self, data: bytes) -> bytes:
        """
        Remove terminal query sequences from data before displaying.
        These queries (ESC[6n, ESC[c, etc.) are meant for the terminal emulator,
        not for display to the user.

        Args:
            data: Raw bytes from server

        Returns:
            Filtered bytes with queries removed
        """
        # Remove common terminal queries (very specific patterns only!)
        # Device Status Report - ESC[5n
        data = re.sub(rb'\x1b\[5n', b'', data)

        # Cursor Position Report - ESC[6n
        data = re.sub(rb'\x1b\[6n', b'', data)

        # Device Attributes - ESC[c or ESC[0c (but NOT ESC[...m color codes!)
        # Must match EXACTLY: ESC [ optional0 c
        data = re.sub(rb'\x1b\[0c(?![^\x1b])', b'', data)  # ESC[0c
        data = re.sub(rb'\x1b\[c(?![^\x1b])', b'', data)   # ESC[c

        # Secondary Device Attributes - ESC[>0c or ESC[>c
        data = re.sub(rb'\x1b\[>0c', b'', data)
        data = re.sub(rb'\x1b\[>c', b'', data)

        # DECID - ESC Z
        data = re.sub(rb'\x1bZ', b'', data)

        return data

    async def _respond_with_cursor_tracker(self, data: bytes, csi_pattern: re.Pattern) -> None:
        """
        Use CursorTracker to process CSI sequences and respond to queries.
        This allows MikroTik to detect terminal capabilities quickly with accurate cursor positions.

        Args:
            data: Raw bytes received from remote
            csi_pattern: Compiled regex pattern for extracting CSI sequences
        """
        if not self._process or not self._process.stdin or not self._cursor_tracker:
            return

        try:
            # Extract all CSI sequences from data
            for match in csi_pattern.finditer(data):
                seq_bytes = match.group(1)
                try:
                    seq_str = seq_bytes.decode('ascii')
                except UnicodeDecodeError:
                    continue

                # Process sequence and get response if needed
                response = self._cursor_tracker.process_sequence(seq_str)
                if response:
                    # Send response immediately
                    logger.debug(f"CursorTracker: Query ESC[{seq_str} -> Response {response!r}")
                    self._process.stdin.write(response)
                    # Note: Not awaiting drain() here for performance
                    # The buffer should handle multiple small responses

            # Drain once after processing all sequences
            await self._process.stdin.drain()

        except Exception as e:
            logger.warning(f"Error in cursor tracker response: {e}")

    async def _respond_to_terminal_queries_legacy(self, data: bytes) -> None:
        """
        Legacy terminal query response (without cursor tracking).
        Used when proactive_terminal_response is disabled.

        Args:
            data: Raw bytes received from remote
        """
        if not self._process or not self._process.stdin:
            return

        for pattern, response in TERMINAL_QUERIES.items():
            if pattern.search(data):
                try:
                    self._process.stdin.write(response)
                    await self._process.stdin.drain()
                except Exception as e:
                    logger.warning(f"Failed to send terminal query response: {e}")

    async def disconnect(self) -> None:
        """Close SSH connection gracefully."""
        logger.info("Disconnecting SSH session")
        self._manual_disconnect = True
        self._connected = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._process:
            self._process.close()
            self._process = None

        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

        logger.info("SSH session disconnected")

    async def send_input(self, data: str) -> None:
        """
        Send input data to the terminal.

        Args:
            data: String data to send (can include special chars like \\n)
        """
        if not self._connected or not self._process:
            logger.warning("Cannot send input: not connected")
            return

        try:
            self._process.stdin.write(data.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending input: {e}")

    async def resize_terminal(self, width: int, height: int) -> None:
        """
        Resize the PTY terminal.

        Args:
            width: New terminal width in columns
            height: New terminal height in rows
        """
        if not self._connected or not self._process:
            return

        try:
            self._process.change_terminal_size(width, height)
            self.config.term_width = width
            self.config.term_height = height

            # Update cursor tracker dimensions
            if self._cursor_tracker:
                self._cursor_tracker.width = width
                self._cursor_tracker.height = height

            logger.debug(f"Terminal resized to {width}x{height}")
        except Exception as e:
            logger.error(f"Error resizing terminal: {e}")

    async def execute_command(self, command: str, timeout: float = 30.0) -> str:
        """
        Execute a single command and return the output.
        This method is designed for AI agent use.

        Note: For interactive sessions, use send_input() instead.
        This creates a separate channel for command execution.

        Args:
            command: Command to execute
            timeout: Maximum time to wait for command completion

        Returns:
            Command output (stdout + stderr)
        """
        if not self._conn:
            raise RuntimeError("Not connected")

        try:
            result = await asyncio.wait_for(
                self._conn.run(command, check=False),
                timeout=timeout
            )
            output = result.stdout or ""
            if result.stderr:
                output += result.stderr
            return output
        except asyncio.TimeoutError:
            raise TimeoutError(f"Command timed out after {timeout}s")
