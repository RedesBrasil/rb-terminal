"""
Mixins for host display components.
Eliminates code duplication between HostCard, HostListItem, and HostsTableWidget.
"""

from typing import Optional, List
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Signal

from core.data_manager import Host


class HostFieldMixin:
    """
    Mixin providing field value extraction for host display components.

    Requires:
        - self._host: Host object
    """

    _host: Host

    def _get_field_value(self, field: str, host: Host = None) -> str:
        """Get display value for a field."""
        h = host if host else self._host

        if field == "name":
            return h.name
        elif field == "host":
            extra_ips = len(h.hosts) - 1 if h.hosts else 0
            text = h.host
            if extra_ips > 0:
                text += f" (+{extra_ips})"
            return text
        elif field == "host_with_port":
            extra_ips = len(h.hosts) - 1 if h.hosts else 0
            text = f"{h.host}:{h.port}"
            if extra_ips > 0:
                text += f" (+{extra_ips})"
            return text
        elif field == "port":
            return str(h.port)
        elif field == "username":
            return h.username or "-"
        elif field == "device_type":
            return h.device_type or "-"
        elif field == "manufacturer":
            return h.manufacturer or "-"
        elif field == "os_version":
            return h.os_version or "-"
        elif field == "functions":
            return ", ".join(h.functions) if h.functions else "-"
        elif field == "groups":
            return ", ".join(h.groups) if h.groups else "-"
        elif field == "tags":
            return ", ".join(h.tags) if h.tags else "-"
        return "-"


class HostMenuMixin:
    """
    Mixin providing context menu functionality for host display components.

    Requires:
        - self._host: Host object
        - self.connect_requested: Signal(str, str)
        - self.edit_requested: Signal(str)
        - self.delete_requested: Signal(str)
        - self.winbox_requested: Signal(str, str)
        - self.web_access_requested: Signal(str, str)
    """

    _host: Host

    # Signals that must be defined in the class using this mixin
    connect_requested: Signal
    edit_requested: Signal
    delete_requested: Signal
    winbox_requested: Signal
    web_access_requested: Signal

    @staticmethod
    def get_menu_style() -> str:
        """Get common menu stylesheet."""
        return """
            QMenu {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 2px;
                color: #dcdcdc;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """

    def _create_ip_submenu(self, parent_menu: QMenu, action_name: str, signal, host: Host = None) -> None:
        """Create a submenu with IP options or simple action if only one IP."""
        h = host if host else self._host
        hosts = h.hosts if h.hosts else []

        if len(hosts) <= 1:
            # Single IP - simple action
            action = parent_menu.addAction(action_name)
            action.triggered.connect(lambda: signal.emit(h.id, ""))
        else:
            # Multiple IPs - create submenu
            submenu = parent_menu.addMenu(action_name)
            submenu.setStyleSheet(self.get_menu_style())

            for ip in hosts:
                ip_action = submenu.addAction(ip)
                ip_action.triggered.connect(lambda checked, addr=ip, hid=h.id: signal.emit(hid, addr))

    def _build_context_menu(self, parent, host: Host = None) -> QMenu:
        """Build and return a context menu for a host."""
        h = host if host else self._host

        menu = QMenu(parent)
        menu.setStyleSheet(self.get_menu_style())

        # SSH/Connect with IP submenu
        self._create_ip_submenu(menu, "Acesso SSH", self.connect_requested, h)

        # Winbox with IP submenu
        self._create_ip_submenu(menu, "Winbox", self.winbox_requested, h)

        # Web access with IP submenu
        self._create_ip_submenu(menu, "Acesso Web", self.web_access_requested, h)

        menu.addSeparator()

        edit_action = menu.addAction("Editar")
        edit_action.triggered.connect(lambda: self.edit_requested.emit(h.id))

        delete_action = menu.addAction("Excluir")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(h.id))

        return menu
