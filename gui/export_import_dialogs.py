"""
Export and Import dialogs for RB Terminal.
"""

import json
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QGroupBox, QRadioButton, QButtonGroup,
    QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class ExportDialog(QDialog):
    """Dialog for configuring export options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportar Dados")
        self.setMinimumWidth(400)
        self.setModal(True)

        self._options = {}
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Selecione o que exportar:")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Checkboxes for what to include
        self._settings_cb = QCheckBox("Configuracoes (API key, modelo, etc.)")
        self._settings_cb.setChecked(True)
        layout.addWidget(self._settings_cb)

        self._hosts_cb = QCheckBox("Hosts")
        self._hosts_cb.setChecked(True)
        self._hosts_cb.toggled.connect(self._on_hosts_toggled)
        layout.addWidget(self._hosts_cb)

        # Password options (only if hosts selected)
        self._password_frame = QFrame()
        password_layout = QVBoxLayout(self._password_frame)
        password_layout.setContentsMargins(20, 0, 0, 0)

        self._include_passwords_cb = QCheckBox("Incluir senhas dos hosts")
        self._include_passwords_cb.toggled.connect(self._on_passwords_toggled)
        password_layout.addWidget(self._include_passwords_cb)

        # Password fields (only if include passwords)
        self._password_fields = QFrame()
        pw_layout = QVBoxLayout(self._password_fields)
        pw_layout.setContentsMargins(20, 10, 0, 0)

        pw_info = QLabel("As senhas serao criptografadas com esta senha:")
        pw_info.setStyleSheet("color: #888;")
        pw_layout.addWidget(pw_info)

        self._export_password = QLineEdit()
        self._export_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._export_password.setPlaceholderText("Senha para o arquivo exportado")
        pw_layout.addWidget(self._export_password)

        self._export_password_confirm = QLineEdit()
        self._export_password_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._export_password_confirm.setPlaceholderText("Confirmar senha")
        pw_layout.addWidget(self._export_password_confirm)

        self._password_fields.setVisible(False)
        password_layout.addWidget(self._password_fields)

        layout.addWidget(self._password_frame)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        btn_export = QPushButton("Exportar")
        btn_export.setDefault(True)
        btn_export.clicked.connect(self._on_export)
        btn_layout.addWidget(btn_export)

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
            QCheckBox {
                color: #dcdcdc;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
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

    def _on_hosts_toggled(self, checked: bool) -> None:
        self._password_frame.setVisible(checked)
        if not checked:
            self._include_passwords_cb.setChecked(False)

    def _on_passwords_toggled(self, checked: bool) -> None:
        self._password_fields.setVisible(checked)

    def _on_export(self) -> None:
        if not self._settings_cb.isChecked() and not self._hosts_cb.isChecked():
            QMessageBox.warning(self, "Erro", "Selecione pelo menos uma opcao para exportar.")
            return

        if self._include_passwords_cb.isChecked():
            pw1 = self._export_password.text()
            pw2 = self._export_password_confirm.text()

            if not pw1:
                QMessageBox.warning(self, "Erro", "Digite uma senha para proteger o arquivo.")
                return

            if pw1 != pw2:
                QMessageBox.warning(self, "Erro", "As senhas nao conferem.")
                return

        self._options = {
            "include_settings": self._settings_cb.isChecked(),
            "include_hosts": self._hosts_cb.isChecked(),
            "include_passwords": self._include_passwords_cb.isChecked(),
            "export_password": self._export_password.text() if self._include_passwords_cb.isChecked() else None
        }
        self.accept()

    def get_options(self) -> dict:
        return self._options


class ImportDialog(QDialog):
    """Dialog for configuring import options."""

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar Dados")
        self.setMinimumWidth(400)
        self.setModal(True)

        self._file_path = file_path
        self._file_info = self._read_file_info()
        self._options = {}
        self._setup_ui()
        self._apply_style()

    def _read_file_info(self) -> dict:
        """Read and validate the import file."""
        try:
            with open(self._file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                "valid": True,
                "has_settings": "settings" in data,
                "has_hosts": "hosts" in data,
                "hosts_count": len(data.get("hosts", [])),
                "has_encrypted_passwords": data.get("has_encrypted_passwords", False),
                "exported_at": data.get("exported_at", "Desconhecido")
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # File info
        info_title = QLabel("Arquivo selecionado:")
        info_title_font = QFont()
        info_title_font.setBold(True)
        info_title.setFont(info_title_font)
        layout.addWidget(info_title)

        file_label = QLabel(str(self._file_path.name))
        file_label.setStyleSheet("color: #888;")
        layout.addWidget(file_label)

        if not self._file_info["valid"]:
            error_label = QLabel(f"Erro ao ler arquivo:\n{self._file_info['error']}")
            error_label.setStyleSheet("color: #f14c4c;")
            layout.addWidget(error_label)

            btn_layout = QHBoxLayout()
            btn_cancel = QPushButton("Fechar")
            btn_cancel.clicked.connect(self.reject)
            btn_layout.addWidget(btn_cancel)
            layout.addLayout(btn_layout)
            return

        # Content summary
        summary = []
        if self._file_info["has_settings"]:
            summary.append("Configuracoes")
        if self._file_info["has_hosts"]:
            summary.append(f"{self._file_info['hosts_count']} hosts")
        if self._file_info["has_encrypted_passwords"]:
            summary.append("senhas criptografadas")

        summary_label = QLabel(f"Conteudo: {', '.join(summary)}")
        layout.addWidget(summary_label)

        date_label = QLabel(f"Exportado em: {self._file_info['exported_at']}")
        date_label.setStyleSheet("color: #888;")
        layout.addWidget(date_label)

        layout.addSpacing(10)

        # Password field (if needed)
        if self._file_info["has_encrypted_passwords"]:
            pw_label = QLabel("Senha do arquivo exportado:")
            layout.addWidget(pw_label)

            self._import_password = QLineEdit()
            self._import_password.setEchoMode(QLineEdit.EchoMode.Password)
            self._import_password.setPlaceholderText("Digite a senha usada na exportacao")
            layout.addWidget(self._import_password)

        # Import mode
        mode_label = QLabel("Modo de importacao:")
        mode_font = QFont()
        mode_font.setBold(True)
        mode_label.setFont(mode_font)
        layout.addWidget(mode_label)

        self._merge_radio = QRadioButton("Mesclar (adicionar novos, manter existentes)")
        self._merge_radio.setChecked(True)
        layout.addWidget(self._merge_radio)

        self._replace_radio = QRadioButton("Substituir (apagar existentes)")
        layout.addWidget(self._replace_radio)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        btn_import = QPushButton("Importar")
        btn_import.setDefault(True)
        btn_import.clicked.connect(self._on_import)
        btn_layout.addWidget(btn_import)

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
            QRadioButton {
                color: #dcdcdc;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555555;
                border-radius: 8px;
                background-color: #3c3c3c;
            }
            QRadioButton::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
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

    def _on_import(self) -> None:
        self._options = {
            "merge": self._merge_radio.isChecked(),
            "import_password": None
        }

        if self._file_info["has_encrypted_passwords"]:
            pw = self._import_password.text()
            if not pw:
                QMessageBox.warning(self, "Erro", "Digite a senha do arquivo exportado.")
                return
            self._options["import_password"] = pw

        self.accept()

    def get_options(self) -> dict:
        return self._options
