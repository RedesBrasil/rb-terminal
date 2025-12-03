"""
Dialog for adding and editing SSH hosts.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox,
    QCheckBox, QDialogButtonBox, QMessageBox, QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal

from core.hosts import Host, HostsManager
from core.device_types import get_device_types_manager

logger = logging.getLogger(__name__)


class HostDialog(QDialog):
    """Dialog for adding or editing a host."""

    def __init__(
        self,
        hosts_manager: HostsManager,
        host: Optional[Host] = None,
        parent=None
    ):
        """
        Initialize host dialog.

        Args:
            hosts_manager: The hosts manager instance
            host: Host to edit (None for new host)
            parent: Parent widget
        """
        super().__init__(parent)
        self._hosts_manager = hosts_manager
        self._host = host
        self._is_edit_mode = host is not None

        self._setup_ui()
        self._apply_style()

        if self._is_edit_mode:
            self._populate_fields()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        title = "Editar Host" if self._is_edit_mode else "Adicionar Host"
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Form layout
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Ex: Mikrotik Principal")
        form.addRow("Nome:", self._name_input)

        # Host
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("192.168.1.1")
        form.addRow("Host/IP:", self._host_input)

        # Port
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        form.addRow("Porta:", self._port_input)

        # Username
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("Opcional - pedido no terminal se vazio")
        form.addRow("Usuário:", self._user_input)

        # Password section
        password_layout = QVBoxLayout()

        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_input.setPlaceholderText("Opcional - pedido no terminal se vazio")
        password_layout.addWidget(self._pass_input)

        # Show password checkbox
        self._show_pass_cb = QCheckBox("Mostrar senha")
        self._show_pass_cb.toggled.connect(self._toggle_password_visibility)
        password_layout.addWidget(self._show_pass_cb)

        # Clear password option (only in edit mode)
        if self._is_edit_mode:
            self._clear_pass_cb = QCheckBox("Remover senha salva")
            self._clear_pass_cb.toggled.connect(self._on_clear_password_toggled)
            password_layout.addWidget(self._clear_pass_cb)

        form.addRow("Senha:", password_layout)

        # Device type (editable combobox)
        self._device_type = QComboBox()
        self._device_type.setEditable(True)
        self._device_type.addItem("")  # Empty option for optional field
        self._device_type.addItems(get_device_types_manager().get_all())
        self._device_type.setCurrentText("")
        self._device_type.lineEdit().setPlaceholderText("Ex: Linux, MikroTik, Cisco...")
        form.addRow("Tipo Dispositivo:", self._device_type)

        # Advanced options section (collapsible)
        self._advanced_toggle = QPushButton("▶ Opções Avançadas")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setStyleSheet("text-align: left; padding: 5px; background: transparent; border: none; color: #888888;")
        self._advanced_toggle.toggled.connect(self._toggle_advanced_options)
        form.addRow("", self._advanced_toggle)

        self._advanced_section = QWidget()
        self._advanced_layout = QFormLayout()
        self._advanced_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._advanced_section.setLayout(self._advanced_layout)
        self._advanced_section.setVisible(False)  # Hidden by default

        # Terminal type (moved to advanced)
        self._terminal_type = QComboBox()
        self._terminal_type.addItems(["xterm", "xterm-256color", "vt100"])
        self._terminal_type.setCurrentText("xterm")  # Default to "xterm"
        self._advanced_layout.addRow("Tipo Terminal:", self._terminal_type)

        form.addRow("", self._advanced_section)

        layout.addLayout(form)

        # Info label
        info_label = QLabel(
            "Dica: Usuário e senha são opcionais - o terminal pedirá se não fornecidos.\n"
            "O tipo de dispositivo ajuda a IA a usar comandos apropriados."
        )
        info_label.setStyleSheet("color: #888888; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _apply_style(self) -> None:
        """Apply dark theme style."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #dcdcdc;
            }
            QLabel {
                color: #dcdcdc;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px;
                color: #dcdcdc;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #007acc;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #dcdcdc;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                color: #dcdcdc;
                selection-background-color: #007acc;
            }
            QCheckBox {
                color: #dcdcdc;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 3px;
                padding: 8px 16px;
                color: white;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
            QDialogButtonBox QPushButton[text="Cancel"] {
                background-color: #555555;
            }
            QDialogButtonBox QPushButton[text="Cancel"]:hover {
                background-color: #666666;
            }
        """)

    def _populate_fields(self) -> None:
        """Populate fields with existing host data."""
        if not self._host:
            return

        self._name_input.setText(self._host.name)
        self._host_input.setText(self._host.host)
        self._port_input.setValue(self._host.port)
        self._user_input.setText(self._host.username)
        self._terminal_type.setCurrentText(self._host.terminal_type)
        if self._host.device_type:
            self._device_type.setCurrentText(self._host.device_type)

        # Show placeholder for password if saved
        if self._host.password_encrypted:
            self._pass_input.setPlaceholderText("••••••••  (senha salva)")

    def _toggle_password_visibility(self, checked: bool) -> None:
        """Toggle password visibility."""
        if checked:
            self._pass_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_clear_password_toggled(self, checked: bool) -> None:
        """Handle clear password checkbox toggle."""
        self._pass_input.setEnabled(not checked)
        if checked:
            self._pass_input.clear()

    def _toggle_advanced_options(self, checked: bool) -> None:
        """Toggle advanced options visibility."""
        self._advanced_section.setVisible(checked)
        if checked:
            self._advanced_toggle.setText("▼ Opções Avançadas")
        else:
            self._advanced_toggle.setText("▶ Opções Avançadas")

    def _on_save(self) -> None:
        """Handle save button click."""
        name = self._name_input.text().strip()
        host = self._host_input.text().strip()
        port = self._port_input.value()
        username = self._user_input.text().strip()
        password = self._pass_input.text()
        terminal_type = self._terminal_type.currentText()
        device_type = self._device_type.currentText().strip()

        # Validation
        if not name:
            QMessageBox.warning(self, "Erro", "Digite um nome para o host.")
            self._name_input.setFocus()
            return

        if not host:
            QMessageBox.warning(self, "Erro", "Digite o endereço IP ou hostname.")
            self._host_input.setFocus()
            return

        # Username and password are optional - will be prompted during connection if needed

        # Save custom device type if user typed a new one
        if device_type:
            get_device_types_manager().ensure_exists(device_type)

        try:
            if self._is_edit_mode:
                # Update existing host
                clear_password = hasattr(self, '_clear_pass_cb') and self._clear_pass_cb.isChecked()
                self._hosts_manager.update(
                    host_id=self._host.id,
                    name=name,
                    host=host,
                    port=port,
                    username=username,
                    password=password if password else None,
                    terminal_type=terminal_type,
                    device_type=device_type if device_type else None,
                    disable_terminal_detection=False,
                    clear_password=clear_password
                )
            else:
                # Add new host
                self._hosts_manager.add(
                    name=name,
                    host=host,
                    port=port,
                    username=username,
                    password=password if password else None,
                    terminal_type=terminal_type,
                    device_type=device_type if device_type else None,
                    disable_terminal_detection=False
                )

            self.accept()

        except Exception as e:
            logger.error(f"Failed to save host: {e}")
            QMessageBox.critical(
                self,
                "Erro",
                f"Erro ao salvar host:\n{str(e)}"
            )


class PasswordPromptDialog(QDialog):
    """Dialog to prompt for password when connecting to a host without saved password."""

    def __init__(self, host_name: str, parent=None):
        """
        Initialize password prompt dialog.

        Args:
            host_name: Name of the host for display
            parent: Parent widget
        """
        super().__init__(parent)
        self._password = ""
        self._setup_ui(host_name)
        self._apply_style()

    def _setup_ui(self, host_name: str) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Senha Necessária")
        self.setMinimumWidth(350)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Info label
        label = QLabel(f"Digite a senha para conectar em:\n{host_name}")
        label.setWordWrap(True)
        layout.addWidget(label)

        layout.addSpacing(10)

        # Password input
        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_input.setPlaceholderText("Senha")
        self._pass_input.returnPressed.connect(self._on_ok)
        layout.addWidget(self._pass_input)

        # Show password checkbox
        show_pass = QCheckBox("Mostrar senha")
        show_pass.toggled.connect(
            lambda c: self._pass_input.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(show_pass)

        layout.addSpacing(10)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Conectar")
        ok_btn.clicked.connect(self._on_ok)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

        # Focus password input
        self._pass_input.setFocus()

    def _apply_style(self) -> None:
        """Apply dark theme style."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #dcdcdc;
            }
            QLabel {
                color: #dcdcdc;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 8px;
                color: #dcdcdc;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QCheckBox {
                color: #888888;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 3px;
                padding: 8px 16px;
                color: white;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def _on_ok(self) -> None:
        """Handle OK button click."""
        self._password = self._pass_input.text()
        self.accept()

    def get_password(self) -> str:
        """Get the entered password."""
        return self._password


class QuickConnectDialog(QDialog):
    """Dialog for quick connection without saving the host."""

    def __init__(self, parent=None):
        """Initialize quick connect dialog."""
        super().__init__(parent)
        self._connection_data = {}
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Conexao Rapida")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Info label
        info = QLabel("Conectar sem salvar o host")
        info.setStyleSheet("color: #888888; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(info)

        # Form layout
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Host
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("192.168.1.1")
        form.addRow("Host/IP:", self._host_input)

        # Port
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        form.addRow("Porta:", self._port_input)

        # Username
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("Opcional - pedido no terminal se vazio")
        form.addRow("Usuario:", self._user_input)

        # Password
        password_layout = QVBoxLayout()
        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_input.setPlaceholderText("Opcional - pedido no terminal se vazio")
        password_layout.addWidget(self._pass_input)

        show_pass = QCheckBox("Mostrar senha")
        show_pass.toggled.connect(
            lambda c: self._pass_input.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password
            )
        )
        password_layout.addWidget(show_pass)
        form.addRow("Senha:", password_layout)

        # Device type (editable combobox)
        self._device_type = QComboBox()
        self._device_type.setEditable(True)
        self._device_type.addItem("")  # Empty option for optional field
        self._device_type.addItems(get_device_types_manager().get_all())
        self._device_type.setCurrentText("")
        self._device_type.lineEdit().setPlaceholderText("Ex: Linux, MikroTik, Cisco...")
        form.addRow("Tipo Dispositivo:", self._device_type)

        # Advanced options section (collapsible)
        self._advanced_toggle = QPushButton("▶ Opções Avançadas")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setStyleSheet("text-align: left; padding: 5px; background: transparent; border: none; color: #888888;")
        self._advanced_toggle.toggled.connect(self._toggle_advanced_options)
        form.addRow("", self._advanced_toggle)

        self._advanced_section = QWidget()
        self._advanced_layout = QFormLayout()
        self._advanced_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._advanced_section.setLayout(self._advanced_layout)
        self._advanced_section.setVisible(False)  # Hidden by default

        # Terminal type (moved to advanced)
        self._terminal_type = QComboBox()
        self._terminal_type.addItems(["xterm", "xterm-256color", "vt100"])
        self._terminal_type.setCurrentText("xterm")  # Default to "xterm"
        self._advanced_layout.addRow("Tipo Terminal:", self._terminal_type)

        form.addRow("", self._advanced_section)

        layout.addLayout(form)
        layout.addSpacing(15)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("background-color: #555555;")
        button_layout.addWidget(cancel_btn)

        connect_btn = QPushButton("Conectar")
        connect_btn.clicked.connect(self._on_connect)
        connect_btn.setDefault(True)
        button_layout.addWidget(connect_btn)

        layout.addLayout(button_layout)

        # Enter key triggers connect
        self._pass_input.returnPressed.connect(self._on_connect)

        # Focus host input
        self._host_input.setFocus()

    def _apply_style(self) -> None:
        """Apply dark theme style."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #dcdcdc;
            }
            QLabel {
                color: #dcdcdc;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px;
                color: #dcdcdc;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #007acc;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #dcdcdc;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                color: #dcdcdc;
                selection-background-color: #007acc;
            }
            QCheckBox {
                color: #888888;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 3px;
                padding: 8px 16px;
                color: white;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def _toggle_advanced_options(self, checked: bool) -> None:
        """Toggle advanced options visibility."""
        self._advanced_section.setVisible(checked)
        if checked:
            self._advanced_toggle.setText("▼ Opções Avançadas")
        else:
            self._advanced_toggle.setText("▶ Opções Avançadas")

    def _on_connect(self) -> None:
        """Handle connect button click."""
        host = self._host_input.text().strip()
        username = self._user_input.text().strip()
        device_type = self._device_type.currentText().strip()

        if not host:
            QMessageBox.warning(self, "Erro", "Digite o endereco IP ou hostname.")
            self._host_input.setFocus()
            return

        # Username and password are optional - will be prompted during connection if needed

        # Save custom device type if user typed a new one
        if device_type:
            get_device_types_manager().ensure_exists(device_type)

        self._connection_data = {
            "host": host,
            "port": self._port_input.value(),
            "username": username,
            "password": self._pass_input.text(),
            "terminal_type": self._terminal_type.currentText(),
            "device_type": device_type if device_type else None
        }
        self.accept()

    def get_connection_data(self) -> dict:
        """Get the connection data entered by user."""
        return self._connection_data
