"""
Device types management module.
Manages the list of device types (Linux, MikroTik, etc.) with support for custom types.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from core.crypto import get_config_dir

logger = logging.getLogger(__name__)

# Default device types that come pre-configured
DEFAULT_DEVICE_TYPES = [
    "Linux",
    "MikroTik",
    "Huawei",
    "Cisco"
]


class DeviceTypesManager:
    """
    Manages device types storage and retrieval.

    Device types are stored in a JSON file. Users can add custom types
    by typing them in the host form, and they will be saved for future use.
    """

    def __init__(self):
        """Initialize device types manager."""
        self._config_dir = get_config_dir()
        self._types_file = self._config_dir / "device_types.json"
        self._custom_types: list[str] = []
        self._load()

    def _load(self) -> None:
        """Load custom device types from JSON file."""
        self._config_dir.mkdir(parents=True, exist_ok=True)

        if not self._types_file.exists():
            logger.info("No device types file found, using defaults only")
            self._custom_types = []
            return

        try:
            with open(self._types_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._custom_types = data.get("custom_types", [])
            logger.info(f"Loaded {len(self._custom_types)} custom device types")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in device types file: {e}")
            self._custom_types = []
        except Exception as e:
            logger.error(f"Failed to load device types: {e}")
            self._custom_types = []

    def _save(self) -> None:
        """Save custom device types to JSON file."""
        try:
            data = {"custom_types": self._custom_types}
            with open(self._types_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Device types saved to file")
        except Exception as e:
            logger.error(f"Failed to save device types: {e}")
            raise

    def get_all(self) -> list[str]:
        """
        Get all device types (defaults + custom).

        Returns:
            List of device type names, defaults first then custom sorted alphabetically
        """
        # Start with defaults in order
        all_types = DEFAULT_DEVICE_TYPES.copy()

        # Add custom types that aren't already in defaults (sorted)
        for custom in sorted(self._custom_types):
            if custom not in all_types:
                all_types.append(custom)

        return all_types

    def get_defaults(self) -> list[str]:
        """Get only the default device types."""
        return DEFAULT_DEVICE_TYPES.copy()

    def get_custom(self) -> list[str]:
        """Get only the custom device types."""
        return self._custom_types.copy()

    def add_custom(self, device_type: str) -> bool:
        """
        Add a custom device type if it doesn't exist.

        Args:
            device_type: The device type name to add

        Returns:
            True if added, False if already exists
        """
        device_type = device_type.strip()
        if not device_type:
            return False

        # Check if already exists in defaults or custom
        all_types_lower = [t.lower() for t in self.get_all()]
        if device_type.lower() in all_types_lower:
            logger.debug(f"Device type already exists: {device_type}")
            return False

        self._custom_types.append(device_type)
        self._save()
        logger.info(f"Added custom device type: {device_type}")
        return True

    def remove_custom(self, device_type: str) -> bool:
        """
        Remove a custom device type.

        Args:
            device_type: The device type name to remove

        Returns:
            True if removed, False if not found or is a default type
        """
        # Can't remove default types
        if device_type in DEFAULT_DEVICE_TYPES:
            logger.warning(f"Cannot remove default device type: {device_type}")
            return False

        try:
            self._custom_types.remove(device_type)
            self._save()
            logger.info(f"Removed custom device type: {device_type}")
            return True
        except ValueError:
            logger.warning(f"Device type not found for removal: {device_type}")
            return False

    def is_valid(self, device_type: str) -> bool:
        """Check if a device type is in the list."""
        return device_type in self.get_all()

    def ensure_exists(self, device_type: str) -> None:
        """
        Ensure a device type exists, adding it as custom if necessary.

        This is used when saving a host - if the user typed a new device type,
        it will be added to the custom list.

        Args:
            device_type: The device type to ensure exists
        """
        if device_type and not self.is_valid(device_type):
            self.add_custom(device_type)


# Singleton instance for convenience
_instance: Optional[DeviceTypesManager] = None


def get_device_types_manager() -> DeviceTypesManager:
    """Get the singleton DeviceTypesManager instance."""
    global _instance
    if _instance is None:
        _instance = DeviceTypesManager()
    return _instance
