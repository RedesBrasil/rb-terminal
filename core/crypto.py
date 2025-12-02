"""
Cryptography module for secure password storage.
Uses Fernet symmetric encryption from cryptography library.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class CryptoManager:
    """
    Manages encryption/decryption of sensitive data using Fernet.

    The encryption key is stored in a separate file and generated
    on first use. All passwords are encrypted before saving.
    """

    def __init__(self, config_dir: Path):
        """
        Initialize crypto manager.

        Args:
            config_dir: Directory where the key file will be stored
        """
        self._config_dir = config_dir
        self._key_file = config_dir / ".key"
        self._fernet: Optional[Fernet] = None
        self._ensure_key()

    def _ensure_key(self) -> None:
        """Ensure encryption key exists, create if not."""
        self._config_dir.mkdir(parents=True, exist_ok=True)

        if self._key_file.exists():
            try:
                key = self._key_file.read_bytes()
                self._fernet = Fernet(key)
                logger.debug("Loaded encryption key from file")
            except Exception as e:
                logger.error(f"Failed to load encryption key: {e}")
                self._generate_new_key()
        else:
            self._generate_new_key()

    def _generate_new_key(self) -> None:
        """Generate a new encryption key and save it."""
        key = Fernet.generate_key()
        try:
            self._key_file.write_bytes(key)
            # Set restrictive permissions (Windows handles this differently)
            if os.name != 'nt':
                os.chmod(self._key_file, 0o600)
            self._fernet = Fernet(key)
            logger.info("Generated new encryption key")
        except Exception as e:
            logger.error(f"Failed to save encryption key: {e}")
            raise

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded encrypted string
        """
        if not self._fernet:
            raise RuntimeError("Encryption not initialized")

        if not plaintext:
            return ""

        encrypted = self._fernet.encrypt(plaintext.encode('utf-8'))
        return encrypted.decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string.

        Args:
            ciphertext: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string

        Raises:
            InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        if not self._fernet:
            raise RuntimeError("Encryption not initialized")

        if not ciphertext:
            return ""

        try:
            decrypted = self._fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted.decode('utf-8')
        except InvalidToken:
            logger.error("Failed to decrypt: invalid token (wrong key or corrupted)")
            raise
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise


def get_config_dir() -> Path:
    """
    Get the application configuration directory.

    Returns:
        Path to ~/.rb-terminal/
    """
    if os.name == 'nt':
        # Windows: use APPDATA or USERPROFILE
        base = os.environ.get('APPDATA') or os.environ.get('USERPROFILE', '')
        config_dir = Path(base) / '.rb-terminal'
    else:
        # Linux/Mac: use HOME
        config_dir = Path.home() / '.rb-terminal'

    return config_dir
