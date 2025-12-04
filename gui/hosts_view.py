"""
Hosts view widget for displaying all hosts in card or list format.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QScrollArea, QFrame, QGridLayout, QLabel,
    QMenu, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

from core.data_manager import DataManager, Host
from gui.host_card import HostCard, HostListItem, AddHostCard


class FlowLayout(QGridLayout):
    """Grid layout that arranges items in a flow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(16)
        self.setContentsMargins(16, 16, 16, 16)


class HostsView(QWidget):
    """Main view for displaying and managing hosts."""

    connect_requested = Signal(str)  # host_id
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id
    add_requested = Signal()
    quick_connect_requested = Signal()

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self._data_manager = data_manager
        self._view_mode = self._data_manager.get_hosts_view_mode()
        self._sort_by = self._data_manager.get_hosts_sort_by()
        self._search_text = ""
        # Filter state for each category
        self._selected_tags: list[str] = []
        self._selected_manufacturers: list[str] = []
        self._selected_functions: list[str] = []
        self._selected_groups: list[str] = []
        self._host_widgets: list = []

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

        # Filters button (replaces Tags button)
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
        self._sort_combo.addItem("IP", "host")
        self._sort_combo.addItem("Tipo", "device_type")
        self._sort_combo.addItem("Fabricante", "manufacturer")
        self._sort_combo.setCurrentIndex(
            {"name": 0, "host": 1, "device_type": 2, "manufacturer": 3}.get(self._sort_by, 0)
        )
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

    def _get_menu_style(self) -> str:
        """Get common menu stylesheet."""
        return """
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
            QMenu::item:checked {
                background-color: #0e639c;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555555;
                margin: 4px 8px;
            }
        """

    def _show_filters_menu(self):
        """Show menu for filtering by multiple categories."""
        menu = QMenu(self)
        menu.setStyleSheet(self._get_menu_style())

        # Clear all filters option
        total_filters = (len(self._selected_tags) + len(self._selected_manufacturers) +
                        len(self._selected_functions) + len(self._selected_groups))
        if total_filters > 0:
            clear_action = menu.addAction("✕ Limpar todos os filtros")
            clear_action.triggered.connect(self._clear_all_filters)
            menu.addSeparator()

        # Tags submenu
        tags_menu = menu.addMenu(f"Tags" + (f" ({len(self._selected_tags)})" if self._selected_tags else ""))
        tags_menu.setStyleSheet(self._get_menu_style())
        self._populate_filter_submenu(
            tags_menu,
            self._data_manager.get_tags(),
            self._selected_tags,
            self._toggle_tag_filter
        )

        # Fabricantes submenu
        manufacturers_menu = menu.addMenu(f"Fabricante" + (f" ({len(self._selected_manufacturers)})" if self._selected_manufacturers else ""))
        manufacturers_menu.setStyleSheet(self._get_menu_style())
        # Combine defaults with saved manufacturers
        from gui.hosts_dialog import DEFAULT_MANUFACTURERS
        all_manufacturers = list(DEFAULT_MANUFACTURERS)
        for m in self._data_manager.get_manufacturers():
            if m not in all_manufacturers:
                all_manufacturers.append(m)
        self._populate_filter_submenu(
            manufacturers_menu,
            all_manufacturers,
            self._selected_manufacturers,
            self._toggle_manufacturer_filter
        )

        # Funções submenu
        functions_menu = menu.addMenu(f"Função" + (f" ({len(self._selected_functions)})" if self._selected_functions else ""))
        functions_menu.setStyleSheet(self._get_menu_style())
        # Combine defaults with saved functions
        from gui.hosts_dialog import DEFAULT_FUNCTIONS
        all_functions = list(DEFAULT_FUNCTIONS)
        for f in self._data_manager.get_functions():
            if f not in all_functions:
                all_functions.append(f)
        self._populate_filter_submenu(
            functions_menu,
            all_functions,
            self._selected_functions,
            self._toggle_function_filter
        )

        # Grupos submenu
        groups_menu = menu.addMenu(f"Grupos" + (f" ({len(self._selected_groups)})" if self._selected_groups else ""))
        groups_menu.setStyleSheet(self._get_menu_style())
        self._populate_filter_submenu(
            groups_menu,
            self._data_manager.get_groups(),
            self._selected_groups,
            self._toggle_group_filter
        )

        menu.exec(self._filters_btn.mapToGlobal(self._filters_btn.rect().bottomLeft()))

    def _populate_filter_submenu(self, menu: QMenu, available: list, selected: list, toggle_fn):
        """Populate a filter submenu with checkable items."""
        if not available:
            action = menu.addAction("Nenhum disponível")
            action.setEnabled(False)
            return

        # Clear this category option
        if selected:
            clear_action = menu.addAction("✕ Limpar")
            clear_action.triggered.connect(lambda: self._clear_category_filter(selected))
            menu.addSeparator()

        for item in available:
            action = menu.addAction(item)
            action.setCheckable(True)
            action.setChecked(item in selected)
            action.triggered.connect(lambda checked, i=item: toggle_fn(i, checked))

    def _toggle_tag_filter(self, tag: str, checked: bool):
        """Toggle a tag in the filter."""
        if checked and tag not in self._selected_tags:
            self._selected_tags.append(tag)
        elif not checked and tag in self._selected_tags:
            self._selected_tags.remove(tag)
        self._update_filters_button()
        self.refresh()

    def _toggle_manufacturer_filter(self, manufacturer: str, checked: bool):
        """Toggle a manufacturer in the filter."""
        if checked and manufacturer not in self._selected_manufacturers:
            self._selected_manufacturers.append(manufacturer)
        elif not checked and manufacturer in self._selected_manufacturers:
            self._selected_manufacturers.remove(manufacturer)
        self._update_filters_button()
        self.refresh()

    def _toggle_function_filter(self, function: str, checked: bool):
        """Toggle a function in the filter."""
        if checked and function not in self._selected_functions:
            self._selected_functions.append(function)
        elif not checked and function in self._selected_functions:
            self._selected_functions.remove(function)
        self._update_filters_button()
        self.refresh()

    def _toggle_group_filter(self, group: str, checked: bool):
        """Toggle a group in the filter."""
        if checked and group not in self._selected_groups:
            self._selected_groups.append(group)
        elif not checked and group in self._selected_groups:
            self._selected_groups.remove(group)
        self._update_filters_button()
        self.refresh()

    def _clear_category_filter(self, selected_list: list):
        """Clear a specific category filter."""
        selected_list.clear()
        self._update_filters_button()
        self.refresh()

    def _clear_all_filters(self):
        """Clear all filters."""
        self._selected_tags.clear()
        self._selected_manufacturers.clear()
        self._selected_functions.clear()
        self._selected_groups.clear()
        self._update_filters_button()
        self.refresh()

    def _update_filters_button(self):
        """Update filters button text to show filter count."""
        total = (len(self._selected_tags) + len(self._selected_manufacturers) +
                len(self._selected_functions) + len(self._selected_groups))
        if total > 0:
            self._filters_btn.setText(f"Filtros ({total})")
            self._filters_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0e639c;
                    border: 1px solid #007acc;
                    border-radius: 4px;
                    padding: 8px 16px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #1177bb;
                }
            """)
        else:
            self._filters_btn.setText("Filtros")
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
            """)

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

    def _filter_hosts(self, hosts: list[Host]) -> list[Host]:
        """Filter hosts based on search text and selected filters."""
        filtered = []

        for host in hosts:
            # Search filter - includes all host fields except password and terminal_type
            if self._search_text:
                searchable_parts = [
                    host.id,
                    host.name,
                    host.host,
                    str(host.port),
                    host.username,
                    host.device_type or '',
                    host.manufacturer or '',
                    host.os_version or '',
                    ' '.join(host.tags),
                    ' '.join(host.functions),
                    ' '.join(host.groups),
                    host.notes or '',
                    host.created_at or '',
                ]
                searchable = ' '.join(searchable_parts).lower()
                if self._search_text not in searchable:
                    continue

            # Tag filter (AND logic - host must have ALL selected tags)
            if self._selected_tags:
                if not all(tag in host.tags for tag in self._selected_tags):
                    continue

            # Manufacturer filter (OR logic - host must have ANY selected manufacturer)
            if self._selected_manufacturers:
                if not host.manufacturer or host.manufacturer not in self._selected_manufacturers:
                    continue

            # Function filter (AND logic - host must have ALL selected functions)
            if self._selected_functions:
                if not all(func in host.functions for func in self._selected_functions):
                    continue

            # Group filter (AND logic - host must have ALL selected groups)
            if self._selected_groups:
                if not all(group in host.groups for group in self._selected_groups):
                    continue

            filtered.append(host)

        return filtered

    def _sort_hosts(self, hosts: list[Host]) -> list[Host]:
        """Sort hosts based on current sort setting."""
        if self._sort_by == "name":
            return sorted(hosts, key=lambda h: h.name.lower())
        elif self._sort_by == "host":
            return sorted(hosts, key=lambda h: h.host)
        elif self._sort_by == "device_type":
            return sorted(hosts, key=lambda h: (h.device_type or "zzz").lower())
        elif self._sort_by == "manufacturer":
            return sorted(hosts, key=lambda h: (h.manufacturer or "zzz").lower())
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

        # Get filtered and sorted hosts
        hosts = self._data_manager.get_hosts()
        hosts = self._filter_hosts(hosts)
        hosts = self._sort_hosts(hosts)

        if self._view_mode == "cards":
            self._display_as_cards(hosts)
        else:
            self._display_as_list(hosts)

    def _display_as_cards(self, hosts: list[Host]):
        """Display hosts as cards in a grid."""
        # Calculate columns based on width
        cols = max(1, (self.width() - 32) // 240)
        if cols < 1:
            cols = 3  # Default

        row = 0
        col = 0

        for host in hosts:
            card = HostCard(host)
            card.connect_requested.connect(self.connect_requested.emit)
            card.edit_requested.connect(self.edit_requested.emit)
            card.delete_requested.connect(self.delete_requested.emit)
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

    def _display_as_list(self, hosts: list[Host]):
        """Display hosts as a list."""
        # Reset to vertical layout for list view
        self._hosts_layout.setSpacing(0)
        self._hosts_layout.setContentsMargins(0, 0, 0, 0)

        row = 0
        for host in hosts:
            item = HostListItem(host)
            item.connect_requested.connect(self.connect_requested.emit)
            item.edit_requested.connect(self.edit_requested.emit)
            item.delete_requested.connect(self.delete_requested.emit)
            self._hosts_layout.addWidget(item, row, 0, 1, -1)
            self._host_widgets.append(item)
            row += 1

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
        self._hosts_layout.addWidget(add_btn, row, 0, 1, -1)
        self._host_widgets.append(add_btn)

        # Add stretch
        self._hosts_layout.setRowStretch(row + 1, 1)

    def resizeEvent(self, event):
        """Handle resize to recalculate grid columns."""
        super().resizeEvent(event)
        if self._view_mode == "cards":
            self.refresh()
