"""
Unified data management module.
Handles all application data including settings, hosts, and security configuration.
"""

import json
import base64
import logging
import uuid
import asyncio
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field, asdict

import httpx

from core.crypto import CryptoManager, LegacyCryptoManager, get_config_dir

logger = logging.getLogger(__name__)

DATA_VERSION = "1.0"


@dataclass
class SecurityConfig:
    """Security configuration for the data file."""
    has_master_password: bool = False
    password_salt: Optional[str] = None  # Base64 encoded
    password_hash: Optional[str] = None  # Base64 encoded

    def to_dict(self) -> dict:
        result = {"has_master_password": self.has_master_password}
        if self.has_master_password:
            result["password_salt"] = self.password_salt
            result["password_hash"] = self.password_hash
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityConfig":
        return cls(
            has_master_password=data.get("has_master_password", False),
            password_salt=data.get("password_salt"),
            password_hash=data.get("password_hash")
        )


@dataclass
class Settings:
    """Application settings."""
    openrouter_api_key: str = ""
    default_model: str = "google/gemini-2.5-flash"
    theme: str = "dark"
    max_agent_iterations: int = 10
    chat_position: str = "bottom"
    sftp_position: str = "left"  # Posição do file browser: left, right, bottom
    available_tags: list = field(default_factory=list)
    hosts_view_mode: str = "cards"
    hosts_sort_by: str = "name"
    max_conversations_per_host: int = 10
    available_manufacturers: list = field(default_factory=list)
    available_os_versions: list = field(default_factory=list)
    available_functions: list = field(default_factory=list)
    available_groups: list = field(default_factory=list)
    winbox_path: str = ""  # Caminho completo do executável Winbox
    # Campos visíveis na view de hosts (ordem define posição)
    card_visible_fields: list = field(default_factory=lambda: ["name", "host", "tags", "device_type"])
    list_visible_fields: list = field(default_factory=lambda: ["name", "host", "port", "username", "tags", "device_type", "manufacturer"])
    # Larguras customizadas das colunas na lista (field_id: width)
    list_column_widths: dict = field(default_factory=dict)
    # System prompt customizado para IA (vazio = usar default)
    ai_system_prompt: str = ""
    # Telegram backup settings
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_backup_enabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        return cls(
            openrouter_api_key=data.get("openrouter_api_key", ""),
            default_model=data.get("default_model", "google/gemini-2.5-flash"),
            theme=data.get("theme", "dark"),
            max_agent_iterations=int(data.get("max_agent_iterations", 10) or 10),
            chat_position=data.get("chat_position", "bottom") or "bottom",
            sftp_position=data.get("sftp_position", "left") or "left",
            available_tags=data.get("available_tags", []),
            hosts_view_mode=data.get("hosts_view_mode", "cards") or "cards",
            hosts_sort_by=data.get("hosts_sort_by", "name") or "name",
            max_conversations_per_host=int(data.get("max_conversations_per_host", 10) or 10),
            available_manufacturers=data.get("available_manufacturers", []),
            available_os_versions=data.get("available_os_versions", []),
            available_functions=data.get("available_functions", []),
            available_groups=data.get("available_groups", []),
            winbox_path=data.get("winbox_path", ""),
            card_visible_fields=data.get("card_visible_fields", ["name", "host", "tags", "device_type"]),
            list_visible_fields=data.get("list_visible_fields", ["name", "host", "port", "username", "tags", "device_type", "manufacturer"]),
            list_column_widths=data.get("list_column_widths", {}),
            ai_system_prompt=data.get("ai_system_prompt", ""),
            telegram_bot_token=data.get("telegram_bot_token", ""),
            telegram_chat_id=data.get("telegram_chat_id", ""),
            telegram_backup_enabled=data.get("telegram_backup_enabled", False),
        )


@dataclass
class Host:
    """Represents a saved SSH host."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    hosts: list = field(default_factory=list)  # Lista de IPs/hostnames
    port: int = 22
    username: str = ""
    password_encrypted: Optional[str] = None
    terminal_type: str = "xterm"
    device_type: Optional[str] = None
    disable_terminal_detection: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list = field(default_factory=list)
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None
    functions: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    notes: Optional[str] = None
    port_knocking: list = field(default_factory=list)  # [{"protocol": "tcp", "port": 1234}, ...]
    winbox_port: int = 0  # 0 = usar padrão 8291
    http_port: int = 80  # Porta HTTP para acesso web
    https_enabled: bool = False  # Usar HTTPS ao invés de HTTP
    web_username: Optional[str] = None  # Usuário para auto-login web
    web_password_encrypted: Optional[str] = None  # Senha para auto-login web (criptografada)

    @property
    def host(self) -> str:
        """Retorna o primeiro IP/hostname para compatibilidade."""
        return self.hosts[0] if self.hosts else ""

    @property
    def primary_host(self) -> str:
        """Alias para host - retorna o primeiro IP/hostname."""
        return self.host

    def to_dict(self) -> dict:
        data = asdict(self)
        # Também salva 'host' para compatibilidade com versões anteriores
        data["host"] = self.host
        return data

    def get_effective_username(self) -> str:
        """Get username with any required suffixes."""
        if not self.username:
            return ""
        if self.disable_terminal_detection:
            if '+' not in self.username:
                return f"{self.username}+ct"
        return self.username

    @classmethod
    def from_dict(cls, data: dict) -> "Host":
        # Migração: se existir 'host' mas não 'hosts', converte para lista
        hosts_list = data.get("hosts", [])
        if not hosts_list and data.get("host"):
            hosts_list = [data.get("host")]

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            hosts=hosts_list,
            port=data.get("port", 22),
            username=data.get("username", ""),
            password_encrypted=data.get("password_encrypted"),
            terminal_type=data.get("terminal_type", "xterm"),
            device_type=data.get("device_type"),
            disable_terminal_detection=data.get("disable_terminal_detection", False),
            created_at=data.get("created_at", datetime.now().isoformat()),
            tags=data.get("tags", []),
            manufacturer=data.get("manufacturer"),
            os_version=data.get("os_version"),
            functions=data.get("functions", []),
            groups=data.get("groups", []),
            notes=data.get("notes"),
            port_knocking=data.get("port_knocking", []),
            winbox_port=data.get("winbox_port", 0),
            http_port=data.get("http_port", 80),
            https_enabled=data.get("https_enabled", False),
            web_username=data.get("web_username"),
            web_password_encrypted=data.get("web_password_encrypted"),
        )


@dataclass
class ChatMessage:
    """A single chat message in a conversation."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tool_calls: Optional[list] = None  # For assistant messages with tool calls
    tool_call_id: Optional[str] = None  # For tool response messages

    def to_dict(self) -> dict:
        result = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id")
        )


@dataclass
class Conversation:
    """A conversation session with a host."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    host_id: str = ""
    title: str = ""  # Auto-generated from first user message
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # Usage statistics
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "host_id": self.host_id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost": self.total_cost
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            host_id=data.get("host_id", ""),
            title=data.get("title", ""),
            messages=[ChatMessage.from_dict(m) for m in data.get("messages", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_cost=data.get("total_cost", 0.0)
        )


@dataclass
class ImportResult:
    """Result of an import operation."""
    success: bool
    hosts_imported: int = 0
    hosts_skipped: int = 0
    settings_imported: bool = False
    error: Optional[str] = None


class DataManager:
    """
    Unified manager for all application data.

    Handles:
    - Settings and hosts in a single data.json file
    - Master password encryption via PBKDF2
    - Session caching for passwordless unlock
    - Custom data path for sync (Dropbox, etc.)
    - Export/import with optional password protection
    - Migration from legacy separate files
    """

    _instance: Optional["DataManager"] = None

    def __init__(self):
        """Initialize data manager."""
        self._local_dir = get_config_dir()
        self._pointer_path = self._local_dir / "pointer.json"
        self._session_path = self._local_dir / ".session"

        self._data_path: Optional[Path] = None
        self._crypto: Optional[CryptoManager] = None
        self._security: SecurityConfig = SecurityConfig()
        self._settings: Settings = Settings()
        self._hosts: List[Host] = []
        self._conversations: List[Conversation] = []
        self._loaded: bool = False

        # Determine data path
        self._resolve_data_path()

    def _resolve_data_path(self) -> None:
        """Resolve the data file path from pointer or default."""
        self._local_dir.mkdir(parents=True, exist_ok=True)

        if self._pointer_path.exists():
            try:
                with open(self._pointer_path, 'r', encoding='utf-8') as f:
                    pointer = json.load(f)
                    custom_path = pointer.get("data_path")
                    if custom_path:
                        self._data_path = Path(custom_path)
                        logger.debug(f"Using custom data path: {self._data_path}")
                        return
            except Exception as e:
                logger.warning(f"Failed to read pointer file: {e}")

        # Default path
        self._data_path = self._local_dir / "data.json"

    # === State queries ===

    def is_first_run(self) -> bool:
        """Check if this is first run (no data.json exists)."""
        return not self._data_path.exists() and not self._has_legacy_files()

    def _has_legacy_files(self) -> bool:
        """Check if legacy files exist for migration."""
        hosts_file = self._local_dir / "hosts.json"
        settings_file = self._local_dir / "settings.json"
        return hosts_file.exists() or settings_file.exists()

    def has_master_password(self) -> bool:
        """Check if data file has master password protection."""
        if not self._data_path.exists():
            return False

        try:
            with open(self._data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                security = data.get("security", {})
                return security.get("has_master_password", False)
        except Exception:
            return False

    def has_cached_session(self) -> bool:
        """Check if we have a cached session key."""
        return self._session_path.exists()

    def needs_unlock(self) -> bool:
        """Check if unlock is needed (has master password but no cached session)."""
        return self.has_master_password() and not self.has_cached_session()

    def needs_migration(self) -> bool:
        """Check if legacy files need migration."""
        return not self._data_path.exists() and self._has_legacy_files()

    # === Setup (first run) ===

    def setup_master_password(self, password: str) -> None:
        """
        Set up with master password.

        Args:
            password: Master password to use
        """
        # Create crypto with new salt
        self._crypto = CryptoManager(master_password=password)

        # Store security config
        salt = self._crypto.salt
        self._security = SecurityConfig(
            has_master_password=True,
            password_salt=self._crypto.salt_base64,
            password_hash=self._crypto.hash_password(password, salt)
        )

        # Cache session
        self._cache_session()

        # Save initial data
        self._save()
        logger.info("Set up with master password")

    def setup_no_password(self) -> None:
        """Set up without master password (plaintext passwords)."""
        self._crypto = CryptoManager()  # No encryption
        self._security = SecurityConfig(has_master_password=False)
        self._save()
        logger.info("Set up without master password")

    # === Unlock ===

    def unlock(self, password: str) -> bool:
        """
        Unlock with master password.

        Args:
            password: Master password

        Returns:
            True if unlock successful
        """
        if not self._data_path.exists():
            return False

        try:
            with open(self._data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            security = SecurityConfig.from_dict(data.get("security", {}))
            if not security.has_master_password:
                return True  # No password needed

            salt = base64.b64decode(security.password_salt)
            temp_crypto = CryptoManager(master_password=password, salt=salt)

            if not temp_crypto.verify_password(password, salt, security.password_hash):
                return False

            # Password correct - set up crypto and cache
            self._crypto = temp_crypto
            self._security = security
            self._cache_session()
            return True

        except Exception as e:
            logger.error(f"Unlock failed: {e}")
            return False

    def _cache_session(self) -> None:
        """Cache derived key for future sessions."""
        if not self._crypto or not self._crypto.has_key:
            return

        try:
            session_data = {
                "derived_key": self._crypto.get_derived_key_base64()
            }
            with open(self._session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f)
            logger.debug("Session cached")
        except Exception as e:
            logger.error(f"Failed to cache session: {e}")

    def _load_cached_session(self) -> bool:
        """Load cached session key."""
        if not self._session_path.exists():
            return False

        try:
            with open(self._session_path, 'r', encoding='utf-8') as f:
                session = json.load(f)

            key_b64 = session.get("derived_key")
            if not key_b64:
                return False

            self._crypto = CryptoManager()
            self._crypto.set_key_from_base64(key_b64)
            logger.debug("Session loaded from cache")
            return True

        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False

    def clear_session(self) -> None:
        """Clear cached session (for password change or logout)."""
        try:
            if self._session_path.exists():
                self._session_path.unlink()
                logger.debug("Session cleared")
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")

    # === Data path ===

    def get_data_path(self) -> Path:
        """Get current data file path."""
        return self._data_path

    def set_data_path(self, path: Path) -> None:
        """
        Change data file location.

        Args:
            path: New path for data.json
        """
        new_path = (path / "data.json" if path.is_dir() else path).resolve()

        # No-op if the path is unchanged
        if self._data_path.resolve() == new_path:
            return

        # Ensure we have the latest in-memory data so we can write without
        # touching the potentially locked source file.
        if not self._loaded:
            self.load()

        temp_path = new_path.with_suffix(".tmp")

        try:
            self._write_to_path(temp_path)
            temp_path.replace(new_path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

        # Update pointer
        pointer = {"data_path": str(new_path)}
        with open(self._pointer_path, 'w', encoding='utf-8') as f:
            json.dump(pointer, f, indent=2)

        self._data_path = new_path
        logger.info(f"Data path changed to: {new_path}")

    # === Load/Save ===

    def load(self) -> None:
        """Load data from file."""
        if self._loaded:
            return

        # Try cached session first
        if self.has_master_password() and self.has_cached_session():
            if not self._load_cached_session():
                raise RuntimeError("Failed to load cached session")

        if not self._data_path.exists():
            # Check for migration
            if self._has_legacy_files():
                self._migrate_legacy_files()
            self._loaded = True
            return

        try:
            with open(self._data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._security = SecurityConfig.from_dict(data.get("security", {}))
            self._settings = Settings.from_dict(data.get("settings", {}))
            self._hosts = [Host.from_dict(h) for h in data.get("hosts", [])]
            self._conversations = [Conversation.from_dict(c) for c in data.get("conversations", [])]
            self._loaded = True
            logger.info(f"Loaded {len(self._hosts)} hosts, {len(self._conversations)} conversations")

        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            raise

    def _serialize_data(self) -> dict:
        """Serialize current state to a dict for persistence."""
        return {
            "version": DATA_VERSION,
            "security": self._security.to_dict(),
            "settings": self._settings.to_dict(),
            "hosts": [h.to_dict() for h in self._hosts],
            "conversations": [c.to_dict() for c in self._conversations]
        }

    def _write_to_path(self, path: Path) -> None:
        """Write serialized data to the given path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._serialize_data()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save(self, skip_telegram_backup: bool = False) -> None:
        """Save data to file.

        Args:
            skip_telegram_backup: If True, don't send backup to Telegram.
                                  Used for frequent updates like chat messages.
        """
        try:
            self._write_to_path(self._data_path)
            logger.debug("Data saved")
            # Send backup to Telegram if enabled (skip for chat updates)
            if not skip_telegram_backup:
                self._send_telegram_backup()

        except Exception as e:
            logger.error(f"Failed to save data: {e}")
            raise

    def save(self) -> None:
        """Public save method."""
        self._save()

    # === Migration ===

    def _migrate_legacy_files(self) -> None:
        """Migrate from legacy settings.json and hosts.json."""
        logger.info("Migrating legacy files...")

        hosts_file = self._local_dir / "hosts.json"
        settings_file = self._local_dir / "settings.json"
        legacy_crypto = LegacyCryptoManager(self._local_dir)

        # Migrate settings
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings_data = json.load(f)
                self._settings = Settings.from_dict(settings_data)
                logger.info("Migrated settings")
            except Exception as e:
                logger.warning(f"Failed to migrate settings: {e}")

        # Migrate hosts
        if hosts_file.exists():
            try:
                with open(hosts_file, 'r', encoding='utf-8') as f:
                    hosts_data = json.load(f)

                for h in hosts_data.get("hosts", []):
                    host = Host.from_dict(h)

                    # Decrypt password with legacy key if available
                    if host.password_encrypted and legacy_crypto.has_key:
                        try:
                            plaintext = legacy_crypto.decrypt(host.password_encrypted)
                            # Store as plaintext until user sets master password
                            host.password_encrypted = plaintext
                        except Exception:
                            logger.warning(f"Failed to decrypt password for host {host.name}")
                            host.password_encrypted = None

                    self._hosts.append(host)

                logger.info(f"Migrated {len(self._hosts)} hosts")

            except Exception as e:
                logger.warning(f"Failed to migrate hosts: {e}")

        # Security: no master password after migration (user can set later)
        self._security = SecurityConfig(has_master_password=False)
        self._crypto = CryptoManager()  # No encryption

        self._save()
        logger.info("Migration complete")

    def delete_legacy_files(self) -> None:
        """Delete legacy files after confirming migration success."""
        legacy_crypto = LegacyCryptoManager(self._local_dir)
        legacy_crypto.delete_key_file()

        for filename in ["hosts.json", "settings.json"]:
            filepath = self._local_dir / filename
            if filepath.exists():
                try:
                    filepath.unlink()
                    logger.info(f"Deleted legacy file: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to delete {filename}: {e}")

    # === Master password management ===

    def change_master_password(self, old_password: str, new_password: str) -> bool:
        """
        Change master password.

        Args:
            old_password: Current password (or empty if none)
            new_password: New password (or empty to remove)

        Returns:
            True if successful
        """
        # Verify old password if exists
        if self._security.has_master_password:
            salt = base64.b64decode(self._security.password_salt)
            if not self._crypto.verify_password(old_password, salt, self._security.password_hash):
                return False

        # Decrypt all passwords with old key
        decrypted_passwords = {}
        for host in self._hosts:
            if host.password_encrypted:
                try:
                    decrypted_passwords[host.id] = self._crypto.decrypt(host.password_encrypted)
                except Exception:
                    decrypted_passwords[host.id] = None

        # Set up new crypto
        if new_password:
            self._crypto = CryptoManager(master_password=new_password)
            self._security = SecurityConfig(
                has_master_password=True,
                password_salt=self._crypto.salt_base64,
                password_hash=self._crypto.hash_password(new_password, self._crypto.salt)
            )
        else:
            self._crypto = CryptoManager()
            self._security = SecurityConfig(has_master_password=False)

        # Re-encrypt passwords with new key
        for host in self._hosts:
            plaintext = decrypted_passwords.get(host.id)
            if plaintext:
                host.password_encrypted = self._crypto.encrypt(plaintext)

        # Clear and recreate session
        self.clear_session()
        if new_password:
            self._cache_session()

        self._save()
        return True

    # === Settings accessors ===

    @property
    def settings(self) -> Settings:
        return self._settings

    def get_api_key(self) -> str:
        return self._settings.openrouter_api_key

    def set_api_key(self, key: str) -> None:
        self._settings.openrouter_api_key = key
        self._save()

    def get_model(self) -> str:
        return self._settings.default_model

    def set_model(self, model: str) -> None:
        self._settings.default_model = model
        self._save()

    def get_max_iterations(self) -> int:
        return max(1, self._settings.max_agent_iterations)

    def set_max_iterations(self, iterations: int) -> None:
        self._settings.max_agent_iterations = max(1, min(100, iterations))
        self._save()

    def get_chat_position(self) -> str:
        pos = self._settings.chat_position
        return pos if pos in {"bottom", "left", "right"} else "bottom"

    def set_chat_position(self, position: str) -> None:
        if position in {"bottom", "left", "right"}:
            self._settings.chat_position = position
            self._save()

    def get_sftp_position(self) -> str:
        pos = self._settings.sftp_position
        return pos if pos in {"bottom", "left", "right"} else "left"

    def set_sftp_position(self, position: str) -> None:
        if position in {"bottom", "left", "right"}:
            self._settings.sftp_position = position
            self._save()

    def get_tags(self) -> List[str]:
        return list(self._settings.available_tags)

    def add_tag(self, tag: str) -> None:
        tag = tag.strip()
        if tag and tag not in self._settings.available_tags:
            self._settings.available_tags.append(tag)
            self._settings.available_tags.sort()
            self._save()

    def remove_tag(self, tag: str) -> None:
        if tag in self._settings.available_tags:
            self._settings.available_tags.remove(tag)
            self._save()

    def get_manufacturers(self) -> List[str]:
        return list(self._settings.available_manufacturers)

    def add_manufacturer(self, value: str) -> None:
        value = value.strip()
        if value and value not in self._settings.available_manufacturers:
            self._settings.available_manufacturers.append(value)
            self._settings.available_manufacturers.sort()
            self._save()

    def get_os_versions(self) -> List[str]:
        return list(self._settings.available_os_versions)

    def add_os_version(self, value: str) -> None:
        value = value.strip()
        if value and value not in self._settings.available_os_versions:
            self._settings.available_os_versions.append(value)
            self._settings.available_os_versions.sort()
            self._save()

    def get_functions(self) -> List[str]:
        return list(self._settings.available_functions)

    def add_function(self, value: str) -> None:
        value = value.strip()
        if value and value not in self._settings.available_functions:
            self._settings.available_functions.append(value)
            self._settings.available_functions.sort()
            self._save()

    def get_groups(self) -> List[str]:
        return list(self._settings.available_groups)

    def add_group(self, value: str) -> None:
        value = value.strip()
        if value and value not in self._settings.available_groups:
            self._settings.available_groups.append(value)
            self._settings.available_groups.sort()
            self._save()

    def get_hosts_view_mode(self) -> str:
        mode = self._settings.hosts_view_mode
        return mode if mode in {"cards", "list"} else "cards"

    def set_hosts_view_mode(self, mode: str) -> None:
        if mode in {"cards", "list"}:
            self._settings.hosts_view_mode = mode
            self._save()

    def get_hosts_sort_by(self) -> str:
        sort_by = self._settings.hosts_sort_by
        valid_sorts = {"name", "host", "port", "username", "device_type", "manufacturer", "os_version"}
        return sort_by if sort_by in valid_sorts else "name"

    def set_hosts_sort_by(self, sort_by: str) -> None:
        valid_sorts = {"name", "host", "port", "username", "device_type", "manufacturer", "os_version"}
        if sort_by in valid_sorts:
            self._settings.hosts_sort_by = sort_by
            self._save()

    # === Visible fields settings ===

    # Campos válidos para visibilidade
    VALID_FIELDS = {"name", "host", "port", "username", "tags", "device_type",
                    "manufacturer", "os_version", "functions", "groups"}

    def get_card_visible_fields(self) -> List[str]:
        """Get visible fields for card view (order matters)."""
        fields = self._settings.card_visible_fields
        # Filtrar apenas campos válidos e garantir que 'name' está sempre presente
        valid = [f for f in fields if f in self.VALID_FIELDS]
        if "name" not in valid:
            valid = ["name"] + valid
        return valid if valid else ["name", "host", "tags", "device_type"]

    def set_card_visible_fields(self, fields: List[str]) -> None:
        """Set visible fields for card view (order matters)."""
        # Filtrar campos válidos
        valid = [f for f in fields if f in self.VALID_FIELDS]
        # Garantir que 'name' está sempre primeiro
        if "name" not in valid:
            valid = ["name"] + valid
        elif valid[0] != "name":
            valid.remove("name")
            valid = ["name"] + valid
        self._settings.card_visible_fields = valid
        self._save()

    def get_list_visible_fields(self) -> List[str]:
        """Get visible fields for list/table view (order matters)."""
        fields = self._settings.list_visible_fields
        # Filtrar apenas campos válidos e garantir que 'name' está sempre presente
        valid = [f for f in fields if f in self.VALID_FIELDS]
        if "name" not in valid:
            valid = ["name"] + valid
        return valid if valid else ["name", "host", "port", "username", "tags", "device_type", "manufacturer"]

    def set_list_visible_fields(self, fields: List[str]) -> None:
        """Set visible fields for list/table view (order matters)."""
        # Filtrar campos válidos
        valid = [f for f in fields if f in self.VALID_FIELDS]
        # Garantir que 'name' está sempre primeiro
        if "name" not in valid:
            valid = ["name"] + valid
        elif valid[0] != "name":
            valid.remove("name")
            valid = ["name"] + valid
        self._settings.list_visible_fields = valid
        self._save()

    def get_list_column_widths(self) -> dict:
        """Get custom column widths for list view."""
        return dict(self._settings.list_column_widths)

    def set_list_column_width(self, field: str, width: int) -> None:
        """Set width for a specific column."""
        if field in self.VALID_FIELDS and width > 0:
            self._settings.list_column_widths[field] = width
            self._save()

    def reset_list_column_widths(self) -> None:
        """Reset all column widths to defaults."""
        self._settings.list_column_widths = {}
        self._save()

    # === Conversation settings ===

    def get_max_conversations_per_host(self) -> int:
        """Get maximum conversations to keep per host."""
        return max(1, self._settings.max_conversations_per_host)

    def set_max_conversations_per_host(self, limit: int) -> None:
        """Set maximum conversations per host."""
        self._settings.max_conversations_per_host = max(1, min(100, limit))
        self._save()

    # === AI settings ===

    def get_ai_system_prompt(self) -> str:
        """Get custom AI system prompt (empty = use default)."""
        return self._settings.ai_system_prompt

    def set_ai_system_prompt(self, prompt: str) -> None:
        """Set custom AI system prompt."""
        self._settings.ai_system_prompt = prompt.strip()
        self._save()

    # === Telegram backup settings ===

    def get_telegram_bot_token(self) -> str:
        """Get Telegram bot token."""
        return self._settings.telegram_bot_token

    def get_telegram_chat_id(self) -> str:
        """Get Telegram chat ID."""
        return self._settings.telegram_chat_id

    def is_telegram_backup_enabled(self) -> bool:
        """Check if Telegram backup is enabled."""
        return self._settings.telegram_backup_enabled

    def set_telegram_config(self, token: str, chat_id: str, enabled: bool) -> None:
        """Set Telegram backup configuration."""
        self._settings.telegram_bot_token = token.strip()
        self._settings.telegram_chat_id = chat_id.strip()
        self._settings.telegram_backup_enabled = enabled
        self._save()

    def _send_telegram_backup(self) -> None:
        """Send data.json to Telegram (fire and forget)."""
        if not self._settings.telegram_backup_enabled:
            return
        if not self._settings.telegram_bot_token or not self._settings.telegram_chat_id:
            return
        if not self._data_path or not self._data_path.exists():
            return

        async def send():
            try:
                token = self._settings.telegram_bot_token
                chat_id = self._settings.telegram_chat_id
                url = f"https://api.telegram.org/bot{token}/sendDocument"

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                hostname = platform.node()
                caption = f"RB Terminal Backup\n📅 {timestamp}\n💻 {hostname}"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    with open(self._data_path, "rb") as f:
                        files = {"document": ("data.json", f, "application/json")}
                        data = {"chat_id": chat_id, "caption": caption}
                        response = await client.post(url, data=data, files=files)
                        response.raise_for_status()
                        logger.debug("Telegram backup sent successfully")
            except Exception as e:
                logger.error(f"Failed to send Telegram backup: {e}")

        # Fire and forget - don't block the save
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send())
            else:
                loop.run_until_complete(send())
        except RuntimeError:
            # No event loop running, create a new one
            asyncio.run(send())

    # === Conversation accessors ===

    def get_conversations_for_host(self, host_id: str) -> List[Conversation]:
        """Get all conversations for a host, sorted by updated_at descending."""
        convs = [c for c in self._conversations if c.host_id == host_id]
        convs.sort(key=lambda c: c.updated_at, reverse=True)
        return convs

    def get_conversation_by_id(self, conv_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        for conv in self._conversations:
            if conv.id == conv_id:
                return conv
        return None

    def create_conversation(self, host_id: str, title: str = "") -> Conversation:
        """Create a new conversation for a host."""
        conv = Conversation(host_id=host_id, title=title or "Nova conversa")
        self._conversations.append(conv)
        self._enforce_conversation_limit(host_id)
        self._save(skip_telegram_backup=True)
        return conv

    def update_conversation(
        self,
        conv_id: str,
        messages: List[ChatMessage],
        title: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_cost: Optional[float] = None
    ) -> Optional[Conversation]:
        """Update conversation messages, timestamp, and usage stats."""
        conv = self.get_conversation_by_id(conv_id)
        if not conv:
            return None

        conv.messages = messages
        conv.updated_at = datetime.now().isoformat()

        # Update usage stats if provided
        if prompt_tokens is not None:
            conv.prompt_tokens = prompt_tokens
        if completion_tokens is not None:
            conv.completion_tokens = completion_tokens
        if total_cost is not None:
            conv.total_cost = total_cost

        # Auto-generate title from first user message if not set
        if title:
            conv.title = title
        elif not conv.title or conv.title == "Nova conversa":
            for msg in messages:
                if msg.role == "user" and msg.content:
                    # Use first 50 chars of first user message
                    content = msg.content.strip()
                    conv.title = content[:50] + ("..." if len(content) > 50 else "")
                    break

        self._save(skip_telegram_backup=True)
        return conv

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation."""
        for i, conv in enumerate(self._conversations):
            if conv.id == conv_id:
                self._conversations.pop(i)
                self._save(skip_telegram_backup=True)
                return True
        return False

    def _enforce_conversation_limit(self, host_id: str) -> None:
        """Remove oldest conversations if limit exceeded."""
        convs = self.get_conversations_for_host(host_id)
        limit = self.get_max_conversations_per_host()

        if len(convs) > limit:
            # convs is sorted by updated_at desc, so remove from the end
            to_remove = convs[limit:]
            for conv in to_remove:
                self._conversations.remove(conv)

    # === Hosts accessors ===

    def get_hosts(self) -> List[Host]:
        return self._hosts.copy()

    def get_host_by_id(self, host_id: str) -> Optional[Host]:
        for host in self._hosts:
            if host.id == host_id:
                return host
        return None

    def add_host(
        self,
        name: str,
        hosts: Optional[list] = None,
        port: int = 22,
        username: str = "",
        password: Optional[str] = None,
        terminal_type: str = "xterm",
        device_type: Optional[str] = None,
        disable_terminal_detection: bool = False,
        tags: Optional[list] = None,
        manufacturer: Optional[str] = None,
        os_version: Optional[str] = None,
        functions: Optional[list] = None,
        groups: Optional[list] = None,
        notes: Optional[str] = None,
        port_knocking: Optional[list] = None,
        winbox_port: int = 0,
        http_port: int = 80,
        https_enabled: bool = False,
        web_username: Optional[str] = None,
        web_password: Optional[str] = None
    ) -> Host:
        """Add a new host."""
        password_encrypted = None
        if password:
            password_encrypted = self._crypto.encrypt(password) if self._crypto else password

        web_password_encrypted = None
        if web_password:
            web_password_encrypted = self._crypto.encrypt(web_password) if self._crypto else web_password

        hosts_list = hosts if hosts else []

        new_host = Host(
            name=name,
            hosts=hosts_list,
            port=port,
            username=username,
            password_encrypted=password_encrypted,
            terminal_type=terminal_type,
            device_type=device_type if device_type else None,
            disable_terminal_detection=disable_terminal_detection,
            tags=tags if tags else [],
            manufacturer=manufacturer if manufacturer else None,
            os_version=os_version if os_version else None,
            functions=functions if functions else [],
            groups=groups if groups else [],
            notes=notes if notes else None,
            port_knocking=port_knocking if port_knocking else [],
            winbox_port=winbox_port,
            http_port=http_port,
            https_enabled=https_enabled,
            web_username=web_username if web_username else None,
            web_password_encrypted=web_password_encrypted
        )

        self._hosts.append(new_host)
        self._save()
        logger.info(f"Added new host: {name} ({new_host.host})")
        return new_host

    def update_host(
        self,
        host_id: str,
        name: Optional[str] = None,
        hosts: Optional[list] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        terminal_type: Optional[str] = None,
        device_type: Optional[str] = None,
        disable_terminal_detection: Optional[bool] = None,
        clear_password: bool = False,
        tags: Optional[list] = None,
        manufacturer: Optional[str] = None,
        os_version: Optional[str] = None,
        functions: Optional[list] = None,
        groups: Optional[list] = None,
        notes: Optional[str] = None,
        port_knocking: Optional[list] = None,
        winbox_port: Optional[int] = None,
        http_port: Optional[int] = None,
        https_enabled: Optional[bool] = None,
        web_username: Optional[str] = None,
        web_password: Optional[str] = None,
        clear_web_password: bool = False
    ) -> Optional[Host]:
        """Update an existing host."""
        existing = self.get_host_by_id(host_id)
        if not existing:
            return None

        if name is not None:
            existing.name = name
        if hosts is not None:
            existing.hosts = hosts
        if port is not None:
            existing.port = port
        if username is not None:
            existing.username = username
        if terminal_type is not None:
            existing.terminal_type = terminal_type
        if device_type is not None:
            existing.device_type = device_type if device_type else None
        if disable_terminal_detection is not None:
            existing.disable_terminal_detection = disable_terminal_detection
        if tags is not None:
            existing.tags = tags
        if manufacturer is not None:
            existing.manufacturer = manufacturer if manufacturer else None
        if os_version is not None:
            existing.os_version = os_version if os_version else None
        if functions is not None:
            existing.functions = functions
        if groups is not None:
            existing.groups = groups
        if notes is not None:
            existing.notes = notes if notes else None
        if port_knocking is not None:
            existing.port_knocking = port_knocking
        if winbox_port is not None:
            existing.winbox_port = winbox_port
        if http_port is not None:
            existing.http_port = http_port
        if https_enabled is not None:
            existing.https_enabled = https_enabled
        if web_username is not None:
            existing.web_username = web_username if web_username else None

        if clear_web_password:
            existing.web_password_encrypted = None
        elif web_password is not None:
            if web_password:
                existing.web_password_encrypted = self._crypto.encrypt(web_password) if self._crypto else web_password
            else:
                existing.web_password_encrypted = None

        if clear_password:
            existing.password_encrypted = None
        elif password is not None:
            if password:
                existing.password_encrypted = self._crypto.encrypt(password) if self._crypto else password
            else:
                existing.password_encrypted = None

        self._save()
        logger.info(f"Updated host: {existing.name}")
        return existing

    def delete_host(self, host_id: str) -> bool:
        """Delete a host."""
        for i, host in enumerate(self._hosts):
            if host.id == host_id:
                deleted = self._hosts.pop(i)
                self._save()
                logger.info(f"Deleted host: {deleted.name}")
                return True
        return False

    def get_password(self, host_id: str) -> Optional[str]:
        """Get decrypted password for a host."""
        host = self.get_host_by_id(host_id)
        if not host or not host.password_encrypted:
            return None

        try:
            if self._crypto:
                return self._crypto.decrypt(host.password_encrypted)
            return host.password_encrypted
        except Exception as e:
            logger.error(f"Failed to decrypt password: {e}")
            return None

    def has_password(self, host_id: str) -> bool:
        """Check if host has a saved password."""
        host = self.get_host_by_id(host_id)
        return host is not None and host.password_encrypted is not None

    def get_web_password(self, host: Host) -> Optional[str]:
        """Get decrypted web password for a host."""
        if not host or not host.web_password_encrypted:
            return None

        try:
            if self._crypto:
                return self._crypto.decrypt(host.web_password_encrypted)
            return host.web_password_encrypted
        except Exception as e:
            logger.error(f"Failed to decrypt web password: {e}")
            return None

    # === Export/Import ===

    def export_data(
        self,
        path: Path,
        include_settings: bool = True,
        include_hosts: bool = True,
        include_passwords: bool = False,
        export_password: Optional[str] = None
    ) -> None:
        """
        Export data to a file.

        Args:
            path: File path to export to
            include_settings: Include settings in export
            include_hosts: Include hosts in export
            include_passwords: Include passwords (requires export_password)
        export_password: Password to encrypt exported passwords
        """
        export_crypto = None
        uses_master_crypto = False

        # Decide how to protect passwords: reuse master password crypto if available,
        # otherwise leave as-is (plaintext) when no master password.
        if include_passwords and self._security.has_master_password and self._crypto and self._crypto.has_key:
            export_crypto = self._crypto
            uses_master_crypto = True
        elif include_passwords and export_password:
            export_crypto = CryptoManager(master_password=export_password)

        export_data = {
            "version": DATA_VERSION,
            "exported_at": datetime.now().isoformat(),
            "has_encrypted_passwords": include_passwords and export_crypto is not None
        }

        if include_passwords and export_crypto:
            # If we are reusing the current master crypto, also persist its salt so the
            # import step can derive the same key from the master password.
            if uses_master_crypto:
                export_data["password_salt"] = self._security.password_salt
            else:
                export_data["password_salt"] = export_crypto.salt_base64

        if include_settings:
            export_data["settings"] = self._settings.to_dict()

        if include_hosts:
            hosts_export = []
            for host in self._hosts:
                host_dict = host.to_dict()

                if include_passwords:
                    if host.password_encrypted:
                        plaintext = self.get_password(host.id)
                        if plaintext and export_crypto:
                            # Re-encrypt with export crypto (master or provided password)
                            host_dict["password_exported"] = export_crypto.encrypt(plaintext)
                            host_dict["password_encrypted"] = None
                        else:
                            # Keep as-is (plaintext when no master password)
                            host_dict["password_encrypted"] = plaintext
                    else:
                        host_dict["password_encrypted"] = None
                else:
                    host_dict["password_encrypted"] = None

                hosts_export.append(host_dict)

            export_data["hosts"] = hosts_export

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported data to {path}")

    def import_data(
        self,
        path: Path,
        import_password: Optional[str] = None,
        merge: bool = True
    ) -> ImportResult:
        """
        Import data from a file.

        Args:
            path: File path to import from
            import_password: Password for encrypted passwords
            merge: If True, merge with existing; if False, replace

        Returns:
            ImportResult with details
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            return ImportResult(success=False, error=str(e))

        import_crypto = None
        if data.get("has_encrypted_passwords"):
            if not import_password:
                return ImportResult(success=False, error="Password required for encrypted export")

            salt = base64.b64decode(data.get("password_salt", ""))
            import_crypto = CryptoManager(master_password=import_password, salt=salt)

        result = ImportResult(success=True)

        # Import settings
        if "settings" in data:
            if not merge:
                self._settings = Settings.from_dict(data["settings"])
            else:
                # Only import non-empty values
                imported = data["settings"]
                if imported.get("openrouter_api_key"):
                    self._settings.openrouter_api_key = imported["openrouter_api_key"]
                # Tags are merged
                for tag in imported.get("available_tags", []):
                    if tag not in self._settings.available_tags:
                        self._settings.available_tags.append(tag)
            result.settings_imported = True

        # Import hosts
        if "hosts" in data:
            existing_ids = {h.id for h in self._hosts}

            for host_data in data["hosts"]:
                if not merge and host_data["id"] in existing_ids:
                    result.hosts_skipped += 1
                    continue

                # Handle password
                if "password_exported" in host_data and import_crypto:
                    try:
                        plaintext = import_crypto.decrypt(host_data["password_exported"])
                        host_data["password_encrypted"] = self._crypto.encrypt(plaintext) if self._crypto else plaintext
                    except Exception:
                        host_data["password_encrypted"] = None
                elif merge and host_data["id"] in existing_ids:
                    # Keep existing password when merging
                    existing = self.get_host_by_id(host_data["id"])
                    host_data["password_encrypted"] = existing.password_encrypted if existing else None

                host = Host.from_dict(host_data)

                # If we imported plaintext passwords into an instance with a master
                # password, encrypt them with the current key for at-rest protection.
                if host.password_encrypted and self._crypto and self._crypto.has_key and not data.get("has_encrypted_passwords"):
                    try:
                        host.password_encrypted = self._crypto.encrypt(host.password_encrypted)
                    except Exception:
                        host.password_encrypted = None

                if host.id in existing_ids:
                    # Update existing
                    for i, h in enumerate(self._hosts):
                        if h.id == host.id:
                            self._hosts[i] = host
                            break
                else:
                    self._hosts.append(host)

                result.hosts_imported += 1

        self._save()
        logger.info(f"Imported data: {result.hosts_imported} hosts, settings={result.settings_imported}")
        return result


# Singleton accessor
_data_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """Get the singleton DataManager instance."""
    global _data_manager
    if _data_manager is None:
        _data_manager = DataManager()
    return _data_manager


def reset_data_manager() -> None:
    """Reset singleton (for testing)."""
    global _data_manager
    _data_manager = None
