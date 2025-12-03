"""
Tags widget for selecting and managing tags on hosts.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QFrame,
    QLabel, QPushButton, QCompleter, QSizePolicy, QLayout
)
from PySide6.QtCore import Qt, Signal, QStringListModel, QRect, QSize, QPoint, QTimer
from PySide6.QtGui import QFocusEvent

from core.data_manager import get_data_manager


class FlowLayout(QLayout):
    """A layout that arranges widgets in a flowing grid, wrapping to new lines."""

    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self._item_list = []
        self._spacing = spacing if spacing >= 0 else 4
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        has_items = False

        for item in self._item_list:
            widget = item.widget()
            if widget is None:
                continue

            has_items = True
            space_x = self._spacing
            space_y = self._spacing
            item_size = item.sizeHint()

            next_x = x + item_size.width() + space_x
            if next_x - space_x > effective_rect.right() + 1 and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item_size.width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        if not has_items:
            return 0

        return y + line_height - rect.y() + margins.bottom()


class TagChip(QFrame):
    """A removable tag chip widget."""

    removed = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)

        # Tag text
        self._label = QLabel(self._text)
        self._label.setStyleSheet("background: transparent; color: white; font-size: 11px;")
        layout.addWidget(self._label)

        # Remove button - red X (always visible)
        self._remove_btn = QLabel("✕")
        self._remove_btn.setFixedSize(14, 14)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._remove_btn.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #ff4444;
                font-weight: bold;
                font-size: 11px;
            }
            QLabel:hover {
                color: #ff0000;
            }
        """)
        self._remove_btn.mousePressEvent = lambda e: self.removed.emit(self._text)
        layout.addWidget(self._remove_btn)

        self.setStyleSheet("""
            TagChip {
                background-color: #0e639c;
                border-radius: 10px;
            }
        """)

        # Set fixed size based on content
        self._update_size()

    def _update_size(self):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self._label.font())
        text_width = fm.horizontalAdvance(self._text)
        # margins (10+6) + spacing (6) + button (14) + extra padding
        width = text_width + 10 + 6 + 6 + 14 + 4
        height = 24
        self.setFixedSize(width, height)

    def sizeHint(self):
        return self.size()

    def minimumSizeHint(self):
        return self.size()

    @property
    def text(self) -> str:
        return self._text


class TagInputLineEdit(QLineEdit):
    """Custom QLineEdit that shows completer popup on focus."""

    focus_in = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def focusInEvent(self, event: QFocusEvent):
        """Show completer popup when input receives focus."""
        super().focusInEvent(event)
        self._show_completer()

    def mousePressEvent(self, event):
        """Show completer popup when clicking on input."""
        super().mousePressEvent(event)
        self._show_completer()

    def _show_completer(self):
        """Emit signal and show completer."""
        self.focus_in.emit()
        if self.completer():
            QTimer.singleShot(0, self.completer().complete)


class TagsWidget(QWidget):
    """Widget for managing tags with autocomplete."""

    tags_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data_manager = get_data_manager()
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

        # Chips container with FlowLayout (grows vertically)
        self._chips_container = QWidget()
        self._chips_container.setStyleSheet("background: transparent;")
        self._chips_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._chips_layout = FlowLayout(self._chips_container, margin=2, spacing=4)
        self._chips_container.hide()  # Hidden when no tags

        main_layout.addWidget(self._chips_container)

        # Update completer with available tags
        self._update_completer()

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
        # Use QTimer to clear and reshow completer after processing
        QTimer.singleShot(0, self._clear_and_show_completer)

    def _clear_and_show_completer(self):
        """Clear input and show completer with remaining tags."""
        self._input.clear()
        self._update_completer()
        # Show remaining tags if any
        if self._completer_model.rowCount() > 0:
            self._completer.complete()

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
        if tag not in self._data_manager.get_tags():
            self._data_manager.add_tag(tag)
            self._update_completer()

        # Create chip widget
        chip = TagChip(tag)
        chip.removed.connect(self._remove_tag)
        self._chip_widgets[tag] = chip
        self._chips_layout.addWidget(chip)

        # Show chips container and update layout
        self._chips_container.show()
        self._chips_layout.invalidate()
        self._chips_container.updateGeometry()
        self._chips_container.adjustSize()

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
            self._chips_container.hide()
        else:
            self._chips_layout.invalidate()
            self._chips_container.updateGeometry()
            self._chips_container.adjustSize()

        self.tags_changed.emit(self._selected_tags.copy())

    def _update_completer(self):
        """Update completer with available tags (excluding selected)."""
        available = self._data_manager.get_tags()
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
