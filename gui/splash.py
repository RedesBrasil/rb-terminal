"""
Splash Screen for RB Terminal.
Displays logo during application startup.
"""

from PySide6.QtWidgets import QSplashScreen
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt

from core.resources import get_resource_path


class SplashScreen(QSplashScreen):
    """Splash screen with logo displayed during startup."""

    def __init__(self):
        # Load logo
        logo_path = get_resource_path("logo.ico")
        pixmap = QPixmap(str(logo_path))

        # Scale if too large (max 256x256)
        if pixmap.width() > 256 or pixmap.height() > 256:
            pixmap = pixmap.scaled(
                256, 256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        # Create a larger pixmap with dark background for the splash
        splash_width = max(pixmap.width() + 80, 300)
        splash_height = pixmap.height() + 100
        splash_pixmap = QPixmap(splash_width, splash_height)
        splash_pixmap.fill(QColor("#1e1e1e"))

        # Draw logo centered
        painter = QPainter(splash_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x = (splash_width - pixmap.width()) // 2
        y = 20
        painter.drawPixmap(x, y, pixmap)

        # Draw app name
        painter.setPen(QColor("#dcdcdc"))
        font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        painter.setFont(font)
        text_y = y + pixmap.height() + 30
        painter.drawText(
            0, text_y, splash_width, 30,
            Qt.AlignmentFlag.AlignHCenter,
            "RB Terminal"
        )

        # Draw loading text
        painter.setPen(QColor("#888888"))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.drawText(
            0, text_y + 30, splash_width, 20,
            Qt.AlignmentFlag.AlignHCenter,
            "Loading..."
        )

        painter.end()

        super().__init__(splash_pixmap)
        self.setWindowFlags(
            Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
        )

    def show_message(self, message: str) -> None:
        """Update the loading message."""
        self.showMessage(
            message,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            QColor("#888888")
        )
