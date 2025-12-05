"""
Dialog for adding and editing SSH hosts.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox,
    QCheckBox, QDialogButtonBox, QMessageBox, QFrame, QWidget,
    QTextEdit, QListWidget, QListWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QSize

from core.data_manager import DataManager, Host
from core.device_types import get_device_types_manager
from gui.tags_widget import TagsWidget, ChipsWidget

logger = logging.getLogger(__name__)

# Default values for autocomplete fields
DEFAULT_MANUFACTURERS = [
    "MikroTik",
    "Huawei",
    "Linux",
    "Cisco",
    "Datacom",
]

DEFAULT_OS_VERSIONS = [
    "RouterOS v7",
    "RouterOS v6",
    "Debian 11",
]

DEFAULT_FUNCTIONS = [
    "Borda",
    "Firewall",
    "CGNAT",
    "Servidor de Logs",
    "Monitoramento",
]


class HostDialog(QDialog):
    """Dialog for adding or editing a host."""

    def __init__(
        self,
        data_manager: DataManager,
        host: Optional[Host] = None,
        parent=None
    ):
        """
        Initialize host dialog.

        Args:
            data_manager: The data manager instance
            host: Host to edit (None for new host)
            parent: Parent widget
        """
        super().__init__(parent)
        self._data_manager = data_manager
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

        # Host/IP section (multiple IPs support with drag-drop reordering)
        self._hosts_list = QListWidget()
        self._hosts_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._hosts_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._hosts_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._hosts_list.setSpacing(2)
        self._hosts_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: rgba(60, 60, 60, 0.5);
            }
        """)

        # List of host input entries
        self._host_entries = []  # List of (input, item)

        # Add first host entry (always visible, no remove button)
        self._add_host_entry(is_first=True)

        form.addRow("Host/IP:", self._hosts_list)

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

        # === Additional Info section (collapsible) ===
        self._info_toggle = QPushButton("▶ Informações Adicionais")
        self._info_toggle.setCheckable(True)
        self._info_toggle.setStyleSheet("text-align: left; padding: 5px; background: transparent; border: none; color: #888888;")
        self._info_toggle.toggled.connect(self._toggle_info_section)
        form.addRow("", self._info_toggle)

        self._info_section = QWidget()
        self._info_layout = QFormLayout()
        self._info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._info_section.setLayout(self._info_layout)
        self._info_section.setVisible(False)  # Hidden by default

        # Fabricante (editable combobox)
        self._manufacturer = QComboBox()
        self._manufacturer.setEditable(True)
        self._manufacturer.addItem("")
        # Add defaults first, then saved values (without duplicates)
        manufacturer_items = DEFAULT_MANUFACTURERS.copy()
        for saved in self._data_manager.get_manufacturers():
            if saved not in manufacturer_items:
                manufacturer_items.append(saved)
        self._manufacturer.addItems(manufacturer_items)
        self._manufacturer.setCurrentText("")
        self._manufacturer.lineEdit().setPlaceholderText("Ex: MikroTik, Cisco, Huawei...")
        self._info_layout.addRow("Fabricante:", self._manufacturer)

        # OS / Versão (editable combobox)
        self._os_version = QComboBox()
        self._os_version.setEditable(True)
        self._os_version.addItem("")
        # Add defaults first, then saved values (without duplicates)
        os_items = DEFAULT_OS_VERSIONS.copy()
        for saved in self._data_manager.get_os_versions():
            if saved not in os_items:
                os_items.append(saved)
        self._os_version.addItems(os_items)
        self._os_version.setCurrentText("")
        self._os_version.lineEdit().setPlaceholderText("Ex: RouterOS v7, Debian 11...")
        self._info_layout.addRow("OS / Versão:", self._os_version)

        # Função (chips widget - multiple values)
        def get_functions_with_defaults():
            """Get functions combining defaults with saved values."""
            items = DEFAULT_FUNCTIONS.copy()
            for saved in self._data_manager.get_functions():
                if saved not in items:
                    items.append(saved)
            return items

        self._functions_widget = ChipsWidget(
            get_available_fn=get_functions_with_defaults,
            add_value_fn=self._data_manager.add_function,
            placeholder="Adicionar função..."
        )
        self._info_layout.addRow("Função:", self._functions_widget)

        # Grupos (chips widget - multiple values)
        self._groups_widget = ChipsWidget(
            get_available_fn=self._data_manager.get_groups,
            add_value_fn=self._data_manager.add_group,
            placeholder="Adicionar grupo..."
        )
        self._info_layout.addRow("Grupos:", self._groups_widget)

        # Tags (moved from main form)
        self._tags_widget = TagsWidget()
        self._info_layout.addRow("Tags:", self._tags_widget)

        # Tipo de Dispositivo (moved from main form)
        self._device_type = QComboBox()
        self._device_type.setEditable(True)
        self._device_type.addItem("")
        self._device_type.addItems(get_device_types_manager().get_all())
        self._device_type.setCurrentText("")
        self._device_type.lineEdit().setPlaceholderText("Ex: Roteador, Switch, OLT...")
        self._info_layout.addRow("Tipo Dispositivo:", self._device_type)

        # Observações (QTextEdit for long text)
        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Notas e observações sobre este host...")
        self._notes.setMaximumHeight(80)
        self._notes.setStyleSheet("""
            QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px;
                color: #dcdcdc;
            }
            QTextEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        self._info_layout.addRow("Observações:", self._notes)

        form.addRow("", self._info_section)

        # === Advanced options section (collapsible) ===
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

        # Winbox port
        self._winbox_port = QSpinBox()
        self._winbox_port.setRange(0, 65535)
        self._winbox_port.setValue(0)
        self._winbox_port.setSpecialValueText("8291")
        self._winbox_port.setToolTip("Porta do Winbox (MikroTik). 0 = usar padrao 8291")
        self._advanced_layout.addRow("Porta Winbox:", self._winbox_port)

        # HTTP port and HTTPS checkbox
        http_layout = QHBoxLayout()
        self._http_port = QSpinBox()
        self._http_port.setRange(1, 65535)
        self._http_port.setValue(80)
        self._http_port.setToolTip("Porta HTTP para acesso web")
        http_layout.addWidget(self._http_port)

        self._https_enabled = QCheckBox("HTTPS")
        self._https_enabled.setToolTip("Usar HTTPS ao inves de HTTP")
        http_layout.addWidget(self._https_enabled)
        http_layout.addStretch()

        self._advanced_layout.addRow("Porta HTTP:", http_layout)

        form.addRow("", self._advanced_section)

        # === Port Knocking section (collapsible) ===
        self._knock_toggle = QPushButton("▶ Port Knocking")
        self._knock_toggle.setCheckable(True)
        self._knock_toggle.setStyleSheet("text-align: left; padding: 5px; background: transparent; border: none; color: #888888;")
        self._knock_toggle.toggled.connect(self._toggle_knock_section)
        form.addRow("", self._knock_toggle)

        self._knock_section = QWidget()
        self._knock_section_layout = QVBoxLayout()
        self._knock_section_layout.setContentsMargins(0, 5, 0, 5)
        self._knock_section_layout.setSpacing(5)
        self._knock_section.setLayout(self._knock_section_layout)
        self._knock_section.setVisible(False)  # Hidden by default

        # Port Knocking entries
        self._knock_entries = []  # List of (protocol_combo, port_spin, row_widget)

        # Add button row
        add_btn_row = QHBoxLayout()
        self._add_knock_btn = QPushButton("+")
        self._add_knock_btn.setFixedSize(30, 28)
        self._add_knock_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                color: #dcdcdc;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        self._add_knock_btn.clicked.connect(lambda: self._add_knock_entry())
        add_btn_row.addWidget(self._add_knock_btn)
        add_btn_row.addStretch()
        self._knock_section_layout.addLayout(add_btn_row)

        form.addRow("", self._knock_section)

        layout.addLayout(form)
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

        # Populate hosts (first entry already exists)
        hosts = self._host.hosts if self._host.hosts else []
        if hosts:
            # Set first host in existing entry
            if self._host_entries:
                self._host_entries[0][0].setText(hosts[0])
            # Add additional entries for remaining hosts
            for ip in hosts[1:]:
                self._add_host_entry(value=ip)

        self._port_input.setValue(self._host.port)
        self._user_input.setText(self._host.username)
        self._terminal_type.setCurrentText(self._host.terminal_type)
        if self._host.device_type:
            self._device_type.setCurrentText(self._host.device_type)

        # Set tags
        if self._host.tags:
            self._tags_widget.set_tags(self._host.tags)

        # Show placeholder for password if saved
        if self._host.password_encrypted:
            self._pass_input.setPlaceholderText("••••••••  (senha salva)")

        # New fields
        if self._host.manufacturer:
            self._manufacturer.setCurrentText(self._host.manufacturer)
        if self._host.os_version:
            self._os_version.setCurrentText(self._host.os_version)
        if self._host.functions:
            self._functions_widget.set_values(self._host.functions)
        if self._host.groups:
            self._groups_widget.set_values(self._host.groups)
        if self._host.notes:
            self._notes.setPlainText(self._host.notes)

        # Port knocking entries
        if self._host.port_knocking:
            for entry in self._host.port_knocking:
                self._add_knock_entry(
                    protocol=entry.get("protocol", "tcp"),
                    port=entry.get("port", 1)
                )

        # Winbox port
        if self._host.winbox_port:
            self._winbox_port.setValue(self._host.winbox_port)

        # HTTP settings
        self._http_port.setValue(self._host.http_port)
        self._https_enabled.setChecked(self._host.https_enabled)

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

    def _add_host_entry(self, value: str = "", is_first: bool = False) -> None:
        """Add a new host/IP input row."""
        # Create row widget
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(5)
        row_widget.setLayout(row_layout)

        # Drag handle (grip)
        grip_label = QLabel("⋮⋮")
        grip_label.setCursor(Qt.CursorShape.OpenHandCursor)
        grip_label.setStyleSheet("color: #888888; font-weight: bold; font-size: 14px;")
        grip_label.setFixedWidth(20)
        grip_label.setToolTip("Arraste para reordenar")
        row_layout.addWidget(grip_label)

        # Host input
        host_input = QLineEdit()
        host_input.setPlaceholderText("192.168.1.1 ou hostname")
        host_input.setText(value)
        row_layout.addWidget(host_input)

        if is_first:
            # First entry has + button only
            add_btn = QPushButton("+")
            add_btn.setFixedSize(30, 28)
            add_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    color: #dcdcdc;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """)
            add_btn.clicked.connect(lambda: self._add_host_entry())
            row_layout.addWidget(add_btn)
        else:
            # Additional entries have - button
            remove_btn = QPushButton("−")
            remove_btn.setFixedSize(30, 28)
            remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: #5a3a3a;
                    border: 1px solid #6a4a4a;
                    border-radius: 3px;
                    color: #dcdcdc;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #6a4a4a;
                }
            """)
            remove_btn.clicked.connect(lambda rw=row_widget: self._remove_host_entry(rw))
            row_layout.addWidget(remove_btn)

        # Create list item and add widget
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 36))
        self._hosts_list.addItem(item)
        self._hosts_list.setItemWidget(item, row_widget)

        # Store reference
        self._host_entries.append((host_input, item))

        # Focus the new input if not first
        if not is_first:
            host_input.setFocus()

        # Update list height
        self._update_hosts_list_height()

    def _remove_host_entry(self, row_widget: QWidget) -> None:
        """Remove a host/IP input row."""
        # Find the item by matching the widget
        for i in range(self._hosts_list.count()):
            item = self._hosts_list.item(i)
            if self._hosts_list.itemWidget(item) == row_widget:
                # Remove from entries list
                self._host_entries = [(inp, it) for inp, it in self._host_entries if it != item]
                # Remove from list widget
                self._hosts_list.takeItem(i)
                row_widget.deleteLater()
                self._update_hosts_list_height()
                break

    def _update_hosts_list_height(self) -> None:
        """Update the hosts list height based on number of items."""
        item_height = 40  # Height per item including spacing
        count = self._hosts_list.count()
        height = max(item_height, count * item_height)
        self._hosts_list.setFixedHeight(height)

    def _get_hosts_list(self) -> list:
        """Get list of hosts/IPs from input fields in current order."""
        hosts = []
        # Iterate through list widget to get correct order after drag-drop
        for i in range(self._hosts_list.count()):
            item = self._hosts_list.item(i)
            widget = self._hosts_list.itemWidget(item)
            if widget:
                # Find QLineEdit in the widget (it's the second child after the grip label)
                line_edit = widget.findChild(QLineEdit)
                if line_edit:
                    value = line_edit.text().strip()
                    if value:
                        hosts.append(value)
        return hosts

    def _toggle_info_section(self, checked: bool) -> None:
        """Toggle additional info section visibility."""
        self._info_section.setVisible(checked)
        if checked:
            self._info_toggle.setText("▼ Informações Adicionais")
        else:
            self._info_toggle.setText("▶ Informações Adicionais")
        # Adjust dialog size after toggling section
        self.adjustSize()

    def _toggle_advanced_options(self, checked: bool) -> None:
        """Toggle advanced options visibility."""
        self._advanced_section.setVisible(checked)
        if checked:
            self._advanced_toggle.setText("▼ Opções Avançadas")
        else:
            self._advanced_toggle.setText("▶ Opções Avançadas")
        # Adjust dialog size after toggling section
        self.adjustSize()

    def _toggle_knock_section(self, checked: bool) -> None:
        """Toggle port knocking section visibility."""
        self._knock_section.setVisible(checked)
        if checked:
            self._knock_toggle.setText("▼ Port Knocking")
        else:
            self._knock_toggle.setText("▶ Port Knocking")
        # Adjust dialog size after toggling section
        self.adjustSize()

    def _add_knock_entry(self, protocol: str = "tcp", port: int = 0) -> None:
        """Add a new port knocking entry row."""
        row_widget = QWidget()
        row_widget.setFixedHeight(35)
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        row_widget.setLayout(row_layout)

        # Protocol combo
        protocol_combo = QComboBox()
        protocol_combo.addItems(["tcp", "udp"])
        protocol_combo.setCurrentText(protocol)
        protocol_combo.setFixedWidth(70)
        protocol_combo.setFixedHeight(28)
        row_layout.addWidget(protocol_combo)

        # Port spinbox
        port_spin = QSpinBox()
        port_spin.setRange(1, 65535)
        port_spin.setValue(port if port > 0 else 1)
        port_spin.setFixedWidth(80)
        port_spin.setFixedHeight(28)
        row_layout.addWidget(port_spin)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(25, 28)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a3a3a;
                border: 1px solid #6a4a4a;
                border-radius: 3px;
                color: #dcdcdc;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6a4a4a;
            }
        """)
        remove_btn.clicked.connect(lambda: self._remove_knock_entry(row_widget))
        row_layout.addWidget(remove_btn)

        row_layout.addStretch()

        # Store reference and add to section layout
        self._knock_entries.append((protocol_combo, port_spin, row_widget))
        self._knock_section_layout.addWidget(row_widget)

        # Force layout update
        self.adjustSize()

    def _remove_knock_entry(self, row_widget: QWidget) -> None:
        """Remove a port knocking entry row."""
        for i, (_, _, widget) in enumerate(self._knock_entries):
            if widget == row_widget:
                self._knock_entries.pop(i)
                self._knock_section_layout.removeWidget(row_widget)
                row_widget.deleteLater()
                self.adjustSize()
                break

    def _get_knock_sequence(self) -> list:
        """Get the port knocking sequence as a list of dicts."""
        sequence = []
        for protocol_combo, port_spin, _ in self._knock_entries:
            sequence.append({
                "protocol": protocol_combo.currentText(),
                "port": port_spin.value()
            })
        return sequence

    def _on_save(self) -> None:
        """Handle save button click."""
        name = self._name_input.text().strip()
        hosts = self._get_hosts_list()
        port = self._port_input.value()
        username = self._user_input.text().strip()
        password = self._pass_input.text()
        terminal_type = self._terminal_type.currentText()
        device_type = self._device_type.currentText().strip()
        tags = self._tags_widget.get_tags()

        # New fields
        manufacturer = self._manufacturer.currentText().strip()
        os_version = self._os_version.currentText().strip()
        functions = self._functions_widget.get_values()
        groups = self._groups_widget.get_values()
        notes = self._notes.toPlainText().strip()
        port_knocking = self._get_knock_sequence()
        winbox_port = self._winbox_port.value()
        http_port = self._http_port.value()
        https_enabled = self._https_enabled.isChecked()

        # Validation
        if not name:
            QMessageBox.warning(self, "Erro", "Digite um nome para o host.")
            self._name_input.setFocus()
            return

        if not hosts:
            QMessageBox.warning(self, "Erro", "Digite pelo menos um endereço IP ou hostname.")
            if self._host_entries:
                self._host_entries[0][0].setFocus()
            return

        # Username and password are optional - will be prompted during connection if needed

        # Save custom device type if user typed a new one
        if device_type:
            get_device_types_manager().ensure_exists(device_type)

        # Save new autocomplete values
        if manufacturer:
            self._data_manager.add_manufacturer(manufacturer)
        if os_version:
            self._data_manager.add_os_version(os_version)

        try:
            if self._is_edit_mode:
                # Update existing host
                clear_password = hasattr(self, '_clear_pass_cb') and self._clear_pass_cb.isChecked()
                self._data_manager.update_host(
                    host_id=self._host.id,
                    name=name,
                    hosts=hosts,
                    port=port,
                    username=username,
                    password=password if password else None,
                    terminal_type=terminal_type,
                    device_type=device_type if device_type else None,
                    disable_terminal_detection=False,
                    clear_password=clear_password,
                    tags=tags,
                    manufacturer=manufacturer if manufacturer else None,
                    os_version=os_version if os_version else None,
                    functions=functions,
                    groups=groups,
                    notes=notes if notes else None,
                    port_knocking=port_knocking,
                    winbox_port=winbox_port,
                    http_port=http_port,
                    https_enabled=https_enabled
                )
            else:
                # Add new host
                self._data_manager.add_host(
                    name=name,
                    hosts=hosts,
                    port=port,
                    username=username,
                    password=password if password else None,
                    terminal_type=terminal_type,
                    device_type=device_type if device_type else None,
                    disable_terminal_detection=False,
                    tags=tags,
                    manufacturer=manufacturer if manufacturer else None,
                    os_version=os_version if os_version else None,
                    functions=functions,
                    groups=groups,
                    notes=notes if notes else None,
                    port_knocking=port_knocking,
                    winbox_port=winbox_port,
                    http_port=http_port,
                    https_enabled=https_enabled
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
        self._device_type.lineEdit().setPlaceholderText("Ex: Roteador, Switch, OLT...")
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
        # Adjust dialog size after toggling section
        self.adjustSize()

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
