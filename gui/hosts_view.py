"""
Hosts view widget for displaying all hosts in card or list format.
Refactored to use HostFilterManager for filter logic.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QScrollArea, QFrame, QGridLayout
)
from PySide6.QtCore import Qt, Signal

from core.data_manager import DataManager, Host
from gui.host_card import HostCard, AddHostCard, HostsTableWidget
from gui.fields_config_dialog import FieldsConfigDialog
from gui.hosts.host_filter_manager import HostFilterManager


class FlowLayout(QGridLayout):
    """Grid layout that arranges items in a flow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(16)
        self.setContentsMargins(16, 16, 16, 16)


class HostsView(QWidget):
    """Main view for displaying and managing hosts."""

    connect_requested = Signal(str, str)  # host_id, ip (empty for fallback)
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id
    winbox_requested = Signal(str, str)  # host_id, ip
    web_access_requested = Signal(str, str)  # host_id, ip
    add_requested = Signal()
    quick_connect_requested = Signal()

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self._data_manager = data_manager
        self._view_mode = self._data_manager.get_hosts_view_mode()
        self._sort_by = self._data_manager.get_hosts_sort_by()
        self._search_text = ""
        self._host_widgets: list = []
        self._table_widget: Optional[HostsTableWidget] = None

        # Filter manager
        self._filter_manager = HostFilterManager(data_manager, self)
        self._filter_manager.filters_changed.connect(self._on_filters_changed)

        self._setup_ui()
        self._apply_style()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Hosts area (scrollable)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e1e;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._hosts_container = QWidget()
        self._hosts_container.setStyleSheet("background-color: #1e1e1e;")
        self._hosts_layout = FlowLayout(self._hosts_container)
        self._scroll_area.setWidget(self._hosts_container)

        layout.addWidget(self._scroll_area)

    def _create_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
            }
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Search field
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar hosts...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setMinimumWidth(200)
        self._search_input.setMaximumWidth(400)
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 12px;
                color: #dcdcdc;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
        """)
        layout.addWidget(self._search_input)

        # Filters button
        self._filters_btn = QPushButton("Filtros")
        self._filters_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 16px;
                color: #dcdcdc;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
            }
            QPushButton::menu-indicator {
                image: none;
            }
        """)
        self._filters_btn.clicked.connect(self._show_filters_menu)
        layout.addWidget(self._filters_btn)

        # Sort dropdown
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Nome", "name")
        self._sort_combo.addItem("IP/Host", "host")
        self._sort_combo.addItem("Porta", "port")
        self._sort_combo.addItem("Usuario", "username")
        self._sort_combo.addItem("Tipo", "device_type")
        self._sort_combo.addItem("Fabricante", "manufacturer")
        self._sort_combo.addItem("OS/Versao", "os_version")
        sort_index_map = {"name": 0, "host": 1, "port": 2, "username": 3,
                         "device_type": 4, "manufacturer": 5, "os_version": 6}
        self._sort_combo.setCurrentIndex(sort_index_map.get(self._sort_by, 0))
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self._sort_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 12px;
                color: #dcdcdc;
                min-width: 100px;
            }
            QComboBox:hover {
                background-color: #4c4c4c;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #dcdcdc;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                color: #dcdcdc;
                selection-background-color: #007acc;
            }
        """)
        layout.addWidget(self._sort_combo)

        layout.addStretch()

        # Quick connect button
        quick_btn = QPushButton("Conexao Rapida")
        quick_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 16px;
                color: #dcdcdc;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
            }
        """)
        quick_btn.clicked.connect(self.quick_connect_requested.emit)
        layout.addWidget(quick_btn)

        # Fields configuration button
        self._fields_btn = QPushButton()
        self._fields_btn.setToolTip("Configurar campos visiveis")
        self._fields_btn.setText("☰")
        self._fields_btn.clicked.connect(self._show_fields_config)
        self._fields_btn.setStyleSheet(self._get_toggle_btn_style())
        layout.addWidget(self._fields_btn)

        # View mode toggle buttons
        self._cards_btn = QPushButton()
        self._cards_btn.setToolTip("Visualizar como cards")
        self._cards_btn.setText("▦")
        self._cards_btn.setCheckable(True)
        self._cards_btn.setChecked(self._view_mode == "cards")
        self._cards_btn.clicked.connect(lambda: self._set_view_mode("cards"))
        self._cards_btn.setStyleSheet(self._get_toggle_btn_style())
        layout.addWidget(self._cards_btn)

        self._list_btn = QPushButton()
        self._list_btn.setToolTip("Visualizar como lista")
        self._list_btn.setText("≡")
        self._list_btn.setCheckable(True)
        self._list_btn.setChecked(self._view_mode == "list")
        self._list_btn.clicked.connect(lambda: self._set_view_mode("list"))
        self._list_btn.setStyleSheet(self._get_toggle_btn_style())
        layout.addWidget(self._list_btn)

        return toolbar

    def _get_toggle_btn_style(self) -> str:
        return """
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #dcdcdc;
                font-size: 16px;
                min-width: 36px;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
            }
            QPushButton:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
        """

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
            }
        """)

    def _show_filters_menu(self):
        """Show the filters menu using HostFilterManager."""
        from gui.hosts_dialog import DEFAULT_MANUFACTURERS, DEFAULT_FUNCTIONS

        menu = self._filter_manager.build_filters_menu(
            self,
            default_manufacturers=DEFAULT_MANUFACTURERS,
            default_functions=DEFAULT_FUNCTIONS
        )
        menu.exec(self._filters_btn.mapToGlobal(self._filters_btn.rect().bottomLeft()))

    def _on_filters_changed(self):
        """Handle filter changes from the filter manager."""
        self._filter_manager.update_button_style(self._filters_btn)
        self.refresh()

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._search_text = text.strip().lower()
        self.refresh()

    def _on_sort_changed(self, index: int):
        """Handle sort selection change."""
        self._sort_by = self._sort_combo.itemData(index)
        self._data_manager.set_hosts_sort_by(self._sort_by)
        self.refresh()

    def _set_view_mode(self, mode: str):
        """Set the view mode (cards or list)."""
        self._view_mode = mode
        self._data_manager.set_hosts_view_mode(mode)
        self._cards_btn.setChecked(mode == "cards")
        self._list_btn.setChecked(mode == "list")
        self.refresh()

    def _show_fields_config(self):
        """Show the fields configuration dialog."""
        dialog = FieldsConfigDialog(self._data_manager, self)
        if dialog.exec():
            self.refresh()

    def _on_column_resized(self, field: str, width: int):
        """Handle column resize from table widget."""
        self._data_manager.set_list_column_width(field, width)

    def _sort_hosts(self, hosts: list) -> list:
        """Sort hosts based on current sort setting."""
        if self._sort_by == "name":
            return sorted(hosts, key=lambda h: h.name.lower())
        elif self._sort_by == "host":
            return sorted(hosts, key=lambda h: h.host)
        elif self._sort_by == "port":
            return sorted(hosts, key=lambda h: h.port)
        elif self._sort_by == "username":
            return sorted(hosts, key=lambda h: (h.username or "zzz").lower())
        elif self._sort_by == "device_type":
            return sorted(hosts, key=lambda h: (h.device_type or "zzz").lower())
        elif self._sort_by == "manufacturer":
            return sorted(hosts, key=lambda h: (h.manufacturer or "zzz").lower())
        elif self._sort_by == "os_version":
            return sorted(hosts, key=lambda h: (h.os_version or "zzz").lower())
        return hosts

    def refresh(self):
        """Refresh the hosts display."""
        # Clear existing widgets
        for widget in self._host_widgets:
            widget.deleteLater()
        self._host_widgets.clear()

        # Clear layout
        while self._hosts_layout.count():
            item = self._hosts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get hosts and apply filters
        hosts = self._data_manager.get_hosts()
        hosts = self._filter_manager.apply_filters(hosts, self._search_text)
        hosts = self._sort_hosts(hosts)

        if self._view_mode == "cards":
            self._display_as_cards(hosts)
        else:
            self._display_as_list(hosts)

    def _display_as_cards(self, hosts: list):
        """Display hosts as cards in a grid."""
        visible_fields = self._data_manager.get_card_visible_fields()

        # Calculate columns based on width
        cols = max(1, (self.width() - 32) // 240)
        if cols < 1:
            cols = 3

        row = 0
        col = 0

        for host in hosts:
            card = HostCard(host, visible_fields=visible_fields)
            card.connect_requested.connect(self.connect_requested.emit)
            card.edit_requested.connect(self.edit_requested.emit)
            card.delete_requested.connect(self.delete_requested.emit)
            card.winbox_requested.connect(self.winbox_requested.emit)
            card.web_access_requested.connect(self.web_access_requested.emit)
            self._hosts_layout.addWidget(card, row, col)
            self._host_widgets.append(card)

            col += 1
            if col >= cols:
                col = 0
                row += 1

        # Add "Add Host" card
        add_card = AddHostCard()
        add_card.clicked.connect(self.add_requested.emit)
        self._hosts_layout.addWidget(add_card, row, col)
        self._host_widgets.append(add_card)

        # Add stretch at the end
        self._hosts_layout.setRowStretch(row + 1, 1)

    def _display_as_list(self, hosts: list):
        """Display hosts as a table using QTableWidget."""
        visible_fields = self._data_manager.get_list_visible_fields()
        column_widths = self._data_manager.get_list_column_widths()

        # Reset layout for table view
        self._hosts_layout.setSpacing(0)
        self._hosts_layout.setContentsMargins(0, 0, 0, 0)
        self._hosts_layout.setColumnStretch(0, 1)

        # Create table widget
        self._table_widget = HostsTableWidget(
            visible_fields=visible_fields,
            column_widths=column_widths
        )
        self._table_widget.set_hosts(hosts)

        # Connect signals
        self._table_widget.connect_requested.connect(self.connect_requested.emit)
        self._table_widget.edit_requested.connect(self.edit_requested.emit)
        self._table_widget.delete_requested.connect(self.delete_requested.emit)
        self._table_widget.winbox_requested.connect(self.winbox_requested.emit)
        self._table_widget.web_access_requested.connect(self.web_access_requested.emit)
        self._table_widget.column_width_changed.connect(self._on_column_resized)

        self._hosts_layout.addWidget(self._table_widget, 0, 0, 1, -1)
        self._host_widgets.append(self._table_widget)

        # Add "Add Host" button at the end
        add_btn = QPushButton("+ Adicionar Host")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 16px;
                color: #888888;
                font-size: 13px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2d2d2d;
                color: #007acc;
            }
        """)
        add_btn.clicked.connect(self.add_requested.emit)
        self._hosts_layout.addWidget(add_btn, 1, 0, 1, -1)
        self._host_widgets.append(add_btn)

        # Add stretch
        self._hosts_layout.setRowStretch(2, 1)

    def resizeEvent(self, event):
        """Handle resize to recalculate grid columns."""
        super().resizeEvent(event)
        if self._view_mode == "cards":
            self.refresh()
