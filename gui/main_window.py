"""
Main Window for RB Terminal.
Contains collapsible hosts sidebar, terminal widget with tabs, and AI chat panel.

Refactored to use managers for better separation of concerns:
- SessionManager: Tab and session management
- ConnectionManager: SSH connection handling
- ChatCoordinator: Chat and conversation management
- SFTPCoordinator: File browser and directory sync
- LayoutManager: Splitter and panel layout
"""

import asyncio
import logging
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QStatusBar, QSplitter, QMenu, QFrame, QToolBar, QSizePolicy,
    QLineEdit, QDialog, QTabWidget, QToolButton, QStackedWidget, QFileDialog
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSize, QStandardPaths
from PySide6.QtGui import QCloseEvent, QAction, QIcon

from core.ssh_session import SSHSession, SSHConfig
from core.agent import UsageStats
from core.data_manager import get_data_manager, DataManager
from gui.terminal_widget import TerminalWidget
from gui.chat_widget import ChatWidget
from gui.file_browser import FileBrowser
from gui.hosts_dialog import HostDialog, PasswordPromptDialog, QuickConnectDialog
from gui.settings_dialog import SettingsDialog
from gui.tab_session import TabSession
from gui.hosts_view import HostsView
from gui.setup_dialog import SetupDialog
from gui.unlock_dialog import UnlockDialog
from gui.about_dialog import AboutDialog
from core.resources import get_resource_path

# Import managers
from gui.managers.session_manager import SessionManager
from gui.managers.connection_manager import ConnectionManager
from gui.managers.chat_coordinator import ChatCoordinator
from gui.managers.sftp_coordinator import SFTPCoordinator
from gui.managers.layout_manager import LayoutManager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with hosts view, terminal tabs, and chat."""

    # Signal for thread-safe SSH output handling (includes tab_id)
    _ssh_output_received = Signal(str, str)  # tab_id, data
    # Signal for unexpected disconnection (includes tab_id)
    _unexpected_disconnect = Signal(str)  # tab_id

    def __init__(self):
        super().__init__()

        # Set window icon
        logo_path = get_resource_path("logo.ico")
        self.setWindowIcon(QIcon(str(logo_path)))

        self._resize_timer: Optional[QTimer] = None

        # Initialize data manager and handle setup/unlock
        self._data_manager = get_data_manager()
        if not self._handle_startup():
            # User cancelled setup/unlock - exit
            import sys
            sys.exit(0)

        # Output timer for batching SSH output
        self._output_timer = QTimer()
        self._output_timer.setSingleShot(True)
        self._output_timer.timeout.connect(self._flush_output_buffer)

        self._setup_ui()
        self._setup_managers()
        self._setup_connections()

        # Create first empty tab
        self._session_manager.create_session()

        self._update_ui_state()
        self._refresh_hosts_list()

        # Start maximized
        self.showMaximized()

    def _handle_startup(self) -> bool:
        """Handle application startup - setup or unlock as needed."""
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

        # Case 3: Has master password but no cached session
        elif dm.needs_unlock():
            error_msg = None
            while True:
                dialog = UnlockDialog(self, error_message=error_msg)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return False

                if dm.unlock(dialog.get_password()):
                    break
                error_msg = "Senha incorreta. Tente novamente."

        # Load data
        dm.load()
        return True

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

        # Toolbar
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Stacked widget for hosts view and terminal view
        self._stacked_widget = QStackedWidget()
        main_layout.addWidget(self._stacked_widget)

        # Page 0: Hosts view
        self._hosts_view = HostsView(self._data_manager)
        self._hosts_view.connect_requested.connect(self._connect_to_host)
        self._hosts_view.edit_requested.connect(self._edit_host)
        self._hosts_view.delete_requested.connect(self._delete_host)
        self._hosts_view.winbox_requested.connect(self._launch_winbox)
        self._hosts_view.web_access_requested.connect(self._open_web_access)
        self._hosts_view.add_requested.connect(self._on_add_host_clicked)
        self._hosts_view.quick_connect_requested.connect(self._on_quick_connect)
        self._stacked_widget.addWidget(self._hosts_view)

        # Page 1: Terminal area
        self._terminal_area = QWidget()
        terminal_layout = QVBoxLayout(self._terminal_area)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)
        self._content_layout = terminal_layout

        # Tab widget for terminals
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(False)
        self._tab_widget.setMovable(True)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setStyleSheet("""
            QTabWidget::pane { border: none; background-color: #1e1e1e; }
            QTabBar::tab {
                background-color: #2d2d2d; color: #969696;
                padding: 8px 16px; margin-right: 2px;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background-color: #1e1e1e; color: #ffffff; }
            QTabBar::tab:hover:!selected { background-color: #3c3c3c; }
        """)

        # Chat panel
        self._chat_panel = QFrame()
        self._chat_panel.setStyleSheet("background-color: #252526; border-top: 1px solid #3c3c3c;")
        chat_layout = QVBoxLayout(self._chat_panel)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)
        self._chat = ChatWidget()
        chat_layout.addWidget(self._chat)

        # SFTP panel
        self._sftp_panel = QFrame()
        self._sftp_panel.setStyleSheet("background-color: #252526; border-right: 1px solid #3c3c3c;")
        sftp_layout = QVBoxLayout(self._sftp_panel)
        sftp_layout.setContentsMargins(0, 0, 0, 0)
        sftp_layout.setSpacing(0)
        self._sftp_browser = FileBrowser()
        sftp_layout.addWidget(self._sftp_browser)

        self._stacked_widget.addWidget(self._terminal_area)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Desconectado")

        # Apply dark theme
        self._apply_dark_theme()

    def _setup_managers(self) -> None:
        """Initialize and configure managers."""
        # Session Manager
        self._session_manager = SessionManager(self._tab_widget, self)
        self._session_manager.set_terminal_callbacks(
            on_input=self._on_terminal_input_for_session,
            on_reconnect=self._on_reconnect_for_session,
            on_prelogin_credentials=self._on_prelogin_credentials_for_session,
            on_prelogin_cancelled=self._on_prelogin_cancelled_for_session
        )
        self._session_manager.tab_changed.connect(self._on_tab_changed)

        # Connection Manager
        self._connection_manager = ConnectionManager(self)
        self._connection_manager.set_callbacks(
            on_ssh_output=self._on_ssh_output_for_session,
            on_unexpected_disconnect=lambda sid: self._unexpected_disconnect.emit(sid)
        )

        # Chat Coordinator
        self._chat_coordinator = ChatCoordinator(self._chat, self._data_manager, self)

        # SFTP Coordinator
        self._sftp_coordinator = SFTPCoordinator(self._sftp_browser, self)
        self._sftp_browser.download_requested.connect(self._on_sftp_download_requested)
        self._sftp_browser.upload_requested.connect(self._on_sftp_upload_requested)
        self._sftp_browser.status_message.connect(lambda msg: self._status_bar.showMessage(msg, 3000))
        self._sftp_browser.directory_changed.connect(self._on_sftp_directory_changed)

        # Layout Manager
        self._layout_manager = LayoutManager(
            self._content_layout,
            self._tab_widget,
            self._chat_panel,
            self._sftp_panel,
            self
        )
        self._layout_manager.chat_position = self._data_manager.get_chat_position()
        self._layout_manager.sftp_position = self._data_manager.get_sftp_position()
        self._layout_manager.rebuild_splitters()

    def _create_toolbar(self) -> QToolBar:
        """Create the main toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #252526; border: none;
                border-bottom: 1px solid #3c3c3c; padding: 4px; spacing: 4px;
            }
            QToolButton {
                background-color: transparent; border: none; border-radius: 4px;
                padding: 6px 12px; color: #dcdcdc; font-size: 12px;
            }
            QToolButton:hover { background-color: #3c3c3c; }
            QToolButton:pressed, QToolButton:checked { background-color: #094771; }
        """)

        # Hosts button
        self._hosts_btn = QAction("Hosts", self)
        self._hosts_btn.setToolTip("Voltar para lista de hosts (Ctrl+H)")
        self._hosts_btn.setShortcut("Ctrl+H")
        self._hosts_btn.triggered.connect(self._show_hosts_view)
        toolbar.addAction(self._hosts_btn)

        toolbar.addSeparator()

        # Toggle chat button
        self._toggle_chat_btn = QAction("Chat IA", self)
        self._toggle_chat_btn.setCheckable(True)
        self._toggle_chat_btn.setChecked(False)
        self._toggle_chat_btn.setToolTip("Mostrar/Esconder chat IA (Ctrl+I)")
        self._toggle_chat_btn.setShortcut("Ctrl+I")
        self._toggle_chat_btn.triggered.connect(self._on_toggle_chat)
        toolbar.addAction(self._toggle_chat_btn)

        # Toggle SFTP button
        self._toggle_sftp_btn = QAction("Arquivos", self)
        self._toggle_sftp_btn.setCheckable(True)
        self._toggle_sftp_btn.setChecked(False)
        self._toggle_sftp_btn.setToolTip("Mostrar/Esconder navegador de arquivos (Ctrl+E)")
        self._toggle_sftp_btn.setShortcut("Ctrl+E")
        self._toggle_sftp_btn.triggered.connect(self._on_toggle_sftp)
        toolbar.addAction(self._toggle_sftp_btn)

        # Terminal button
        self._terminal_btn = QAction("Terminal", self)
        self._terminal_btn.setToolTip("Voltar para terminal")
        self._terminal_btn.triggered.connect(self._show_terminal_view)
        self._terminal_btn.setVisible(False)
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

        # Config button
        self._config_btn = QAction("Config", self)
        self._config_btn.setToolTip("Configuracoes do aplicativo")
        self._config_btn.triggered.connect(self._on_config_clicked)
        toolbar.addAction(self._config_btn)

        # About button
        self._about_btn = QAction("Sobre", self)
        self._about_btn.setToolTip("Sobre o RB Terminal")
        self._about_btn.triggered.connect(self._on_about_clicked)
        toolbar.addAction(self._about_btn)

        # Set toggle buttons in layout manager after creation
        if hasattr(self, '_layout_manager'):
            self._layout_manager.set_toggle_buttons(self._toggle_chat_btn, self._toggle_sftp_btn)

        return toolbar

    def _apply_dark_theme(self) -> None:
        """Apply dark theme to the window."""
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QWidget { background-color: #1e1e1e; color: #dcdcdc; }
            QGroupBox {
                background-color: #252526; border: 1px solid #3c3c3c;
                border-radius: 4px; margin-top: 8px; padding: 12px; padding-top: 24px;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #dcdcdc; }
            QLineEdit, QSpinBox {
                background-color: #3c3c3c; border: 1px solid #555555;
                border-radius: 3px; padding: 4px 8px; color: #dcdcdc;
            }
            QLineEdit:focus, QSpinBox:focus { border: 1px solid #007acc; }
            QPushButton {
                background-color: #0e639c; border: none; border-radius: 3px;
                padding: 6px 12px; color: white;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #0d5a8c; }
            QPushButton:disabled { background-color: #555555; color: #888888; }
            QStatusBar { background-color: #007acc; color: white; }
            QSplitter::handle { background-color: #3c3c3c; height: 3px; }
            QSplitter::handle:hover { background-color: #007acc; }
            QMenu {
                background-color: #3c3c3c; border: 1px solid #555555;
                border-radius: 4px; padding: 4px;
            }
            QMenu::item { padding: 6px 24px; border-radius: 2px; }
            QMenu::item:selected { background-color: #094771; }
        """)

    def _setup_connections(self) -> None:
        """Connect signals to slots."""
        # SSH output signal
        self._ssh_output_received.connect(self._on_ssh_output_slot, Qt.ConnectionType.AutoConnection)

        # Unexpected disconnect signal
        self._unexpected_disconnect.connect(self._on_unexpected_disconnect, Qt.ConnectionType.AutoConnection)

        # Chat signals
        self._chat.message_sent.connect(self._on_chat_message)
        self._chat.stop_requested.connect(self._on_stop_agent)
        self._chat.conversation_changed.connect(self._on_conversation_changed)
        self._chat.new_conversation_requested.connect(self._on_new_conversation)

        # Setup resize timer
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_timeout)

        # Keyboard shortcuts
        new_tab_action = QAction("Nova Aba", self)
        new_tab_action.setShortcut("Ctrl+T")
        new_tab_action.triggered.connect(lambda: self._session_manager.create_session())
        self.addAction(new_tab_action)

        close_tab_action = QAction("Fechar Aba", self)
        close_tab_action.setShortcut("Ctrl+W")
        close_tab_action.triggered.connect(self._on_close_current_tab)
        self.addAction(close_tab_action)

        next_tab_action = QAction("Proxima Aba", self)
        next_tab_action.setShortcut("Ctrl+Right")
        next_tab_action.triggered.connect(self._session_manager.next_tab)
        self.addAction(next_tab_action)

        prev_tab_action = QAction("Aba Anterior", self)
        prev_tab_action.setShortcut("Ctrl+Left")
        prev_tab_action.triggered.connect(self._session_manager.prev_tab)
        self.addAction(prev_tab_action)

        # Set toggle buttons in layout manager
        self._layout_manager.set_toggle_buttons(self._toggle_chat_btn, self._toggle_sftp_btn)

    # === Session and Connection Handlers ===

    def _on_terminal_input_for_session(self, session: TabSession, data: str) -> None:
        """Handle input from a specific terminal session."""
        if not session.ssh_session:
            return

        if session.ssh_session.waiting_for_auth:
            session.ssh_session.provide_auth_input(data)
            return

        if session.ssh_session.is_connected:
            asyncio.ensure_future(session.ssh_session.send_input(data))
            self._sftp_coordinator.track_terminal_input(session, data)

    def _on_reconnect_for_session(self, session: TabSession) -> None:
        """Handle reconnect request for a specific session."""
        if session.pending_connection:
            if session.terminal:
                cols, rows = session.terminal.get_terminal_size()
                session.pending_connection["term_width"] = cols
                session.pending_connection["term_height"] = rows

            has_username = bool(session.pending_connection.get("username"))
            if session.terminal:
                session.terminal.start_prelogin(need_username=not has_username, need_password=True)
            return

        if session.config:
            if session.terminal:
                cols, rows = session.terminal.get_terminal_size()
                session.config.term_width = cols
                session.config.term_height = rows
            asyncio.ensure_future(self._connect_session_async(session, session.config))

    def _on_prelogin_credentials_for_session(self, session: TabSession, username: str, password: str) -> None:
        """Handle credentials from terminal pre-login mode."""
        if not session.pending_connection:
            return

        final_username = session.pending_connection.get("username") or username

        if not final_username:
            session.pending_connection = None
            if session.terminal:
                session.terminal.clear()
            return

        config = SSHConfig(
            host=session.pending_connection["host"],
            port=session.pending_connection["port"],
            username=final_username,
            password=password,
            terminal_type=session.pending_connection["terminal_type"],
            term_width=session.pending_connection["term_width"],
            term_height=session.pending_connection["term_height"],
        )

        asyncio.ensure_future(self._connect_session_async(session, config))

    def _on_prelogin_cancelled_for_session(self, session: TabSession) -> None:
        """Handle pre-login cancellation."""
        pass  # Keep pending_connection for R retry

    def _on_tab_changed(self, session: TabSession) -> None:
        """Handle tab change."""
        self._update_ui_state()

        if session:
            self._chat_coordinator.restore_chat_for_session(session)
            if session.terminal:
                session.terminal.set_focus()

            if self._layout_manager.sftp_visible:
                if session.is_connected and session.ssh_session:
                    asyncio.ensure_future(self._sftp_coordinator.connect_for_session(session))
                else:
                    asyncio.ensure_future(self._sftp_coordinator.disconnect())

    @Slot()
    def _on_close_current_tab(self) -> None:
        """Handle Ctrl+W - close current tab."""
        index = self._tab_widget.currentIndex()
        if index >= 0:
            self._session_manager._on_tab_close_requested(index)

    # === SSH Connection ===

    async def _connect_session_async(self, session: TabSession, config: SSHConfig) -> None:
        """Async connection handler for a session."""
        if not session.terminal:
            return

        self._quick_connect_btn.setEnabled(False)
        session.connection_status = "connecting"
        self._session_manager.update_tab_status(session)
        self._status_bar.showMessage(f"Conectando a {config.host}...")
        self._status_bar.setStyleSheet("background-color: #ca5010; color: white;")

        # Port knocking
        if session.port_knocking:
            await self._connection_manager.perform_port_knock(config.host, session.port_knocking)

        success = await self._connection_manager.connect(session, config)

        if success:
            self._connection_manager.create_agent_for_session(
                session,
                on_thinking=lambda status: self._chat.set_status(status),
                on_usage_update=lambda stats: self._chat.update_cost(
                    stats.total_cost, stats.prompt_tokens, stats.completion_tokens
                )
            )
            self._session_manager.update_tab_status(session)
            self._chat_coordinator.restore_chat_for_session(session)
            self._update_ui_state()
        else:
            self._session_manager.update_tab_status(session)
            if session.connection_status == "disconnected" and not session.pending_connection:
                # Connection failed completely
                QMessageBox.critical(
                    self,
                    "Erro de Conexao",
                    f"Falha ao conectar em {config.host}"
                )
            self._update_ui_state()

    async def _close_tab_async(self, session: TabSession, index: int) -> None:
        """Close tab with async disconnect."""
        await self._connection_manager.disconnect(session, self._chat_coordinator.agent_task)
        self._session_manager.remove_session(session, index)
        self._update_ui_state()

    async def _disconnect_session_async(self, session: TabSession) -> None:
        """Async disconnection handler."""
        active_session = self._session_manager.get_active_session()

        await self._connection_manager.disconnect(session, self._chat_coordinator.agent_task)

        if active_session and active_session.id == session.id:
            await self._sftp_coordinator.disconnect()

        self._session_manager.update_tab_status(session)
        self._update_ui_state()

    # === SSH Output Handling ===

    def _on_ssh_output_for_session(self, session: TabSession, data: str) -> None:
        """Handle output received from SSH session."""
        self._ssh_output_received.emit(session.id, data)

    @Slot(str, str)
    def _on_ssh_output_slot(self, tab_id: str, data: str) -> None:
        """Buffer SSH output and process in batches."""
        session = self._session_manager.get_session(tab_id)
        if not session or not session.terminal:
            return

        if session.terminal._disconnected_mode:
            return

        session.output_buffer.append(data)
        if not self._output_timer.isActive():
            self._output_timer.start(10)

    def _flush_output_buffer(self) -> None:
        """Flush buffered output to all terminals."""
        for session in self._session_manager.sessions.values():
            if not session.output_buffer or not session.terminal:
                continue
            if session.terminal._disconnected_mode:
                session.output_buffer.clear()
                continue
            combined = ''.join(session.output_buffer)
            session.output_buffer.clear()
            if combined:
                session.terminal.append_output(combined)

    @Slot(str)
    def _on_unexpected_disconnect(self, tab_id: str) -> None:
        """Handle unexpected disconnection from SSH session."""
        session = self._session_manager.get_session(tab_id)
        if not session:
            return

        self._connection_manager.handle_unexpected_disconnect(session, self._chat_coordinator.agent_task)

        self._output_timer.stop()
        self._session_manager.update_tab_status(session)

        active_session = self._session_manager.get_active_session()
        if active_session and active_session.id == tab_id:
            asyncio.ensure_future(self._sftp_coordinator.disconnect())

        self._update_ui_state()

    # === Chat Handlers ===

    @Slot(str, bool)
    def _on_chat_message(self, message: str, web_search: bool = False) -> None:
        """Handle message from chat widget."""
        session = self._session_manager.get_active_session()
        self._chat_coordinator.start_message_processing(session, message, web_search)

    @Slot()
    def _on_stop_agent(self) -> None:
        """Handle stop button click in chat."""
        session = self._session_manager.get_active_session()
        self._chat_coordinator.stop_agent(session)

    @Slot(str)
    def _on_conversation_changed(self, conv_id: str) -> None:
        """Handle conversation selection from dropdown."""
        session = self._session_manager.get_active_session()
        self._chat_coordinator.on_conversation_changed(session, conv_id)

    @Slot()
    def _on_new_conversation(self) -> None:
        """Handle new conversation request."""
        session = self._session_manager.get_active_session()
        self._chat_coordinator.on_new_conversation(session)

    # === SFTP Handlers ===

    @Slot(list)
    def _on_sftp_download_requested(self, files) -> None:
        """Handle download request from SFTP browser."""
        if not files:
            return

        downloads_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        dest_dir = QFileDialog.getExistingDirectory(self, "Selecionar pasta de destino", downloads_dir)

        if not dest_dir:
            return

        asyncio.ensure_future(self._download_files_async(files, dest_dir))

    async def _download_files_async(self, files, dest_dir: str) -> None:
        """Download files to local directory."""
        downloaded = await self._sftp_coordinator.download_files(
            files, dest_dir,
            progress_callback=lambda msg: self._status_bar.showMessage(msg)
        )
        if downloaded > 0:
            self._status_bar.showMessage(f"{downloaded} arquivo(s) baixado(s)", 3000)

    @Slot(list, str)
    def _on_sftp_upload_requested(self, local_files: list, remote_dir: str) -> None:
        """Handle upload request from SFTP browser."""
        asyncio.ensure_future(self._upload_files_async(local_files, remote_dir))

    async def _upload_files_async(self, local_files: list, remote_dir: str) -> None:
        """Upload files to remote directory."""
        uploaded = await self._sftp_coordinator.upload_files(
            local_files, remote_dir,
            progress_callback=lambda msg: self._status_bar.showMessage(msg)
        )
        if uploaded > 0:
            self._status_bar.showMessage(f"{uploaded} arquivo(s) enviado(s)", 3000)

    @Slot(str)
    def _on_sftp_directory_changed(self, path: str) -> None:
        """Handle SFTP directory change."""
        session = self._session_manager.get_active_session()
        if session:
            session._current_cwd = path

    # === UI State and Navigation ===

    def _update_ui_state(self) -> None:
        """Update UI based on active tab connection state."""
        session = self._session_manager.get_active_session()
        connected = session is not None and session.is_connected

        self._quick_connect_btn.setEnabled(not connected)
        self._chat.set_enabled_state(connected)

        any_connected = self._session_manager.has_connected_sessions()
        self._terminal_btn.setVisible(any_connected)

        if connected and session and session.config:
            host = session.config.host
            self._status_bar.showMessage(f"Conectado a {host}")
            self._status_bar.setStyleSheet("background-color: #107c10; color: white;")
            self._show_terminal_view()
        else:
            self._status_bar.showMessage("Desconectado")
            self._status_bar.setStyleSheet("background-color: #007acc; color: white;")
            if not any_connected:
                self._show_hosts_view()

    def _show_hosts_view(self) -> None:
        """Show the hosts view."""
        self._stacked_widget.setCurrentIndex(0)
        self._hosts_view.refresh()

    def _show_terminal_view(self) -> None:
        """Show the terminal view."""
        self._stacked_widget.setCurrentIndex(1)

    def _refresh_hosts_list(self) -> None:
        """Refresh the hosts view."""
        self._hosts_view.refresh()

    # === Toggle Handlers ===

    @Slot()
    def _on_toggle_chat(self) -> None:
        """Toggle chat panel visibility."""
        visible = self._layout_manager.toggle_chat()
        if visible:
            self._chat.focus_input()

    @Slot()
    def _on_toggle_sftp(self) -> None:
        """Toggle SFTP panel visibility."""
        visible = self._layout_manager.toggle_sftp()
        self._sftp_coordinator.visible = visible

        if visible:
            session = self._session_manager.get_active_session()
            if session and session.is_connected and session.ssh_session:
                asyncio.ensure_future(self._sftp_coordinator.connect_for_session(session))

    # === Host Operations ===

    def _connect_to_host(self, host_id: str, specific_ip: str = "") -> None:
        """Connect to a saved host."""
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        session = self._session_manager.get_active_session()

        if session and session.is_connected:
            session = self._session_manager.create_session()

        if not session:
            session = self._session_manager.create_session()

        password = self._data_manager.get_password(host_id)
        target_ip = specific_ip if specific_ip else host.host

        session.fallback_hosts = host.hosts if not specific_ip and len(host.hosts) > 1 else []
        session.current_host_index = 0

        self._initiate_connection_for_session(
            session=session,
            host=target_ip,
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
        """Unified connection method."""
        if session is None:
            session = self._session_manager.get_active_session()
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

        need_username = not username

        if need_username:
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

    # === External App Launchers ===

    def _launch_winbox(self, host_id: str, specific_ip: str = "") -> None:
        """Launch Winbox for the specified host."""
        winbox_path = self._data_manager.settings.winbox_path
        if not winbox_path:
            QMessageBox.warning(self, "Winbox", "Caminho do Winbox nao configurado.\nConfigure em Configuracoes > Winbox.")
            return

        if not Path(winbox_path).exists():
            QMessageBox.warning(self, "Winbox", f"Executavel nao encontrado:\n{winbox_path}")
            return

        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        target_ip = specific_ip if specific_ip else host.host
        winbox_port = host.winbox_port if host.winbox_port else 8291
        password = self._data_manager.get_password(host_id)

        if host.port_knocking:
            asyncio.create_task(self._connection_manager.perform_port_knock(target_ip, host.port_knocking))
            QTimer.singleShot(500, lambda: self._execute_winbox(
                winbox_path, target_ip, winbox_port, host.username, password or ""
            ))
        else:
            self._execute_winbox(winbox_path, target_ip, winbox_port, host.username, password or "")

    def _format_host_port(self, host: str, port: int) -> str:
        """Format host:port, handling IPv6 addresses."""
        if ':' in host and not host.startswith('['):
            return f"[{host}]:{port}"
        return f"{host}:{port}"

    def _execute_winbox(self, winbox_path: str, host: str, port: int, user: str, password: str) -> None:
        """Execute Winbox with parameters."""
        host_port = self._format_host_port(host, port)
        args = [winbox_path, host_port, user, password]

        try:
            subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
            self._status_bar.showMessage(f"Winbox iniciado para {host_port}", 3000)
        except Exception as e:
            logger.error(f"Failed to launch Winbox: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao iniciar Winbox:\n{e}")

    def _open_web_access(self, host_id: str, specific_ip: str = "") -> None:
        """Open web browser for the specified host."""
        host = self._data_manager.get_host_by_id(host_id)
        if not host:
            return

        target_ip = specific_ip if specific_ip else host.host

        protocol = "https" if host.https_enabled else "http"
        port = host.http_port

        if ':' in target_ip and not target_ip.startswith('['):
            formatted_host = f"[{target_ip}]"
        else:
            formatted_host = target_ip

        if (protocol == "http" and port == 80) or (protocol == "https" and port == 443):
            url = f"{protocol}://{formatted_host}"
        else:
            url = f"{protocol}://{formatted_host}:{port}"

        web_password = self._data_manager.get_web_password(host)
        should_autologin = (
            host.manufacturer in ["MikroTik", "Zabbix", "Proxmox"] and
            host.web_username and
            web_password
        )

        if host.port_knocking:
            asyncio.create_task(self._connection_manager.perform_port_knock(target_ip, host.port_knocking))
            QTimer.singleShot(500, lambda: self._execute_web_access(url, host, should_autologin, web_password))
        else:
            self._execute_web_access(url, host, should_autologin, web_password)

    def _execute_web_access(self, url: str, host=None, should_autologin: bool = False, web_password: str = None) -> None:
        """Open URL in default browser, with optional auto-login."""
        try:
            if should_autologin and host and web_password:
                self._status_bar.showMessage(f"Auto-login em {host.manufacturer}...", 5000)
                try:
                    from core.web_autologin import autologin_mikrotik, autologin_zabbix, autologin_proxmox

                    if host.manufacturer == "MikroTik":
                        autologin_mikrotik(url, host.web_username, web_password)
                    elif host.manufacturer == "Zabbix":
                        autologin_zabbix(url, host.web_username, web_password)
                    elif host.manufacturer == "Proxmox":
                        autologin_proxmox(url, host.web_username, web_password)

                    self._status_bar.showMessage(f"Auto-login concluído: {url}", 3000)
                    return

                except ImportError as e:
                    logger.warning(f"Selenium not installed: {e}")
                    self._status_bar.showMessage("Selenium não instalado, abrindo navegador normal", 3000)
                except Exception as e:
                    logger.error(f"Auto-login failed: {e}")
                    QMessageBox.warning(self, "Aviso", f"Erro no auto-login:\n{e}")

            webbrowser.open(url)
            self._status_bar.showMessage(f"Abrindo navegador: {url}", 3000)

        except Exception as e:
            logger.error(f"Failed to open browser: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao abrir navegador:\n{e}")

    # === Dialog Handlers ===

    @Slot()
    def _on_config_clicked(self) -> None:
        """Handle config button click."""
        dialog = SettingsDialog(parent=self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            new_chat_pos = self._data_manager.get_chat_position()
            new_sftp_pos = self._data_manager.get_sftp_position()
            self._layout_manager.apply_settings_changes(new_chat_pos, new_sftp_pos)

    def _on_about_clicked(self) -> None:
        """Handle about button click."""
        dialog = AboutDialog(parent=self)
        dialog.exec()

    @Slot()
    def _on_quick_connect(self) -> None:
        """Handle quick connect button click."""
        session = self._session_manager.get_active_session()

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

            self._initiate_connection_for_session(
                session=session,
                host=data["host"],
                port=data["port"],
                username=data["username"],
                password=data["password"],
                terminal_type=data["terminal_type"],
                device_type=data.get("device_type"),
                host_id=None
            )

    @Slot()
    def _on_add_host_clicked(self) -> None:
        """Handle add host button click."""
        dialog = HostDialog(self._data_manager, parent=self)
        if dialog.exec():
            self._refresh_hosts_list()

    # === Window Events ===

    def resizeEvent(self, event) -> None:
        """Handle window resize."""
        super().resizeEvent(event)
        if self._resize_timer:
            self._resize_timer.start(200)

    @Slot()
    def _on_resize_timeout(self) -> None:
        """Handle resize timeout."""
        session = self._session_manager.get_active_session()
        if session and session.ssh_session and session.ssh_session.is_connected and session.terminal:
            cols, rows = session.terminal.get_terminal_size()
            asyncio.ensure_future(session.ssh_session.resize_terminal(cols, rows))

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close."""
        connected_sessions = self._session_manager.get_connected_sessions()
        if connected_sessions:
            async def disconnect_all():
                for session in connected_sessions:
                    await self._disconnect_session_async(session)
            asyncio.ensure_future(disconnect_all())
            QTimer.singleShot(100, self.close)
            event.ignore()
        else:
            event.accept()
