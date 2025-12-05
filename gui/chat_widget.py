"""
Chat Widget for AI interaction.
Provides a chat interface for communicating with the AI agent.
"""

import logging
from typing import Optional, List, Tuple
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QStyle, QToolButton,
    QComboBox, QTextBrowser
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QKeyEvent

logger = logging.getLogger(__name__)


class ConversationComboBox(QComboBox):
    """Combobox para selecionar conversas anteriores."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setEditable(False)  # Dropdown simples
        self._all_items: List[Tuple[str, str]] = []  # [(display_text, data), ...]

    def set_items(self, items: List[Tuple[str, str]]) -> None:
        """Set all items for the combobox.

        Args:
            items: List of (display_text, data) tuples
        """
        self._all_items = items
        self.blockSignals(True)
        current_data = self.currentData()

        self.clear()
        self.addItem("Nova conversa", "")
        for display, data in items:
            self.addItem(display, data)

        # Restore selection if possible
        if current_data:
            index = self.findData(current_data)
            if index >= 0:
                self.setCurrentIndex(index)

        self.blockSignals(False)


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

        # Store original data for retrieval
        self._text = text
        self._is_user = is_user

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        # Use QTextBrowser for better text rendering and auto-sizing
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.setFrameShape(QFrame.Shape.NoFrame)
        self._browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Set markdown content
        self._browser.setMarkdown(text)

        # Style based on sender
        if is_user:
            bg_color = "#0e639c"
            text_color = "white"
        else:
            bg_color = "#3c3c3c"
            text_color = "#dcdcdc"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 8px;
            }}
        """)
        self._browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: transparent;
                color: {text_color};
                border: none;
            }}
        """)

        layout.addWidget(self._browser)

        # Track if height needs update
        self._height_valid = False

    def resizeEvent(self, event) -> None:
        """Recalculate height when width changes."""
        super().resizeEvent(event)
        self._update_browser_height()

    def showEvent(self, event) -> None:
        """Calculate height when shown."""
        super().showEvent(event)
        QTimer.singleShot(0, self._update_browser_height)

    def _update_browser_height(self) -> None:
        """Update browser height based on content and available width."""
        # Get available width (frame width minus margins)
        available_width = self.width() - 24  # 12 + 12 margins
        if available_width < 50:
            return

        doc = self._browser.document()
        doc.setTextWidth(available_width)

        # Calculate required height with some padding
        content_height = int(doc.size().height())
        required_height = max(content_height + 2, 20)

        self._browser.setFixedHeight(required_height)

    @property
    def text(self) -> str:
        """Get the original message text."""
        return self._text

    @property
    def is_user(self) -> bool:
        """Check if this is a user message."""
        return self._is_user


class ChatWidget(QWidget):
    """
    Chat widget for AI interaction.

    Provides:
    - Message history display
    - Input field for user messages
    - Send button
    - Status indicator
    - Conversation selector

    Emits:
    - message_sent(str): When user sends a message
    - stop_requested(): When user clicks stop button
    - conversation_changed(str): When user selects a different conversation
    - new_conversation_requested(): When user wants to start a new conversation
    """

    message_sent = Signal(str)
    stop_requested = Signal()
    conversation_changed = Signal(str)  # Emits conv_id or "" for new
    new_conversation_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._is_processing = False
        self._display_messages: List[Tuple[str, bool]] = []  # Track messages for saving
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the chat UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Header with conversation selector
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header = QLabel("Chat IA")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #dcdcdc;
                padding: 4px;
            }
        """)
        header_layout.addWidget(header)

        # Account balance label (subtle, right-aligned in header)
        self._balance_label = QLabel("")
        self._balance_label.setStyleSheet("""
            QLabel {
                color: #6a9955;
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self._balance_label.setToolTip("Saldo OpenRouter")
        self._balance_label.hide()
        header_layout.addWidget(self._balance_label)

        # Conversation selector combobox
        self._conversation_combo = ConversationComboBox()
        self._conversation_combo.setToolTip("Clique para ver conversas anteriores")
        self._conversation_combo.setMinimumWidth(200)
        self._conversation_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                color: #dcdcdc;
                min-height: 24px;
            }
            QComboBox:hover {
                border: 1px solid #007acc;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
            }
            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                selection-background-color: #094771;
                color: #dcdcdc;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px;
                min-height: 24px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #3c3c3c;
            }
        """)
        self._conversation_combo.addItem("Nova conversa", "")
        self._conversation_combo.currentIndexChanged.connect(self._on_conversation_selected)
        header_layout.addWidget(self._conversation_combo, 1)

        # New conversation button
        self._new_conv_btn = QPushButton("+")
        self._new_conv_btn.setToolTip("Iniciar nova conversa")
        self._new_conv_btn.setFixedSize(26, 26)
        self._new_conv_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 4px;
                color: white;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
        """)
        self._new_conv_btn.clicked.connect(self._on_new_conversation)
        header_layout.addWidget(self._new_conv_btn)

        layout.addLayout(header_layout)

        # Cost display label
        self._cost_label = QLabel("")
        self._cost_label.setStyleSheet("""
            QLabel {
                color: #4ec9b0;
                font-size: 11px;
                padding: 2px 4px;
            }
        """)
        self._cost_label.setToolTip("Custo da conversa atual")
        self._cost_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._cost_label.setMinimumWidth(0)
        self._cost_label.hide()  # Hidden until there's cost data
        layout.addWidget(self._cost_label)

        # Status indicator
        self._status_label = QLabel("Pronto")
        self._status_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 11px;
                padding: 2px;
            }
        """)
        # Prevent status label from expanding the chat width
        self._status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._status_label.setMinimumWidth(0)
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
        self._input_field.setViewportMargins(0, 0, 0, 0)
        input_layout.addWidget(self._input_field)

        # Unified action button (Send / Stop) placed inside input field
        self._action_btn = QToolButton(self._input_field)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setIconSize(QSize(16, 16))
        self._action_btn.setAutoRaise(True)
        self._action_btn.clicked.connect(self._on_action_clicked)
        self._action_btn.resize(26, 26)
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
        margin = 4
        width = self._action_btn.width()
        height = self._action_btn.height()
        viewport_rect = self._input_field.viewport().geometry()
        x = viewport_rect.right() - width - margin + self._input_field.frameWidth()
        y = viewport_rect.bottom() - height - margin + self._input_field.frameWidth()
        self._action_btn.move(x, y)
        self._action_btn.raise_()

    def add_message(self, text: str, is_user: bool, track: bool = True) -> None:
        """
        Add a message to the chat history.

        Args:
            text: Message text
            is_user: True if message is from user, False if from AI
            track: If True, add to display_messages for persistence
        """
        # Normalize line endings and trim leading/trailing blanks
        normalized = text.replace("\r\n", "\n")
        if is_user:
            normalized = normalized.strip()
        else:
            normalized = normalized.lstrip()

        # Track message for persistence
        if track:
            self._display_messages.append((normalized, is_user))

        # Remove the stretch at the end
        stretch_item = self._messages_layout.takeAt(self._messages_layout.count() - 1)

        # Add message bubble - no alignment restriction to use full width
        bubble = MessageBubble(normalized, is_user)
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
        self._status_label.setToolTip(status if len(status) > 50 else "")

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
        # Clear tracked messages
        self._display_messages.clear()

        # Reset cost display
        self.reset_cost()

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

    # === Conversation management ===

    def _on_conversation_selected(self, index: int) -> None:
        """Handle conversation selection from combobox."""
        conv_id = self._conversation_combo.currentData()
        self.conversation_changed.emit(conv_id or "")

    def _on_new_conversation(self) -> None:
        """Handle new conversation button click."""
        self.new_conversation_requested.emit()

    def set_conversations(self, conversations: List[Tuple[str, str, str]]) -> None:
        """
        Populate the conversation selector.

        Args:
            conversations: List of (conv_id, title, updated_at) tuples
        """
        items = []
        for conv_id, title, updated_at in conversations:
            # Format: "Title - DD/MM HH:MM"
            try:
                dt = datetime.fromisoformat(updated_at)
                timestamp = dt.strftime("%d/%m %H:%M")
            except Exception:
                timestamp = ""

            display = title[:30] + ("..." if len(title) > 30 else "")
            if timestamp:
                display += f" - {timestamp}"

            items.append((display, conv_id))

        self._conversation_combo.set_items(items)

    def set_current_conversation(self, conv_id: Optional[str]) -> None:
        """Select a conversation in the combobox."""
        self._conversation_combo.blockSignals(True)

        if not conv_id:
            self._conversation_combo.setCurrentIndex(0)
        else:
            index = self._conversation_combo.findData(conv_id)
            if index >= 0:
                self._conversation_combo.setCurrentIndex(index)

        self._conversation_combo.blockSignals(False)

    def restore_messages(self, messages: List[Tuple[str, bool]]) -> None:
        """
        Restore chat messages from saved state.

        Args:
            messages: List of (text, is_user) tuples
        """
        self.clear_messages()
        for text, is_user in messages:
            self.add_message(text, is_user, track=False)
        # Update tracked messages
        self._display_messages = list(messages)

    def get_display_messages(self) -> List[Tuple[str, bool]]:
        """
        Get current display messages for saving.

        Returns:
            List of (text, is_user) tuples
        """
        return self._display_messages.copy()

    def update_cost(self, total_cost: float, prompt_tokens: int, completion_tokens: int) -> None:
        """
        Update the cost display.

        Args:
            total_cost: Total cost in USD
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens used
        """
        if total_cost > 0 or prompt_tokens > 0 or completion_tokens > 0:
            total_tokens = prompt_tokens + completion_tokens
            if total_cost >= 0.01:
                cost_text = f"${total_cost:.4f}"
            elif total_cost > 0:
                cost_text = f"${total_cost:.6f}"
            else:
                cost_text = "$0.00"
            self._cost_label.setText(f"💰 {cost_text} | {total_tokens:,} tokens")
            self._cost_label.show()
        else:
            self._cost_label.hide()

    def reset_cost(self) -> None:
        """Reset the cost display for a new conversation."""
        self._cost_label.setText("")
        self._cost_label.hide()

    def update_balance(self, balance: Optional[float]) -> None:
        """
        Update the account balance display.

        Args:
            balance: Balance in USD, or None to hide
        """
        if balance is not None:
            if balance < 0:
                # Negative balance - show in red
                self._balance_label.setStyleSheet("""
                    QLabel {
                        color: #f14c4c;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
                self._balance_label.setText(f"💳 ${balance:.2f}")
            elif balance < 1.0:
                # Low balance - show in yellow
                self._balance_label.setStyleSheet("""
                    QLabel {
                        color: #cca700;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
                self._balance_label.setText(f"💳 ${balance:.2f}")
            else:
                # Normal balance - show in green
                self._balance_label.setStyleSheet("""
                    QLabel {
                        color: #6a9955;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
                self._balance_label.setText(f"💳 ${balance:.2f}")
            self._balance_label.show()
        else:
            self._balance_label.hide()
