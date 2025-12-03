"""
Cryptography module for secure password storage.
Supports both legacy Fernet-based encryption and new PBKDF2-derived master password.
"""

import os
import base64
import hashlib
import logging
import secrets
from pathlib import Path
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# PBKDF2 parameters
PBKDF2_ITERATIONS = 600000  # OWASP recommendation for 2024+
SALT_LENGTH = 32


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


class CryptoManager:
    """
    Manages encryption/decryption of sensitive data.

    Supports two modes:
    1. Master password mode: Key derived from user password via PBKDF2
    2. No password mode: Passwords stored in plaintext (user's choice)
    """

    def __init__(self, master_password: Optional[str] = None, salt: Optional[bytes] = None):
        """
        Initialize crypto manager.

        Args:
            master_password: Optional master password to derive key from
            salt: Optional salt (required if master_password is provided for existing data)
        """
        self._key: Optional[bytes] = None
        self._fernet: Optional[Fernet] = None
        self._salt: Optional[bytes] = salt

        if master_password:
            if salt:
                # Existing data - use provided salt
                self._key, _ = self._derive_key(master_password, salt)
            else:
                # New setup - generate new salt
                self._key, self._salt = self._derive_key(master_password)
            self._fernet = Fernet(base64.urlsafe_b64encode(self._key))

    def _derive_key(self, password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Derive encryption key from password using PBKDF2.

        Args:
            password: Master password
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (derived_key, salt)
        """
        if salt is None:
            salt = secrets.token_bytes(SALT_LENGTH)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        return key, salt

    @property
    def salt(self) -> Optional[bytes]:
        """Get the salt used for key derivation."""
        return self._salt

    @property
    def salt_base64(self) -> Optional[str]:
        """Get salt as base64 string."""
        if self._salt:
            return base64.b64encode(self._salt).decode('utf-8')
        return None

    @property
    def has_key(self) -> bool:
        """Check if encryption key is available."""
        return self._key is not None

    def get_derived_key_base64(self) -> Optional[str]:
        """Get derived key as base64 for session caching."""
        if self._key:
            return base64.b64encode(self._key).decode('utf-8')
        return None

    def set_key_from_base64(self, key_base64: str) -> None:
        """Set derived key from base64 (for session cache restore)."""
        self._key = base64.b64decode(key_base64)
        self._fernet = Fernet(base64.urlsafe_b64encode(self._key))

    def hash_password(self, password: str, salt: bytes) -> str:
        """
        Hash master password for validation.

        Args:
            password: Master password
            salt: Salt to use

        Returns:
            Base64-encoded password hash
        """
        # Use PBKDF2 with different info to create verification hash
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt + b'_verify',  # Different salt for verification
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        hash_bytes = kdf.derive(password.encode('utf-8'))
        return base64.b64encode(hash_bytes).decode('utf-8')

    def verify_password(self, password: str, salt: bytes, stored_hash: str) -> bool:
        """
        Verify master password against stored hash.

        Args:
            password: Password to verify
            salt: Salt used during hashing
            stored_hash: Base64-encoded hash to compare

        Returns:
            True if password matches
        """
        computed_hash = self.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, stored_hash)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded encrypted string, or plaintext if no key
        """
        if not plaintext:
            return ""

        if not self._fernet:
            # No encryption - return as-is (user chose no master password)
            return plaintext

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
        if not ciphertext:
            return ""

        if not self._fernet:
            # No encryption - return as-is
            return ciphertext

        try:
            decrypted = self._fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted.decode('utf-8')
        except InvalidToken:
            logger.error("Failed to decrypt: invalid token (wrong key or corrupted)")
            raise
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise


class LegacyCryptoManager:
    """
    Legacy crypto manager for migration from old Fernet-based system.
    Used only for reading old encrypted passwords during migration.
    """

    def __init__(self, config_dir: Path):
        """
        Initialize legacy crypto manager.

        Args:
            config_dir: Directory where the key file is stored
        """
        self._config_dir = config_dir
        self._key_file = config_dir / ".key"
        self._fernet: Optional[Fernet] = None
        self._load_key()

    def _load_key(self) -> bool:
        """Load encryption key from file."""
        if not self._key_file.exists():
            return False

        try:
            key = self._key_file.read_bytes()
            self._fernet = Fernet(key)
            logger.debug("Loaded legacy encryption key from file")
            return True
        except Exception as e:
            logger.error(f"Failed to load legacy encryption key: {e}")
            return False

    @property
    def has_key(self) -> bool:
        """Check if legacy key exists."""
        return self._fernet is not None

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string using legacy key.

        Args:
            ciphertext: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string
        """
        if not self._fernet:
            raise RuntimeError("Legacy encryption key not loaded")

        if not ciphertext:
            return ""

        try:
            decrypted = self._fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted.decode('utf-8')
        except InvalidToken:
            logger.error("Failed to decrypt with legacy key")
            raise
        except Exception as e:
            logger.error(f"Legacy decryption error: {e}")
            raise

    def delete_key_file(self) -> bool:
        """Delete legacy key file after successful migration."""
        try:
            if self._key_file.exists():
                self._key_file.unlink()
                logger.info("Deleted legacy .key file")
                return True
        except Exception as e:
            logger.error(f"Failed to delete legacy key file: {e}")
        return False
