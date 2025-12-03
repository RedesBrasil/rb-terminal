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
        self._selected_tags: list[str] = []
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

        # Tags filter button
        self._tags_btn = QPushButton("Tags")
        self._tags_btn.setStyleSheet("""
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
        self._tags_btn.clicked.connect(self._show_tags_menu)
        layout.addWidget(self._tags_btn)

        # Sort dropdown
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Nome", "name")
        self._sort_combo.addItem("IP", "host")
        self._sort_combo.addItem("Tipo", "device_type")
        self._sort_combo.setCurrentIndex(
            {"name": 0, "host": 1, "device_type": 2}.get(self._sort_by, 0)
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

    def _show_tags_menu(self):
        """Show menu for filtering by tags."""
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
            QMenu::item:checked {
                background-color: #0e639c;
            }
        """)

        # Get all available tags
        available_tags = self._data_manager.get_tags()

        if not available_tags:
            action = menu.addAction("Nenhuma tag disponivel")
            action.setEnabled(False)
        else:
            # Clear filter option
            clear_action = menu.addAction("Limpar filtro")
            clear_action.triggered.connect(self._clear_tag_filter)
            menu.addSeparator()

            # Tag options (checkable)
            for tag in available_tags:
                action = menu.addAction(tag)
                action.setCheckable(True)
                action.setChecked(tag in self._selected_tags)
                action.triggered.connect(lambda checked, t=tag: self._toggle_tag_filter(t, checked))

        menu.exec(self._tags_btn.mapToGlobal(self._tags_btn.rect().bottomLeft()))

    def _toggle_tag_filter(self, tag: str, checked: bool):
        """Toggle a tag in the filter."""
        if checked and tag not in self._selected_tags:
            self._selected_tags.append(tag)
        elif not checked and tag in self._selected_tags:
            self._selected_tags.remove(tag)
        self._update_tags_button()
        self.refresh()

    def _clear_tag_filter(self):
        """Clear all tag filters."""
        self._selected_tags.clear()
        self._update_tags_button()
        self.refresh()

    def _update_tags_button(self):
        """Update tags button text to show filter count."""
        if self._selected_tags:
            self._tags_btn.setText(f"Tags ({len(self._selected_tags)})")
            self._tags_btn.setStyleSheet("""
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
            self._tags_btn.setText("Tags")
            self._tags_btn.setStyleSheet("""
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
        """Filter hosts based on search text and selected tags."""
        filtered = []

        for host in hosts:
            # Search filter
            if self._search_text:
                searchable = f"{host.name} {host.host} {host.port} {host.username} {host.device_type or ''} {' '.join(host.tags)}".lower()
                if self._search_text not in searchable:
                    continue

            # Tag filter (AND logic)
            if self._selected_tags:
                if not all(tag in host.tags for tag in self._selected_tags):
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
