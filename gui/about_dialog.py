"""
About Dialog for RB Terminal.
Displays application information and logo.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt

from core.resources import get_resource_path


class AboutDialog(QDialog):
    """About dialog showing app info and logo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About RB Terminal")
        self.setFixedSize(350, 250)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # Set window icon
        logo_path = get_resource_path("logo.ico")
        self.setWindowIcon(QIcon(str(logo_path)))

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 20)

        # Logo
        logo_path = get_resource_path("logo.ico")
        logo_pixmap = QPixmap(str(logo_path))
        if logo_pixmap.width() > 64:
            logo_pixmap = logo_pixmap.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        logo_label = QLabel()
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)

        # App name
        name_label = QLabel("RB Terminal")
        name_label.setObjectName("appName")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # Version
        version_label = QLabel("Version 0.1.0")
        version_label.setObjectName("version")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        # Description
        desc_label = QLabel("SSH Terminal with AI Integration")
        desc_label.setObjectName("description")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)

        layout.addStretch()

        # OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _apply_style(self) -> None:
        """Apply dark theme styling."""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #dcdcdc;
            }
            QLabel#appName {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#version {
                font-size: 12px;
                color: #888888;
            }
            QLabel#description {
                font-size: 11px;
                color: #aaaaaa;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8c;
            }
        """)
