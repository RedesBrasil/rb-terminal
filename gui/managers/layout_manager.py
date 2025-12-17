"""
Layout Manager - Handles splitters and panel visibility.
Extracted from main_window.py for better separation of concerns.
"""

import logging
from typing import Optional, Dict, List

from PySide6.QtWidgets import QSplitter, QFrame, QWidget, QTabWidget, QVBoxLayout
from PySide6.QtCore import Qt, QObject, Signal

logger = logging.getLogger(__name__)


class LayoutManager(QObject):
    """
    Manages splitters and panel layout.

    Responsibilities:
    - Managing chat panel visibility and position
    - Managing SFTP panel visibility and position
    - Handling splitter sizes and persistence
    - Rebuilding layout when position changes
    """

    # Signals
    chat_visibility_changed = Signal(bool)
    sftp_visibility_changed = Signal(bool)

    def __init__(
        self,
        content_layout: QVBoxLayout,
        tab_widget: QTabWidget,
        chat_panel: QFrame,
        sftp_panel: QFrame,
        parent=None
    ):
        super().__init__(parent)
        self._content_layout = content_layout
        self._tab_widget = tab_widget
        self._chat_panel = chat_panel
        self._sftp_panel = sftp_panel

        # Positions
        self._chat_position = "bottom"
        self._sftp_position = "left"

        # Visibility
        self._chat_visible = False
        self._sftp_visible = False

        # Splitters
        self._terminal_chat_splitter: Optional[QSplitter] = None
        self._sftp_splitter: Optional[QSplitter] = None

        # Splitter sizes cache
        self._splitter_sizes: Dict[str, List[int]] = {
            "bottom": [700, 300],
            "left": [300, 700],
            "right": [700, 300],
        }
        self._sftp_splitter_sizes: Dict[str, List[int]] = {
            "bottom": [700, 250],
            "left": [250, 700],
            "right": [700, 250],
        }
        self._applying_splitter_sizes = False

        # Toggle buttons (set by MainWindow)
        self._toggle_chat_btn = None
        self._toggle_sftp_btn = None

    def set_toggle_buttons(self, chat_btn, sftp_btn) -> None:
        """Set references to toggle buttons for sync."""
        self._toggle_chat_btn = chat_btn
        self._toggle_sftp_btn = sftp_btn

    @property
    def chat_visible(self) -> bool:
        """Check if chat panel is visible."""
        return self._chat_visible

    @property
    def sftp_visible(self) -> bool:
        """Check if SFTP panel is visible."""
        return self._sftp_visible

    @property
    def chat_position(self) -> str:
        """Get chat panel position."""
        return self._chat_position

    @chat_position.setter
    def chat_position(self, value: str) -> None:
        """Set chat panel position."""
        if value != self._chat_position:
            self._chat_position = value
            self._update_chat_panel_style()

    @property
    def sftp_position(self) -> str:
        """Get SFTP panel position."""
        return self._sftp_position

    @sftp_position.setter
    def sftp_position(self, value: str) -> None:
        """Set SFTP panel position."""
        if value != self._sftp_position:
            self._sftp_position = value
            self._update_sftp_panel_style()

    def _update_chat_panel_style(self) -> None:
        """Update chat panel border based on position."""
        if self._chat_panel is None:
            return

        if self._chat_position == "bottom":
            border = "border-top: 1px solid #3c3c3c;"
        elif self._chat_position == "left":
            border = "border-right: 1px solid #3c3c3c;"
        else:  # right
            border = "border-left: 1px solid #3c3c3c;"

        self._chat_panel.setStyleSheet(f"background-color: #252526; {border}")

    def _update_sftp_panel_style(self) -> None:
        """Update SFTP panel border based on position."""
        if self._sftp_panel is None:
            return

        if self._sftp_position == "bottom":
            border = "border-top: 1px solid #3c3c3c;"
        elif self._sftp_position == "left":
            border = "border-right: 1px solid #3c3c3c;"
        else:  # right
            border = "border-left: 1px solid #3c3c3c;"

        self._sftp_panel.setStyleSheet(f"background-color: #252526; {border}")

    def _create_terminal_chat_splitter(self) -> QSplitter:
        """Create splitter configured for the selected chat position."""
        if self._chat_position == "bottom":
            splitter = QSplitter(Qt.Orientation.Vertical)
            splitter.addWidget(self._tab_widget)
            splitter.addWidget(self._chat_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
        elif self._chat_position == "left":
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._chat_panel)
            splitter.addWidget(self._tab_widget)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
        else:  # right
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._tab_widget)
            splitter.addWidget(self._chat_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        return splitter

    def _create_main_splitter_with_sftp(self, inner_widget: QWidget) -> QSplitter:
        """Create main splitter that includes SFTP panel."""
        if self._sftp_position == "bottom":
            splitter = QSplitter(Qt.Orientation.Vertical)
            splitter.addWidget(inner_widget)
            splitter.addWidget(self._sftp_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
        elif self._sftp_position == "left":
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._sftp_panel)
            splitter.addWidget(inner_widget)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
        else:  # right
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(inner_widget)
            splitter.addWidget(self._sftp_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        return splitter

    def rebuild_splitters(self) -> None:
        """Rebuild splitters when layout or orientation changes."""
        # Disconnect and remove existing splitters
        if self._sftp_splitter:
            try:
                self._sftp_splitter.splitterMoved.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._sftp_splitter.setParent(None)

        if self._terminal_chat_splitter:
            try:
                self._terminal_chat_splitter.splitterMoved.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._terminal_chat_splitter.setParent(None)

        # Create terminal+chat splitter
        self._terminal_chat_splitter = self._create_terminal_chat_splitter()
        self._terminal_chat_splitter.splitterMoved.connect(self._on_splitter_moved)

        # Create main splitter with SFTP
        self._sftp_splitter = self._create_main_splitter_with_sftp(self._terminal_chat_splitter)
        self._sftp_splitter.splitterMoved.connect(self._on_sftp_splitter_moved)

        self._content_layout.addWidget(self._sftp_splitter, 1)
        self.apply_chat_visibility()
        self.apply_sftp_visibility()

    def _get_default_splitter_sizes(self, position: str) -> List[int]:
        """Default splitter sizes for each chat orientation."""
        if position == "bottom":
            return [700, 280]
        if position == "left":
            return [300, 700]
        return [700, 300]

    def _get_default_sftp_splitter_sizes(self, position: str) -> List[int]:
        """Default splitter sizes for SFTP panel."""
        if position == "bottom":
            return [700, 250]
        if position == "left":
            return [250, 700]
        return [700, 250]

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Store splitter sizes when user manually adjusts layout."""
        if self._applying_splitter_sizes or not self._chat_visible:
            return
        if self._terminal_chat_splitter:
            self._splitter_sizes[self._chat_position] = self._terminal_chat_splitter.sizes()

    def _on_sftp_splitter_moved(self, pos: int, index: int) -> None:
        """Store SFTP splitter sizes when user manually adjusts layout."""
        if self._applying_splitter_sizes or not self._sftp_visible:
            return
        if self._sftp_splitter:
            self._sftp_splitter_sizes[self._sftp_position] = self._sftp_splitter.sizes()

    def apply_chat_visibility(self) -> None:
        """Adjust splitter sizes based on chat visibility."""
        if not self._terminal_chat_splitter:
            return

        # Hide or show panel widget
        if self._chat_panel:
            self._chat_panel.setVisible(self._chat_visible)

        if not self._chat_visible:
            hide_sizes = [1, 0] if self._chat_position != "left" else [0, 1]
            self._applying_splitter_sizes = True
            self._terminal_chat_splitter.setSizes(hide_sizes)
            self._applying_splitter_sizes = False
        else:
            sizes = self._splitter_sizes.get(self._chat_position)
            if not sizes:
                sizes = self._get_default_splitter_sizes(self._chat_position)
            self._applying_splitter_sizes = True
            self._terminal_chat_splitter.setSizes(sizes)
            self._applying_splitter_sizes = False

        # Sync toolbar toggle state without re-triggering signals
        if self._toggle_chat_btn:
            blocked = self._toggle_chat_btn.blockSignals(True)
            self._toggle_chat_btn.setChecked(self._chat_visible)
            self._toggle_chat_btn.blockSignals(blocked)

    def apply_sftp_visibility(self) -> None:
        """Adjust splitter sizes based on SFTP panel visibility."""
        if not self._sftp_splitter:
            return

        # Hide or show panel widget
        if self._sftp_panel:
            self._sftp_panel.setVisible(self._sftp_visible)

        if not self._sftp_visible:
            hide_sizes = [1, 0] if self._sftp_position != "left" else [0, 1]
            self._applying_splitter_sizes = True
            self._sftp_splitter.setSizes(hide_sizes)
            self._applying_splitter_sizes = False
        else:
            sizes = self._sftp_splitter_sizes.get(self._sftp_position)
            if not sizes:
                sizes = self._get_default_sftp_splitter_sizes(self._sftp_position)
            self._applying_splitter_sizes = True
            self._sftp_splitter.setSizes(sizes)
            self._applying_splitter_sizes = False

        # Sync toolbar toggle state without re-triggering signals
        if self._toggle_sftp_btn:
            blocked = self._toggle_sftp_btn.blockSignals(True)
            self._toggle_sftp_btn.setChecked(self._sftp_visible)
            self._toggle_sftp_btn.blockSignals(blocked)

    def toggle_chat(self) -> bool:
        """Toggle chat panel visibility. Returns new visibility state."""
        self._chat_visible = not self._chat_visible
        self.apply_chat_visibility()
        self.chat_visibility_changed.emit(self._chat_visible)
        return self._chat_visible

    def toggle_sftp(self) -> bool:
        """Toggle SFTP panel visibility. Returns new visibility state."""
        self._sftp_visible = not self._sftp_visible
        self.apply_sftp_visibility()
        self.sftp_visibility_changed.emit(self._sftp_visible)
        return self._sftp_visible

    def set_chat_visible(self, visible: bool) -> None:
        """Set chat panel visibility."""
        if self._chat_visible != visible:
            self._chat_visible = visible
            self.apply_chat_visibility()
            self.chat_visibility_changed.emit(self._chat_visible)

    def set_sftp_visible(self, visible: bool) -> None:
        """Set SFTP panel visibility."""
        if self._sftp_visible != visible:
            self._sftp_visible = visible
            self.apply_sftp_visibility()
            self.sftp_visibility_changed.emit(self._sftp_visible)

    def apply_settings_changes(self, new_chat_position: str, new_sftp_position: str) -> bool:
        """Apply settings that might impact layout. Returns True if rebuild needed."""
        rebuild_needed = False

        if new_chat_position != self._chat_position:
            self._chat_position = new_chat_position
            self._update_chat_panel_style()
            rebuild_needed = True

        if new_sftp_position != self._sftp_position:
            self._sftp_position = new_sftp_position
            self._update_sftp_panel_style()
            rebuild_needed = True

        if rebuild_needed:
            self.rebuild_splitters()

        return rebuild_needed
