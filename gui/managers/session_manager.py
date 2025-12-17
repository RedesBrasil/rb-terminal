"""
Session Manager - Handles terminal tab sessions.
Extracted from main_window.py for better separation of concerns.
"""

import asyncio
import logging
from typing import Optional, Dict, Callable

from PySide6.QtWidgets import QTabWidget, QTabBar, QLabel, QMessageBox
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor, QPainter, QPixmap, QIcon

from gui.tab_session import TabSession
from gui.terminal_widget import TerminalWidget

logger = logging.getLogger(__name__)


class SessionManager(QObject):
    """
    Manages terminal tab sessions.

    Responsibilities:
    - Creating and removing tab sessions
    - Tracking session state (connected, disconnected, connecting)
    - Managing tab widget UI (icons, titles, close buttons)
    - Providing access to active and specific sessions
    """

    # Signals
    session_created = Signal(TabSession)
    session_removed = Signal(str)  # session_id
    tab_changed = Signal(TabSession)  # new active session

    def __init__(self, tab_widget: QTabWidget, parent=None):
        super().__init__(parent)
        self._sessions: Dict[str, TabSession] = {}
        self._tab_widget = tab_widget
        self._status_icons = {}
        self._create_status_icons()

        # Callbacks for terminal signals (set by MainWindow)
        self._on_terminal_input: Optional[Callable] = None
        self._on_reconnect: Optional[Callable] = None
        self._on_prelogin_credentials: Optional[Callable] = None
        self._on_prelogin_cancelled: Optional[Callable] = None

        # Connect tab widget signals
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

    def set_terminal_callbacks(
        self,
        on_input: Callable,
        on_reconnect: Callable,
        on_prelogin_credentials: Callable,
        on_prelogin_cancelled: Callable
    ) -> None:
        """Set callbacks for terminal events."""
        self._on_terminal_input = on_input
        self._on_reconnect = on_reconnect
        self._on_prelogin_credentials = on_prelogin_credentials
        self._on_prelogin_cancelled = on_prelogin_cancelled

    def _create_status_icons(self) -> None:
        """Create status icons for tab states."""
        def create_circle_icon(color: QColor) -> QIcon:
            pixmap = QPixmap(12, 12)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(1, 1, 10, 10)
            painter.end()
            return QIcon(pixmap)

        self._status_icons = {
            "disconnected": create_circle_icon(QColor(128, 128, 128)),
            "connecting": create_circle_icon(QColor(202, 80, 16)),
            "connected": create_circle_icon(QColor(16, 124, 16)),
        }

    @property
    def sessions(self) -> Dict[str, TabSession]:
        """Get all sessions."""
        return self._sessions

    @property
    def status_icons(self) -> Dict[str, QIcon]:
        """Get status icons."""
        return self._status_icons

    def get_active_session(self) -> Optional[TabSession]:
        """Get the currently active tab's session."""
        if not self._tab_widget:
            return None
        index = self._tab_widget.currentIndex()
        if index < 0:
            return None
        widget = self._tab_widget.widget(index)
        if not widget:
            return None
        # Find session by terminal widget
        for session in self._sessions.values():
            if session.terminal is widget:
                return session
        return None

    def get_session(self, session_id: str) -> Optional[TabSession]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    def get_session_by_terminal(self, terminal: TerminalWidget) -> Optional[TabSession]:
        """Get session by its terminal widget."""
        for session in self._sessions.values():
            if session.terminal is terminal:
                return session
        return None

    def has_connected_sessions(self) -> bool:
        """Check if any session is connected."""
        return any(s.is_connected for s in self._sessions.values())

    def get_connected_sessions(self) -> list:
        """Get list of connected sessions."""
        return [s for s in self._sessions.values() if s.is_connected]

    def create_session(self) -> TabSession:
        """Create a new empty terminal tab session."""
        session = TabSession()
        session.terminal = TerminalWidget()

        # Connect terminal signals
        if self._on_terminal_input:
            session.terminal.input_entered.connect(
                lambda data, s=session: self._on_terminal_input(s, data)
            )
        if self._on_reconnect:
            session.terminal.reconnect_requested.connect(
                lambda s=session: self._on_reconnect(s)
            )
        if self._on_prelogin_credentials:
            session.terminal.prelogin_credentials.connect(
                lambda u, p, s=session: self._on_prelogin_credentials(s, u, p)
            )
        if self._on_prelogin_cancelled:
            session.terminal.prelogin_cancelled.connect(
                lambda s=session: self._on_prelogin_cancelled(s)
            )

        # Add to sessions dict
        self._sessions[session.id] = session

        # Add tab to widget
        index = self._tab_widget.addTab(session.terminal, session.display_name)

        # Add custom close button
        close_btn = self._create_tab_close_button(session.terminal)
        self._tab_widget.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close_btn)

        self._tab_widget.setCurrentIndex(index)

        self.session_created.emit(session)
        return session

    def _create_tab_close_button(self, terminal: TerminalWidget) -> QLabel:
        """Create a custom close button for a tab."""
        close_btn = QLabel("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close_btn.setStyleSheet("""
            QLabel {
                background-color: #c42b1c;
                color: white;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
            }
            QLabel:hover {
                background-color: #e81123;
            }
        """)
        # Find current index by terminal widget (handles tab reordering)
        close_btn.mousePressEvent = lambda e, t=terminal: self._on_tab_close_requested(
            self._tab_widget.indexOf(t)
        )
        return close_btn

    def update_tab_status(self, session: TabSession) -> None:
        """Update tab icon and title for a session."""
        if not session.terminal:
            return

        # Find tab index
        for i in range(self._tab_widget.count()):
            if self._tab_widget.widget(i) is session.terminal:
                self._tab_widget.setTabText(i, session.display_name)
                # Only show icon when connecting or connected (not disconnected)
                if session.connection_status == "disconnected":
                    self._tab_widget.setTabIcon(i, QIcon())  # Empty icon
                else:
                    self._tab_widget.setTabIcon(i, self._status_icons[session.connection_status])
                break

    def remove_session(self, session: TabSession, index: int) -> None:
        """Remove a tab from the widget and cleanup."""
        session_id = session.id

        # Remove from sessions dict
        if session.id in self._sessions:
            del self._sessions[session.id]

        # Remove tab
        self._tab_widget.removeTab(index)

        self.session_removed.emit(session_id)

        # If no tabs left, create a new empty one
        if self._tab_widget.count() == 0:
            self.create_session()

    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close request. Returns session to close or None if cancelled."""
        widget = self._tab_widget.widget(index)
        if not widget:
            return

        # Find session
        session = self.get_session_by_terminal(widget)
        if not session:
            return

        # Ask for confirmation
        parent = self._tab_widget.window()
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle("Fechar aba")
        msg_box.setText("Deseja fechar esta aba?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.button(QMessageBox.Yes).setText("Sim")
        msg_box.button(QMessageBox.No).setText("Não")

        if msg_box.exec() != QMessageBox.Yes:
            return

        # Emit signal for MainWindow to handle disconnect if needed
        # MainWindow will call remove_session after disconnecting
        if session.is_connected:
            # MainWindow handles async disconnect
            from PySide6.QtCore import QTimer
            # Store session and index for later removal
            self._pending_close = (session, index)
            # MainWindow should listen to this and call close_session_async
            self.close_requested = Signal(TabSession, int)
            # For now, emit through parent
            parent = self._tab_widget.window()
            if hasattr(parent, '_close_tab_async'):
                asyncio.ensure_future(parent._close_tab_async(session, index))
        else:
            self.remove_session(session, index)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change."""
        session = self.get_active_session()
        if session:
            self.tab_changed.emit(session)

    def next_tab(self) -> None:
        """Switch to next tab."""
        if not self._tab_widget or self._tab_widget.count() <= 1:
            return
        current = self._tab_widget.currentIndex()
        next_index = (current + 1) % self._tab_widget.count()
        self._tab_widget.setCurrentIndex(next_index)

    def prev_tab(self) -> None:
        """Switch to previous tab."""
        if not self._tab_widget or self._tab_widget.count() <= 1:
            return
        current = self._tab_widget.currentIndex()
        prev_index = (current - 1) % self._tab_widget.count()
        self._tab_widget.setCurrentIndex(prev_index)
