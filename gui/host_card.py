"""
Host card widget for displaying a host in card or list format.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSizePolicy, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent

from core.data_manager import Host


# Field display names
FIELD_LABELS = {
    "name": "Nome",
    "host": "IP/Host",
    "port": "Porta",
    "username": "Usuario",
    "tags": "Tags",
    "device_type": "Tipo",
    "manufacturer": "Fabricante",
    "os_version": "OS/Versao",
    "functions": "Funcoes",
    "groups": "Grupos",
}

# Column widths for table view (0 = stretch)
FIELD_WIDTHS = {
    "name": 0,  # Stretch
    "host": 180,
    "port": 60,
    "username": 100,
    "tags": 180,
    "device_type": 100,
    "manufacturer": 100,
    "os_version": 90,
    "functions": 120,
    "groups": 120,
}


class TagLabel(QLabel):
    """Small tag label for display in cards."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QLabel {
                background-color: #0e639c;
                color: white;
                padding: 2px 6px;
                border-radius: 8px;
                font-size: 10px;
            }
        """)


class HostCard(QFrame):
    """Card widget for displaying a host."""

    connect_requested = Signal(str, str)  # host_id, ip (empty for fallback)
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id
    winbox_requested = Signal(str, str)  # host_id, ip
    web_access_requested = Signal(str, str)  # host_id, ip

    def __init__(self, host: Host, visible_fields: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self._host = host
        self._visible_fields = visible_fields or ["name", "host", "tags", "device_type"]
        self._setup_ui()
        self._apply_style()

    def _get_field_value(self, field: str) -> str:
        """Get display value for a field."""
        if field == "name":
            return self._host.name
        elif field == "host":
            extra_ips = len(self._host.hosts) - 1 if self._host.hosts else 0
            text = f"{self._host.host}:{self._host.port}"
            if extra_ips > 0:
                text += f" (+{extra_ips})"
            return text
        elif field == "port":
            return str(self._host.port)
        elif field == "username":
            return self._host.username or "-"
        elif field == "device_type":
            return self._host.device_type or ""
        elif field == "manufacturer":
            return self._host.manufacturer or ""
        elif field == "os_version":
            return self._host.os_version or ""
        elif field == "functions":
            return ", ".join(self._host.functions) if self._host.functions else ""
        elif field == "groups":
            return ", ".join(self._host.groups) if self._host.groups else ""
        return ""

    def _setup_ui(self):
        self.setFixedSize(220, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        for field in self._visible_fields:
            if field == "name":
                # Host name - always bold and prominent
                name_label = QLabel(self._host.name)
                name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
                name_label.setWordWrap(True)
                layout.addWidget(name_label)

            elif field == "host":
                # Host address with port
                address_label = QLabel(self._get_field_value("host"))
                address_label.setStyleSheet("font-size: 12px; color: #888888;")
                layout.addWidget(address_label)

            elif field == "tags":
                # Tags as colored badges
                if self._host.tags:
                    tags_layout = QHBoxLayout()
                    tags_layout.setContentsMargins(0, 4, 0, 0)
                    tags_layout.setSpacing(4)

                    for tag in self._host.tags[:3]:
                        tag_label = TagLabel(tag)
                        tags_layout.addWidget(tag_label)

                    if len(self._host.tags) > 3:
                        more_label = QLabel(f"+{len(self._host.tags) - 3}")
                        more_label.setStyleSheet("color: #888888; font-size: 10px;")
                        tags_layout.addWidget(more_label)

                    tags_layout.addStretch()
                    layout.addLayout(tags_layout)

            elif field in ("device_type", "manufacturer", "os_version", "port", "username", "functions", "groups"):
                # Other fields as simple text
                value = self._get_field_value(field)
                if value:
                    field_label = QLabel(value)
                    field_label.setStyleSheet("font-size: 11px; color: #666666;")
                    layout.addWidget(field_label)

        layout.addStretch()

    def _apply_style(self):
        self.setStyleSheet("""
            HostCard {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
            }
            HostCard:hover {
                background-color: #353535;
                border-color: #007acc;
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
        """

    def _create_ip_submenu(self, parent_menu: QMenu, action_name: str, signal) -> None:
        """Create a submenu with IP options or simple action if only one IP."""
        hosts = self._host.hosts if self._host.hosts else []

        if len(hosts) <= 1:
            # Single IP - simple action
            action = parent_menu.addAction(action_name)
            action.triggered.connect(lambda: signal.emit(self._host.id, ""))
        else:
            # Multiple IPs - create submenu
            submenu = parent_menu.addMenu(action_name)
            submenu.setStyleSheet(self._get_menu_style())

            for ip in hosts:
                ip_action = submenu.addAction(ip)
                ip_action.triggered.connect(lambda checked, addr=ip: signal.emit(self._host.id, addr))

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._get_menu_style())

        # SSH/Connect with IP submenu
        self._create_ip_submenu(menu, "Acesso SSH", self.connect_requested)

        # Winbox with IP submenu
        self._create_ip_submenu(menu, "Winbox", self.winbox_requested)

        # Web access with IP submenu
        self._create_ip_submenu(menu, "Acesso Web", self.web_access_requested)

        menu.addSeparator()

        edit_action = menu.addAction("Editar")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self._host.id))

        delete_action = menu.addAction("Excluir")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self._host.id))

        menu.exec(self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.connect_requested.emit(self._host.id, "")  # Empty = use fallback
        super().mouseDoubleClickEvent(event)

    @property
    def host(self) -> Host:
        return self._host


class HostListItem(QFrame):
    """List item widget for displaying a host in list/table view."""

    connect_requested = Signal(str, str)  # host_id, ip (empty for fallback)
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id
    winbox_requested = Signal(str, str)  # host_id, ip
    web_access_requested = Signal(str, str)  # host_id, ip

    def __init__(self, host: Host, visible_fields: Optional[List[str]] = None,
                 column_widths: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._host = host
        self._visible_fields = visible_fields or ["name", "host", "port", "username", "tags", "device_type", "manufacturer"]
        self._column_widths = column_widths or {}
        self._field_widgets: dict = {}  # field_id -> widget
        self._setup_ui()
        self._apply_style()

    def _get_field_value(self, field: str) -> str:
        """Get display value for a field."""
        if field == "name":
            return self._host.name
        elif field == "host":
            extra_ips = len(self._host.hosts) - 1 if self._host.hosts else 0
            text = self._host.host
            if extra_ips > 0:
                text += f" (+{extra_ips})"
            return text
        elif field == "port":
            return str(self._host.port)
        elif field == "username":
            return self._host.username or "-"
        elif field == "device_type":
            return self._host.device_type or "-"
        elif field == "manufacturer":
            return self._host.manufacturer or "-"
        elif field == "os_version":
            return self._host.os_version or "-"
        elif field == "functions":
            return ", ".join(self._host.functions) if self._host.functions else "-"
        elif field == "groups":
            return ", ".join(self._host.groups) if self._host.groups else "-"
        return "-"

    def _get_effective_width(self, field: str) -> int:
        """Get effective width for a field (custom or default)."""
        if field in self._column_widths:
            return self._column_widths[field]
        return FIELD_WIDTHS.get(field, 100)

    def update_column_width(self, field: str, width: int) -> None:
        """Update width of a specific column."""
        if field in self._field_widgets:
            widget = self._field_widgets[field]
            if field == "name":
                widget.setMinimumWidth(width)
            else:
                widget.setFixedWidth(width)

    def _setup_ui(self):
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._field_widgets = {}
        for field in self._visible_fields:
            width = self._get_effective_width(field)

            if field == "name":
                # Name column - stretch
                name_label = QLabel(self._host.name)
                name_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff; padding-left: 12px;")
                if width == 0:
                    name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                    name_label.setMinimumWidth(100)
                else:
                    name_label.setFixedWidth(width)
                layout.addWidget(name_label)
                self._field_widgets[field] = name_label

            elif field == "tags":
                # Tags as colored badges
                tags_container = QWidget()
                tags_container.setFixedWidth(width)
                tags_layout = QHBoxLayout(tags_container)
                tags_layout.setContentsMargins(4, 0, 4, 0)
                tags_layout.setSpacing(4)

                if self._host.tags:
                    for tag in self._host.tags[:2]:
                        tag_label = TagLabel(tag)
                        tags_layout.addWidget(tag_label)

                    if len(self._host.tags) > 2:
                        more_label = QLabel(f"+{len(self._host.tags) - 2}")
                        more_label.setStyleSheet("color: #888888; font-size: 10px;")
                        tags_layout.addWidget(more_label)

                tags_layout.addStretch()
                layout.addWidget(tags_container)
                self._field_widgets[field] = tags_container

            else:
                # Other fields as simple text with fixed width
                value = self._get_field_value(field)
                field_label = QLabel(value)
                field_label.setStyleSheet("font-size: 11px; color: #888888; padding-left: 4px;")
                if width > 0:
                    field_label.setFixedWidth(width)
                else:
                    field_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                layout.addWidget(field_label)
                self._field_widgets[field] = field_label

    def _apply_style(self):
        self.setStyleSheet("""
            HostListItem {
                background-color: #2d2d2d;
                border-bottom: 1px solid #3c3c3c;
            }
            HostListItem:hover {
                background-color: #353535;
            }
            HostListItem QLabel {
                background-color: transparent;
            }
            HostListItem QWidget {
                background-color: transparent;
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
        """

    def _create_ip_submenu(self, parent_menu: QMenu, action_name: str, signal) -> None:
        """Create a submenu with IP options or simple action if only one IP."""
        hosts = self._host.hosts if self._host.hosts else []

        if len(hosts) <= 1:
            # Single IP - simple action
            action = parent_menu.addAction(action_name)
            action.triggered.connect(lambda: signal.emit(self._host.id, ""))
        else:
            # Multiple IPs - create submenu
            submenu = parent_menu.addMenu(action_name)
            submenu.setStyleSheet(self._get_menu_style())

            for ip in hosts:
                ip_action = submenu.addAction(ip)
                ip_action.triggered.connect(lambda checked, addr=ip: signal.emit(self._host.id, addr))

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._get_menu_style())

        # SSH/Connect with IP submenu
        self._create_ip_submenu(menu, "Acesso SSH", self.connect_requested)

        # Winbox with IP submenu
        self._create_ip_submenu(menu, "Winbox", self.winbox_requested)

        # Web access with IP submenu
        self._create_ip_submenu(menu, "Acesso Web", self.web_access_requested)

        menu.addSeparator()

        edit_action = menu.addAction("Editar")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self._host.id))

        delete_action = menu.addAction("Excluir")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self._host.id))

        menu.exec(self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.connect_requested.emit(self._host.id, "")  # Empty = use fallback
        super().mouseDoubleClickEvent(event)

    @property
    def host(self) -> Host:
        return self._host


class HostTableHeader(QFrame):
    """Header row for table-style list view with resizable columns."""

    column_resized = Signal(str, int)  # field_id, new_width

    RESIZE_MARGIN = 6  # Pixels from edge to trigger resize cursor
    MIN_COLUMN_WIDTH = 40

    def __init__(self, visible_fields: Optional[List[str]] = None,
                 column_widths: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._visible_fields = visible_fields or ["name", "host", "port", "username", "tags", "device_type", "manufacturer"]
        self._column_widths = column_widths or {}
        self._header_labels: List[QLabel] = []
        self._resizing = False
        self._resize_field = None
        self._resize_start_x = 0
        self._resize_start_width = 0
        self._setup_ui()
        self._apply_style()
        self.setMouseTracking(True)

    def get_column_widths(self) -> dict:
        """Get current column widths."""
        widths = {}
        for i, field in enumerate(self._visible_fields):
            if i < len(self._header_labels):
                widths[field] = self._header_labels[i].width()
        return widths

    def _get_effective_width(self, field: str) -> int:
        """Get effective width for a field (custom or default)."""
        if field in self._column_widths:
            return self._column_widths[field]
        return FIELD_WIDTHS.get(field, 100)

    def _setup_ui(self):
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header_labels = []
        for field in self._visible_fields:
            width = self._get_effective_width(field)
            label_text = FIELD_LABELS.get(field, field.title())

            header_label = QLabel(label_text)
            header_label.setProperty("field_id", field)

            if field == "name":
                header_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #888888; padding-left: 12px;")
                if width == 0:
                    # Name column stretches
                    header_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                    header_label.setMinimumWidth(100)
                else:
                    header_label.setFixedWidth(width)
            else:
                header_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #888888; padding-left: 4px;")
                header_label.setFixedWidth(width if width > 0 else 100)

            layout.addWidget(header_label)
            self._header_labels.append(header_label)

    def _apply_style(self):
        self.setStyleSheet("""
            HostTableHeader {
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
            }
            HostTableHeader QLabel {
                background-color: transparent;
            }
        """)

    def _get_field_at_x(self, x: int) -> Optional[tuple]:
        """Get field and edge info at x position. Returns (field_id, is_right_edge, label_index)."""
        for i, label in enumerate(self._header_labels):
            label_rect = label.geometry()
            # Check if near right edge of this label
            if abs(x - label_rect.right()) <= self.RESIZE_MARGIN:
                field = self._visible_fields[i]
                # Don't allow resizing the last column or "name" if it's stretch
                if i < len(self._header_labels) - 1:
                    return (field, True, i)
        return None

    def mouseMoveEvent(self, event):
        x = event.position().x()

        if self._resizing:
            # Calculate new width
            delta = x - self._resize_start_x
            new_width = max(self.MIN_COLUMN_WIDTH, self._resize_start_width + int(delta))

            # Update label width
            for i, label in enumerate(self._header_labels):
                if self._visible_fields[i] == self._resize_field:
                    label.setFixedWidth(new_width)
                    break

            # Emit signal for live update
            self.column_resized.emit(self._resize_field, new_width)
        else:
            # Check if over resize edge
            edge_info = self._get_field_at_x(int(x))
            if edge_info:
                self.setCursor(Qt.CursorShape.SplitHCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().x()
            edge_info = self._get_field_at_x(int(x))
            if edge_info:
                field, _, idx = edge_info
                self._resizing = True
                self._resize_field = field
                self._resize_start_x = x
                self._resize_start_width = self._header_labels[idx].width()
                self.grabMouse()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self.releaseMouse()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            # Final emit
            if self._resize_field:
                for label in self._header_labels:
                    if label.property("field_id") == self._resize_field:
                        self.column_resized.emit(self._resize_field, label.width())
                        break
        super().mouseReleaseEvent(event)


class AddHostCard(QFrame):
    """Card widget for adding a new host."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        self.setFixedSize(220, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Plus icon
        plus_label = QLabel("+")
        plus_label.setStyleSheet("font-size: 32px; color: #888888;")
        plus_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(plus_label)

        # Text
        text_label = QLabel("Adicionar Host")
        text_label.setStyleSheet("font-size: 12px; color: #888888;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label)

    def _apply_style(self):
        self.setStyleSheet("""
            AddHostCard {
                background-color: transparent;
                border: 2px dashed #3c3c3c;
                border-radius: 8px;
            }
            AddHostCard:hover {
                border-color: #007acc;
                background-color: rgba(0, 122, 204, 0.1);
            }
        """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HostsTableWidget(QTableWidget):
    """Table widget for displaying hosts with native column resizing."""

    connect_requested = Signal(str, str)  # host_id, ip (empty for fallback)
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id
    winbox_requested = Signal(str, str)  # host_id, ip
    web_access_requested = Signal(str, str)  # host_id, ip
    column_width_changed = Signal(str, int)  # field_id, width

    def __init__(self, visible_fields: Optional[List[str]] = None,
                 column_widths: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._visible_fields = visible_fields or ["name", "host", "port", "username", "tags", "device_type", "manufacturer"]
        self._column_widths = column_widths or {}
        self._hosts: List[Host] = []
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """Setup the table UI."""
        # Configure table
        self.setColumnCount(len(self._visible_fields))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.doubleClicked.connect(self._on_double_click)

        # Setup header
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(False)
        header.setHighlightSections(False)
        header.sectionResized.connect(self._on_section_resized)

        # Set header labels
        labels = [FIELD_LABELS.get(f, f.title()) for f in self._visible_fields]
        self.setHorizontalHeaderLabels(labels)

        # Set column widths and resize modes
        for i, field in enumerate(self._visible_fields):
            width = self._column_widths.get(field, FIELD_WIDTHS.get(field, 100))
            if field == "name" and width == 0:
                # Name column stretches
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                if width > 0:
                    self.setColumnWidth(i, width)
                else:
                    self.setColumnWidth(i, 100)

        # Set minimum section size for resizing
        header.setMinimumSectionSize(40)

    def _apply_style(self):
        """Apply dark theme style."""
        self.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: none;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid #3c3c3c;
            }
            QTableWidget::item:selected {
                background-color: #094771;
            }
            QTableWidget::item:hover {
                background-color: #2d2d2d;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #888888;
                padding: 8px 12px;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                border-right: 1px solid #3c3c3c;
                font-weight: bold;
                font-size: 11px;
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QHeaderView::section:hover {
                background-color: #2d2d2d;
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

    def set_hosts(self, hosts: List[Host]):
        """Set the hosts to display."""
        self._hosts = hosts
        self.setRowCount(len(hosts))

        for row, host in enumerate(hosts):
            self._populate_row(row, host)

        # Set row height
        self.verticalHeader().setDefaultSectionSize(40)

    def _populate_row(self, row: int, host: Host):
        """Populate a row with host data."""
        for col, field in enumerate(self._visible_fields):
            value = self._get_field_value(host, field)
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, host.id)

            # Style based on field
            if field == "name":
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(Qt.GlobalColor.white)
            elif field == "tags":
                # Tags as comma-separated text (simplified from badges)
                item.setText(", ".join(host.tags) if host.tags else "-")
                item.setForeground(Qt.GlobalColor.cyan)
            else:
                item.setForeground(Qt.GlobalColor.gray)

            self.setItem(row, col, item)

    def _get_field_value(self, host: Host, field: str) -> str:
        """Get display value for a field."""
        if field == "name":
            return host.name
        elif field == "host":
            extra_ips = len(host.hosts) - 1 if host.hosts else 0
            text = host.host
            if extra_ips > 0:
                text += f" (+{extra_ips})"
            return text
        elif field == "port":
            return str(host.port)
        elif field == "username":
            return host.username or "-"
        elif field == "device_type":
            return host.device_type or "-"
        elif field == "manufacturer":
            return host.manufacturer or "-"
        elif field == "os_version":
            return host.os_version or "-"
        elif field == "functions":
            return ", ".join(host.functions) if host.functions else "-"
        elif field == "groups":
            return ", ".join(host.groups) if host.groups else "-"
        elif field == "tags":
            return ", ".join(host.tags) if host.tags else "-"
        return "-"

    def _get_host_at_row(self, row: int) -> Optional[Host]:
        """Get host at the given row."""
        if 0 <= row < len(self._hosts):
            return self._hosts[row]
        return None

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
        """

    def _create_ip_submenu(self, parent_menu: QMenu, action_name: str, signal, host: Host) -> None:
        """Create a submenu with IP options or simple action if only one IP."""
        hosts = host.hosts if host.hosts else []

        if len(hosts) <= 1:
            action = parent_menu.addAction(action_name)
            action.triggered.connect(lambda: signal.emit(host.id, ""))
        else:
            submenu = parent_menu.addMenu(action_name)
            submenu.setStyleSheet(self._get_menu_style())

            for ip in hosts:
                ip_action = submenu.addAction(ip)
                ip_action.triggered.connect(lambda checked, addr=ip: signal.emit(host.id, addr))

    def _show_context_menu(self, pos):
        """Show context menu for host actions."""
        item = self.itemAt(pos)
        if not item:
            return

        row = item.row()
        host = self._get_host_at_row(row)
        if not host:
            return

        menu = QMenu(self)
        menu.setStyleSheet(self._get_menu_style())

        self._create_ip_submenu(menu, "Acesso SSH", self.connect_requested, host)
        self._create_ip_submenu(menu, "Winbox", self.winbox_requested, host)
        self._create_ip_submenu(menu, "Acesso Web", self.web_access_requested, host)

        menu.addSeparator()

        edit_action = menu.addAction("Editar")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(host.id))

        delete_action = menu.addAction("Excluir")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(host.id))

        menu.exec(self.viewport().mapToGlobal(pos))

    def _on_double_click(self, index):
        """Handle double click to connect."""
        host = self._get_host_at_row(index.row())
        if host:
            self.connect_requested.emit(host.id, "")

    def _on_section_resized(self, logical_index: int, old_size: int, new_size: int):
        """Handle column resize and emit signal to save width."""
        if 0 <= logical_index < len(self._visible_fields):
            field = self._visible_fields[logical_index]
            self.column_width_changed.emit(field, new_size)

    def get_column_widths(self) -> dict:
        """Get current column widths."""
        widths = {}
        for i, field in enumerate(self._visible_fields):
            widths[field] = self.columnWidth(i)
        return widths
