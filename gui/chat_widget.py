"""
Chat Widget for AI interaction.
Provides a chat interface for communicating with the AI agent.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QStyle, QToolButton
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QEvent, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor, QKeyEvent

logger = logging.getLogger(__name__)


class ChatInputField(QTextEdit):
    """Custom text input that sends on Enter and allows Shift+Enter for newlines."""

    enter_pressed = Signal()
    resized = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press - Enter sends, Shift+Enter adds newline."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter: add newline
                super().keyPressEvent(event)
            else:
                # Enter: send message
                self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class MessageBubble(QFrame):
    """A message bubble for displaying chat messages."""

    def __init__(self, text: str, is_user: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)

        # Message label
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        # Style based on sender
        if is_user:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #0e639c;
                    border-radius: 8px;
                    margin-left: 50px;
                }
            """)
            label.setStyleSheet("""
                QTextEdit {
                    background-color: transparent;
                    color: white;
                    border: none;
                }
            """)
        else:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #3c3c3c;
                    border-radius: 8px;
                    margin-right: 50px;
                }
            """)
            label.setStyleSheet("""
                QTextEdit {
                    background-color: transparent;
                    color: #dcdcdc;
                    border: none;
                }
            """)

        layout.addWidget(label)


class ChatWidget(QWidget):
    """
    Chat widget for AI interaction.

    Provides:
    - Message history display
    - Input field for user messages
    - Send button
    - Status indicator

    Emits:
    - message_sent(str): When user sends a message
    - stop_requested(): When user clicks stop button
    """

    message_sent = Signal(str)
    stop_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._is_processing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the chat UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Header
        header = QLabel("Chat IA")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #dcdcdc;
                padding: 4px;
            }
        """)
        layout.addWidget(header)

        # Status indicator
        self._status_label = QLabel("Pronto")
        self._status_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 11px;
                padding: 2px;
            }
        """)
        layout.addWidget(self._status_label)

        # Messages area
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #3c3c3c;
                background-color: #252525;
                border-radius: 4px;
            }
        """)

        # Container for messages
        self._messages_container = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_container)
        self._messages_layout.setContentsMargins(8, 8, 8, 8)
        self._messages_layout.setSpacing(6)
        self._messages_layout.addStretch()  # Push messages to top

        self._scroll_area.setWidget(self._messages_container)
        layout.addWidget(self._scroll_area, 1)  # Stretch factor

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._input_field = ChatInputField()
        self._input_field.setPlaceholderText("Digite sua mensagem...")
        self._input_field.setStyleSheet("""
            QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #dcdcdc;
            }
            QTextEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        # Set fixed height for 3 lines (approx 60px)
        self._input_field.setFixedHeight(60)
        self._input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input_field.enter_pressed.connect(self._on_send_clicked)
        self._input_field.setViewportMargins(0, 0, 40, 0)
        input_layout.addWidget(self._input_field)

        # Unified action button (Send / Stop) placed inside input field
        self._action_btn = QToolButton(self._input_field)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setIconSize(QSize(16, 16))
        self._action_btn.setAutoRaise(True)
        self._action_btn.clicked.connect(self._on_action_clicked)
        self._action_btn.resize(28, 28)
        self._input_field.resized.connect(self._position_action_button)
        QTimer.singleShot(0, self._position_action_button)

        layout.addLayout(input_layout)
        self._update_action_button()

    @Slot()
    def _on_send_clicked(self) -> None:
        """Handle send button click."""
        message = self._input_field.toPlainText().strip()
        if message and not self._is_processing:
            self._input_field.clear()
            self.add_message(message, is_user=True)
            self.message_sent.emit(message)

    @Slot()
    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        self.stop_requested.emit()
        self.set_status("Parando...")

    def _on_action_clicked(self) -> None:
        """Handle action button depending on processing state."""
        if self._is_processing:
            self._on_stop_clicked()
        else:
            self._on_send_clicked()

    def _update_action_button(self) -> None:
        """Update action button icon and tooltip."""
        if self._is_processing:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop)
            tooltip = "Parar IA"
            self._action_btn.setStyleSheet("""
                QToolButton {
                    background-color: #d13438;
                    border-radius: 6px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #e81123;
                }
                QToolButton:pressed {
                    background-color: #c50f1f;
                }
                QToolButton:disabled {
                    background-color: #555555;
                }
            """)
        else:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
            tooltip = "Enviar mensagem"
            self._action_btn.setStyleSheet("""
                QToolButton {
                    background-color: #0e639c;
                    border-radius: 6px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #1177bb;
                }
                QToolButton:pressed {
                    background-color: #0d5a8c;
                }
                QToolButton:disabled {
                    background-color: #555555;
                }
            """)

        self._action_btn.setIcon(icon)
        self._action_btn.setToolTip(tooltip)
        self._position_action_button()

    def _position_action_button(self) -> None:
        """Position the action button inside the input field."""
        if not hasattr(self, "_action_btn") or not self._action_btn:
            return
        margin = 8
        size = self._action_btn.height()
        viewport_rect = self._input_field.viewport().geometry()
        x = viewport_rect.right() - size - margin + self._input_field.frameWidth()
        y = viewport_rect.bottom() - size - margin + self._input_field.frameWidth()
        self._action_btn.move(x, y)
        self._action_btn.raise_()

    def add_message(self, text: str, is_user: bool) -> None:
        """
        Add a message to the chat history.

        Args:
            text: Message text
            is_user: True if message is from user, False if from AI
        """
        # Remove the stretch at the end
        stretch_item = self._messages_layout.takeAt(self._messages_layout.count() - 1)

        # Add message bubble
        bubble = MessageBubble(text, is_user)
        self._messages_layout.addWidget(bubble)

        # Re-add stretch
        self._messages_layout.addStretch()

        # Scroll to bottom
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        """Scroll chat to bottom."""
        scrollbar = self._scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_status(self, status: str) -> None:
        """
        Set status text.

        Args:
            status: Status message to display
        """
        self._status_label.setText(status)

    def set_processing(self, processing: bool) -> None:
        """
        Set processing state.

        Args:
            processing: True if AI is processing, False otherwise
        """
        self._is_processing = processing
        # Keep input enabled, but toggle action button behavior
        if self._input_field.isEnabled():
            self._action_btn.setEnabled(True)
        else:
            self._action_btn.setEnabled(False)
        self._update_action_button()

        if processing:
            self.set_status("IA pensando...")
        else:
            self.set_status("Pronto")
            # Focus back to input field after AI response
            self._input_field.setFocus()

    def clear_messages(self) -> None:
        """Clear all messages from chat."""
        # Remove all widgets except the stretch
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_enabled_state(self, enabled: bool) -> None:
        """
        Enable or disable the chat widget.

        Args:
            enabled: True to enable, False to disable
        """
        self._input_field.setEnabled(enabled)
        self._action_btn.setEnabled(enabled)
        self._update_action_button()

        if not enabled:
            self.set_status("Conecte-se a um host primeiro")
        elif not self._is_processing:
            self.set_status("Pronto")
