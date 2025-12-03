"""
Host card widget for displaying a host in card or list format.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent

from core.hosts import Host


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

    connect_requested = Signal(str)  # host_id
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id

    def __init__(self, host: Host, parent=None):
        super().__init__(parent)
        self._host = host
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        self.setFixedSize(220, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Host name
        name_label = QLabel(self._host.name)
        name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        # Host address
        address_label = QLabel(f"{self._host.host}:{self._host.port}")
        address_label.setStyleSheet("font-size: 12px; color: #888888;")
        layout.addWidget(address_label)

        # Tags row
        if self._host.tags:
            tags_layout = QHBoxLayout()
            tags_layout.setContentsMargins(0, 4, 0, 0)
            tags_layout.setSpacing(4)

            for tag in self._host.tags[:3]:  # Show max 3 tags
                tag_label = TagLabel(tag)
                tags_layout.addWidget(tag_label)

            if len(self._host.tags) > 3:
                more_label = QLabel(f"+{len(self._host.tags) - 3}")
                more_label.setStyleSheet("color: #888888; font-size: 10px;")
                tags_layout.addWidget(more_label)

            tags_layout.addStretch()
            layout.addLayout(tags_layout)

        layout.addStretch()

        # Device type (bottom)
        if self._host.device_type:
            device_label = QLabel(self._host.device_type)
            device_label.setStyleSheet("font-size: 11px; color: #666666;")
            layout.addWidget(device_label)

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

    def _show_context_menu(self, pos):
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
        """)

        connect_action = menu.addAction("Conectar")
        connect_action.triggered.connect(lambda: self.connect_requested.emit(self._host.id))

        menu.addSeparator()

        edit_action = menu.addAction("Editar")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self._host.id))

        delete_action = menu.addAction("Excluir")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self._host.id))

        menu.exec(self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.connect_requested.emit(self._host.id)
        super().mouseDoubleClickEvent(event)

    @property
    def host(self) -> Host:
        return self._host


class HostListItem(QFrame):
    """List item widget for displaying a host in list view."""

    connect_requested = Signal(str)  # host_id
    edit_requested = Signal(str)  # host_id
    delete_requested = Signal(str)  # host_id

    def __init__(self, host: Host, parent=None):
        super().__init__(parent)
        self._host = host
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Left section: name and address
        left_layout = QVBoxLayout()
        left_layout.setSpacing(2)

        name_label = QLabel(self._host.name)
        name_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        left_layout.addWidget(name_label)

        address_label = QLabel(f"{self._host.host}:{self._host.port}")
        address_label.setStyleSheet("font-size: 11px; color: #888888;")
        left_layout.addWidget(address_label)

        layout.addLayout(left_layout)

        # Tags section
        if self._host.tags:
            tags_layout = QHBoxLayout()
            tags_layout.setSpacing(4)

            for tag in self._host.tags[:3]:
                tag_label = TagLabel(tag)
                tags_layout.addWidget(tag_label)

            if len(self._host.tags) > 3:
                more_label = QLabel(f"+{len(self._host.tags) - 3}")
                more_label.setStyleSheet("color: #888888; font-size: 10px;")
                tags_layout.addWidget(more_label)

            layout.addLayout(tags_layout)

        layout.addStretch()

        # Device type (right)
        if self._host.device_type:
            device_label = QLabel(self._host.device_type)
            device_label.setStyleSheet("font-size: 11px; color: #666666;")
            layout.addWidget(device_label)

    def _apply_style(self):
        self.setStyleSheet("""
            HostListItem {
                background-color: #2d2d2d;
                border-bottom: 1px solid #3c3c3c;
            }
            HostListItem:hover {
                background-color: #353535;
            }
        """)

    def _show_context_menu(self, pos):
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
        """)

        connect_action = menu.addAction("Conectar")
        connect_action.triggered.connect(lambda: self.connect_requested.emit(self._host.id))

        menu.addSeparator()

        edit_action = menu.addAction("Editar")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self._host.id))

        delete_action = menu.addAction("Excluir")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self._host.id))

        menu.exec(self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.connect_requested.emit(self._host.id)
        super().mouseDoubleClickEvent(event)

    @property
    def host(self) -> Host:
        return self._host


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
