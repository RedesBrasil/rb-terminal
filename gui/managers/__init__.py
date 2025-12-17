"""
Managers module for RB Terminal.
Extracted from main_window.py for better separation of concerns.
"""

from gui.managers.session_manager import SessionManager
from gui.managers.connection_manager import ConnectionManager
from gui.managers.chat_coordinator import ChatCoordinator
from gui.managers.sftp_coordinator import SFTPCoordinator
from gui.managers.layout_manager import LayoutManager

__all__ = [
    "SessionManager",
    "ConnectionManager",
    "ChatCoordinator",
    "SFTPCoordinator",
    "LayoutManager",
]
