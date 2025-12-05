"""
Resource path helper for PyInstaller compatibility.
Works both in development (running as script) and production (compiled .exe).
"""

import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> Path:
    """Return absolute path to a resource, works in dev and compiled .exe.

    Args:
        relative_path: Path relative to the project root (e.g., 'logo.ico')

    Returns:
        Absolute Path to the resource
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as compiled .exe (PyInstaller)
        base_path = Path(sys._MEIPASS)
    else:
        # Running as script in development
        base_path = Path(__file__).parent.parent

    return base_path / relative_path
