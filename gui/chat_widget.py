"""
Chat Widget for AI interaction.
Provides a chat interface for communicating with the AI agent.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor

logger = logging.getLogger(__name__)


class MessageBubble(QFrame):
    """A message bubble for displaying chat messages."""

    def __init__(self, text: str, is_user: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        # Message label
        label = QTextEdit()
        label.setReadOnly(True)
        label.setPlainText(text)
        label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        label.setFrameShape(QFrame.Shape.NoFrame)

        # Auto-resize height
        doc = label.document()
        doc.setTextWidth(label.viewport().width())
        height = int(doc.size().height()) + 10
        label.setFixedHeight(min(height, 300))

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
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()  # Push messages to top

        self._scroll_area.setWidget(self._messages_container)
        layout.addWidget(self._scroll_area, 1)  # Stretch factor

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Digite sua mensagem...")
        self._input_field.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #dcdcdc;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        self._input_field.returnPressed.connect(self._on_send_clicked)
        input_layout.addWidget(self._input_field)

        # Send button
        self._send_btn = QPushButton("Enviar")
        self._send_btn.setFixedWidth(70)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        self._send_btn.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self._send_btn)

        # Stop button
        self._stop_btn = QPushButton("Parar")
        self._stop_btn.setFixedWidth(70)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                border: none;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QPushButton:hover {
                background-color: #e81123;
            }
            QPushButton:pressed {
                background-color: #c50f1f;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setEnabled(False)
        input_layout.addWidget(self._stop_btn)

        layout.addLayout(input_layout)

    @Slot()
    def _on_send_clicked(self) -> None:
        """Handle send button click."""
        message = self._input_field.text().strip()
        if message and not self._is_processing:
            self._input_field.clear()
            self.add_message(message, is_user=True)
            self.message_sent.emit(message)

    @Slot()
    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        self.stop_requested.emit()
        self.set_status("Parando...")

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
        self._send_btn.setEnabled(not processing)
        self._stop_btn.setEnabled(processing)
        self._input_field.setEnabled(not processing)

        if processing:
            self.set_status("IA pensando...")
        else:
            self.set_status("Pronto")

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
        self._input_field.setEnabled(enabled and not self._is_processing)
        self._send_btn.setEnabled(enabled and not self._is_processing)

        if not enabled:
            self.set_status("Conecte-se a um host primeiro")
        elif not self._is_processing:
            self.set_status("Pronto")
