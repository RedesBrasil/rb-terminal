"""
Main Window for RB Terminal.
Contains collapsible hosts sidebar, terminal widget with tabs, and AI chat panel.
"""

import asyncio
import logging
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, Dict

import asyncssh

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QStatusBar, QSplitter, QMenu, QFrame, QToolBar, QSizePolicy,
    QLineEdit, QDialog, QTabWidget, QToolButton, QStackedWidget
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSize
from PySide6.QtGui import QCloseEvent, QAction, QColor, QPainter, QPixmap, QIcon

from core.ssh_session import SSHSession, SSHConfig
from core.agent import create_agent, SSHAgent
from core.data_manager import get_data_manager, DataManager, ChatMessage
from gui.terminal_widget import TerminalWidget
from gui.chat_widget import ChatWidget
from gui.hosts_dialog import HostDialog, PasswordPromptDialog, QuickConnectDialog
from gui.settings_dialog import SettingsDialog
from gui.tab_session import TabSession
from gui.hosts_view import HostsView
from gui.setup_dialog import SetupDialog
from gui.unlock_dialog import UnlockDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with hosts view, terminal tabs, and chat."""

    # Signal for thread-safe SSH output handling (includes tab_id)
    _ssh_output_received = Signal(str, str)  # tab_id, data
    # Signal for unexpected disconnection (includes tab_id)
    _unexpected_disconnect = Signal(str)  # tab_id

    def __init__(self):
        super().__init__()

        # Tab management
        self._sessions: Dict[str, TabSession] = {}  # tab_id -> TabSession
        self._tab_widget: Optional[QTabWidget] = None
        self._agent_task: Optional[asyncio.Task] = None

        self._resize_timer: Optional[QTimer] = None
        self._chat_visible: bool = False  # Chat starts hidden

        # Initialize data manager and handle setup/unlock
        self._data_manager = get_data_manager()
        if not self._handle_startup():
            # User cancelled setup/unlock - exit
            import sys
            sys.exit(0)

        self._chat_position = self._data_manager.get_chat_position()
        self._splitter_sizes = {
            "bottom": [700, 300],
            "left": [300, 700],
            "right": [700, 300],
        }
        self._applying_splitter_sizes = False

        # Output timer for batching SSH output
        self._output_timer = QTimer()
        self._output_timer.setSingleShot(True)
        self._output_timer.timeout.connect(self._flush_output_buffer)

        # Status icons for tabs
        self._status_icons = {}
        self._create_status_icons()

        self._setup_ui()
        self._setup_connections()

        # Create first empty tab
        self._create_new_tab()

        self._update_ui_state()
        self._refresh_hosts_list()

        # Start maximized
        self.showMaximized()

    def _handle_startup(self) -> bool:
        """
        Handle application startup - setup or unlock as needed.

        Returns:
            True if startup successful, False if user cancelled
        """
        dm = self._data_manager

        # Case 1: First run (no data.json)
        if dm.is_first_run():
            dialog = SetupDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False

            password = dialog.get_master_password()
            if password:
                dm.setup_master_password(password)
            else:
                dm.setup_no_password()

        # Case 2: Needs migration from legacy files
        elif dm.needs_migration():
            dm.load()  # This triggers migration
            # Optionally offer to set master password after migration
            reply = QMessageBox.question(
                self,
                "Migracao Concluida",
                "Dados migrados com sucesso!\n\n"
                "Deseja definir uma senha mestra para proteger suas senhas?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                dialog = SetupDialog(self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    password = dialog.get_master_password()
                    if password:
                        dm.change_master_password("", password)

        # Case 3: Has master password but no cached session (new machine)
        elif dm.needs_unlock():
            error_msg = None
            while True:
                dialog = UnlockDialog(self, error_message=error_msg)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return False

                if dm.unlock(dialog.get_password()):
                    break
                error_msg = "Senha incorreta. Tente novamente."

        # Load data (uses cached session if available)
        dm.load()
        return True

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

    def _setup_ui(self) -> None:
        """Setup the main window UI."""
        self.setWindowTitle("RB Terminal")
        self.setMinimumSize(1000, 600)
        self.resize(1280, 768)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar (always visible)
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Stacked widget for switching between hosts view and terminal view
        self._stacked_widget = QStackedWidget()
        main_layout.addWidget(self._stacked_widget)

        # Page 0: Hosts view (main screen when not connected)
        self._hosts_view = HostsView(self._data_manager)
        self._hosts_view.connect_requested.connect(self._connect_to_host)
        self._hosts_view.edit_requested.connect(self._edit_host)
        self._hosts_view.delete_requested.connect(self._delete_host)
        self._hosts_view.winbox_requested.connect(self._launch_winbox)
        self._hosts_view.web_access_requested.connect(self._open_web_access)
        self._hosts_view.add_requested.connect(self._on_add_host_clicked)
        self._hosts_view.quick_connect_requested.connect(self._on_quick_connect)
        self._stacked_widget.addWidget(self._hosts_view)

        # Page 1: Terminal area (tabs + chat)
        self._terminal_area = QWidget()
        terminal_layout = QVBoxLayout(self._terminal_area)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)
        self._content_layout = terminal_layout

        # Tab widget for multiple terminals
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(False)  # We'll add custom close buttons
        self._tab_widget.setMovable(True)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        # Style the tab widget
        self._tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #969696;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3c3c3c;
            }
        """)

        # Chat panel (position determined by settings)
        self._chat_panel = QFrame()
        self._update_chat_panel_style()
        self._setup_chat_panel()

        self._terminal_chat_splitter: Optional[QSplitter] = None
        self._rebuild_terminal_chat_splitter()

        self._stacked_widget.addWidget(self._terminal_area)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Desconectado")

        # Apply dark theme
        self._apply_dark_theme()

    def _setup_chat_panel(self) -> None:
        """Setup the chat panel content."""
        layout = QVBoxLayout(self._chat_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat widget
        self._chat = ChatWidget()
        layout.addWidget(self._chat)

    def _update_chat_panel_style(self) -> None:
        """Update chat panel border based on position."""
        if not hasattr(self, "_chat_panel") or self._chat_panel is None:
            return

        if self._chat_position == "bottom":
            border = "border-top: 1px solid #3c3c3c;"
        elif self._chat_position == "left":
            border = "border-right: 1px solid #3c3c3c;"
        else:  # right
            border = "border-left: 1px solid #3c3c3c;"

        self._chat_panel.setStyleSheet(f"background-color: #252526; {border}")

    def _create_terminal_chat_splitter(self) -> QSplitter:
        """Create splitter configured for the selected chat position."""
        if self._chat_position == "bottom":
            splitter = QSplitter(Qt.Orientation.Vertical)
            splitter.addWidget(self._tab_widget)
            splitter.addWidget(self._chat_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
        elif self._chat_position == "left":
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._chat_panel)
            splitter.addWidget(self._tab_widget)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
        else:  # right
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._tab_widget)
            splitter.addWidget(self._chat_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        return splitter

    def _rebuild_terminal_chat_splitter(self) -> None:
        """Rebuild splitter when chat layout or orientation changes."""
        if hasattr(self, "_terminal_chat_splitter") and self._terminal_chat_splitter:
            try:
                self._terminal_chat_splitter.splitterMoved.disconnect(self._on_splitter_moved)
            except (TypeError, RuntimeError):
                pass
            self._terminal_chat_splitter.setParent(None)

        splitter = self._create_terminal_chat_splitter()
        self._terminal_chat_splitter = splitter
        self._content_layout.addWidget(splitter, 1)
        splitter.splitterMoved.connect(self._on_splitter_moved)
        self._apply_chat_visibility()

    def _apply_chat_visibility(self) -> None:
        """Adjust splitter sizes based on chat visibility."""
        if not self._terminal_chat_splitter:
            return

        # Hide or show panel widget
        if hasattr(self, "_chat_panel") and self._chat_panel:
            self._chat_panel.setVisible(self._chat_visible)

        if not self._chat_visible:
            hide_sizes = [1, 0] if self._chat_position != "left" else [0, 1]
            self._applying_splitter_sizes = True
            self._terminal_chat_splitter.setSizes(hide_sizes)
            self._applying_splitter_sizes = False
        else:
            sizes = self._splitter_sizes.get(self._chat_position)
            if not sizes:
                sizes = self._get_default_splitter_sizes(self._chat_position)
            self._applying_splitter_sizes = True
            self._terminal_chat_splitter.setSizes(sizes)
            self._applying_splitter_sizes = False

        # Sync toolbar toggle state without re-triggering signals
        if hasattr(self, "_toggle_chat_btn"):
            blocked = self._toggle_chat_btn.blockSignals(True)
            self._toggle_chat_btn.setChecked(self._chat_visible)
            self._toggle_chat_btn.blockSignals(blocked)

    def _get_default_splitter_sizes(self, position: str) -> list[int]:
        """Default splitter sizes for each chat orientation."""
        if position == "bottom":
            return [700, 280]
        if position == "left":
            return [300, 700]
        return [700, 300]

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Store splitter sizes when user manually adjusts layout."""
        if self._applying_splitter_sizes or not self._chat_visible:
            return
        if self._terminal_chat_splitter:
            self._splitter_sizes[self._chat_position] = self._terminal_chat_splitter.sizes()

    def _apply_settings_changes(self) -> None:
        """Apply settings that might impact layout."""
        new_position = self._data_manager.get_chat_position()
        if new_position != self._chat_position:
            self._chat_position = new_position
            self._update_chat_panel_style()
            self._rebuild_terminal_chat_splitter()

    def _create_toolbar(self) -> QToolBar:
        """Create the main toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #252526;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                padding: 4px;
                spacing: 4px;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #dcdcdc;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
            QToolButton:pressed {
                background-color: #094771;
            }
            QToolButton:checked {
                background-color: #094771;
            }
        """)

        # Hosts button - go back to hosts view
        self._hosts_btn = QAction("Hosts", self)
        self._hosts_btn.setToolTip("Voltar para lista de hosts (Ctrl+H)")
        self._hosts_btn.setShortcut("Ctrl+H")
        self._hosts_btn.triggered.connect(self._show_hosts_view)
        toolbar.addAction(self._hosts_btn)

        toolbar.addSeparator()

        # Toggle chat button (starts unchecked/hidden)
        self._toggle_chat_btn = QAction("Chat IA", self)
        self._toggle_chat_btn.setCheckable(True)
        self._toggle_chat_btn.setChecked(False)
        self._toggle_chat_btn.setToolTip("Mostrar/Esconder chat IA (Ctrl+I)")
        self._toggle_chat_btn.setShortcut("Ctrl+I")
        self._toggle_chat_btn.triggered.connect(self._on_toggle_chat)
        toolbar.addAction(self._toggle_chat_btn)

        # Terminal button - return to terminal view (only visible when sessions exist)
        self._terminal_btn = QAction("Terminal", self)
        self._terminal_btn.setToolTip("Voltar para terminal")
        self._terminal_btn.triggered.connect(self._show_terminal_view)
        self._terminal_btn.setVisible(False)  # Hidden by default
        toolbar.addAction(self._terminal_btn)

        toolbar.addSeparator()

        # Quick connect button
        self._quick_connect_btn = QAction("Conexao Rapida", self)
        self._quick_connect_btn.setToolTip("Conectar sem salvar (Ctrl+N)")
        self._quick_connect_btn.setShortcut("Ctrl+N")
        self._quick_connect_btn.triggered.connect(self._on_quick_connect)
        toolbar.addAction(self._quick_connect_btn)

        toolbar.addSeparator()

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Config button (right side)
        self._config_btn = QAction("Config", self)
        self._config_btn.setToolTip("Configuracoes do aplicativo")
        self._config_btn.triggered.connect(self._on_config_clicked)
        toolbar.addAction(self._config_btn)

        return toolbar

    def _apply_dark_theme(self) -> None:
        """Apply dark theme to the window."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
            QGroupBox {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin-top: 8px;
                padding: 12px;
                padding-top: 24px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #dcdcdc;
            }
            QLineEdit, QSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                color: #dcdcdc;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                color: white;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
            }
            QSplitter::handle {
                background-color: #3c3c3c;
                height: 3px;
            }
            QSplitter::handle:hover {
                background-color: #007acc;
            }
            QMenu {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """)

    def _setup_connections(self) -> None:
        """Connect signals to slots."""
        # SSH output signal - use AutoConnection since qasync integrates both loops
        self._ssh_output_received.connect(self._on_ssh_output_slot, Qt.ConnectionType.AutoConnection)

        # Unexpected disconnect signal
        self._unexpected_disconnect.connect(self._on_unexpected_disconnect, Qt.ConnectionType.AutoConnection)

        # Chat signals
        self._chat.message_sent.connect(self._on_chat_message)
        self._chat.stop_requested.connect(self._on_stop_agent)
        self._chat.conversation_changed.connect(self._on_conversation_changed)
        self._chat.new_conversation_requested.connect(self._on_new_conversation)

        # Setup resize timer for terminal resize
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_timeout)

        # Keyboard shortcuts for tabs
        new_tab_action = QAction("Nova Aba", self)
        new_tab_action.setShortcut("Ctrl+T")
        new_tab_action.triggered.connect(self._on_new_tab)
        self.addAction(new_tab_action)

        close_tab_action = QAction("Fechar Aba", self)
        close_tab_action.setShortcut("Ctrl+W")
        close_tab_action.triggered.connect(self._on_close_current_tab)
        self.addAction(close_tab_action)

        next_tab_action = QAction("Proxima Aba", self)
        next_tab_action.setShortcut("Ctrl+Right")
        next_tab_action.triggered.connect(self._on_next_tab)
        self.addAction(next_tab_action)

        prev_tab_action = QAction("Aba Anterior", self)
        prev_tab_action.setShortcut("Ctrl+Left")
        prev_tab_action.triggered.connect(self._on_prev_tab)
        self.addAction(prev_tab_action)

    def _get_active_session(self) -> Optional[TabSession]:
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

    def _get_session_by_terminal(self, terminal: TerminalWidget) -> Optional[TabSession]:
        """Get session by its terminal widget."""
        for session in self._sessions.values():
            if session.terminal is terminal:
                return session
        return None

    def _update_ui_state(self) -> None:
        """Update UI based on active tab connection state."""
        session = self._get_active_session()
        connected = session is not None and session.is_connected

        # Update toolbar buttons
        self._quick_connect_btn.setEnabled(not connected)

        # Update chat state
        self._chat.set_enabled_state(connected)

        # Check if any session is connected
        any_connected = any(s.is_connected for s in self._sessions.values())

        # Show/hide Terminal button based on whether any session is connected
        self._terminal_btn.setVisible(any_connected)

        if connected and session and session.config:
            host = session.config.host
            self._status_bar.showMessage(f"Conectado a {host}")
            self._status_bar.setStyleSheet("background-color: #107c10; color: white;")
            # Show terminal view when connected
            self._show_terminal_view()
        else:
            self._status_bar.showMessage("Desconectado")
            self._status_bar.setStyleSheet("background-color: #007acc; color: white;")
            if not any_connected:
                # Show hosts view when no connection
                self._show_hosts_view()

    def _show_hosts_view(self) -> None:
        """Show the hosts view."""
        self._stacked_widget.setCurrentIndex(0)
        self._hosts_view.refresh()

    def _show_terminal_view(self) -> None:
        """Show the terminal view."""
        self._stacked_widget.setCurrentIndex(1)

    def _create_tab_close_button(self, terminal: QWidget) -> QLabel:
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

    def _create_new_tab(self) -> TabSession:
        """Create a new empty terminal tab."""
        session = TabSession()
        session.terminal = TerminalWidget()

        # Connect terminal signals for this session
        session.terminal.input_entered.connect(
            lambda data, s=session: self._on_terminal_input_for_session(s, data)
        )
        session.terminal.reconnect_requested.connect(
            lambda s=session: self._on_reconnect_for_session(s)
        )
        session.terminal.prelogin_credentials.connect(
            lambda u, p, s=session: self._on_prelogin_credentials_for_session(s, u, p)
        )
        session.terminal.prelogin_cancelled.connect(
            lambda s=session: self._on_prelogin_cancelled_for_session(s)
        )

        # Add to sessions dict
        self._sessions[session.id] = session

        # Add tab to widget (no icon for new disconnected tabs)
        index = self._tab_widget.addTab(session.terminal, session.display_name)

        # Add custom close button
        close_btn = self._create_tab_close_button(session.terminal)
        from PySide6.QtWidgets import QTabBar
        self._tab_widget.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close_btn)

        self._tab_widget.setCurrentIndex(index)

        return session

    def _update_tab_status(self, session: TabSession) -> None:
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

    @Slot()
    def _on_new_tab(self) -> None:
        """Handle new tab request (Ctrl+T or + button)."""
        self._create_new_tab()

    @Slot()
    def _on_close_current_tab(self) -> None:
        """Handle Ctrl+W - close current tab."""
        index = self._tab_widget.currentIndex()
        if index >= 0:
            self._on_tab_close_requested(index)

    @Slot(int)
    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close request."""
        widget = self._tab_widget.widget(index)
        if not widget:
            return

        # Find session
        session = self._get_session_by_terminal(widget)
        if not session:
            return

        # Ask for confirmation
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Fechar aba")
        msg_box.setText("Deseja fechar esta aba?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.button(QMessageBox.Yes).setText("Sim")
        msg_box.button(QMessageBox.No).setText("Não")

        if msg_box.exec() != QMessageBox.Yes:
            return

        # Disconnect if connected
        if session.is_connected:
            asyncio.ensure_future(self._close_tab_async(session, index))
        else:
            self._remove_tab(session, index)

    async def _close_tab_async(self, session: TabSession, index: int) -> None:
        """Close tab with async disconnect."""
        await self._disconnect_session_async(session)
        self._remove_tab(session, index)

    def _remove_tab(self, session: TabSession, index: int) -> None:
        """Remove a tab from the widget and cleanup."""
        # Remove from sessions dict
        if session.id in self._sessions:
            del self._sessions[session.id]

        # Remove tab
        self._tab_widget.removeTab(index)

        # If no tabs left, create a new empty one
        if self._tab_widget.count() == 0:
            self._create_new_tab()
        else:
            self._update_ui_state()

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change - update UI state and chat context."""
        self._update_ui_state()

        # Restore chat state for the new tab
        session = self._get_active_session()
        if session:
            self._restore_chat_for_session(session)
            if session.terminal:
                session.terminal.set_focus()

    @Slot()
    def _on_next_tab(self) -> None:
        """Switch to next tab (Ctrl+Right)."""
        if not self._tab_widget or self._tab_widget.count() <= 1:
            return
        current = self._tab_widget.currentIndex()
        next_index = (current + 1) % self._tab_widget.count()
        self._tab_widget.setCurrentIndex(next_index)

    @Slot()
    def _on_prev_tab(self) -> None:
        """Switch to previous tab (Ctrl+Left)."""
        if not self._tab_widget or self._tab_widget.count() <= 1:
            return
        current = self._tab_widget.currentIndex()
        prev_index = (current - 1) % self._tab_widget.count()
        self._tab_widget.setCurrentIndex(prev_index)

    def _on_terminal_input_for_session(self, session: TabSession, data: str) -> None:
        """Handle input from a specific terminal session."""
        if not session.ssh_session:
            return

        # Check if waiting for authentication input
        if session.ssh_session.waiting_for_auth:
            session.ssh_session.provide_auth_input(data)
            return

        if session.ssh_session.is_connected:
            asyncio.ensure_future(session.ssh_session.send_input(data))

    def _on_reconnect_for_session(self, session: TabSession) -> None:
        """Handle reconnect request for a specific session."""
        # Check if we have pending connection (from cancelled pre-login or auth failure)
        if session.pending_connection:
            if session.terminal:
                cols, rows = session.terminal.get_terminal_size()
                session.pending_connection["term_width"] = cols
                session.pending_connection["term_height"] = rows

            # Check if we already have username (retry password scenario)
            has_username = bool(session.pending_connection.get("username"))
            if session.terminal:
                session.terminal.start_prelogin(need_username=not has_username, need_password=True)
            return

        # Otherwise try to reconnect with last successful config
        if session.config:
            if session.terminal:
                cols, rows = session.terminal.get_terminal_size()
                session.config.term_width = cols
                session.config.term_height = rows
            asyncio.ensure_future(self._connect_session_async(session, session.config))

    def _on_prelogin_credentials_for_session(self, session: TabSession, username: str, password: str) -> None:
        """Handle credentials received from terminal pre-login mode for a session."""
        if not session.pending_connection:
            return

        # Use username from pending_connection if available (retry scenario)
        # Otherwise use the username just entered
        final_username = session.pending_connection.get("username") or username

        if not final_username:
            # User cancelled or empty username
            session.pending_connection = None
            if session.terminal:
                session.terminal.clear()
            return

        # Build config with collected credentials
        config = SSHConfig(
            host=session.pending_connection["host"],
            port=session.pending_connection["port"],
            username=final_username,
            password=password,
            terminal_type=session.pending_connection["terminal_type"],
            term_width=session.pending_connection["term_width"],
            term_height=session.pending_connection["term_height"],
        )

        # Keep pending_connection for retry on auth failure
        asyncio.ensure_future(self._connect_session_async(session, config))

    def _on_prelogin_cancelled_for_session(self, session: TabSession) -> None:
        """Handle pre-login cancellation for a session."""
        # Keep pending_connection so R can retry
        pass

    def _refresh_hosts_list(self) -> None:
        """Refresh the hosts view."""
        self._hosts_view.refresh()

    @Slot()
    def _on_toggle_chat(self) -> None:
        """Toggle chat panel visibility."""
        self._chat_visible = not self._chat_visible
        self._apply_chat_visibility()

    @Slot()
    def _on_config_clicked(self) -> None:
        """Handle config button click - show settings dialog."""
        dialog = SettingsDialog(parent=self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self._apply_settings_changes()

    @Slot()
    def _on_quick_connect(self) -> None:
        """Handle quick connect button click."""
        session = self._get_active_session()

        # Check if active tab is already connected
        if session and session.is_connected:
            reply = QMessageBox.question(
                self,
                "Ja conectado",
                "Deseja desconectar da sessao atual?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            asyncio.ensure_future(self._disconnect_session_async(session))

        dialog = QuickConnectDialog(parent=self)
        if dialog.exec():
            data = dialog.get_connection_data()

            # Use unified connection method with active session
            self._initiate_connection_for_session(
                session=session,
                host=data["host"],
                port=data["port"],
                username=data["username"],
                password=data["password"],
                terminal_type=data["terminal_type"],
                device_type=data.get("device_type"),
                host_id=None  # Quick connect has no saved host ID
            )

    @Slot()
    def _on_add_host_clicked(self) -> None:
        """Handle add host button click."""
        dialog = HostDialog(self._data_manager, parent=self)
        if dialog.exec():
            self._refresh_hosts_list()

    def _initiate_connection_for_session(
        self,
        session: Optional[TabSession],
        host: str,
        port: int,
        username: str,
        password: str,
        terminal_type: str,
        device_type: Optional[str],
        host_id: Optional[str] = None,
        host_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        os_version: Optional[str] = None,
        functions: Optional[list] = None,
        groups: Optional[list] = None,
        tags: Optional[list] = None,
        notes: Optional[str] = None,
        port_knocking: Optional[list] = None
    ) -> None:
        """
        Unified connection method for both saved hosts and quick connect.

        Handles:
        - Checking if credentials need to be prompted via terminal
        - Setting up proactive terminal response for MikroTik
        - Starting pre-login mode or direct connection

        Args:
            session: The tab session to connect (uses active if None)
            host: Host address or IP
            port: SSH port
            username: Username (empty string triggers pre-login prompt)
            password: Password (empty string with username uses keyboard-interactive)
            terminal_type: Terminal type (xterm, xterm-256color, vt100)
            device_type: Device type for AI context (Linux, MikroTik, etc.)
            host_id: Host ID for saved hosts (None for quick connect)
            host_name: Display name for saved hosts
            manufacturer: Device manufacturer
            os_version: Operating system and version
            functions: Device functions/roles
            groups: Device groups
            tags: Device tags
            notes: Additional notes about the device
        """
        if session is None:
            session = self._get_active_session()
        if session is None or session.terminal is None:
            return

        cols, rows = session.terminal.get_terminal_size()

        session.host_id = host_id
        session.host_name = host_name
        session.device_type = device_type
        session.manufacturer = manufacturer
        session.os_version = os_version
        session.functions = functions
        session.groups = groups
        session.tags = tags
        session.notes = notes
        session.port_knocking = port_knocking

        # Check if we need to ask for credentials in terminal (like PuTTY)
        need_username = not username

        if need_username:
            # Store pending connection data and start pre-login mode
            session.pending_connection = {
                "host": host,
                "port": port,
                "terminal_type": terminal_type,
                "term_width": cols,
                "term_height": rows,
            }
            session.terminal.start_prelogin(need_username=True, need_password=True)
            self._show_terminal_view()
            return

        # Has username - connect directly (password via keyboard-interactive if needed)
        config = SSHConfig(
            host=host,
            port=port,
            username=username,
            password=password or "",
            terminal_type=terminal_type,
            term_width=cols,
            term_height=rows,
        )

        asyncio.ensure_future(self._connect_session_async(session, config))

    def _connect_to_host(self, host_id: str) -> None:
        """Connect to a saved host. Opens new tab if current is connected."""
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        session = self._get_active_session()

        # If current tab is connected, create a new tab for the new connection
        if session and session.is_connected:
            session = self._create_new_tab()

        if not session:
            session = self._create_new_tab()

        # Get saved password if available (may be None)
        password = self._data_manager.get_password(host_id)

        # Use unified connection method
        # get_effective_username() applies +ct suffix for MikroTik if configured (deprecated)
        self._initiate_connection_for_session(
            session=session,
            host=host.host,
            port=host.port,
            username=host.get_effective_username(),
            password=password or "",
            terminal_type=host.terminal_type,
            device_type=host.device_type,
            host_id=host_id,
            host_name=host.name,
            manufacturer=host.manufacturer,
            os_version=host.os_version,
            functions=host.functions,
            groups=host.groups,
            tags=host.tags,
            notes=host.notes,
            port_knocking=host.port_knocking
        )

    def _edit_host(self, host_id: str) -> None:
        """Edit a saved host."""
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        dialog = HostDialog(self._data_manager, host=host, parent=self)
        if dialog.exec():
            self._refresh_hosts_list()

    def _delete_host(self, host_id: str) -> None:
        """Delete a saved host."""
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        reply = QMessageBox.question(
            self,
            "Confirmar Exclusao",
            f"Tem certeza que deseja excluir o host '{host.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._data_manager.delete_host(host_id)
            self._refresh_hosts_list()

    def _create_agent_for_session(self, session: TabSession) -> None:
        """Create AI agent for a session's SSH connection."""
        if not session.ssh_session or not session.terminal:
            return

        async def execute_command(cmd: str) -> str:
            if session.ssh_session and session.ssh_session.is_connected:
                return await session.ssh_session.execute_command(cmd)
            raise RuntimeError("Not connected")

        def on_command_executed(cmd: str, output: str) -> None:
            def _normalize_for_terminal(text: str) -> str:
                # Convert lone LF or CR into CRLF so the terminal cursor resets to column 0.
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                return text.replace("\n", "\r\n")

            # Ensure injected command lines respect carriage return to avoid offsetting columns
            if session.terminal:
                session.terminal.append_output(f"\r\n$ {cmd}\r\n")
                session.terminal.append_output(_normalize_for_terminal(output))

        def on_thinking(status: str) -> None:
            self._chat.set_status(status)

        # Get connection info from config
        host_address = session.config.host if session.config else None
        host_port = session.config.port if session.config else None
        username = session.config.username if session.config else None

        session.agent = create_agent(
            execute_command=execute_command,
            on_command_executed=on_command_executed,
            on_thinking=on_thinking,
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

    def _create_disconnect_callback_for_session(self, session: TabSession):
        """Create a disconnect callback for a specific session."""
        def callback():
            self._unexpected_disconnect.emit(session.id)
        return callback

    async def _perform_port_knock(self, host: str, sequence: list) -> None:
        """Execute port knocking sequence (fire and forget)."""
        import socket
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

    def _launch_winbox(self, host_id: str) -> None:
        """Launch Winbox for the specified host."""
        # Check if Winbox path is configured
        winbox_path = self._data_manager.settings.winbox_path
        if not winbox_path:
            QMessageBox.warning(
                self, "Winbox",
                "Caminho do Winbox nao configurado.\n"
                "Configure em Configuracoes > Winbox."
            )
            return

        if not Path(winbox_path).exists():
            QMessageBox.warning(
                self, "Winbox",
                f"Executavel nao encontrado:\n{winbox_path}"
            )
            return

        # Get host data
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        # Winbox port (0 = use default 8291)
        winbox_port = host.winbox_port if host.winbox_port else 8291

        # Decrypt password
        password = self._data_manager.get_password(host_id)

        # Port knocking before opening Winbox
        if host.port_knocking:
            asyncio.create_task(self._perform_port_knock(host.host, host.port_knocking))
            # Small delay for port knocking to complete
            QTimer.singleShot(500, lambda: self._execute_winbox(
                winbox_path, host.host, winbox_port, host.username, password or ""
            ))
        else:
            self._execute_winbox(winbox_path, host.host, winbox_port, host.username, password or "")

    def _execute_winbox(self, winbox_path: str, host: str, port: int, user: str, password: str) -> None:
        """Execute Winbox with parameters."""
        # Format: winbox.exe ip:port user password
        args = [winbox_path, f"{host}:{port}", user, password]

        try:
            subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
            self._status_bar.showMessage(f"Winbox iniciado para {host}:{port}", 3000)
            logger.info(f"Winbox launched for {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to launch Winbox: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao iniciar Winbox:\n{e}")

    def _open_web_access(self, host_id: str) -> None:
        """Open web browser for the specified host."""
        # Get host data
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        # Build URL
        protocol = "https" if host.https_enabled else "http"
        port = host.http_port

        # Only add port to URL if not default
        if (protocol == "http" and port == 80) or (protocol == "https" and port == 443):
            url = f"{protocol}://{host.host}"
        else:
            url = f"{protocol}://{host.host}:{port}"

        # Port knocking before opening browser
        if host.port_knocking:
            asyncio.create_task(self._perform_port_knock(host.host, host.port_knocking))
            # Small delay for port knocking to complete
            QTimer.singleShot(500, lambda: self._execute_web_access(url))
        else:
            self._execute_web_access(url)

    def _execute_web_access(self, url: str) -> None:
        """Open URL in default browser."""
        try:
            webbrowser.open(url)
            self._status_bar.showMessage(f"Abrindo navegador: {url}", 3000)
            logger.info(f"Opened browser for {url}")
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao abrir navegador:\n{e}")

    async def _connect_session_async(self, session: TabSession, config: SSHConfig) -> None:
        """Async connection handler for a session."""
        if not session.terminal:
            return

        self._quick_connect_btn.setEnabled(False)
        session.connection_status = "connecting"
        self._update_tab_status(session)
        self._status_bar.showMessage(f"Conectando a {config.host}...")
        self._status_bar.setStyleSheet("background-color: #ca5010; color: white;")

        # Port knocking before SSH connection
        if session.port_knocking:
            await self._perform_port_knock(config.host, session.port_knocking)

        try:
            session.ssh_session = SSHSession(
                config,
                lambda data, s=session: self._on_ssh_output_for_session(s, data),
                self._create_disconnect_callback_for_session(session)
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

            self._create_agent_for_session(session)
            self._update_tab_status(session)
            self._restore_chat_for_session(session)
            self._update_ui_state()

        except asyncssh.PermissionDenied:
            # Authentication failed - ask for password again
            logger.warning(f"Authentication failed for {config.username}@{config.host}")
            session.ssh_session = None
            session.connection_status = "disconnected"
            self._update_tab_status(session)

            # Store connection data for retry (keep username)
            cols, rows = session.terminal.get_terminal_size()
            session.pending_connection = {
                "host": config.host,
                "port": config.port,
                "username": config.username,  # Keep the username
                "terminal_type": config.terminal_type,
                "term_width": cols,
                "term_height": rows,
            }

            # Show error and prompt for password again
            session.terminal.append_output("Access denied\r\n")
            session.terminal.start_prelogin(need_username=False, need_password=True)
            self._update_ui_state()

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            session.ssh_session = None
            session.pending_connection = None
            session.connection_status = "disconnected"
            self._update_tab_status(session)
            QMessageBox.critical(
                self,
                "Erro de Conexao",
                f"Falha ao conectar em {config.host}:\n{str(e)}"
            )
            self._update_ui_state()

    @Slot()
    def _on_disconnect_clicked(self) -> None:
        """Handle disconnect button click."""
        session = self._get_active_session()
        if session:
            session.config = None  # Clear config on manual disconnect
            asyncio.ensure_future(self._disconnect_session_async(session))

    @Slot(str)
    def _on_unexpected_disconnect(self, tab_id: str) -> None:
        """Handle unexpected disconnection from SSH session."""
        logger.info(f"Unexpected disconnect detected for tab {tab_id}")

        # Find session by ID
        session = self._sessions.get(tab_id)
        if not session:
            return

        # Clean up session state
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
        session.agent = None
        session.ssh_session = None
        session.connection_status = "disconnected"

        # Clear any pending output buffer
        self._output_timer.stop()
        session.output_buffer.clear()

        # Update tab status
        self._update_tab_status(session)

        # Show disconnected message in terminal
        if session.terminal:
            session.terminal.show_disconnected_message()
        self._update_ui_state()

    async def _disconnect_session_async(self, session: TabSession) -> None:
        """Async disconnection handler for a session."""
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            try:
                await self._agent_task
            except asyncio.CancelledError:
                pass
            self._agent_task = None

        if session.agent:
            await session.agent.close()
            session.agent = None

        if session.ssh_session:
            await session.ssh_session.disconnect()
            session.ssh_session = None

        session.connection_status = "disconnected"
        self._update_tab_status(session)
        self._update_ui_state()

    def _on_ssh_output_for_session(self, session: TabSession, data: str) -> None:
        """Handle output received from SSH session for a specific session."""
        # Use signal for thread-safe communication
        self._ssh_output_received.emit(session.id, data)

    @Slot(str, str)
    def _on_ssh_output_slot(self, tab_id: str, data: str) -> None:
        """Buffer SSH output and process in batches."""
        session = self._sessions.get(tab_id)
        if not session or not session.terminal:
            return

        # Ignore output if terminal is in disconnected mode
        if session.terminal._disconnected_mode:
            return

        session.output_buffer.append(data)
        # Start timer if not already running (10ms batching window)
        if not self._output_timer.isActive():
            self._output_timer.start(10)

    def _flush_output_buffer(self) -> None:
        """Flush buffered output to all terminals."""
        for session in self._sessions.values():
            if not session.output_buffer or not session.terminal:
                continue
            # Don't flush if terminal is in disconnected mode
            if session.terminal._disconnected_mode:
                session.output_buffer.clear()
                continue
            # Combine all buffered data
            combined = ''.join(session.output_buffer)
            session.output_buffer.clear()
            # Process combined data at once
            if combined:
                session.terminal.append_output(combined)

    @Slot(str)
    def _on_chat_message(self, message: str) -> None:
        """Handle message from chat widget."""
        session = self._get_active_session()
        if not session or not session.agent or not session.ssh_session:
            self._chat.add_message("Erro: Conecte-se a um host primeiro.", is_user=False)
            return

        self._chat.set_processing(True)
        self._agent_task = asyncio.ensure_future(self._process_chat_message(session, message))

    async def _process_chat_message(self, session: TabSession, message: str) -> None:
        """Process chat message with AI agent."""
        try:
            if session.agent:
                response = await session.agent.chat(message)
                self._chat.add_message(response, is_user=False)

                # Update session chat state with current display messages
                session.chat_state.display_messages = self._chat.get_display_messages()

                # Save to persistent storage (only for saved hosts)
                self._save_chat_to_conversation(session)

        except asyncio.CancelledError:
            self._chat.add_message("Operacao cancelada.", is_user=False)
        except Exception as e:
            logger.error(f"Agent error: {e}")
            self._chat.add_message(f"Erro: {str(e)}", is_user=False)
        finally:
            self._chat.set_processing(False)

    @Slot()
    def _on_stop_agent(self) -> None:
        """Handle stop button click in chat."""
        session = self._get_active_session()
        if session and session.agent:
            session.agent.cancel()
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()

    # === Chat conversation management ===

    def _restore_chat_for_session(self, session: TabSession) -> None:
        """Restore chat widget state for a session."""
        # Clear current chat messages
        self._chat.clear_messages()

        # Load conversations for this host (if saved host)
        if session.host_id:
            convs = self._data_manager.get_conversations_for_host(session.host_id)
            conv_list = [(c.id, c.title, c.updated_at) for c in convs]
            self._chat.set_conversations(conv_list)
            self._chat.set_current_conversation(session.chat_state.conversation_id)
        else:
            # Quick connect - no saved conversations
            self._chat.set_conversations([])
            self._chat.set_current_conversation(None)

        # Restore display messages from session state
        if session.chat_state.display_messages:
            self._chat.restore_messages(session.chat_state.display_messages)

        # Sync agent messages if continuing a conversation
        if session.agent and session.chat_state.conversation_id:
            conv = self._data_manager.get_conversation_by_id(session.chat_state.conversation_id)
            if conv and conv.messages:
                # Restore agent.messages from conversation
                session.agent.messages = [
                    {
                        "role": m.role,
                        "content": m.content,
                        **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                        **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {})
                    }
                    for m in conv.messages
                ]

    def _save_chat_to_conversation(self, session: TabSession) -> None:
        """Save current chat to persistent conversation."""
        # Only save for saved hosts (not quick connect)
        if not session.host_id or not session.agent:
            return

        # Convert agent messages to ChatMessage objects
        chat_messages = []
        for msg in session.agent.messages:
            chat_messages.append(ChatMessage(
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id")
            ))

        if not chat_messages:
            return

        if session.chat_state.conversation_id:
            # Update existing conversation
            self._data_manager.update_conversation(
                session.chat_state.conversation_id,
                chat_messages
            )
        else:
            # Create new conversation
            conv = self._data_manager.create_conversation(session.host_id)
            session.chat_state.conversation_id = conv.id
            self._data_manager.update_conversation(conv.id, chat_messages)

        # Refresh conversation list in UI
        convs = self._data_manager.get_conversations_for_host(session.host_id)
        conv_list = [(c.id, c.title, c.updated_at) for c in convs]
        self._chat.set_conversations(conv_list)
        self._chat.set_current_conversation(session.chat_state.conversation_id)

    @Slot(str)
    def _on_conversation_changed(self, conv_id: str) -> None:
        """Handle conversation selection from dropdown."""
        session = self._get_active_session()
        if not session:
            return

        # Save current state first
        if session.chat_state.conversation_id and session.agent:
            self._save_chat_to_conversation(session)

        # Clear chat
        self._chat.clear_messages()

        if conv_id:
            # Load existing conversation
            conv = self._data_manager.get_conversation_by_id(conv_id)
            if conv:
                session.chat_state.conversation_id = conv_id

                # Restore display messages (only user and assistant with content)
                display_msgs = []
                for msg in conv.messages:
                    if msg.role == "user":
                        display_msgs.append((msg.content, True))
                    elif msg.role == "assistant" and msg.content:
                        display_msgs.append((msg.content, False))

                session.chat_state.display_messages = display_msgs
                self._chat.restore_messages(display_msgs)

                # Restore agent messages
                if session.agent:
                    session.agent.messages = [
                        {
                            "role": m.role,
                            "content": m.content,
                            **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                            **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {})
                        }
                        for m in conv.messages
                    ]
        else:
            # New conversation
            session.chat_state.clear()
            if session.agent:
                session.agent.reset()

    @Slot()
    def _on_new_conversation(self) -> None:
        """Handle new conversation request."""
        session = self._get_active_session()
        if not session:
            return

        # Save current conversation first (if exists)
        if session.chat_state.conversation_id and session.agent:
            self._save_chat_to_conversation(session)

        # Clear state
        session.chat_state.clear()
        self._chat.clear_messages()
        self._chat.set_current_conversation(None)

        if session.agent:
            session.agent.reset()

    def resizeEvent(self, event) -> None:
        """Handle window resize."""
        super().resizeEvent(event)
        if self._resize_timer:
            self._resize_timer.start(200)

    @Slot()
    def _on_resize_timeout(self) -> None:
        """Handle resize timeout - update active terminal size."""
        session = self._get_active_session()
        if session and session.ssh_session and session.ssh_session.is_connected and session.terminal:
            cols, rows = session.terminal.get_terminal_size()
            asyncio.ensure_future(
                session.ssh_session.resize_terminal(cols, rows)
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close - disconnect all sessions."""
        # Check if any session is connected
        connected_sessions = [s for s in self._sessions.values() if s.is_connected]
        if connected_sessions:
            # Disconnect all sessions
            async def disconnect_all():
                for session in connected_sessions:
                    await self._disconnect_session_async(session)
            asyncio.ensure_future(disconnect_all())
            QTimer.singleShot(100, self.close)
            event.ignore()
        else:
            event.accept()
