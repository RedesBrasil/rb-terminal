"""
First-run setup dialog for RB Terminal.
Allows user to choose master password protection.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QStackedWidget, QWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class SetupDialog(QDialog):
    """
    First-run setup dialog.

    Presents user with choice to:
    1. Set up master password (recommended)
    2. Continue without password protection
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RB Terminal - Configuracao Inicial")
        self.setMinimumWidth(500)
        self.setModal(True)

        # Force dark theme on dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e0e0e0;
            }
        """)

        self._master_password: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Stacked widget for pages
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0: Initial choice
        self._stack.addWidget(self._create_choice_page())

        # Page 1: Set master password
        self._stack.addWidget(self._create_password_page())

        # Page 2: Security warning (no password)
        self._stack.addWidget(self._create_warning_page())

    def _create_choice_page(self) -> QWidget:
        """Create the initial choice page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)

        # Title
        title = QLabel("Bem-vindo ao RB Terminal!")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Como voce deseja proteger suas senhas salvas?")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Option 1: With master password
        btn_with_password = self._create_option_button(
            "Definir Senha Mestra (Recomendado)",
            "Suas senhas serao criptografadas com uma senha que so voce conhece.\n"
            "Necessario para sincronizacao entre computadores.",
            "#2e7d32"  # Green
        )
        btn_with_password.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        layout.addWidget(btn_with_password)

        layout.addSpacing(10)

        # Option 2: Without password
        btn_no_password = self._create_option_button(
            "Nao Definir Senha Mestra",
            "Eu entendo os RISCOS: senhas serao salvas sem criptografia\n"
            "no arquivo de dados.",
            "#c62828"  # Red
        )
        btn_no_password.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        layout.addWidget(btn_no_password)

        layout.addStretch()

        return page

    def _create_option_button(self, title: str, description: str, color: str) -> QPushButton:
        """Create a styled option button."""
        btn = QPushButton()
        btn.setMinimumHeight(100)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Create content layout
        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(20, 15, 20, 15)

        # Text container
        text_container = QWidget()
        text_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: #ffffff;")
        text_layout.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        desc_label.setStyleSheet("color: #b0b0b0;")
        desc_label.setWordWrap(True)
        text_layout.addWidget(desc_label)

        content_layout.addWidget(text_container, 1)

        # Arrow indicator
        arrow_label = QLabel("→")
        arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        arrow_font = QFont()
        arrow_font.setPointSize(18)
        arrow_label.setFont(arrow_font)
        arrow_label.setStyleSheet(f"color: {color};")
        content_layout.addWidget(arrow_label)

        # Set button style with left border accent
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2a2a2a;
                border: 2px solid #404040;
                border-left: 4px solid {color};
                border-radius: 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: #363636;
                border: 2px solid {color};
                border-left: 4px solid {color};
            }}
            QPushButton:pressed {{
                background-color: #404040;
            }}
        """)

        # Create layout for button
        btn_layout = QVBoxLayout(btn)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(content)

        return btn

    def _create_password_page(self) -> QWidget:
        """Create the master password setup page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(15)

        # Title
        title = QLabel("Criar Senha Mestra")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Password field
        layout.addWidget(QLabel("Senha:"))
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Digite sua senha mestra")
        layout.addWidget(self._password_edit)

        # Confirm field
        layout.addWidget(QLabel("Confirmar:"))
        self._confirm_edit = QLineEdit()
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_edit.setPlaceholderText("Digite novamente")
        layout.addWidget(self._confirm_edit)

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

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Voltar")
        btn_cancel.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        btn_confirm = QPushButton("Confirmar")
        btn_confirm.setDefault(True)
        btn_confirm.clicked.connect(self._on_password_confirm)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #388e3c;
            }
        """)
        btn_layout.addWidget(btn_confirm)

        layout.addLayout(btn_layout)

        return page

    def _create_warning_page(self) -> QWidget:
        """Create the security warning page (no password)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(15)

        # Title with warning icon
        title = QLabel("Aviso de Seguranca")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ff9800;")
        layout.addWidget(title)

        # Warning message
        warning_frame = QFrame()
        warning_frame.setStyleSheet("""
            QFrame {
                background-color: #4a2020;
                border: 1px solid #c62828;
                border-radius: 6px;
                padding: 15px;
            }
        """)
        warning_layout = QVBoxLayout(warning_frame)
        warning_text = QLabel(
            "Sem senha mestra, suas senhas de conexao serao salvas em "
            "TEXTO PLANO no arquivo de dados.\n\n"
            "Qualquer pessoa com acesso ao arquivo podera ver suas senhas."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #ef9a9a;")
        warning_layout.addWidget(warning_text)
        layout.addWidget(warning_frame)

        # Confirmation question
        confirm_label = QLabel("Tem certeza que deseja continuar sem protecao?")
        confirm_label.setStyleSheet("color: #888;")
        layout.addWidget(confirm_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_back = QPushButton("Voltar")
        btn_back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_layout.addWidget(btn_back)

        btn_layout.addStretch()

        btn_continue = QPushButton("Continuar Assim")
        btn_continue.clicked.connect(self._on_no_password_confirm)
        btn_continue.setStyleSheet("""
            QPushButton {
                background-color: #c62828;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        btn_layout.addWidget(btn_continue)

        layout.addLayout(btn_layout)

        return page

    def _on_password_confirm(self) -> None:
        """Handle password confirmation."""
        password = self._password_edit.text()
        confirm = self._confirm_edit.text()

        if not password:
            QMessageBox.warning(self, "Erro", "Digite uma senha.")
            return

        if len(password) < 4:
            QMessageBox.warning(self, "Erro", "A senha deve ter pelo menos 4 caracteres.")
            return

        if password != confirm:
            QMessageBox.warning(self, "Erro", "As senhas nao conferem.")
            self._confirm_edit.clear()
            self._confirm_edit.setFocus()
            return

        self._master_password = password
        self.accept()

    def _on_no_password_confirm(self) -> None:
        """Handle no-password confirmation."""
        self._master_password = None
        self.accept()

    def get_master_password(self) -> str | None:
        """Get the master password if set."""
        return self._master_password
