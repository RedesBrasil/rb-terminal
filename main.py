#!/usr/bin/env python3
"""
RB Terminal - Entry Point

A desktop SSH terminal with AI integration.
Uses PySide6 for GUI and asyncssh for SSH connections.
"""

import sys
import asyncio
import logging
import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import qasync

from gui.main_window import MainWindow


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application.

    Args:
        debug: If True, set log level to DEBUG. Otherwise, use INFO.
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main() -> int:
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="RB Terminal - SSH Terminal with AI Integration"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (verbose output)"
    )
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    if args.debug:
        logger.info("Starting RB Terminal (DEBUG MODE)")
    else:
        logger.info("Starting RB Terminal")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("RB Terminal")
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
