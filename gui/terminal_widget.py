"""
Terminal Widget for SSH output and input.
Uses pyte as a VT100/xterm terminal emulator for proper escape sequence handling.
"""

import logging
from typing import Optional

import pyte

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, Signal, QTimer, QElapsedTimer, QPoint
from PySide6.QtGui import (
    QFont, QKeyEvent, QColor, QPainter, QFontMetrics, QFontDatabase,
    QMouseEvent, QWheelEvent
)
from PySide6.QtCore import QEvent

logger = logging.getLogger(__name__)

# Default terminal size
DEFAULT_COLS = 120
DEFAULT_ROWS = 30

# ANSI color names to QColor mapping (standard terminal colors)
ANSI_COLORS = {
    # Standard colors (0-7)
    "black": QColor(0, 0, 0),
    "red": QColor(205, 49, 49),
    "green": QColor(13, 188, 121),
    "yellow": QColor(229, 229, 16),
    "blue": QColor(36, 114, 200),
    "magenta": QColor(188, 63, 188),
    "cyan": QColor(17, 168, 205),
    "white": QColor(229, 229, 229),
    # Bright colors (8-15)
    "brightblack": QColor(102, 102, 102),
    "brightred": QColor(241, 76, 76),
    "brightgreen": QColor(35, 209, 139),
    "brightyellow": QColor(245, 245, 67),
    "brightblue": QColor(59, 142, 234),
    "brightmagenta": QColor(214, 112, 214),
    "brightcyan": QColor(41, 184, 219),
    "brightwhite": QColor(255, 255, 255),
    # Aliases
    "brown": QColor(229, 229, 16),
    "lightgray": QColor(229, 229, 229),
    "lightgrey": QColor(229, 229, 229),
    "darkgray": QColor(102, 102, 102),
    "darkgrey": QColor(102, 102, 102),
    "lightred": QColor(241, 76, 76),
    "lightgreen": QColor(35, 209, 139),
    "lightyellow": QColor(245, 245, 67),
    "lightblue": QColor(59, 142, 234),
    "lightmagenta": QColor(214, 112, 214),
    "lightcyan": QColor(41, 184, 219),
}

# Numeric color indices
ANSI_COLORS_BY_INDEX = [
    QColor(0, 0, 0),        # 0: Black
    QColor(205, 49, 49),    # 1: Red
    QColor(13, 188, 121),   # 2: Green
    QColor(229, 229, 16),   # 3: Yellow
    QColor(36, 114, 200),   # 4: Blue
    QColor(188, 63, 188),   # 5: Magenta
    QColor(17, 168, 205),   # 6: Cyan
    QColor(229, 229, 229),  # 7: White
    QColor(102, 102, 102),  # 8: Bright Black
    QColor(241, 76, 76),    # 9: Bright Red
    QColor(35, 209, 139),   # 10: Bright Green
    QColor(245, 245, 67),   # 11: Bright Yellow
    QColor(59, 142, 234),   # 12: Bright Blue
    QColor(214, 112, 214),  # 13: Bright Magenta
    QColor(41, 184, 219),   # 14: Bright Cyan
    QColor(255, 255, 255),  # 15: Bright White
]


def parse_color(color_value, default: QColor) -> QColor:
    """Parse pyte color value to QColor."""
    if color_value is None or color_value == "default":
        return default

    # String color name
    if isinstance(color_value, str):
        color_lower = color_value.lower().replace("_", "").replace("-", "")
        if color_lower in ANSI_COLORS:
            return ANSI_COLORS[color_lower]

        if color_value.isdigit():
            idx = int(color_value)
            if 0 <= idx < len(ANSI_COLORS_BY_INDEX):
                return ANSI_COLORS_BY_INDEX[idx]
            elif idx < 256:
                return _get_256_color(idx)

    # Integer color index
    if isinstance(color_value, int):
        if 0 <= color_value < len(ANSI_COLORS_BY_INDEX):
            return ANSI_COLORS_BY_INDEX[color_value]
        elif color_value < 256:
            return _get_256_color(color_value)

    return default


def _get_256_color(idx: int) -> QColor:
    """Convert 256-color index to QColor."""
    if idx < 16:
        return ANSI_COLORS_BY_INDEX[idx]
    elif idx < 232:
        idx -= 16
        r = (idx // 36) * 51
        g = ((idx // 6) % 6) * 51
        b = (idx % 6) * 51
        return QColor(r, g, b)
    else:
        gray = (idx - 232) * 10 + 8
        return QColor(gray, gray, gray)


class TerminalWidget(QWidget):
    """
    Terminal emulator widget using pyte for VT100/xterm emulation.
    """

    input_entered = Signal(str)
    reconnect_requested = Signal()
    # Signal emitted when pre-login credentials are entered (username, password)
    prelogin_credentials = Signal(str, str)
    # Signal emitted when pre-login is cancelled (Ctrl+C or Escape)
    prelogin_cancelled = Signal()

    DEFAULT_FG = QColor(220, 220, 220)
    DEFAULT_BG = QColor(30, 30, 30)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Terminal emulator (pyte)
        self._cols = DEFAULT_COLS
        self._rows = DEFAULT_ROWS
        self._screen = pyte.Screen(self._cols, self._rows)
        self._stream = pyte.Stream(self._screen)

        # Font settings
        self._font = self._create_font()
        self._font_metrics: Optional[QFontMetrics] = None
        self._char_width = 8
        self._char_height = 16

        # Rendering throttle - limit repaints to ~60fps
        self._update_pending = False
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._do_update)
        self._min_update_interval = 16  # ~60fps

        # Cursor blink
        self._cursor_visible = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(530)

        # Disconnected mode
        self._disconnected_mode = False

        # Pre-login mode (local username/password prompt like PuTTY)
        self._prelogin_mode = False
        self._prelogin_stage = ""  # "username" or "password"
        self._prelogin_buffer = ""
        self._prelogin_username = ""
        self._prelogin_need_password = True

        # Text selection (copy on select like PuTTY)
        self._selection_start: Optional[QPoint] = None  # (col, row)
        self._selection_end: Optional[QPoint] = None    # (col, row)
        self._is_selecting = False

        # Font zoom settings
        self._font_size = 11  # Default font size
        self._min_font_size = 6
        self._max_font_size = 32

        # Setup
        self._setup_ui()
        self._update_font_metrics()

    def _create_font(self) -> QFont:
        """Create the best available monospace font."""
        preferred_fonts = [
            "Cascadia Mono",
            "Consolas",
            "JetBrains Mono",
            "Fira Code",
            "Source Code Pro",
            "DejaVu Sans Mono",
            "Courier New",
            "monospace",
        ]

        available_families = QFontDatabase.families()

        for font_name in preferred_fonts:
            if font_name in available_families:
                font = QFont(font_name, 11)
                font.setStyleHint(QFont.StyleHint.Monospace)
                font.setFixedPitch(True)
                font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
                logger.info(f"Using font: {font_name}")
                return font

        font = QFont("monospace", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        return font

    def _setup_ui(self) -> None:
        """Setup the terminal UI components."""
        self.setMinimumSize(400, 200)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(True)

        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.DEFAULT_BG)
        self.setPalette(palette)

    def _update_font_metrics(self) -> None:
        """Update font metrics for character sizing."""
        self._font_metrics = QFontMetrics(self._font)
        self._char_width = self._font_metrics.horizontalAdvance('M')
        self._char_height = self._font_metrics.height()

    def _blink_cursor(self) -> None:
        """Toggle cursor visibility for blinking effect."""
        self._cursor_visible = not self._cursor_visible
        self._schedule_update()

    def _schedule_update(self) -> None:
        """Schedule a throttled update."""
        if not self._update_pending:
            self._update_pending = True
            if not self._update_timer.isActive():
                self._update_timer.start(self._min_update_interval)

    def _do_update(self) -> None:
        """Perform the actual update."""
        self._update_pending = False
        self.update()

    def resizeEvent(self, event) -> None:
        """Handle widget resize."""
        super().resizeEvent(event)
        self._resize_terminal()

    def _resize_terminal(self) -> None:
        """Resize the pyte screen to match widget size."""
        if self._char_width <= 0 or self._char_height <= 0:
            return

        new_cols = max(40, self.width() // self._char_width)
        new_rows = max(10, self.height() // self._char_height)

        if new_cols != self._cols or new_rows != self._rows:
            self._cols = new_cols
            self._rows = new_rows
            self._screen.resize(self._rows, self._cols)
            logger.debug(f"Terminal resized to {self._cols}x{self._rows}")
            self._schedule_update()

    def paintEvent(self, event) -> None:
        """Render the terminal screen with antialiasing."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)

        # Background
        painter.fillRect(self.rect(), self.DEFAULT_BG)

        # Selection highlight color
        selection_bg = QColor(70, 130, 180)  # Steel blue
        selection_fg = QColor(255, 255, 255)

        # Cache for styled fonts
        font_cache = {}

        # Render each character
        buffer = self._screen.buffer
        for row in range(min(self._rows, len(buffer))):
            y = row * self._char_height
            line = buffer[row]

            for col in range(min(self._cols, len(line))):
                x = col * self._char_width
                char = line[col]

                # Check if this cell is selected
                is_selected = self._is_cell_selected(col, row)

                # Get colors
                fg = parse_color(char.fg, self.DEFAULT_FG)
                bg = parse_color(char.bg, self.DEFAULT_BG)

                # Handle reverse video
                if char.reverse:
                    fg, bg = bg, fg

                # Handle bold
                if char.bold and char.fg in ("default", None):
                    fg = QColor(255, 255, 255)

                # Override colors if selected
                if is_selected:
                    bg = selection_bg
                    fg = selection_fg

                # Draw background if not default or if selected
                if bg != self.DEFAULT_BG or is_selected:
                    painter.fillRect(x, y, self._char_width, self._char_height, bg)

                # Draw character
                char_data = char.data
                if char_data and char_data != ' ':
                    painter.setPen(fg)

                    style_key = (char.bold, char.italics, char.underscore)
                    if style_key not in font_cache:
                        styled_font = QFont(self._font)
                        if char.bold:
                            styled_font.setBold(True)
                        if char.italics:
                            styled_font.setItalic(True)
                        if char.underscore:
                            styled_font.setUnderline(True)
                        font_cache[style_key] = styled_font

                    painter.setFont(font_cache[style_key])
                    text_y = y + self._char_height - self._font_metrics.descent()
                    painter.drawText(x, text_y, char_data)

        # Reset font
        painter.setFont(self._font)

        # Draw cursor
        if self._cursor_visible and self.hasFocus():
            cursor_x = self._screen.cursor.x * self._char_width
            cursor_y = self._screen.cursor.y * self._char_height
            painter.fillRect(
                cursor_x, cursor_y,
                self._char_width, self._char_height,
                QColor(200, 200, 200, 180)
            )

        painter.end()

    def event(self, event) -> bool:
        """Override event to capture special keys before Qt processes them."""
        if event.type() == event.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            if key == Qt.Key.Key_Tab:
                # Send Tab to terminal instead of changing focus
                self._send_input("\t")
                return True
            elif key == Qt.Key.Key_Backtab:
                # Shift+Tab - also send to terminal
                self._send_input("\x1b[Z")  # Shift+Tab escape sequence
                return True
            elif key == Qt.Key.Key_Insert and (modifiers & Qt.KeyboardModifier.ShiftModifier):
                # Shift+Insert - Paste from clipboard
                self._paste_from_clipboard()
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard events for terminal input."""
        key = event.key()
        modifiers = event.modifiers()

        # Handle pre-login mode (local username/password prompt)
        if self._prelogin_mode:
            self._handle_prelogin_key(event)
            return

        # Handle disconnected mode - only respond to R key
        if self._disconnected_mode:
            if key == Qt.Key.Key_R and modifiers == Qt.KeyboardModifier.NoModifier:
                self._disconnected_mode = False
                self.reconnect_requested.emit()
            return

        # Enter key
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._send_input("\r")
            return

        # Arrow keys
        if key == Qt.Key.Key_Up:
            self._send_input("\x1b[A")
            return
        if key == Qt.Key.Key_Down:
            self._send_input("\x1b[B")
            return
        if key == Qt.Key.Key_Right:
            self._send_input("\x1b[C")
            return
        if key == Qt.Key.Key_Left:
            self._send_input("\x1b[D")
            return

        # Home/End
        if key == Qt.Key.Key_Home:
            self._send_input("\x1b[H")
            return
        if key == Qt.Key.Key_End:
            self._send_input("\x1b[F")
            return

        # Page Up/Down
        if key == Qt.Key.Key_PageUp:
            self._send_input("\x1b[5~")
            return
        if key == Qt.Key.Key_PageDown:
            self._send_input("\x1b[6~")
            return

        # Delete
        if key == Qt.Key.Key_Delete:
            self._send_input("\x1b[3~")
            return

        # Insert
        if key == Qt.Key.Key_Insert:
            self._send_input("\x1b[2~")
            return

        # Function keys
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            fn = key - Qt.Key.Key_F1 + 1
            if fn <= 4:
                self._send_input(f"\x1bO{chr(ord('P') + fn - 1)}")
            else:
                codes = {5: 15, 6: 17, 7: 18, 8: 19, 9: 20, 10: 21, 11: 23, 12: 24}
                if fn in codes:
                    self._send_input(f"\x1b[{codes[fn]}~")
            return

        # Ctrl+C
        if key == Qt.Key.Key_C and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._send_input("\x03")
            return

        # Ctrl+V - Paste from clipboard
        if key == Qt.Key.Key_V and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._paste_from_clipboard()
            return

        # Ctrl+Plus / Ctrl+= - Zoom in
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._zoom_in()
            return

        # Ctrl+Minus - Zoom out
        if key == Qt.Key.Key_Minus and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._zoom_out()
            return

        # Ctrl+0 - Reset zoom
        if key == Qt.Key.Key_0 and modifiers == Qt.KeyboardModifier.ControlModifier:
            self.reset_zoom()
            return

        # Shift+Insert - Paste from clipboard
        if key == Qt.Key.Key_Insert and (modifiers & Qt.KeyboardModifier.ShiftModifier):
            self._paste_from_clipboard()
            return

        # Ctrl+D
        if key == Qt.Key.Key_D and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._send_input("\x04")
            return

        # Ctrl+L
        if key == Qt.Key.Key_L and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._send_input("\x0c")
            return

        # Ctrl+Z
        if key == Qt.Key.Key_Z and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._send_input("\x1a")
            return

        # Tab is handled in event() to prevent focus change

        # Backspace
        if key == Qt.Key.Key_Backspace:
            self._send_input("\x7f")
            return

        # Escape
        if key == Qt.Key.Key_Escape:
            self._send_input("\x1b")
            return

        # Regular character input
        text = event.text()
        if text:
            self._send_input(text)

    def _send_input(self, data: str) -> None:
        """Send input data and emit signal."""
        # Clear selection when user types
        if self._selection_start is not None:
            self.clear_selection()
        self.input_entered.emit(data)

    def append_output(self, text: str) -> None:
        """
        Append text to terminal output.
        Called from SSH session with received data.
        """
        if not text:
            return

        # Feed to pyte stream - process immediately
        try:
            self._stream.feed(text)
        except Exception as e:
            logger.warning(f"Error processing terminal data: {e}")
            # Try character by character as fallback
            for char in text:
                try:
                    self._stream.feed(char)
                except Exception:
                    pass

        # Schedule throttled repaint
        self._schedule_update()

    def clear(self) -> None:
        """Clear terminal content."""
        self._screen.reset()
        self._disconnected_mode = False
        self._prelogin_mode = False
        self._prelogin_stage = ""
        self._prelogin_buffer = ""
        self._prelogin_username = ""
        self._schedule_update()

    def show_disconnected_message(self) -> None:
        """Show disconnected message and enable reconnect mode."""
        self._screen.reset()
        self._disconnected_mode = True

        # Center the message on screen
        msg_line1 = "Conexao perdida"
        msg_line2 = "Pressione R para reconectar"

        center_row = max(1, self._rows // 2)
        center_col1 = max(1, (self._cols - len(msg_line1)) // 2 + 1)
        center_col2 = max(1, (self._cols - len(msg_line2)) // 2 + 1)

        # Use ANSI escape sequences via stream (proper way to write to pyte)
        # Clear screen and move cursor
        self._stream.feed("\x1b[2J")  # Clear screen
        # Position and write first message
        self._stream.feed(f"\x1b[{center_row};{center_col1}H{msg_line1}")
        # Position and write second message
        self._stream.feed(f"\x1b[{center_row + 2};{center_col2}H{msg_line2}")
        # Hide cursor at bottom
        self._stream.feed(f"\x1b[{self._rows};1H")

        self._schedule_update()
        self.setFocus()

    def start_prelogin(self, need_username: bool = True, need_password: bool = True) -> None:
        """
        Start pre-login mode to collect credentials locally (like PuTTY).

        Args:
            need_username: Whether to prompt for username
            need_password: Whether to prompt for password after username
        """
        self._screen.reset()
        self._prelogin_mode = True
        self._prelogin_buffer = ""
        self._prelogin_username = ""
        self._prelogin_need_password = need_password
        self._disconnected_mode = False

        if need_username:
            self._prelogin_stage = "username"
            self._stream.feed("login as: ")
        elif need_password:
            self._prelogin_stage = "password"
            self._stream.feed("Password: ")
        else:
            # Nothing to collect
            self._prelogin_mode = False
            self.prelogin_credentials.emit("", "")
            return

        self._schedule_update()
        self.setFocus()

    def cancel_prelogin(self) -> None:
        """Cancel pre-login mode."""
        self._prelogin_mode = False
        self._prelogin_stage = ""
        self._prelogin_buffer = ""
        self._prelogin_username = ""

    def _show_cancelled_message(self) -> None:
        """Show cancelled message with reconnect option."""
        self._screen.reset()
        self._disconnected_mode = True

        msg_line1 = "Conexao cancelada"
        msg_line2 = "Pressione R para tentar novamente"

        center_row = max(1, self._rows // 2)
        center_col1 = max(1, (self._cols - len(msg_line1)) // 2 + 1)
        center_col2 = max(1, (self._cols - len(msg_line2)) // 2 + 1)

        self._stream.feed("\x1b[2J")  # Clear screen
        self._stream.feed(f"\x1b[{center_row};{center_col1}H{msg_line1}")
        self._stream.feed(f"\x1b[{center_row + 2};{center_col2}H{msg_line2}")
        self._stream.feed(f"\x1b[{self._rows};1H")

        self._schedule_update()
        self.setFocus()

    def _handle_prelogin_key(self, event: "QKeyEvent") -> bool:
        """
        Handle key press in pre-login mode.
        Returns True if key was consumed.
        """
        if not self._prelogin_mode:
            return False

        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Enter - submit current field
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._prelogin_stage == "username":
                self._prelogin_username = self._prelogin_buffer
                self._prelogin_buffer = ""
                self._stream.feed("\r\n")

                if self._prelogin_need_password:
                    self._prelogin_stage = "password"
                    self._stream.feed("Password: ")
                else:
                    # Done - emit credentials
                    self._prelogin_mode = False
                    self.prelogin_credentials.emit(self._prelogin_username, "")
            elif self._prelogin_stage == "password":
                password = self._prelogin_buffer
                self._prelogin_buffer = ""
                self._stream.feed("\r\n")
                self._prelogin_mode = False
                self.prelogin_credentials.emit(self._prelogin_username, password)

            self._schedule_update()
            return True

        # Backspace
        if key == Qt.Key.Key_Backspace:
            if self._prelogin_buffer:
                self._prelogin_buffer = self._prelogin_buffer[:-1]
                # Echo backspace only for username (not password)
                if self._prelogin_stage == "username":
                    self._stream.feed("\b \b")
                self._schedule_update()
            return True

        # Escape or Ctrl+C - cancel and show reconnect option
        is_ctrl_c = key == Qt.Key.Key_C and (modifiers & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_Escape or is_ctrl_c:
            self._stream.feed("\r\n^C\r\n")
            self.cancel_prelogin()
            self._show_cancelled_message()
            self.prelogin_cancelled.emit()
            return True

        # Regular character
        if text and len(text) == 1 and text.isprintable():
            self._prelogin_buffer += text
            # Echo character only for username (not password)
            if self._prelogin_stage == "username":
                self._stream.feed(text)
            self._schedule_update()
            return True

        return True  # Consume all other keys in prelogin mode

    @property
    def is_prelogin_mode(self) -> bool:
        """Check if terminal is in pre-login mode."""
        return self._prelogin_mode

    def get_terminal_size(self) -> tuple[int, int]:
        """Get terminal size in characters."""
        return self._cols, self._rows

    def set_focus(self) -> None:
        """Set focus to the terminal."""
        self.setFocus()

    # --- Text Selection (copy on select) ---

    def _pixel_to_cell(self, pos: QPoint) -> QPoint:
        """Convert pixel position to terminal cell (col, row)."""
        col = max(0, min(pos.x() // self._char_width, self._cols - 1))
        row = max(0, min(pos.y() // self._char_height, self._rows - 1))
        return QPoint(col, row)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press - start selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._selection_start = self._pixel_to_cell(event.pos())
            self._selection_end = self._selection_start
            self._is_selecting = True
            self._schedule_update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move - update selection."""
        if self._is_selecting:
            self._selection_end = self._pixel_to_cell(event.pos())
            self._schedule_update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release - finish selection and copy to clipboard, or paste with right click."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._selection_end = self._pixel_to_cell(event.pos())
            self._is_selecting = False

            # Copy selected text to clipboard
            selected_text = self._get_selected_text()
            if selected_text:
                clipboard = QApplication.clipboard()
                clipboard.setText(selected_text)
                logger.debug(f"Copied to clipboard: {len(selected_text)} chars")

            self._schedule_update()

        # Right click - paste from clipboard
        elif event.button() == Qt.MouseButton.RightButton:
            self._paste_from_clipboard()

        super().mouseReleaseEvent(event)

    def _get_selection_bounds(self) -> tuple[QPoint, QPoint]:
        """Get selection bounds ordered (start before end)."""
        if self._selection_start is None or self._selection_end is None:
            return None, None

        start = self._selection_start
        end = self._selection_end

        # Order by row, then by column
        if (start.y() > end.y()) or (start.y() == end.y() and start.x() > end.x()):
            start, end = end, start

        return start, end

    def _is_cell_selected(self, col: int, row: int) -> bool:
        """Check if a cell is within the selection."""
        start, end = self._get_selection_bounds()
        if start is None or end is None:
            return False

        # Same row
        if start.y() == end.y():
            return row == start.y() and start.x() <= col <= end.x()

        # First row
        if row == start.y():
            return col >= start.x()

        # Last row
        if row == end.y():
            return col <= end.x()

        # Middle rows
        return start.y() < row < end.y()

    def _get_selected_text(self) -> str:
        """Get the text within the current selection."""
        start, end = self._get_selection_bounds()
        if start is None or end is None:
            return ""

        # Don't copy if it's just a click (no actual selection)
        if start.x() == end.x() and start.y() == end.y():
            return ""

        lines = []
        buffer = self._screen.buffer

        for row in range(start.y(), end.y() + 1):
            if row >= len(buffer):
                continue

            line = buffer[row]
            line_text = ""

            if start.y() == end.y():
                # Single row selection
                for col in range(start.x(), min(end.x() + 1, len(line))):
                    line_text += line[col].data if line[col].data else " "
            elif row == start.y():
                # First row
                for col in range(start.x(), min(self._cols, len(line))):
                    line_text += line[col].data if line[col].data else " "
            elif row == end.y():
                # Last row
                for col in range(0, min(end.x() + 1, len(line))):
                    line_text += line[col].data if line[col].data else " "
            else:
                # Middle row - full line
                for col in range(min(self._cols, len(line))):
                    line_text += line[col].data if line[col].data else " "

            lines.append(line_text.rstrip())

        return "\n".join(lines)

    def clear_selection(self) -> None:
        """Clear the current selection."""
        self._selection_start = None
        self._selection_end = None
        self._is_selecting = False
        self._schedule_update()

    def _paste_from_clipboard(self) -> None:
        """Paste text from clipboard to terminal."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            # Clear any selection before pasting
            if self._selection_start is not None:
                self.clear_selection()
            # Send text to terminal (convert newlines to carriage returns)
            text = text.replace('\r\n', '\r').replace('\n', '\r')
            self._send_input(text)
            logger.debug(f"Pasted from clipboard: {len(text)} chars")

    # --- Font Zoom (Ctrl + Mouse Wheel) ---

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel - zoom with Ctrl, otherwise ignore."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + Wheel = Zoom
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom_in()
            elif delta < 0:
                self._zoom_out()
            event.accept()
        else:
            # Pass to parent (no scroll in terminal for now)
            super().wheelEvent(event)

    def _zoom_in(self) -> None:
        """Increase font size."""
        if self._font_size < self._max_font_size:
            self._font_size += 1
            self._apply_font_size()

    def _zoom_out(self) -> None:
        """Decrease font size."""
        if self._font_size > self._min_font_size:
            self._font_size -= 1
            self._apply_font_size()

    def _apply_font_size(self) -> None:
        """Apply the current font size and update terminal."""
        self._font.setPointSize(self._font_size)
        self._update_font_metrics()
        self._resize_terminal()
        self._schedule_update()
        logger.debug(f"Font size changed to {self._font_size}")

    def reset_zoom(self) -> None:
        """Reset font size to default (11)."""
        self._font_size = 11
        self._apply_font_size()

    def showEvent(self, event) -> None:
        """Handle show event."""
        super().showEvent(event)
        self._update_font_metrics()
        self._resize_terminal()

    def focusInEvent(self, event) -> None:
        """Handle focus in."""
        super().focusInEvent(event)
        self._cursor_visible = True
        self._schedule_update()

    def focusOutEvent(self, event) -> None:
        """Handle focus out."""
        super().focusOutEvent(event)
        self._cursor_visible = False
        self._schedule_update()
