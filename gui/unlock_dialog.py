"""
Unlock dialog for RB Terminal.
Used when master password is required but session is not cached.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class UnlockDialog(QDialog):
    """
    Dialog to unlock the application with master password.

    Shown when:
    - First time on this machine (data.json with master password, no .session)
    - Session file was deleted or corrupted
    """

    def __init__(self, parent=None, error_message: str = None):
        super().__init__(parent)
        self.setWindowTitle("RB Terminal - Desbloquear")
        self.setMinimumWidth(400)
        self.setModal(True)

        self._password: str = ""
        self._error_message = error_message
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("Desbloquear RB Terminal")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Info message
        info = QLabel(
            "Seus dados estao protegidos por senha mestra.\n"
            "Digite sua senha para continuar."
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #888;")
        layout.addWidget(info)

        layout.addSpacing(10)

        # Error message (if any)
        if self._error_message:
            error_frame = QFrame()
            error_frame.setStyleSheet("""
                QFrame {
                    background-color: #4a2020;
                    border: 1px solid #c62828;
                    border-radius: 6px;
                    padding: 10px;
                }
            """)
            error_layout = QVBoxLayout(error_frame)
            error_label = QLabel(self._error_message)
            error_label.setStyleSheet("color: #ef9a9a;")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_layout.addWidget(error_label)
            layout.addWidget(error_frame)

        # Password field
        layout.addWidget(QLabel("Senha Mestra:"))
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Digite sua senha mestra")
        self._password_edit.returnPressed.connect(self._on_unlock)
        layout.addWidget(self._password_edit)

        layout.addSpacing(20)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_exit = QPushButton("Sair")
        btn_exit.clicked.connect(self.reject)
        btn_layout.addWidget(btn_exit)

        btn_layout.addStretch()

        btn_unlock = QPushButton("Desbloquear")
        btn_unlock.setDefault(True)
        btn_unlock.clicked.connect(self._on_unlock)
        btn_unlock.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
        """)
        btn_layout.addWidget(btn_unlock)

        layout.addLayout(btn_layout)

        # Focus password field
        self._password_edit.setFocus()

    def _on_unlock(self) -> None:
        """Handle unlock button click."""
        self._password = self._password_edit.text()
        if self._password:
            self.accept()

    def get_password(self) -> str:
        """Get the entered password."""
        return self._password

    def clear_password(self) -> None:
        """Clear the password field."""
        self._password_edit.clear()
        self._password_edit.setFocus()

    def set_error(self, message: str) -> None:
        """Set error message and recreate UI."""
        self._error_message = message
        # Clear layout and recreate
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._setup_ui()
