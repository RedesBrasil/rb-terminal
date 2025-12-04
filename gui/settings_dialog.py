"""
Settings Dialog for RB Terminal.
Allows users to configure API key and other settings.
Fetches available models from OpenRouter API.
"""

import logging
from pathlib import Path
from typing import Optional

import httpx

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QFormLayout, QMessageBox, QListWidget,
    QListWidgetItem, QApplication, QSpinBox, QComboBox, QFileDialog,
    QFrame
)
from PySide6.QtCore import Qt, QThread, Signal, QEvent

from core.data_manager import get_data_manager

logger = logging.getLogger(__name__)


class ModelFetcher(QThread):
    """Thread to fetch models from OpenRouter API."""

    models_fetched = Signal(list)  # List of (name, id) tuples
    error_occurred = Signal(str)

    def run(self):
        """Fetch models from OpenRouter API."""
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get("https://openrouter.ai/api/v1/models")
                response.raise_for_status()
                data = response.json()

                models = []
                for model in data.get("data", []):
                    model_id = model.get("id", "")
                    name = model.get("name", model_id)
                    # Format: "Provider: Model Name" or just use the name
                    models.append((name, model_id))

                # Sort by name
                models.sort(key=lambda x: x[0].lower())
                self.models_fetched.emit(models)

        except httpx.TimeoutException:
            self.error_occurred.emit("Timeout ao buscar modelos. Verifique sua conexao.")
        except httpx.HTTPStatusError as e:
            self.error_occurred.emit(f"Erro HTTP: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            self.error_occurred.emit(f"Erro ao buscar modelos: {str(e)}")


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data_manager = get_data_manager()
        self._all_models: list[tuple[str, str]] = []  # (name, id)
        self._model_fetcher: Optional[ModelFetcher] = None
        self._setup_ui()
        self._load_current_settings()
        self._fetch_models()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Configuracoes")
        self.setMinimumWidth(600)
        self.setMinimumHeight(200)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # API Settings Group
        api_group = QGroupBox("API OpenRouter")
        api_layout = QFormLayout(api_group)

        # API Key
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setPlaceholderText("sk-or-v1-...")
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Show/Hide API Key button
        api_key_row = QHBoxLayout()
        self._toggle_key_btn = QPushButton("Mostrar")
        self._toggle_key_btn.setFixedWidth(80)
        self._toggle_key_btn.clicked.connect(self._toggle_api_key_visibility)
        api_key_row.addWidget(self._api_key_edit)
        api_key_row.addWidget(self._toggle_key_btn)
        api_layout.addRow("API Key:", api_key_row)

        # Model search (shows selected model, click to open list)
        self._model_search = QLineEdit()
        self._model_search.setPlaceholderText("Clique para selecionar modelo...")
        self._model_search.textChanged.connect(self._filter_models)
        self._model_search.installEventFilter(self)
        api_layout.addRow("Modelo:", self._model_search)

        # Model list (hidden by default)
        self._model_list = QListWidget()
        self._model_list.setMinimumHeight(250)
        self._model_list.setMaximumHeight(250)
        self._model_list.itemClicked.connect(self._on_model_clicked)
        self._model_list.hide()  # Hidden by default
        api_layout.addRow("", self._model_list)

        # Status label for loading (hidden by default)
        self._status_label = QLabel("Carregando modelos...")
        self._status_label.setStyleSheet("color: #888888;")
        self._status_label.hide()
        api_layout.addRow("", self._status_label)

        # Max iterations
        self._iteration_spin = QSpinBox()
        self._iteration_spin.setRange(1, 100)
        self._iteration_spin.setValue(10)
        self._iteration_spin.setToolTip("Limite de iteracoes que a IA pode executar por tarefa")
        api_layout.addRow("Iteracoes IA:", self._iteration_spin)

        # Chat position
        self._chat_position_combo = QComboBox()
        self._chat_position_combo.addItem("Abaixo do terminal", "bottom")
        self._chat_position_combo.addItem("A direita do terminal", "right")
        self._chat_position_combo.addItem("A esquerda do terminal", "left")
        self._chat_position_combo.setToolTip("Posicao do painel de chat em relacao ao terminal")
        api_layout.addRow("Posicao do Chat:", self._chat_position_combo)

        # Max conversations per host
        self._max_conversations_spin = QSpinBox()
        self._max_conversations_spin.setRange(1, 100)
        self._max_conversations_spin.setValue(10)
        self._max_conversations_spin.setToolTip("Quantidade maxima de conversas salvas por host (conversas antigas sao removidas automaticamente)")
        api_layout.addRow("Historico de conversas:", self._max_conversations_spin)

        # Link to OpenRouter
        link_label = QLabel('<a href="https://openrouter.ai/keys">Obter API Key no OpenRouter</a>')
        link_label.setOpenExternalLinks(True)
        api_layout.addRow("", link_label)

        layout.addWidget(api_group)

        # Storage Group
        storage_group = QGroupBox("Armazenamento de Dados")
        storage_layout = QFormLayout(storage_group)

        # Current path display
        self._data_path_label = QLabel()
        self._data_path_label.setWordWrap(True)
        self._data_path_label.setStyleSheet("color: #888888;")
        storage_layout.addRow("Local atual:", self._data_path_label)

        # Change path button
        change_path_btn = QPushButton("Alterar Local...")
        change_path_btn.setToolTip(
            "Use um caminho sincronizado (Dropbox, OneDrive, Google Drive)\n"
            "para acessar seus hosts em multiplos computadores."
        )
        change_path_btn.clicked.connect(self._on_change_data_path)
        storage_layout.addRow("", change_path_btn)

        # Security status
        self._security_label = QLabel()
        storage_layout.addRow("Seguranca:", self._security_label)

        # Change master password button
        self._change_password_btn = QPushButton("Alterar Senha Mestra...")
        self._change_password_btn.clicked.connect(self._on_change_master_password)
        storage_layout.addRow("", self._change_password_btn)

        layout.addWidget(storage_group)

        # Backup Group
        backup_group = QGroupBox("Backup")
        backup_layout = QHBoxLayout(backup_group)

        export_btn = QPushButton("Exportar Dados...")
        export_btn.setToolTip("Exportar configuracoes e hosts para arquivo")
        export_btn.clicked.connect(self._on_export)
        backup_layout.addWidget(export_btn)

        import_btn = QPushButton("Importar Dados...")
        import_btn.setToolTip("Importar configuracoes e hosts de arquivo")
        import_btn.clicked.connect(self._on_import)
        backup_layout.addWidget(import_btn)

        backup_layout.addStretch()

        layout.addWidget(backup_group)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Salvar")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        buttons_layout.addWidget(save_btn)

        layout.addLayout(buttons_layout)

        # Apply dark theme
        self._apply_dark_theme()

    def _apply_dark_theme(self) -> None:
        """Apply dark theme to dialog."""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
            QGroupBox {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin-top: 12px;
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
            QLabel {
                color: #dcdcdc;
            }
            QLineEdit, QSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px 8px;
                color: #dcdcdc;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #007acc;
            }
            QListWidget {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 3px;
                color: #dcdcdc;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #3c3c3c;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QListWidget::item:hover:!selected {
                background-color: #383838;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                color: white;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
            QLabel a {
                color: #3794ff;
            }
        """)

    def _fetch_models(self) -> None:
        """Start fetching models from OpenRouter API."""
        self._model_fetcher = ModelFetcher()
        self._model_fetcher.models_fetched.connect(self._on_models_fetched)
        self._model_fetcher.error_occurred.connect(self._on_fetch_error)
        self._model_fetcher.start()

    def _on_models_fetched(self, models: list) -> None:
        """Handle models fetched from API."""
        self._all_models = models
        self._status_label.setText(f"{len(models)} modelos disponiveis")
        self._status_label.setStyleSheet("color: #4ec9b0;")

    def _on_fetch_error(self, error: str) -> None:
        """Handle error fetching models."""
        self._status_label.setText("Erro ao carregar modelos. Verifique sua conexao ou API Key.")
        self._status_label.setStyleSheet("color: #f14c4c;")
        self._all_models = []

    def eventFilter(self, obj, event) -> bool:
        """Event filter to show model list when clicking on search field."""
        if obj == self._model_search:
            if event.type() == QEvent.Type.FocusIn:
                self._show_model_list()
        return super().eventFilter(obj, event)

    def _show_model_list(self) -> None:
        """Show the model list and populate it."""
        # Save current selection to show in placeholder
        current_model = self._model_search.property("model_id") or ""

        # Clear the search field for fresh search
        self._model_search.blockSignals(True)
        self._model_search.clear()
        if current_model:
            self._model_search.setPlaceholderText(f"Atual: {current_model} - Digite para filtrar...")
        else:
            self._model_search.setPlaceholderText("Digite para filtrar modelos...")
        self._model_search.blockSignals(False)

        self._model_list.show()
        self._status_label.show()
        self._filter_models()

        # Resize dialog to fit list
        self.adjustSize()

    def _hide_model_list(self) -> None:
        """Hide the model list."""
        self._model_list.hide()
        self._status_label.hide()
        self._model_search.setPlaceholderText("Clique para selecionar modelo...")

        # Resize dialog to compact size
        self.adjustSize()

    def _filter_models(self) -> None:
        """Filter models based on search text."""
        # Only filter if list is visible
        if not self._model_list.isVisible():
            return

        search_text = self._model_search.text().lower().strip()

        self._model_list.clear()

        for name, model_id in self._all_models:
            # Search in both name and id
            if not search_text or search_text in name.lower() or search_text in model_id.lower():
                item = QListWidgetItem(f"{name}")
                item.setData(Qt.ItemDataRole.UserRole, model_id)
                item.setToolTip(model_id)
                self._model_list.addItem(item)

        # Show count
        visible_count = self._model_list.count()
        total_count = len(self._all_models)
        if search_text:
            self._status_label.setText(f"Mostrando {visible_count} de {total_count} modelos")
        elif total_count > 0:
            self._status_label.setText(f"{total_count} modelos disponiveis")

    def _on_model_clicked(self, item: QListWidgetItem) -> None:
        """Handle model click - select and hide list."""
        model_id = item.data(Qt.ItemDataRole.UserRole)
        name = item.text()

        # Set the selected model in the search field
        self._model_search.setText(f"{name}")
        self._model_search.setProperty("model_id", model_id)

        # Hide the list
        self._hide_model_list()

        # Move focus away from search field
        self._api_key_edit.setFocus()

    def _load_current_settings(self) -> None:
        """Load current settings into the form."""
        dm = self._data_manager

        # API Key
        self._api_key_edit.setText(dm.get_api_key())

        # Model - show current model ID in search field
        current_model = dm.get_model()
        self._model_search.setText(current_model)
        self._model_search.setProperty("model_id", current_model)

        # Iterations
        self._iteration_spin.setValue(dm.get_max_iterations())

        # Chat position
        chat_position = dm.get_chat_position()
        index = self._chat_position_combo.findData(chat_position)
        if index != -1:
            self._chat_position_combo.setCurrentIndex(index)
        else:
            self._chat_position_combo.setCurrentIndex(0)

        # Max conversations per host
        self._max_conversations_spin.setValue(dm.get_max_conversations_per_host())

        # Data path
        data_path = dm.get_data_path()
        self._data_path_label.setText(str(data_path))

        # Security status
        if dm.has_master_password():
            self._security_label.setText("Com senha mestra")
            self._security_label.setStyleSheet("color: #4ec9b0;")
            self._change_password_btn.setText("Alterar Senha Mestra...")
        else:
            self._security_label.setText("Sem senha mestra (senhas em texto plano)")
            self._security_label.setStyleSheet("color: #f14c4c;")
            self._change_password_btn.setText("Definir Senha Mestra...")

    def _toggle_api_key_visibility(self) -> None:
        """Toggle API key visibility."""
        if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_key_btn.setText("Esconder")
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_key_btn.setText("Mostrar")

    def _get_selected_model_id(self) -> Optional[str]:
        """Get the selected model ID."""
        # Get from property (set when user selects from list)
        model_id = self._model_search.property("model_id")
        if model_id:
            return model_id

        # Fallback to text (if user typed manually)
        text = self._model_search.text().strip()
        return text if text else None

    def _on_save(self) -> None:
        """Save settings."""
        api_key = self._api_key_edit.text().strip()
        model = self._get_selected_model_id()

        # Validate API key
        if not api_key:
            QMessageBox.warning(
                self,
                "API Key Obrigatoria",
                "Por favor, insira sua API Key do OpenRouter.\n\n"
                "Voce pode obter uma em: https://openrouter.ai/keys"
            )
            return

        # Validate model
        if not model:
            QMessageBox.warning(
                self,
                "Modelo Obrigatorio",
                "Por favor, selecione um modelo da lista."
            )
            return

        # Update settings
        dm = self._data_manager
        dm.set_api_key(api_key)
        dm.set_model(model)
        dm.set_max_iterations(self._iteration_spin.value())
        chat_position = self._chat_position_combo.currentData()
        if chat_position:
            dm.set_chat_position(chat_position)
        dm.set_max_conversations_per_host(self._max_conversations_spin.value())

        QMessageBox.information(
            self,
            "Configuracoes Salvas",
            "As configuracoes foram salvas com sucesso."
        )
        self.accept()

    def _on_change_data_path(self) -> None:
        """Handle change data path button click."""
        current_path = self._data_manager.get_data_path().parent
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Diretorio para Dados",
            str(current_path),
            QFileDialog.Option.ShowDirsOnly
        )

        if not new_dir:
            return

        new_path = Path(new_dir)

        reply = QMessageBox.question(
            self,
            "Confirmar Alteracao",
            f"Mover dados para:\n{new_path}\n\n"
            "Os dados serao copiados para o novo local.\n"
            "Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._data_manager.set_data_path(new_path)
                self._data_path_label.setText(str(self._data_manager.get_data_path()))
                QMessageBox.information(
                    self,
                    "Sucesso",
                    "Local dos dados alterado com sucesso."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Erro",
                    f"Falha ao mover dados:\n{str(e)}"
                )

    def _on_change_master_password(self) -> None:
        """Handle change master password button click."""
        from gui.change_password_dialog import ChangePasswordDialog

        has_password = self._data_manager.has_master_password()
        dialog = ChangePasswordDialog(has_current_password=has_password, parent=self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            old_password = dialog.get_old_password()
            new_password = dialog.get_new_password()

            if self._data_manager.change_master_password(old_password, new_password):
                self._load_current_settings()  # Refresh display
                QMessageBox.information(
                    self,
                    "Sucesso",
                    "Senha mestra alterada com sucesso."
                )
            else:
                QMessageBox.critical(
                    self,
                    "Erro",
                    "Senha atual incorreta."
                )

    def _on_export(self) -> None:
        """Handle export button click."""
        from gui.export_import_dialogs import ExportDialog

        dialog = ExportDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            options = dialog.get_options()

            # Get file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Exportar Dados",
                "rb-terminal-backup.json",
                "JSON Files (*.json)"
            )

            if not file_path:
                return

            try:
                self._data_manager.export_data(
                    path=Path(file_path),
                    include_settings=options["include_settings"],
                    include_hosts=options["include_hosts"],
                    include_passwords=options["include_passwords"],
                    export_password=options.get("export_password")
                )
                QMessageBox.information(
                    self,
                    "Sucesso",
                    f"Dados exportados para:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Erro",
                    f"Falha ao exportar:\n{str(e)}"
                )

    def _on_import(self) -> None:
        """Handle import button click."""
        from gui.export_import_dialogs import ImportDialog

        # Get file path first
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar Dados",
            "",
            "JSON Files (*.json)"
        )

        if not file_path:
            return

        dialog = ImportDialog(Path(file_path), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            options = dialog.get_options()

            try:
                result = self._data_manager.import_data(
                    path=Path(file_path),
                    import_password=options.get("import_password"),
                    merge=options["merge"]
                )

                if result.success:
                    msg = f"Importacao concluida!\n\n"
                    msg += f"Hosts importados: {result.hosts_imported}\n"
                    if result.hosts_skipped > 0:
                        msg += f"Hosts ignorados: {result.hosts_skipped}\n"
                    if result.settings_imported:
                        msg += "Configuracoes importadas: Sim"

                    QMessageBox.information(self, "Sucesso", msg)
                    self._load_current_settings()  # Refresh
                else:
                    QMessageBox.critical(
                        self,
                        "Erro",
                        f"Falha ao importar:\n{result.error}"
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Erro",
                    f"Falha ao importar:\n{str(e)}"
                )

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        # Stop model fetcher if running
        if self._model_fetcher and self._model_fetcher.isRunning():
            self._model_fetcher.terminate()
            self._model_fetcher.wait()
        super().closeEvent(event)
