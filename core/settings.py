"""
Settings management module.
Handles loading and saving application settings to user config directory.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field

from core.crypto import get_config_dir

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_SETTINGS = {
    "openrouter_api_key": "",
    "default_model": "google/gemini-2.5-flash",
    "theme": "dark",
    "max_agent_iterations": 10,
    "chat_position": "bottom",
    "available_tags": [],
    "hosts_view_mode": "cards",
    "hosts_sort_by": "name",
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
    max_agent_iterations: int = 10
    chat_position: str = "bottom"
    available_tags: list = field(default_factory=list)
    hosts_view_mode: str = "cards"
    hosts_sort_by: str = "name"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Create Settings from dictionary."""
        return cls(
            openrouter_api_key=data.get("openrouter_api_key", ""),
            default_model=data.get("default_model", "google/gemini-2.5-flash"),
            theme=data.get("theme", "dark"),
            max_agent_iterations=int(data.get("max_agent_iterations", 10) or 10),
            chat_position=data.get("chat_position", "bottom") or "bottom",
            available_tags=data.get("available_tags", []),
            hosts_view_mode=data.get("hosts_view_mode", "cards") or "cards",
            hosts_sort_by=data.get("hosts_sort_by", "name") or "name",
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

    def get_max_iterations(self) -> int:
        """Get max AI iterations."""
        value = getattr(self.settings, "max_agent_iterations", DEFAULT_SETTINGS["max_agent_iterations"])
        try:
            value_int = int(value)
        except (TypeError, ValueError):
            value_int = DEFAULT_SETTINGS["max_agent_iterations"]
        return max(1, value_int)

    def set_max_iterations(self, iterations: int) -> None:
        """Set max AI iterations (clamped to sensible bounds)."""
        safe_value = max(1, min(100, int(iterations)))
        self.settings.max_agent_iterations = safe_value

    def get_chat_position(self) -> str:
        """Get chat panel position."""
        value = getattr(self.settings, "chat_position", DEFAULT_SETTINGS["chat_position"])
        if value not in {"bottom", "left", "right"}:
            value = DEFAULT_SETTINGS["chat_position"]
        return value

    def set_chat_position(self, position: str) -> None:
        """Set chat panel position."""
        allowed = {"bottom", "left", "right"}
        if position not in allowed:
            position = DEFAULT_SETTINGS["chat_position"]
        self.settings.chat_position = position

    def reload(self) -> None:
        """Reload settings from file."""
        self._load()

    # Tags management
    def get_tags(self) -> list[str]:
        """Get list of available tags."""
        return list(self.settings.available_tags)

    def add_tag(self, tag: str) -> None:
        """Add a new tag to the available tags list."""
        tag = tag.strip()
        if tag and tag not in self.settings.available_tags:
            self.settings.available_tags.append(tag)
            self.settings.available_tags.sort()
            self.save()

    def remove_tag(self, tag: str) -> None:
        """Remove a tag from the available tags list."""
        if tag in self.settings.available_tags:
            self.settings.available_tags.remove(tag)
            self.save()

    # Hosts view settings
    def get_hosts_view_mode(self) -> str:
        """Get hosts view mode ('cards' or 'list')."""
        mode = getattr(self.settings, "hosts_view_mode", "cards")
        if mode not in {"cards", "list"}:
            mode = "cards"
        return mode

    def set_hosts_view_mode(self, mode: str) -> None:
        """Set hosts view mode."""
        if mode in {"cards", "list"}:
            self.settings.hosts_view_mode = mode
            self.save()

    def get_hosts_sort_by(self) -> str:
        """Get hosts sort field ('name', 'host', 'device_type')."""
        sort_by = getattr(self.settings, "hosts_sort_by", "name")
        if sort_by not in {"name", "host", "device_type"}:
            sort_by = "name"
        return sort_by

    def set_hosts_sort_by(self, sort_by: str) -> None:
        """Set hosts sort field."""
        if sort_by in {"name", "host", "device_type"}:
            self.settings.hosts_sort_by = sort_by
            self.save()


# Singleton instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the singleton SettingsManager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
