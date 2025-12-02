"""
Main Window for SSH AI Terminal.
Contains collapsible hosts sidebar, terminal widget, and bottom AI chat panel.
"""

import asyncio
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QStatusBar, QSplitter, QListWidget, QListWidgetItem,
    QMenu, QFrame, QToolBar, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QPropertyAnimation, QEasingCurve, Property, QSize, QMetaObject, Q_ARG
from PySide6.QtGui import QCloseEvent, QAction

from core.ssh_session import SSHSession, SSHConfig
from core.agent import create_agent, SSHAgent
from core.hosts import HostsManager
from gui.terminal_widget import TerminalWidget
from gui.chat_widget import ChatWidget
from gui.hosts_dialog import HostDialog, PasswordPromptDialog, QuickConnectDialog

logger = logging.getLogger(__name__)


class CollapsibleSidebar(QFrame):
    """Collapsible sidebar widget with animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded_width = 250
        self._collapsed_width = 0
        self._is_expanded = True
        self._animation: Optional[QPropertyAnimation] = None

        self.setMinimumWidth(0)
        self.setMaximumWidth(self._expanded_width)

    def get_sidebar_width(self) -> int:
        return self.maximumWidth()

    def set_sidebar_width(self, width: int) -> None:
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)

    sidebar_width = Property(int, get_sidebar_width, set_sidebar_width)

    def toggle(self) -> None:
        """Toggle sidebar visibility with animation."""
        self._is_expanded = not self._is_expanded
        self._animate_to(self._expanded_width if self._is_expanded else self._collapsed_width)

    def expand(self) -> None:
        """Expand the sidebar."""
        if not self._is_expanded:
            self._is_expanded = True
            self._animate_to(self._expanded_width)

    def collapse(self) -> None:
        """Collapse the sidebar."""
        if self._is_expanded:
            self._is_expanded = False
            self._animate_to(self._collapsed_width)

    def is_expanded(self) -> bool:
        return self._is_expanded

    def _animate_to(self, target_width: int) -> None:
        """Animate to target width."""
        if self._animation:
            self._animation.stop()

        self._animation = QPropertyAnimation(self, b"sidebar_width")
        self._animation.setDuration(200)
        self._animation.setStartValue(self.maximumWidth())
        self._animation.setEndValue(target_width)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.start()


class MainWindow(QMainWindow):
    """Main application window with collapsible hosts sidebar and bottom chat."""

    # Signal for thread-safe SSH output handling
    _ssh_output_received = Signal(str)
    # Signal for unexpected disconnection
    _unexpected_disconnect = Signal()

    def __init__(self):
        super().__init__()

        self._ssh_session: Optional[SSHSession] = None
        self._agent: Optional[SSHAgent] = None
        self._resize_timer: Optional[QTimer] = None
        self._agent_task: Optional[asyncio.Task] = None
        self._current_host_id: Optional[str] = None
        self._current_device_type: Optional[str] = None
        self._chat_visible: bool = False  # Chat starts hidden
        self._last_config: Optional[SSHConfig] = None  # For reconnection

        # Output buffer for batching SSH output
        self._output_buffer: list[str] = []
        self._output_timer = QTimer()
        self._output_timer.setSingleShot(True)
        self._output_timer.timeout.connect(self._flush_output_buffer)

        # Initialize hosts manager
        self._hosts_manager = HostsManager()

        self._setup_ui()
        self._setup_connections()
        self._update_ui_state()
        self._refresh_hosts_list()

    def _setup_ui(self) -> None:
        """Setup the main window UI."""
        self.setWindowTitle("SSH AI Terminal")
        self.setMinimumSize(1000, 600)
        self.resize(1280, 768)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Collapsible sidebar for hosts
        self._sidebar = CollapsibleSidebar()
        self._setup_sidebar()
        main_layout.addWidget(self._sidebar)

        # Main content area (terminal + bottom chat)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        content_layout.addWidget(toolbar)

        # Terminal area (with vertical splitter for chat)
        self._terminal_chat_splitter = QSplitter(Qt.Orientation.Vertical)

        # Terminal widget
        self._terminal = TerminalWidget()
        self._terminal_chat_splitter.addWidget(self._terminal)

        # Chat panel at bottom (starts hidden)
        self._chat_panel = QFrame()
        self._chat_panel.setStyleSheet("background-color: #252526; border-top: 1px solid #3c3c3c;")
        self._setup_chat_panel()
        self._terminal_chat_splitter.addWidget(self._chat_panel)

        # Set splitter sizes (chat hidden initially)
        self._terminal_chat_splitter.setSizes([1, 0])
        self._terminal_chat_splitter.setStretchFactor(0, 1)  # Terminal stretches
        self._terminal_chat_splitter.setStretchFactor(1, 0)  # Chat fixed

        content_layout.addWidget(self._terminal_chat_splitter, 1)

        main_layout.addWidget(content_widget, 1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Desconectado")

        # Apply dark theme
        self._apply_dark_theme()

    def _setup_sidebar(self) -> None:
        """Setup the hosts sidebar content."""
        layout = QVBoxLayout(self._sidebar)
        layout.setContentsMargins(8, 8, 8, 8)

        # Title
        title = QLabel("Hosts")
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        # Hosts list
        self._hosts_list = QListWidget()
        self._hosts_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._hosts_list.customContextMenuRequested.connect(self._on_hosts_context_menu)
        self._hosts_list.itemDoubleClicked.connect(self._on_host_double_clicked)
        layout.addWidget(self._hosts_list)

        # Add host button
        self._add_host_btn = QPushButton("+ Adicionar Host")
        self._add_host_btn.clicked.connect(self._on_add_host_clicked)
        layout.addWidget(self._add_host_btn)

    def _setup_chat_panel(self) -> None:
        """Setup the chat panel content."""
        layout = QVBoxLayout(self._chat_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat widget
        self._chat = ChatWidget()
        layout.addWidget(self._chat)

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

        # Toggle hosts sidebar button
        self._toggle_hosts_btn = QAction("Hosts", self)
        self._toggle_hosts_btn.setCheckable(True)
        self._toggle_hosts_btn.setChecked(True)
        self._toggle_hosts_btn.setToolTip("Mostrar/Esconder lista de hosts (Ctrl+H)")
        self._toggle_hosts_btn.setShortcut("Ctrl+H")
        self._toggle_hosts_btn.triggered.connect(self._on_toggle_hosts)
        toolbar.addAction(self._toggle_hosts_btn)

        toolbar.addSeparator()

        # Toggle chat button (starts unchecked/hidden)
        self._toggle_chat_btn = QAction("Chat IA", self)
        self._toggle_chat_btn.setCheckable(True)
        self._toggle_chat_btn.setChecked(False)
        self._toggle_chat_btn.setToolTip("Mostrar/Esconder chat IA (Ctrl+J)")
        self._toggle_chat_btn.setShortcut("Ctrl+J")
        self._toggle_chat_btn.triggered.connect(self._on_toggle_chat)
        toolbar.addAction(self._toggle_chat_btn)

        toolbar.addSeparator()

        # Quick connect button
        self._quick_connect_btn = QAction("Conexao Rapida", self)
        self._quick_connect_btn.setToolTip("Conectar sem salvar (Ctrl+N)")
        self._quick_connect_btn.setShortcut("Ctrl+N")
        self._quick_connect_btn.triggered.connect(self._on_quick_connect)
        toolbar.addAction(self._quick_connect_btn)

        toolbar.addSeparator()

        # Disconnect button
        self._disconnect_btn = QAction("Desconectar", self)
        self._disconnect_btn.setToolTip("Desconectar sessao atual (Ctrl+D)")
        self._disconnect_btn.setShortcut("Ctrl+D")
        self._disconnect_btn.triggered.connect(self._on_disconnect_clicked)
        self._disconnect_btn.setEnabled(False)
        toolbar.addAction(self._disconnect_btn)

        toolbar.addSeparator()

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

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
            QListWidget {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid #3c3c3c;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QListWidget::item:hover:!selected {
                background-color: #2a2d2e;
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
            CollapsibleSidebar {
                background-color: #252526;
                border-right: 1px solid #3c3c3c;
            }
        """)

    def _setup_connections(self) -> None:
        """Connect signals to slots."""
        self._terminal.input_entered.connect(self._on_terminal_input)
        self._terminal.reconnect_requested.connect(self._on_reconnect_requested)

        # SSH output signal - use AutoConnection since qasync integrates both loops
        self._ssh_output_received.connect(self._on_ssh_output_slot, Qt.ConnectionType.AutoConnection)

        # Unexpected disconnect signal
        self._unexpected_disconnect.connect(self._on_unexpected_disconnect, Qt.ConnectionType.AutoConnection)

        # Chat signals
        self._chat.message_sent.connect(self._on_chat_message)
        self._chat.stop_requested.connect(self._on_stop_agent)

        # Setup resize timer for terminal resize
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_timeout)

    def _update_ui_state(self) -> None:
        """Update UI based on connection state."""
        connected = self._ssh_session is not None and self._ssh_session.is_connected

        # Update toolbar buttons
        self._quick_connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)

        # Update chat state
        self._chat.set_enabled_state(connected)

        if connected:
            host = self._ssh_session.config.host
            self._status_bar.showMessage(f"Conectado a {host}")
            self._status_bar.setStyleSheet("background-color: #107c10; color: white;")
            # Collapse sidebar when connected
            self._sidebar.collapse()
            self._toggle_hosts_btn.setChecked(False)
        else:
            self._status_bar.showMessage("Desconectado")
            self._status_bar.setStyleSheet("background-color: #007acc; color: white;")
            self._current_host_id = None
            self._current_device_type = None
            # Expand sidebar when disconnected
            self._sidebar.expand()
            self._toggle_hosts_btn.setChecked(True)

    def _refresh_hosts_list(self) -> None:
        """Refresh the hosts list widget."""
        self._hosts_list.clear()
        hosts = self._hosts_manager.get_all()

        for host in hosts:
            item = QListWidgetItem()
            display_text = f"{host.name}\n{host.host}:{host.port}"
            item.setText(display_text)
            item.setData(Qt.ItemDataRole.UserRole, host.id)

            if host.password_encrypted:
                item.setToolTip(f"{host.username}@{host.host}:{host.port}\nSenha salva")
            else:
                item.setToolTip(f"{host.username}@{host.host}:{host.port}\nSem senha salva")

            self._hosts_list.addItem(item)

    @Slot()
    def _on_toggle_hosts(self) -> None:
        """Toggle hosts sidebar visibility."""
        self._sidebar.toggle()

    @Slot()
    def _on_toggle_chat(self) -> None:
        """Toggle chat panel visibility."""
        self._chat_visible = not self._chat_visible
        if self._chat_visible:
            # Show chat (terminal: 70%, chat: 30%)
            self._terminal_chat_splitter.setSizes([700, 300])
        else:
            # Hide chat
            self._terminal_chat_splitter.setSizes([1, 0])

    @Slot()
    def _on_quick_connect(self) -> None:
        """Handle quick connect button click."""
        # Check if already connected
        if self._ssh_session and self._ssh_session.is_connected:
            reply = QMessageBox.question(
                self,
                "Ja conectado",
                "Deseja desconectar da sessao atual?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            asyncio.ensure_future(self._disconnect_async())

        dialog = QuickConnectDialog(parent=self)
        if dialog.exec():
            data = dialog.get_connection_data()
            cols, rows = self._terminal.get_terminal_size()
            config = SSHConfig(
                host=data["host"],
                port=data["port"],
                username=data["username"],
                password=data["password"],
                terminal_type=data["terminal_type"],
                term_width=cols,
                term_height=rows
            )

            self._current_device_type = data.get("device_type")
            asyncio.ensure_future(self._connect_async(config))

    @Slot()
    def _on_add_host_clicked(self) -> None:
        """Handle add host button click."""
        dialog = HostDialog(self._hosts_manager, parent=self)
        if dialog.exec():
            self._refresh_hosts_list()

    @Slot(QListWidgetItem)
    def _on_host_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double click on host item - connect."""
        host_id = item.data(Qt.ItemDataRole.UserRole)
        self._connect_to_host(host_id)

    def _on_hosts_context_menu(self, position) -> None:
        """Show context menu for hosts list."""
        item = self._hosts_list.itemAt(position)
        if not item:
            return

        host_id = item.data(Qt.ItemDataRole.UserRole)
        host = self._hosts_manager.get_by_id(host_id)
        if not host:
            return

        menu = QMenu(self)

        connect_action = QAction("Conectar", self)
        connect_action.triggered.connect(lambda: self._connect_to_host(host_id))
        menu.addAction(connect_action)

        menu.addSeparator()

        edit_action = QAction("Editar", self)
        edit_action.triggered.connect(lambda: self._edit_host(host_id))
        menu.addAction(edit_action)

        delete_action = QAction("Excluir", self)
        delete_action.triggered.connect(lambda: self._delete_host(host_id))
        menu.addAction(delete_action)

        menu.exec(self._hosts_list.mapToGlobal(position))

    def _connect_to_host(self, host_id: str) -> None:
        """Connect to a saved host."""
        host = self._hosts_manager.get_by_id(host_id)
        if not host:
            return

        if self._ssh_session and self._ssh_session.is_connected:
            reply = QMessageBox.question(
                self,
                "Ja conectado",
                "Deseja desconectar da sessao atual e conectar ao novo host?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            asyncio.ensure_future(self._disconnect_and_connect(host_id))
            return

        # Get saved password if available (may be None)
        password = self._hosts_manager.get_password(host_id)
        # Password can be None - will be requested via terminal if needed

        self._current_host_id = host_id
        self._current_device_type = host.device_type
        cols, rows = self._terminal.get_terminal_size()
        config = SSHConfig(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password or "",
            terminal_type=host.terminal_type,
            term_width=cols,
            term_height=rows
        )

        asyncio.ensure_future(self._connect_async(config))

    async def _disconnect_and_connect(self, host_id: str) -> None:
        """Disconnect current session and connect to new host."""
        await self._disconnect_async()
        self._connect_to_host(host_id)

    def _edit_host(self, host_id: str) -> None:
        """Edit a saved host."""
        host = self._hosts_manager.get_by_id(host_id)
        if not host:
            return

        dialog = HostDialog(self._hosts_manager, host=host, parent=self)
        if dialog.exec():
            self._refresh_hosts_list()

    def _delete_host(self, host_id: str) -> None:
        """Delete a saved host."""
        host = self._hosts_manager.get_by_id(host_id)
        if not host:
            return

        reply = QMessageBox.question(
            self,
            "Confirmar Exclusao",
            f"Tem certeza que deseja excluir o host '{host.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._hosts_manager.delete(host_id)
            self._refresh_hosts_list()

    def _create_agent(self) -> None:
        """Create AI agent for current SSH session."""
        if not self._ssh_session:
            return

        async def execute_command(cmd: str) -> str:
            if self._ssh_session and self._ssh_session.is_connected:
                return await self._ssh_session.execute_command(cmd)
            raise RuntimeError("Not connected")

        def on_command_executed(cmd: str, output: str) -> None:
            self._terminal.append_output(f"\n$ {cmd}\n")
            self._terminal.append_output(output)

        def on_thinking(status: str) -> None:
            self._chat.set_status(status)

        self._agent = create_agent(
            execute_command=execute_command,
            on_command_executed=on_command_executed,
            on_thinking=on_thinking,
            device_type=self._current_device_type
        )

    def _on_disconnect_callback(self) -> None:
        """Callback called from SSH session when connection is lost unexpectedly."""
        self._unexpected_disconnect.emit()

    async def _connect_async(self, config: SSHConfig) -> None:
        """Async connection handler."""
        self._quick_connect_btn.setEnabled(False)
        self._status_bar.showMessage(f"Conectando a {config.host}...")
        self._status_bar.setStyleSheet("background-color: #ca5010; color: white;")

        try:
            self._ssh_session = SSHSession(
                config,
                self._on_ssh_output,
                self._on_disconnect_callback
            )
            await self._ssh_session.connect()
            self._last_config = config  # Save for reconnection
            self._terminal.clear()
            self._terminal.set_focus()

            # Send terminal size after connection
            cols, rows = self._terminal.get_terminal_size()
            await self._ssh_session.resize_terminal(cols, rows)

            self._create_agent()
            self._chat.clear_messages()
            self._update_ui_state()

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._ssh_session = None
            QMessageBox.critical(
                self,
                "Erro de Conexao",
                f"Falha ao conectar em {config.host}:\n{str(e)}"
            )
            self._update_ui_state()

    @Slot()
    def _on_disconnect_clicked(self) -> None:
        """Handle disconnect button click."""
        self._last_config = None  # Clear config on manual disconnect
        asyncio.ensure_future(self._disconnect_async())

    @Slot()
    def _on_unexpected_disconnect(self) -> None:
        """Handle unexpected disconnection from SSH session."""
        logger.info("Unexpected disconnect detected")
        # Clean up session state
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
        self._agent = None
        self._ssh_session = None

        # Clear any pending output buffer to prevent overwriting the message
        self._output_timer.stop()
        self._output_buffer.clear()

        # Show disconnected message in terminal
        self._terminal.show_disconnected_message()
        self._update_ui_state()

    @Slot()
    def _on_reconnect_requested(self) -> None:
        """Handle reconnect request from terminal (user pressed R)."""
        if self._last_config:
            # Update terminal size before reconnecting
            cols, rows = self._terminal.get_terminal_size()
            self._last_config.term_width = cols
            self._last_config.term_height = rows
            asyncio.ensure_future(self._connect_async(self._last_config))

    async def _disconnect_async(self) -> None:
        """Async disconnection handler."""
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            try:
                await self._agent_task
            except asyncio.CancelledError:
                pass
            self._agent_task = None

        if self._agent:
            await self._agent.close()
            self._agent = None

        if self._ssh_session:
            await self._ssh_session.disconnect()
            self._ssh_session = None

        self._update_ui_state()

    def _on_ssh_output(self, data: str) -> None:
        """Handle output received from SSH session (called from async task)."""
        # Use signal for thread-safe communication
        self._ssh_output_received.emit(data)

    @Slot(str)
    def _on_ssh_output_slot(self, data: str) -> None:
        """Buffer SSH output and process in batches."""
        # Ignore output if terminal is in disconnected mode
        if self._terminal._disconnected_mode:
            return
        self._output_buffer.append(data)
        # Start timer if not already running (10ms batching window)
        if not self._output_timer.isActive():
            self._output_timer.start(10)

    def _flush_output_buffer(self) -> None:
        """Flush buffered output to terminal."""
        if not self._output_buffer:
            return
        # Don't flush if terminal is in disconnected mode
        if self._terminal._disconnected_mode:
            self._output_buffer.clear()
            return
        # Combine all buffered data
        combined = ''.join(self._output_buffer)
        self._output_buffer.clear()
        # Process combined data at once
        if combined:
            self._terminal.append_output(combined)

    @Slot(str)
    def _on_terminal_input(self, data: str) -> None:
        """Handle input from terminal widget."""
        if self._ssh_session:
            # Check if waiting for authentication input
            if self._ssh_session.waiting_for_auth:
                self._ssh_session.provide_auth_input(data)
                return

            if self._ssh_session.is_connected:
                asyncio.ensure_future(self._ssh_session.send_input(data))

    @Slot(str)
    def _on_chat_message(self, message: str) -> None:
        """Handle message from chat widget."""
        if not self._agent or not self._ssh_session:
            self._chat.add_message("Erro: Conecte-se a um host primeiro.", is_user=False)
            return

        self._chat.set_processing(True)
        self._agent_task = asyncio.ensure_future(self._process_chat_message(message))

    async def _process_chat_message(self, message: str) -> None:
        """Process chat message with AI agent."""
        try:
            response = await self._agent.chat(message)
            self._chat.add_message(response, is_user=False)
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
        if self._agent:
            self._agent.cancel()
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()

    def resizeEvent(self, event) -> None:
        """Handle window resize."""
        super().resizeEvent(event)
        if self._resize_timer:
            self._resize_timer.start(200)

    @Slot()
    def _on_resize_timeout(self) -> None:
        """Handle resize timeout - update terminal size."""
        if self._ssh_session and self._ssh_session.is_connected:
            cols, rows = self._terminal.get_terminal_size()
            asyncio.ensure_future(
                self._ssh_session.resize_terminal(cols, rows)
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close."""
        if self._ssh_session and self._ssh_session.is_connected:
            asyncio.ensure_future(self._disconnect_async())
            QTimer.singleShot(100, self.close)
            event.ignore()
        else:
            event.accept()
