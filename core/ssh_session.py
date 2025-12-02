"""
SSH Session wrapper using asyncssh.
Provides a clean interface for SSH connections with PTY support.
Designed to be reusable by the AI agent in future stages.
"""

import asyncio
import logging
from typing import Callable, Optional, Tuple, List
from dataclasses import dataclass

import asyncssh

logger = logging.getLogger(__name__)


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
            # Build connection options
            connect_options = {
                "host": self.config.host,
                "port": self.config.port,
                "known_hosts": None,  # Skip host key verification for simplicity
            }

            # Add username if provided
            if self.config.username:
                connect_options["username"] = self.config.username

            # Add password if provided, otherwise use keyboard-interactive
            if self.config.password:
                connect_options["password"] = self.config.password
            elif self.config.username:
                # Has username but no password - try keyboard-interactive
                connect_options["kbdint_auth"] = self._keyboard_interactive_auth

            # If no username at all, use keyboard-interactive for everything
            if not self.config.username:
                connect_options["username"] = ""
                connect_options["kbdint_auth"] = self._keyboard_interactive_auth

            self._conn = await asyncssh.connect(**connect_options)

            # Start interactive shell with PTY
            self._process = await self._conn.create_process(
                term_type=self.config.terminal_type,
                term_size=(self.config.term_width, self.config.term_height),
                encoding=None,  # Binary mode for raw terminal data
            )

            self._connected = True
            logger.info("SSH connection established")

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
