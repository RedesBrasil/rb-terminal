"""
Settings management module.
Handles loading and saving application settings to user config directory.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from core.crypto import get_config_dir

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_SETTINGS = {
    "openrouter_api_key": "",
    "default_model": "google/gemini-2.5-flash",
    "theme": "dark"
}


def get_base_path() -> Path:
    """Get base path for resources (supports PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys._MEIPASS)
    else:
        # Running as script
        return Path(__file__).parent.parent


@dataclass
class Settings:
    """Application settings."""
    openrouter_api_key: str = ""
    default_model: str = "google/gemini-2.5-flash"
    theme: str = "dark"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Create Settings from dictionary."""
        return cls(
            openrouter_api_key=data.get("openrouter_api_key", ""),
            default_model=data.get("default_model", "google/gemini-2.5-flash"),
            theme=data.get("theme", "dark")
        )


class SettingsManager:
    """Manages application settings with persistence."""

    def __init__(self):
        self._config_dir = get_config_dir()
        self._settings_file = self._config_dir / "settings.json"
        self._settings: Optional[Settings] = None
        self._load()

    def _load(self) -> None:
        """Load settings from file."""
        settings_data = {}

        # Priority 1: User config directory (%APPDATA%\.rb-terminal\settings.json)
        if self._settings_file.exists():
            try:
                with open(self._settings_file, "r", encoding="utf-8") as f:
                    settings_data = json.load(f)
                    logger.debug(f"Loaded settings from {self._settings_file}")
            except Exception as e:
                logger.warning(f"Failed to load settings from user dir: {e}")

        # Priority 2: Bundled config (for PyInstaller or development)
        if not settings_data:
            base_path = get_base_path()
            bundled_config = base_path / "config" / "settings.json"
            if bundled_config.exists():
                try:
                    with open(bundled_config, "r", encoding="utf-8") as f:
                        settings_data = json.load(f)
                        logger.debug(f"Loaded settings from bundled config")
                except Exception as e:
                    logger.warning(f"Failed to load bundled settings: {e}")

        # Priority 3: Local config (for development)
        if not settings_data:
            local_config = Path(__file__).parent.parent / "config" / "settings.json"
            if local_config.exists():
                try:
                    with open(local_config, "r", encoding="utf-8") as f:
                        settings_data = json.load(f)
                        logger.debug(f"Loaded settings from local config")
                except Exception as e:
                    logger.warning(f"Failed to load local settings: {e}")

        # Apply defaults for missing keys
        for key, value in DEFAULT_SETTINGS.items():
            if key not in settings_data:
                settings_data[key] = value

        self._settings = Settings.from_dict(settings_data)

    def save(self) -> bool:
        """
        Save settings to user config directory.

        Returns:
            True if saved successfully, False otherwise
        """
        if not self._settings:
            return False

        try:
            # Ensure config directory exists
            self._config_dir.mkdir(parents=True, exist_ok=True)

            # Write settings file
            with open(self._settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Settings saved to {self._settings_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    @property
    def settings(self) -> Settings:
        """Get current settings."""
        if not self._settings:
            self._settings = Settings()
        return self._settings

    def get_api_key(self) -> str:
        """Get OpenRouter API key."""
        return self.settings.openrouter_api_key

    def set_api_key(self, key: str) -> None:
        """Set OpenRouter API key."""
        self.settings.openrouter_api_key = key

    def get_model(self) -> str:
        """Get default model."""
        return self.settings.default_model

    def set_model(self, model: str) -> None:
        """Set default model."""
        self.settings.default_model = model

    def reload(self) -> None:
        """Reload settings from file."""
        self._load()


# Singleton instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the singleton SettingsManager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
