"""
Debug script to capture and analyze terminal queries from MikroTik.
Run this to see exactly what escape sequences are being sent.
"""

import asyncio
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncssh
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def hexdump(data: bytes, prefix: str = "") -> str:
    """Format bytes as hex dump for debugging."""
    hex_str = ' '.join(f'{b:02x}' for b in data)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
    return f"{prefix}HEX: {hex_str}\n{prefix}ASC: {ascii_str}"


def describe_escape_sequence(data: bytes) -> str:
    """Describe known escape sequences."""
    descriptions = []

    # Common terminal queries
    patterns = [
        (b'\x1b[c', 'DA1 - Primary Device Attributes'),
        (b'\x1b[0c', 'DA1 - Primary Device Attributes (explicit 0)'),
        (b'\x1b[>c', 'DA2 - Secondary Device Attributes'),
        (b'\x1b[>0c', 'DA2 - Secondary Device Attributes (explicit 0)'),
        (b'\x1b[6n', 'DSR - Device Status Report (cursor position)'),
        (b'\x1b[5n', 'DSR - Device Status Report (operating status)'),
        (b'\x1bZ', 'DECID - DEC Terminal ID (legacy)'),
        (b'\x1b[?1h', 'DECCKM - Cursor Keys Mode (application)'),
        (b'\x1b[?1l', 'DECCKM - Cursor Keys Mode (normal)'),
        (b'\x1b[?25h', 'DECTCEM - Show cursor'),
        (b'\x1b[?25l', 'DECTCEM - Hide cursor'),
        (b'\x1b[?2004h', 'Bracketed Paste Mode ON'),
        (b'\x1b[?2004l', 'Bracketed Paste Mode OFF'),
    ]

    for pattern, desc in patterns:
        if pattern in data:
            descriptions.append(desc)

    return '; '.join(descriptions) if descriptions else 'Unknown'


class DebugSSHSession:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.conn = None
        self.process = None
        self.captured_queries = []

    async def connect(self):
        print(f"\n{'='*60}")
        print(f"Connecting to {self.host}:{self.port} as {self.username}")
        print(f"{'='*60}\n")

        self.conn = await asyncssh.connect(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            known_hosts=None,
        )

        # Try different terminal types to see if behavior changes
        for term_type in ['xterm-256color', 'xterm', 'vt100']:
            print(f"\n>>> Testing terminal type: {term_type}")
            await self._test_terminal(term_type)
            await asyncio.sleep(0.5)

        print("\n\n" + "="*60)
        print("SUMMARY OF CAPTURED QUERIES")
        print("="*60)
        for i, (term, data, desc) in enumerate(self.captured_queries):
            print(f"\n[{i+1}] Terminal: {term}")
            print(hexdump(data, "    "))
            print(f"    DESC: {desc}")

    async def _test_terminal(self, term_type: str):
        """Test a specific terminal type."""
        try:
            process = await self.conn.create_process(
                term_type=term_type,
                term_size=(80, 24),
                encoding=None,
            )

            # Capture first 5 seconds of output
            start = asyncio.get_event_loop().time()
            buffer = b''

            while asyncio.get_event_loop().time() - start < 3:
                try:
                    data = await asyncio.wait_for(
                        process.stdout.read(8192),
                        timeout=0.1
                    )
                    if data:
                        buffer += data

                        # Check for escape sequences
                        if b'\x1b' in data:
                            desc = describe_escape_sequence(data)
                            self.captured_queries.append((term_type, data, desc))
                            print(f"\n!!! Escape sequence detected:")
                            print(hexdump(data, "    "))
                            print(f"    Description: {desc}")

                except asyncio.TimeoutError:
                    continue

            # Show all captured data
            if buffer:
                print(f"\n    Total received ({len(buffer)} bytes):")
                print(hexdump(buffer[:200], "    "))  # First 200 bytes
                if len(buffer) > 200:
                    print(f"    ... and {len(buffer) - 200} more bytes")

            process.close()

        except Exception as e:
            print(f"    Error: {e}")

    async def disconnect(self):
        if self.conn:
            self.conn.close()
            await self.conn.wait_closed()


async def main():
    if len(sys.argv) < 4:
        print("Usage: python debug_terminal_queries.py <host> <username> <password> [port]")
        print("\nExample: python debug_terminal_queries.py 192.168.1.1 admin password123")
        sys.exit(1)

    host = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 22

    session = DebugSSHSession(host, port, username, password)

    try:
        await session.connect()
    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        await session.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
