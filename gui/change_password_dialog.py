"""
Change master password dialog for RB Terminal.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class ChangePasswordDialog(QDialog):
    """Dialog for changing or setting the master password."""

    def __init__(self, has_current_password: bool = True, parent=None):
        super().__init__(parent)

        self._has_current_password = has_current_password
        self._old_password = ""
        self._new_password = ""

        if has_current_password:
            self.setWindowTitle("Alterar Senha Mestra")
        else:
            self.setWindowTitle("Definir Senha Mestra")

        self.setMinimumWidth(400)
        self.setModal(True)

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Current password (only if has one)
        if self._has_current_password:
            current_label = QLabel("Senha atual:")
            layout.addWidget(current_label)

            self._current_password = QLineEdit()
            self._current_password.setEchoMode(QLineEdit.EchoMode.Password)
            self._current_password.setPlaceholderText("Digite sua senha atual")
            layout.addWidget(self._current_password)

            layout.addSpacing(10)

        # New password
        new_label = QLabel("Nova senha:")
        layout.addWidget(new_label)

        self._new_password_edit = QLineEdit()
        self._new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_password_edit.setPlaceholderText("Digite a nova senha")
        layout.addWidget(self._new_password_edit)

        # Confirm password
        confirm_label = QLabel("Confirmar nova senha:")
        layout.addWidget(confirm_label)

        self._confirm_password = QLineEdit()
        self._confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_password.setPlaceholderText("Digite novamente")
        layout.addWidget(self._confirm_password)

        # Warning
        warning_frame = QFrame()
        warning_frame.setStyleSheet("""
            QFrame {
                background-color: #3d3520;
                border: 1px solid #6d5520;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        warning_layout = QVBoxLayout(warning_frame)
        warning_label = QLabel(
            "Guarde bem esta senha!\n\n"
            "Ela sera necessaria para:\n"
            "  - Abrir o app em outro computador\n"
            "  - Recuperar senhas apos reinstalar"
        )
        warning_label.setStyleSheet("color: #ffd54f;")
        warning_layout.addWidget(warning_label)
        layout.addWidget(warning_frame)

        # Option to remove password
        if self._has_current_password:
            layout.addSpacing(10)
            remove_label = QLabel("Ou deixe os campos vazios para remover a senha mestra.")
            remove_label.setStyleSheet("color: #888;")
            remove_label.setWordWrap(True)
            layout.addWidget(remove_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        btn_save = QPushButton("Salvar")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #dcdcdc;
            }
            QLabel {
                color: #dcdcdc;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 8px;
                color: #dcdcdc;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                border-radius: 3px;
                padding: 8px 20px;
                color: white;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def _on_save(self) -> None:
        new_pw = self._new_password_edit.text()
        confirm_pw = self._confirm_password.text()

        # Allow empty password only if removing (has current password)
        if not new_pw and not self._has_current_password:
            QMessageBox.warning(self, "Erro", "Digite uma nova senha.")
            return

        if new_pw:
            if len(new_pw) < 4:
                QMessageBox.warning(self, "Erro", "A senha deve ter pelo menos 4 caracteres.")
                return

            if new_pw != confirm_pw:
                QMessageBox.warning(self, "Erro", "As senhas nao conferem.")
                self._confirm_password.clear()
                self._confirm_password.setFocus()
                return

        # If removing password, confirm
        if not new_pw and self._has_current_password:
            reply = QMessageBox.warning(
                self,
                "Remover Senha Mestra",
                "Voce esta removendo a protecao por senha.\n\n"
                "Suas senhas de conexao ficarao em texto plano no arquivo de dados.\n\n"
                "Tem certeza?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._old_password = self._current_password.text() if self._has_current_password else ""
        self._new_password = new_pw
        self.accept()

    def get_old_password(self) -> str:
        return self._old_password

    def get_new_password(self) -> str:
        return self._new_password
