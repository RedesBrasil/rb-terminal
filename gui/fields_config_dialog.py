"""
Dialog for configuring visible fields in hosts view.
"""

from typing import List, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QListWidget, QListWidgetItem, QPushButton, QDialogButtonBox,
    QLabel, QAbstractItemView
)
from PySide6.QtCore import Qt

from core.data_manager import DataManager


# Field definitions: (id, display_name)
AVAILABLE_FIELDS = [
    ("name", "Nome"),
    ("host", "IP/Host"),
    ("port", "Porta"),
    ("username", "Usuario"),
    ("tags", "Tags"),
    ("device_type", "Tipo Dispositivo"),
    ("manufacturer", "Fabricante"),
    ("os_version", "OS/Versao"),
    ("functions", "Funcoes"),
    ("groups", "Grupos"),
]

# Default fields for each view
DEFAULT_CARD_FIELDS = ["name", "host", "tags", "device_type"]
DEFAULT_LIST_FIELDS = ["name", "host", "port", "username", "tags", "device_type", "manufacturer"]


class FieldsConfigDialog(QDialog):
    """Dialog for configuring visible fields in card and list views."""

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self._data_manager = data_manager
        self._setup_ui()
        self._apply_style()
        self._load_current_config()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("Configurar Campos Visiveis")
        self.setMinimumWidth(350)
        self.setMinimumHeight(450)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Instructions
        info = QLabel("Marque os campos que deseja exibir.\nArraste para reordenar.")
        info.setStyleSheet("color: #888888; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(info)

        # Tab widget for Cards and List
        self._tab_widget = QTabWidget()
        layout.addWidget(self._tab_widget)

        # Cards tab
        cards_widget = QWidget()
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.setContentsMargins(5, 10, 5, 5)

        self._cards_list = self._create_field_list()
        cards_layout.addWidget(self._cards_list)

        cards_reset_btn = QPushButton("Restaurar Padrao")
        cards_reset_btn.clicked.connect(self._reset_cards)
        cards_reset_btn.setStyleSheet("background-color: #555555;")
        cards_layout.addWidget(cards_reset_btn)

        self._tab_widget.addTab(cards_widget, "Cards")

        # List tab
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(5, 10, 5, 5)

        self._list_list = self._create_field_list()
        list_layout.addWidget(self._list_list)

        list_reset_btn = QPushButton("Restaurar Padrao")
        list_reset_btn.clicked.connect(self._reset_list)
        list_reset_btn.setStyleSheet("background-color: #555555;")
        list_layout.addWidget(list_reset_btn)

        self._tab_widget.addTab(list_widget, "Lista")

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_field_list(self) -> QListWidget:
        """Create a list widget with drag-and-drop support."""
        list_widget = QListWidget()
        list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        return list_widget

    def _populate_list(self, list_widget: QListWidget, visible_fields: List[str]) -> None:
        """Populate a list widget with fields."""
        list_widget.clear()

        # Build ordered list: visible fields first (in order), then remaining fields
        field_map = {f[0]: f[1] for f in AVAILABLE_FIELDS}
        all_field_ids = [f[0] for f in AVAILABLE_FIELDS]

        # Add visible fields in their order
        ordered_fields = []
        for field_id in visible_fields:
            if field_id in field_map:
                ordered_fields.append(field_id)

        # Add remaining fields not in visible list
        for field_id in all_field_ids:
            if field_id not in ordered_fields:
                ordered_fields.append(field_id)

        # Create list items
        for field_id in ordered_fields:
            display_name = field_map.get(field_id, field_id)

            # Mark "name" as required
            if field_id == "name":
                display_name = f"{display_name} (obrigatorio)"

            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, field_id)

            # Set checkable
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            # "name" is always checked and cannot be unchecked
            if field_id == "name":
                item.setCheckState(Qt.CheckState.Checked)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            else:
                if field_id in visible_fields:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)

            list_widget.addItem(item)

    def _get_fields_from_list(self, list_widget: QListWidget) -> List[str]:
        """Get ordered list of checked field IDs from a list widget."""
        fields = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                field_id = item.data(Qt.ItemDataRole.UserRole)
                fields.append(field_id)
        return fields

    def _load_current_config(self) -> None:
        """Load current configuration from data manager."""
        card_fields = self._data_manager.get_card_visible_fields()
        list_fields = self._data_manager.get_list_visible_fields()

        self._populate_list(self._cards_list, card_fields)
        self._populate_list(self._list_list, list_fields)

    def _reset_cards(self) -> None:
        """Reset cards to default fields."""
        self._populate_list(self._cards_list, DEFAULT_CARD_FIELDS)

    def _reset_list(self) -> None:
        """Reset list to default fields."""
        self._populate_list(self._list_list, DEFAULT_LIST_FIELDS)

    def _on_save(self) -> None:
        """Save configuration."""
        card_fields = self._get_fields_from_list(self._cards_list)
        list_fields = self._get_fields_from_list(self._list_list)

        self._data_manager.set_card_visible_fields(card_fields)
        self._data_manager.set_list_visible_fields(list_fields)

        self.accept()

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
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #2d2d2d;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #dcdcdc;
                padding: 8px 20px;
                border: 1px solid #3c3c3c;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2d2d2d;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab:hover:!selected {
                background-color: #454545;
            }
            QListWidget {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                color: #dcdcdc;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px 5px;
                border-bottom: 1px solid #454545;
            }
            QListWidget::item:selected {
                background-color: #454545;
            }
            QListWidget::item:hover {
                background-color: #404040;
            }
            QListWidget::indicator {
                width: 16px;
                height: 16px;
            }
            QListWidget::indicator:unchecked {
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #3c3c3c;
            }
            QListWidget::indicator:checked {
                border: 1px solid #007acc;
                border-radius: 3px;
                background-color: #007acc;
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
