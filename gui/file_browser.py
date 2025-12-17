"""
File Browser Widget for SFTP navigation.
Provides a file browser interface for remote file management.
"""

import asyncio
import logging
import os
from pathlib import Path, PurePosixPath
from typing import Optional, List, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QToolButton,
    QFrame, QMenu, QMessageBox, QFileDialog,
    QInputDialog, QAbstractItemView, QApplication, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QKeyEvent, QDragEnterEvent, QDropEvent

from core.sftp_manager import SFTPManager, FileInfo
from gui.remote_file_editor import RemoteFileEditor
from gui.file_browser_utils import (
    FILE_ICONS, get_file_icon, format_size,
    format_bytes_progress, format_folder_progress
)

logger = logging.getLogger(__name__)


class FileListWidget(QListWidget):
    """Custom list widget with drag support for downloads."""

    files_dropped = Signal(list)  # List of local file paths for upload
    drag_started = Signal(list)   # List of FileInfo for download

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

        self._files: List[FileInfo] = []

    def set_files(self, files: List[FileInfo]) -> None:
        """Store file info for drag operations."""
        self._files = files

    def get_selected_files(self) -> List[FileInfo]:
        """Get FileInfo for selected items."""
        selected = []
        for item in self.selectedItems():
            # Get the path from UserRole data instead of using index
            # This avoids off-by-one errors when ".." item is present
            path = item.data(Qt.ItemDataRole.UserRole)
            if path == "..":
                continue
            # Find file by path
            for file_info in self._files:
                if file_info.path == path:
                    selected.append(file_info)
                    break
        return selected

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept file drops from Windows."""
        if event.mimeData().hasUrls():
            # Check if all URLs are local files
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Handle drag move."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle file drop for upload."""
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    files.append(url.toLocalFile())
            if files:
                self.files_dropped.emit(files)
                event.acceptProposedAction()
                return
        event.ignore()

    def startDrag(self, supportedActions) -> None:
        """Start drag for download."""
        selected = self.get_selected_files()
        if not selected:
            return

        # Filter out directories for now (only files)
        files_only = [f for f in selected if not f.is_dir]
        if not files_only:
            return

        # Emit signal to trigger download
        self.drag_started.emit(files_only)


class PathComboBox(QComboBox):
    """Editable combobox for path navigation with history."""

    path_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._history: List[str] = []
        self._max_history = 20

        self.lineEdit().returnPressed.connect(self._on_return_pressed)

    def set_path(self, path: str) -> None:
        """Set current path and add to history."""
        self.blockSignals(True)
        self.setEditText(path)

        # Add to history if not already present
        if path in self._history:
            self._history.remove(path)
        self._history.insert(0, path)

        # Trim history
        if len(self._history) > self._max_history:
            self._history = self._history[:self._max_history]

        # Update dropdown
        self.clear()
        for p in self._history:
            self.addItem(p)

        self.blockSignals(False)

    def _on_return_pressed(self) -> None:
        """Handle enter key in path edit."""
        path = self.currentText().strip()
        if path:
            self.path_changed.emit(path)


class FileBrowser(QWidget):
    """
    File browser widget for SFTP navigation.

    Provides:
    - Directory listing with icons
    - Navigation (back, forward, up, refresh)
    - Path editing
    - File operations (download, upload, rename, delete, mkdir)
    - Drag & drop support
    - Follow terminal folder option

    Signals:
    - file_double_clicked(str): When user double-clicks a file
    - directory_changed(str): When current directory changes
    - download_requested(list): List of FileInfo to download
    - upload_requested(list, str): Local files and remote directory
    - status_message(str): Status updates
    """

    file_double_clicked = Signal(str)
    directory_changed = Signal(str)
    download_requested = Signal(list)  # List of FileInfo
    upload_requested = Signal(list, str)  # Local paths, remote dir
    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._sftp: Optional[SFTPManager] = None
        self._current_path = "/"
        self._files: List[FileInfo] = []
        self._history: List[str] = []
        self._history_index = -1
        self._follow_terminal = False
        self._loading = False
        self._show_hidden = True
        self._remote_editor: Optional[RemoteFileEditor] = None

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        """Setup the file browser UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Path bar
        path_layout = QHBoxLayout()
        path_layout.setSpacing(4)

        self._path_combo = PathComboBox()
        self._path_combo.setToolTip("Caminho atual (edite e pressione Enter)")
        self._path_combo.path_changed.connect(self._on_path_entered)
        path_layout.addWidget(self._path_combo, 1)

        layout.addLayout(path_layout)

        # File list
        self._file_list = FileListWidget()
        self._file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_list.customContextMenuRequested.connect(self._show_context_menu)
        self._file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._file_list.files_dropped.connect(self._on_files_dropped)
        self._file_list.drag_started.connect(self._on_drag_started)
        layout.addWidget(self._file_list, 1)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(2)

        # Back button
        self._back_btn = QToolButton()
        self._back_btn.setText("\u2190")  # ←
        self._back_btn.setToolTip("Voltar (Backspace)")
        self._back_btn.clicked.connect(self.go_back)
        toolbar_layout.addWidget(self._back_btn)

        # Forward button
        self._forward_btn = QToolButton()
        self._forward_btn.setText("\u2192")  # →
        self._forward_btn.setToolTip("Avançar")
        self._forward_btn.clicked.connect(self.go_forward)
        toolbar_layout.addWidget(self._forward_btn)

        # Up button
        self._up_btn = QToolButton()
        self._up_btn.setText("\u2191")  # ↑
        self._up_btn.setToolTip("Pasta pai")
        self._up_btn.clicked.connect(self.go_up)
        toolbar_layout.addWidget(self._up_btn)

        toolbar_layout.addSpacing(8)

        # Refresh button
        self._refresh_btn = QToolButton()
        self._refresh_btn.setText("\u21BB")  # ↻
        self._refresh_btn.setToolTip("Atualizar (F5)")
        self._refresh_btn.clicked.connect(self.refresh)
        toolbar_layout.addWidget(self._refresh_btn)

        # New folder button
        self._new_folder_btn = QToolButton()
        self._new_folder_btn.setText("\U0001F4C1+")  # 📁+
        self._new_folder_btn.setToolTip("Nova pasta (Ctrl+Shift+N)")
        self._new_folder_btn.clicked.connect(self._on_new_folder)
        toolbar_layout.addWidget(self._new_folder_btn)

        # New file button
        self._new_file_btn = QToolButton()
        self._new_file_btn.setText("\U0001F4C4+")  # 📄+
        self._new_file_btn.setToolTip("Novo arquivo (Ctrl+N)")
        self._new_file_btn.clicked.connect(self._on_new_file)
        toolbar_layout.addWidget(self._new_file_btn)

        # Upload button
        self._upload_btn = QToolButton()
        self._upload_btn.setText("\u2191\U0001F4C4")  # ↑📄
        self._upload_btn.setToolTip("Upload de arquivo")
        self._upload_btn.clicked.connect(self._on_upload_click)
        toolbar_layout.addWidget(self._upload_btn)

        toolbar_layout.addStretch()

        # Hidden files toggle
        self._hidden_btn = QToolButton()
        self._hidden_btn.setText("\u2022")  # bullet
        self._hidden_btn.setToolTip("Mostrar/ocultar arquivos ocultos")
        self._hidden_btn.setCheckable(True)
        self._hidden_btn.setChecked(True)
        self._hidden_btn.clicked.connect(self._on_toggle_hidden)
        toolbar_layout.addWidget(self._hidden_btn)

        layout.addLayout(toolbar_layout)

        # Follow terminal checkbox
        follow_layout = QHBoxLayout()
        follow_layout.setContentsMargins(0, 4, 0, 0)

        self._follow_checkbox = QCheckBox("Follow terminal folder")
        self._follow_checkbox.setToolTip("Sincronizar com diretório do terminal")
        self._follow_checkbox.stateChanged.connect(self._on_follow_changed)
        follow_layout.addWidget(self._follow_checkbox)
        follow_layout.addStretch()

        layout.addLayout(follow_layout)

        # Status bar
        self._status_label = QLabel("Desconectado")
        self._status_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self._status_label)

        # Update button states
        self._update_nav_buttons()

    def _apply_style(self) -> None:
        """Apply dark theme styling."""
        self.setStyleSheet("""
            FileBrowser {
                background-color: #252526;
            }

            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                outline: none;
            }

            QListWidget::item {
                padding: 4px 8px;
                border-radius: 3px;
            }

            QListWidget::item:selected {
                background-color: #094771;
            }

            QListWidget::item:hover:!selected {
                background-color: #2a2d2e;
            }

            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                color: #dcdcdc;
            }

            QComboBox:hover {
                border: 1px solid #007acc;
            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
            }

            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                selection-background-color: #094771;
                color: #dcdcdc;
            }

            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
                color: #dcdcdc;
                font-size: 14px;
            }

            QToolButton:hover {
                background-color: #3c3c3c;
            }

            QToolButton:pressed {
                background-color: #094771;
            }

            QToolButton:disabled {
                color: #555555;
            }

            QToolButton:checked {
                background-color: #094771;
            }

            QCheckBox {
                color: #dcdcdc;
                spacing: 5px;
            }

            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #555555;
                border-radius: 2px;
                background-color: #3c3c3c;
            }

            QCheckBox::indicator:checked {
                background-color: #0e639c;
                border-color: #0e639c;
            }

            QCheckBox::indicator:hover {
                border-color: #007acc;
            }
        """)

    def _update_nav_buttons(self) -> None:
        """Update navigation button states."""
        self._back_btn.setEnabled(self._history_index > 0)
        self._forward_btn.setEnabled(self._history_index < len(self._history) - 1)
        self._up_btn.setEnabled(self._current_path != "/")

        # Enable/disable all buttons based on connection
        connected = self._sftp is not None and self._sftp.is_connected
        self._refresh_btn.setEnabled(connected)
        self._new_folder_btn.setEnabled(connected)
        self._new_file_btn.setEnabled(connected)
        self._upload_btn.setEnabled(connected)
        self._hidden_btn.setEnabled(connected)
        self._path_combo.setEnabled(connected)

    def _set_status(self, message: str) -> None:
        """Set status message."""
        self._status_label.setText(message)
        self.status_message.emit(message)

    # === Connection management ===

    async def connect(self, ssh_conn) -> None:
        """
        Connect to SFTP using SSH connection.

        Args:
            ssh_conn: asyncssh.SSHClientConnection
        """
        self._sftp = SFTPManager()
        try:
            await self._sftp.connect(ssh_conn)
            self._current_path = self._sftp.home_dir
            self._history = [self._current_path]
            self._history_index = 0
            self._set_status("Conectado")

            # Create remote file editor
            self._remote_editor = RemoteFileEditor(self._sftp, self._set_status)

            await self._load_directory(self._current_path)
        except Exception as e:
            logger.error(f"SFTP connect failed: {e}")
            self._set_status(f"Erro: {e}")
            self._sftp = None
            raise

    async def disconnect(self) -> None:
        """Disconnect SFTP."""
        # Close remote editor and cleanup temp files
        if self._remote_editor:
            self._remote_editor.close_all()
            self._remote_editor = None

        if self._sftp:
            await self._sftp.disconnect()
            self._sftp = None
        self.clear()

    def clear(self) -> None:
        """Clear the file browser."""
        self._file_list.clear()
        self._files = []
        self._path_combo.setEditText("")
        self._history = []
        self._history_index = -1
        self._set_status("Desconectado")
        self._update_nav_buttons()

    @property
    def is_connected(self) -> bool:
        """Check if SFTP is connected."""
        return self._sftp is not None and self._sftp.is_connected

    @property
    def current_path(self) -> str:
        """Get current directory path."""
        return self._current_path

    @property
    def follow_terminal(self) -> bool:
        """Get follow terminal state."""
        return self._follow_terminal

    # === Directory navigation ===

    async def _load_directory(self, path: str, add_to_history: bool = True) -> None:
        """Load directory contents."""
        if not self._sftp or self._loading:
            return

        self._loading = True
        self._set_status("Carregando...")

        try:
            # Change directory and get listing
            new_path = await self._sftp.change_dir(path)
            files = await self._sftp.list_dir(
                new_path,
                show_hidden=self._show_hidden
            )

            self._current_path = new_path
            self._files = files
            self._file_list.set_files(files)

            # Update history
            if add_to_history:
                # Remove forward history
                if self._history_index < len(self._history) - 1:
                    self._history = self._history[:self._history_index + 1]
                # Add new path if different from current
                if not self._history or self._history[-1] != new_path:
                    self._history.append(new_path)
                    self._history_index = len(self._history) - 1

            # Update UI
            self._path_combo.set_path(new_path)
            self._populate_file_list()
            self._update_nav_buttons()
            self._set_status(f"{len(files)} itens")
            self.directory_changed.emit(new_path)

        except FileNotFoundError:
            self._set_status(f"Diretório não encontrado: {path}")
            # Don't show QMessageBox - it blocks the event loop and freezes terminal
            logger.warning(f"Directory not found: {path}")
        except PermissionError:
            self._set_status(f"Permissão negada: {path}")
            logger.warning(f"Permission denied: {path}")
        except Exception as e:
            logger.error(f"Error loading directory: {e}")
            self._set_status(f"Erro: {e}")
        finally:
            self._loading = False

    def _populate_file_list(self) -> None:
        """Populate the file list widget."""
        self._file_list.clear()

        # Add parent directory entry if not at root
        if self._current_path != "/":
            item = QListWidgetItem(f"{FILE_ICONS['folder']}  ..")
            item.setData(Qt.ItemDataRole.UserRole, "..")
            self._file_list.addItem(item)

        # Add files
        for file_info in self._files:
            icon = get_file_icon(file_info)
            name = file_info.name

            # Add link indicator
            if file_info.is_link:
                name = f"{name} -> {file_info.link_target or '?'}"

            # Format size for files
            if file_info.is_dir:
                size_str = ""
            else:
                size_str = f"  ({format_size(file_info.size)})"

            item = QListWidgetItem(f"{icon}  {name}{size_str}")
            item.setData(Qt.ItemDataRole.UserRole, file_info.path)
            item.setToolTip(
                f"Tamanho: {format_size(file_info.size)}\n"
                f"Modificado: {file_info.modified.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Permissões: {file_info.permissions}\n"
                f"Dono: {file_info.owner}:{file_info.group}"
            )
            self._file_list.addItem(item)

    def set_path(self, path: str) -> None:
        """
        Set current path (for follow terminal).

        Args:
            path: Directory path
        """
        if self._sftp and path != self._current_path:
            asyncio.ensure_future(self._load_directory(path))

    def refresh(self) -> None:
        """Refresh current directory."""
        if self._sftp:
            asyncio.ensure_future(self._load_directory(self._current_path, add_to_history=False))

    def go_back(self) -> None:
        """Navigate to previous directory in history."""
        if self._history_index > 0:
            self._history_index -= 1
            path = self._history[self._history_index]
            asyncio.ensure_future(self._load_directory(path, add_to_history=False))

    def go_forward(self) -> None:
        """Navigate to next directory in history."""
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            path = self._history[self._history_index]
            asyncio.ensure_future(self._load_directory(path, add_to_history=False))

    def go_up(self) -> None:
        """Navigate to parent directory."""
        if self._current_path != "/":
            parent = str(PurePosixPath(self._current_path).parent)
            asyncio.ensure_future(self._load_directory(parent))

    # === Event handlers ===

    def _on_path_entered(self, path: str) -> None:
        """Handle path entered in combo box."""
        asyncio.ensure_future(self._load_directory(path))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on file item."""
        path = item.data(Qt.ItemDataRole.UserRole)

        if path == "..":
            self.go_up()
            return

        # Find file info
        for file_info in self._files:
            if file_info.path == path:
                if file_info.is_dir:
                    asyncio.ensure_future(self._load_directory(path))
                else:
                    # Open file for remote editing
                    self._open_file_for_editing(path)
                return

    def _open_file_for_editing(self, remote_path: str) -> None:
        """Open a file for remote editing."""
        if self._remote_editor:
            asyncio.ensure_future(self._remote_editor.open_file(remote_path))

    def _on_follow_changed(self, state: int) -> None:
        """Handle follow terminal checkbox change."""
        self._follow_terminal = state == 2  # Qt.CheckState.Checked = 2
        logger.debug(f"Follow terminal changed: {self._follow_terminal}")

    def _on_toggle_hidden(self) -> None:
        """Toggle hidden files visibility."""
        self._show_hidden = self._hidden_btn.isChecked()
        self.refresh()

    def _on_files_dropped(self, files: List[str]) -> None:
        """Handle files dropped for upload."""
        if not self._sftp:
            return
        self.upload_requested.emit(files, self._current_path)

    def _on_drag_started(self, files: List[FileInfo]) -> None:
        """Handle drag started for download."""
        self.download_requested.emit(files)

    def _on_upload_click(self) -> None:
        """Handle upload button click - show menu with file/folder options."""
        if not self._sftp:
            return

        # Show menu with options
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """)

        files_action = menu.addAction("\U0001F4C4 Upload de arquivos...")
        files_action.triggered.connect(self._on_upload_files)

        folder_action = menu.addAction("\U0001F4C1 Upload de pasta...")
        folder_action.triggered.connect(self._on_upload_folder)

        # Show menu below the button
        menu.exec(self._upload_btn.mapToGlobal(self._upload_btn.rect().bottomLeft()))

    def _on_upload_files(self) -> None:
        """Handle upload files selection."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar arquivos para upload",
            "",
            "Todos os arquivos (*.*)"
        )

        if files:
            self.upload_requested.emit(files, self._current_path)

    def _on_upload_folder(self) -> None:
        """Handle upload folder selection."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecionar pasta para upload",
            ""
        )

        if folder:
            self.upload_requested.emit([folder], self._current_path)

    def _on_new_folder(self) -> None:
        """Handle new folder button click."""
        if not self._sftp:
            return

        name, ok = QInputDialog.getText(
            self,
            "Nova Pasta",
            "Nome da pasta:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if ok and name:
            asyncio.ensure_future(self._create_folder(name))

    async def _create_folder(self, name: str) -> None:
        """Create a new folder."""
        try:
            path = str(PurePosixPath(self._current_path) / name)
            await self._sftp.mkdir(path)
            self._set_status(f"Pasta criada: {name}")
            self.refresh()
        except FileExistsError:
            QMessageBox.warning(self, "Erro", f"Pasta já existe: {name}")
        except PermissionError:
            QMessageBox.warning(self, "Erro", "Permissão negada")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao criar pasta: {e}")

    def _on_new_file(self) -> None:
        """Handle new file button click."""
        if not self._sftp:
            return

        name, ok = QInputDialog.getText(
            self,
            "Novo Arquivo",
            "Nome do arquivo:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if ok and name:
            asyncio.ensure_future(self._create_file(name))

    async def _create_file(self, name: str) -> None:
        """Create a new empty file."""
        try:
            path = str(PurePosixPath(self._current_path) / name)
            await self._sftp.create_file(path)
            self._set_status(f"Arquivo criado: {name}")
            self.refresh()
        except FileExistsError:
            QMessageBox.warning(self, "Erro", f"Arquivo já existe: {name}")
        except PermissionError:
            QMessageBox.warning(self, "Erro", "Permissão negada")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao criar arquivo: {e}")

    # === Context menu ===

    def _show_context_menu(self, pos) -> None:
        """Show context menu for file operations."""
        item = self._file_list.itemAt(pos)
        selected = self._file_list.get_selected_files()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 2px;
                color: #dcdcdc;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555555;
                margin: 4px 8px;
            }
        """)

        if item and item.data(Qt.ItemDataRole.UserRole) != "..":
            # Edit action (single file only, not directory)
            if len(selected) == 1 and not selected[0].is_dir:
                edit_action = menu.addAction("Editar")
                edit_action.triggered.connect(lambda: self._open_file_for_editing(selected[0].path))

            # Download action
            download_action = menu.addAction("Download")
            download_action.triggered.connect(lambda: self._context_download(selected))

            menu.addSeparator()

            # Rename action (single item only)
            if len(selected) == 1:
                rename_action = menu.addAction("Renomear")
                rename_action.triggered.connect(lambda: self._context_rename(selected[0]))

            # Delete action
            delete_action = menu.addAction("Excluir")
            delete_action.triggered.connect(lambda: self._context_delete(selected))

            menu.addSeparator()

            # Copy path action
            copy_path_action = menu.addAction("Copiar caminho")
            copy_path_action.triggered.connect(
                lambda: self._context_copy_path(selected[0] if selected else None)
            )

        # Always show these options
        menu.addSeparator()

        upload_files_action = menu.addAction("\U0001F4C4 Upload de arquivos...")
        upload_files_action.triggered.connect(self._on_upload_files)

        upload_folder_action = menu.addAction("\U0001F4C1 Upload de pasta...")
        upload_folder_action.triggered.connect(self._on_upload_folder)

        menu.addSeparator()

        new_folder_action = menu.addAction("Nova pasta")
        new_folder_action.triggered.connect(self._on_new_folder)

        new_file_action = menu.addAction("Novo arquivo")
        new_file_action.triggered.connect(self._on_new_file)

        refresh_action = menu.addAction("Atualizar")
        refresh_action.triggered.connect(self.refresh)

        menu.exec(self._file_list.mapToGlobal(pos))

    def _context_download(self, files: List[FileInfo]) -> None:
        """Handle download from context menu."""
        if files:
            self.download_requested.emit(files)

    def _context_rename(self, file_info: FileInfo) -> None:
        """Handle rename from context menu."""
        new_name, ok = QInputDialog.getText(
            self,
            "Renomear",
            "Novo nome:",
            QLineEdit.EchoMode.Normal,
            file_info.name
        )

        if ok and new_name and new_name != file_info.name:
            asyncio.ensure_future(self._rename_file(file_info, new_name))

    async def _rename_file(self, file_info: FileInfo, new_name: str) -> None:
        """Rename a file."""
        try:
            await self._sftp.rename(file_info.path, new_name)
            self._set_status(f"Renomeado: {file_info.name} -> {new_name}")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao renomear: {e}")

    def _context_delete(self, files: List[FileInfo]) -> None:
        """Handle delete from context menu."""
        if not files:
            return

        # Build confirmation message
        if len(files) == 1:
            msg = f"Excluir '{files[0].name}'?"
        else:
            msg = f"Excluir {len(files)} itens?"

        # Check for directories
        has_dirs = any(f.is_dir for f in files)
        if has_dirs:
            msg += "\n\nATENÇÃO: Pastas serão excluídas recursivamente!"

        reply = QMessageBox.question(
            self,
            "Confirmar exclusão",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            asyncio.ensure_future(self._delete_files(files))

    async def _delete_files(self, files: List[FileInfo]) -> None:
        """Delete files."""
        deleted = 0
        for file_info in files:
            try:
                await self._sftp.delete(file_info.path, recursive=file_info.is_dir)
                deleted += 1
            except Exception as e:
                logger.error(f"Error deleting {file_info.path}: {e}")
                QMessageBox.warning(
                    self, "Erro",
                    f"Erro ao excluir '{file_info.name}': {e}"
                )

        if deleted > 0:
            self._set_status(f"{deleted} item(s) excluído(s)")
            self.refresh()

    def _context_copy_path(self, file_info: Optional[FileInfo]) -> None:
        """Copy file path to clipboard."""
        if file_info:
            path = file_info.path
        else:
            path = self._current_path

        clipboard = QApplication.clipboard()
        clipboard.setText(path)
        self._set_status("Caminho copiado")

    # === Keyboard handling ===

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_F5:
            self.refresh()
        elif key == Qt.Key.Key_Backspace:
            self.go_up()
        elif key == Qt.Key.Key_Delete:
            selected = self._file_list.get_selected_files()
            if selected:
                self._context_delete(selected)
        elif key == Qt.Key.Key_F2:
            selected = self._file_list.get_selected_files()
            if len(selected) == 1:
                self._context_rename(selected[0])
        elif key == Qt.Key.Key_N and modifiers & Qt.KeyboardModifier.ControlModifier and modifiers & Qt.KeyboardModifier.ShiftModifier:
            self._on_new_folder()
        elif key == Qt.Key.Key_N and modifiers & Qt.KeyboardModifier.ControlModifier and not modifiers & Qt.KeyboardModifier.ShiftModifier:
            self._on_new_file()
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            items = self._file_list.selectedItems()
            if items:
                self._on_item_double_clicked(items[0])
        else:
            super().keyPressEvent(event)

    # === Public methods for external use ===

    async def upload_files(
        self,
        local_files: List[str],
        remote_dir: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> int:
        """
        Upload files and directories to remote directory.

        Args:
            local_files: List of local file/directory paths
            remote_dir: Remote directory path
            progress_callback: Optional callback(message) for formatted progress

        Returns:
            Number of files uploaded successfully
        """
        if not self._sftp:
            return 0

        uploaded = 0
        for local_path in local_files:
            try:
                local_file = Path(local_path)

                if local_file.is_dir():
                    # Upload directory recursively with folder progress
                    self._set_status(f"Enviando pasta: {local_file.name}...")

                    def make_folder_callback(folder_name):
                        def callback(name, done, total):
                            if progress_callback:
                                progress_callback(format_folder_progress(folder_name, done, total, "Enviando"))
                        return callback

                    count = await self._sftp.upload_directory(
                        local_path,
                        remote_dir,
                        make_folder_callback(local_file.name)
                    )
                    uploaded += count
                    self._set_status(f"Pasta enviada: {local_file.name} ({count} arquivos)")
                else:
                    # Upload single file with bytes progress
                    remote_path = str(PurePosixPath(remote_dir) / local_file.name)

                    def make_file_callback(name):
                        def callback(done, total):
                            if progress_callback:
                                progress_callback(format_bytes_progress(name, done, total, "Enviando"))
                        return callback

                    await self._sftp.upload(local_path, remote_path, make_file_callback(local_file.name))
                    uploaded += 1
                    self._set_status(f"Upload: {local_file.name}")

            except Exception as e:
                logger.error(f"Upload failed for {local_path}: {e}")
                QMessageBox.warning(
                    self, "Erro",
                    f"Erro ao fazer upload de '{Path(local_path).name}': {e}"
                )

        if uploaded > 0:
            self.refresh()

        return uploaded

    async def download_files(
        self,
        files: List[FileInfo],
        local_dir: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> int:
        """
        Download files and directories to local directory.

        Args:
            files: List of FileInfo to download
            local_dir: Local directory path
            progress_callback: Optional callback(message) for formatted progress

        Returns:
            Number of files downloaded successfully
        """
        if not self._sftp:
            return 0

        downloaded = 0
        for file_info in files:
            try:
                if file_info.is_dir:
                    # Download directory recursively with folder progress
                    self._set_status(f"Baixando pasta: {file_info.name}...")

                    def make_folder_callback(folder_name):
                        def callback(name, done, total):
                            if progress_callback:
                                progress_callback(format_folder_progress(folder_name, done, total, "Baixando"))
                        return callback

                    count = await self._sftp.download_directory(
                        file_info.path,
                        local_dir,
                        make_folder_callback(file_info.name)
                    )
                    downloaded += count
                    self._set_status(f"Pasta baixada: {file_info.name} ({count} arquivos)")
                else:
                    # Download single file with bytes progress
                    local_path = os.path.join(local_dir, file_info.name)

                    def make_file_callback(name):
                        def callback(done, total):
                            if progress_callback:
                                progress_callback(format_bytes_progress(name, done, total, "Baixando"))
                        return callback

                    await self._sftp.download(file_info.path, local_path, make_file_callback(file_info.name))
                    downloaded += 1
                    self._set_status(f"Download: {file_info.name}")

            except Exception as e:
                logger.error(f"Download failed for {file_info.path}: {e}")
                QMessageBox.warning(
                    self, "Erro",
                    f"Erro ao baixar '{file_info.name}': {e}"
                )

        return downloaded

    def get_sftp_manager(self) -> Optional[SFTPManager]:
        """Get the SFTP manager instance."""
        return self._sftp
