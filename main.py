#!/usr/bin/env python3
"""
SSH AI Terminal - Entry Point

A desktop SSH terminal with AI integration.
Uses PySide6 for GUI and asyncssh for SSH connections.
"""

import sys
import asyncio
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import qasync

from gui.main_window import MainWindow


def setup_logging() -> None:
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main() -> int:
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting SSH AI Terminal")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("SSH AI Terminal")
    app.setApplicationVersion("0.1.0")

    # Enable high DPI scaling
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    # Create async event loop integrated with Qt
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run the event loop
    with loop:
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            logger.info("Shutting down")

    return 0


if __name__ == "__main__":
    sys.exit(main())
