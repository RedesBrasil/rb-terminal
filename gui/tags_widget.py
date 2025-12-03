"""
Tags widget for selecting and managing tags on hosts.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QFrame,
    QLabel, QPushButton, QCompleter, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QStringListModel, QEvent
from PySide6.QtGui import QKeyEvent, QFocusEvent

from core.settings import get_settings_manager


class TagChip(QFrame):
    """A removable tag chip widget."""

    removed = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        # Tag text
        label = QLabel(self._text)
        label.setStyleSheet("background: transparent; color: white; font-size: 11px;")
        layout.addWidget(label)

        # Remove button
        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.7);
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        remove_btn.clicked.connect(lambda: self.removed.emit(self._text))
        layout.addWidget(remove_btn)

        self.setStyleSheet("""
            TagChip {
                background-color: #0e639c;
                border-radius: 10px;
            }
        """)

    @property
    def text(self) -> str:
        return self._text


class FlowLayout(QHBoxLayout):
    """Simple horizontal layout that wraps items."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(4)
        self.setContentsMargins(0, 0, 0, 0)


class TagInputLineEdit(QLineEdit):
    """Custom QLineEdit that shows completer popup on focus."""

    focus_in = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def focusInEvent(self, event: QFocusEvent):
        """Show completer popup when input receives focus."""
        super().focusInEvent(event)
        # Emit signal to update completer list
        self.focus_in.emit()
        # Show completer with all available options
        if self.completer():
            self.completer().complete()


class TagsWidget(QWidget):
    """Widget for managing tags with autocomplete."""

    tags_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings_manager = get_settings_manager()
        self._selected_tags: list[str] = []
        self._chip_widgets: dict[str, TagChip] = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # Input field with autocomplete
        self._input = TagInputLineEdit()
        self._input.setPlaceholderText("Adicionar tag...")
        self._input.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px;
                color: #dcdcdc;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        self._input.returnPressed.connect(self._add_current_tag)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.focus_in.connect(self._update_completer)
        main_layout.addWidget(self._input)

        # Setup autocomplete
        self._completer = QCompleter()
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer_model = QStringListModel()
        self._completer.setModel(self._completer_model)
        self._completer.activated.connect(self._on_completer_activated)
        self._input.setCompleter(self._completer)

        # Style the completer popup
        popup = self._completer.popup()
        popup.setStyleSheet("""
            QListView {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 3px;
                color: #dcdcdc;
            }
            QListView::item {
                padding: 6px 8px;
            }
            QListView::item:selected {
                background-color: #094771;
            }
            QListView::item:hover:!selected {
                background-color: #383838;
            }
        """)

        # Chips container (horizontal scroll)
        self._chips_scroll = QScrollArea()
        self._chips_scroll.setWidgetResizable(True)
        self._chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._chips_scroll.setFixedHeight(36)
        self._chips_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)

        self._chips_container = QWidget()
        self._chips_layout = FlowLayout(self._chips_container)
        self._chips_scroll.setWidget(self._chips_container)
        self._chips_scroll.hide()  # Hidden when no tags

        main_layout.addWidget(self._chips_scroll)

        # Update completer with available tags
        self._update_completer()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle comma key to add tag."""
        if self._input.hasFocus() and event.text() == ',':
            self._add_current_tag()
            return
        super().keyPressEvent(event)

    def _on_text_changed(self, text: str):
        """Handle text change - check for comma."""
        if ',' in text:
            # Remove comma and add tag
            clean_text = text.replace(',', '').strip()
            self._input.setText(clean_text)
            if clean_text:
                self._add_tag(clean_text)
                self._input.clear()

    def _on_completer_activated(self, text: str):
        """Handle completer selection."""
        self._add_tag(text)
        self._input.clear()

    def _add_current_tag(self):
        """Add the current input text as a tag."""
        text = self._input.text().strip()
        if text:
            self._add_tag(text)
            self._input.clear()

    def _add_tag(self, tag: str):
        """Add a tag to the selected list."""
        tag = tag.strip()
        if not tag or tag in self._selected_tags:
            return

        self._selected_tags.append(tag)

        # Save new tag to settings if not already there
        if tag not in self._settings_manager.get_tags():
            self._settings_manager.add_tag(tag)
            self._update_completer()

        # Create chip widget
        chip = TagChip(tag)
        chip.removed.connect(self._remove_tag)
        self._chip_widgets[tag] = chip
        self._chips_layout.addWidget(chip)

        # Show chips container
        self._chips_scroll.show()

        self.tags_changed.emit(self._selected_tags.copy())

    def _remove_tag(self, tag: str):
        """Remove a tag from the selected list."""
        if tag not in self._selected_tags:
            return

        self._selected_tags.remove(tag)

        # Remove chip widget
        if tag in self._chip_widgets:
            chip = self._chip_widgets.pop(tag)
            chip.deleteLater()

        # Hide chips container if empty
        if not self._selected_tags:
            self._chips_scroll.hide()

        self.tags_changed.emit(self._selected_tags.copy())

    def _update_completer(self):
        """Update completer with available tags (excluding selected)."""
        available = self._settings_manager.get_tags()
        filtered = [t for t in available if t not in self._selected_tags]
        self._completer_model.setStringList(filtered)

    def set_tags(self, tags: list[str]):
        """Set the currently selected tags."""
        # Clear existing
        for tag in list(self._selected_tags):
            self._remove_tag(tag)

        # Add new tags
        for tag in tags:
            self._add_tag(tag)

    def get_tags(self) -> list[str]:
        """Get the currently selected tags."""
        return self._selected_tags.copy()

    def clear(self):
        """Clear all selected tags."""
        for tag in list(self._selected_tags):
            self._remove_tag(tag)
