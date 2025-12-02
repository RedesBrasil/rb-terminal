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

# Terminal query patterns that require responses
# These are escape sequences that remote devices send to detect terminal capabilities
# MikroTik specifically uses these to decide whether to enable colors
#
# Response format reference (from VT220 spec):
# - DA1 (Primary): CSI ? 62 ; Ps... c  where Ps are feature codes
# - DA2 (Secondary): CSI > Pp ; Pv ; Pc c  where Pp=terminal type, Pv=version, Pc=ROM
#
# Feature codes for DA1: 1=132cols, 2=printer, 6=selective-erase, 8=UDK, 9=NRCS
TERMINAL_QUERIES = {
    # Primary Device Attributes (DA1) - ESC[c or ESC[0c
    # Response: VT220 with 132-col, printer, selective-erase support
    re.compile(rb'\x1b\[0?c(?!\?)'): b'\x1b[?62;1;2;6;8c',

    # Secondary Device Attributes (DA2) - ESC[>c or ESC[>0c
    # Response: VT220 (1), version 10, no ROM cartridge (0)
    re.compile(rb'\x1b\[>0?c'): b'\x1b[>1;10;0c',

    # DECID (ESC Z) - legacy terminal ID request
    # Response: same as DA1
    re.compile(rb'\x1bZ'): b'\x1b[?62;1;2;6;8c',

    # Cursor Position Report (DSR 6) - ESC[6n
    # Response: cursor at row 1, col 1
    re.compile(rb'\x1b\[6n'): b'\x1b[1;1R',

    # Device Status Report (DSR 5) - ESC[5n
    # Response: terminal OK
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
        # Track which queries we've already responded to (avoid duplicates)
        responded_queries: set = set()
        # Only respond to queries in the first few seconds of connection
        query_response_window = 5.0  # seconds
        connection_start = asyncio.get_event_loop().time()

        try:
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
                        # Handle terminal queries only in the first few seconds
                        # Respond BEFORE processing output to minimize latency
                        elapsed = asyncio.get_event_loop().time() - connection_start
                        if elapsed < query_response_window:
                            await self._respond_to_terminal_queries_async(data, responded_queries)

                        # Decode bytes to string, handling encoding errors
                        try:
                            text = data.decode('utf-8', errors='replace')
                        except Exception:
                            text = data.decode('latin-1', errors='replace')
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
                except (asyncssh.ChannelClosedError, asyncssh.ConnectionLost, BrokenPipeError):
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

    async def _respond_to_terminal_queries_async(self, data: bytes, responded: set) -> None:
        """
        Check for terminal capability queries and send appropriate responses.
        This is needed for devices like MikroTik that query terminal capabilities
        before enabling colors.

        Uses async write with drain to ensure immediate delivery.
        Tracks which queries have been responded to avoid duplicates.

        Args:
            data: Raw bytes received from remote
            responded: Set of query patterns already responded to
        """
        if not self._process or not self._process.stdin:
            return

        for pattern, response in TERMINAL_QUERIES.items():
            # Skip if we've already responded to this query type
            pattern_id = pattern.pattern
            if pattern_id in responded:
                continue

            if pattern.search(data):
                logger.info(f"Terminal query detected: {pattern.pattern!r}, responding with: {response!r}")
                try:
                    # Write and flush immediately to avoid MikroTik timeout
                    self._process.stdin.write(response)
                    await self._process.stdin.drain()
                    responded.add(pattern_id)
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
