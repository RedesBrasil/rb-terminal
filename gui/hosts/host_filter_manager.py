"""
Host Filter Manager - Manages host filtering state and logic.
Extracted from hosts_view.py for better separation of concerns.
"""

from typing import List, Set, Callable, Optional
from PySide6.QtWidgets import QMenu, QPushButton
from PySide6.QtCore import QObject, Signal

from core.data_manager import Host, DataManager


class HostFilterManager(QObject):
    """
    Manages host filtering state and logic.

    Responsibilities:
    - Tracking active filters (tags, manufacturers, functions, groups)
    - Building filter menus
    - Applying filters to host lists
    - Updating filter button appearance
    """

    filters_changed = Signal()

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self._data_manager = data_manager

        # Filter state
        self._selected_tags: List[str] = []
        self._selected_manufacturers: List[str] = []
        self._selected_functions: List[str] = []
        self._selected_groups: List[str] = []

    @property
    def total_filter_count(self) -> int:
        """Get total number of active filters."""
        return (
            len(self._selected_tags) +
            len(self._selected_manufacturers) +
            len(self._selected_functions) +
            len(self._selected_groups)
        )

    @property
    def selected_tags(self) -> List[str]:
        return self._selected_tags.copy()

    @property
    def selected_manufacturers(self) -> List[str]:
        return self._selected_manufacturers.copy()

    @property
    def selected_functions(self) -> List[str]:
        return self._selected_functions.copy()

    @property
    def selected_groups(self) -> List[str]:
        return self._selected_groups.copy()

    def clear_all(self) -> None:
        """Clear all filters."""
        self._selected_tags.clear()
        self._selected_manufacturers.clear()
        self._selected_functions.clear()
        self._selected_groups.clear()
        self.filters_changed.emit()

    def clear_tags(self) -> None:
        """Clear tag filters."""
        self._selected_tags.clear()
        self.filters_changed.emit()

    def clear_manufacturers(self) -> None:
        """Clear manufacturer filters."""
        self._selected_manufacturers.clear()
        self.filters_changed.emit()

    def clear_functions(self) -> None:
        """Clear function filters."""
        self._selected_functions.clear()
        self.filters_changed.emit()

    def clear_groups(self) -> None:
        """Clear group filters."""
        self._selected_groups.clear()
        self.filters_changed.emit()

    def toggle_tag(self, tag: str, checked: bool) -> None:
        """Toggle a tag filter."""
        if checked and tag not in self._selected_tags:
            self._selected_tags.append(tag)
        elif not checked and tag in self._selected_tags:
            self._selected_tags.remove(tag)
        self.filters_changed.emit()

    def toggle_manufacturer(self, manufacturer: str, checked: bool) -> None:
        """Toggle a manufacturer filter."""
        if checked and manufacturer not in self._selected_manufacturers:
            self._selected_manufacturers.append(manufacturer)
        elif not checked and manufacturer in self._selected_manufacturers:
            self._selected_manufacturers.remove(manufacturer)
        self.filters_changed.emit()

    def toggle_function(self, function: str, checked: bool) -> None:
        """Toggle a function filter."""
        if checked and function not in self._selected_functions:
            self._selected_functions.append(function)
        elif not checked and function in self._selected_functions:
            self._selected_functions.remove(function)
        self.filters_changed.emit()

    def toggle_group(self, group: str, checked: bool) -> None:
        """Toggle a group filter."""
        if checked and group not in self._selected_groups:
            self._selected_groups.append(group)
        elif not checked and group in self._selected_groups:
            self._selected_groups.remove(group)
        self.filters_changed.emit()

    def apply_filters(self, hosts: List[Host], search_text: str = "") -> List[Host]:
        """Apply all active filters to a list of hosts."""
        filtered = []
        search_lower = search_text.lower() if search_text else ""

        for host in hosts:
            # Search filter
            if search_lower:
                searchable_parts = [
                    host.id,
                    host.name,
                    host.host,
                    str(host.port),
                    host.username,
                    host.device_type or '',
                    host.manufacturer or '',
                    host.os_version or '',
                    ' '.join(host.tags),
                    ' '.join(host.functions),
                    ' '.join(host.groups),
                    host.notes or '',
                    host.created_at or '',
                ]
                searchable = ' '.join(searchable_parts).lower()
                if search_lower not in searchable:
                    continue

            # Tag filter (AND logic)
            if self._selected_tags:
                if not all(tag in host.tags for tag in self._selected_tags):
                    continue

            # Manufacturer filter (OR logic)
            if self._selected_manufacturers:
                if not host.manufacturer or host.manufacturer not in self._selected_manufacturers:
                    continue

            # Function filter (AND logic)
            if self._selected_functions:
                if not all(func in host.functions for func in self._selected_functions):
                    continue

            # Group filter (AND logic)
            if self._selected_groups:
                if not all(group in host.groups for group in self._selected_groups):
                    continue

            filtered.append(host)

        return filtered

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
            QMenu::item:checked {
                background-color: #0e639c;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555555;
                margin: 4px 8px;
            }
        """

    def build_filters_menu(self, parent, default_manufacturers: List[str] = None, default_functions: List[str] = None) -> QMenu:
        """Build the complete filters menu."""
        menu = QMenu(parent)
        menu.setStyleSheet(self.get_menu_style())

        # Clear all filters option
        if self.total_filter_count > 0:
            clear_action = menu.addAction("✕ Limpar todos os filtros")
            clear_action.triggered.connect(self.clear_all)
            menu.addSeparator()

        # Tags submenu
        tags_label = "Tags"
        if self._selected_tags:
            tags_label += f" ({len(self._selected_tags)})"
        tags_menu = menu.addMenu(tags_label)
        tags_menu.setStyleSheet(self.get_menu_style())
        self._populate_submenu(
            tags_menu,
            self._data_manager.get_tags(),
            self._selected_tags,
            self.toggle_tag,
            self.clear_tags
        )

        # Manufacturers submenu
        mfg_label = "Fabricante"
        if self._selected_manufacturers:
            mfg_label += f" ({len(self._selected_manufacturers)})"
        mfg_menu = menu.addMenu(mfg_label)
        mfg_menu.setStyleSheet(self.get_menu_style())

        all_manufacturers = list(default_manufacturers or [])
        for m in self._data_manager.get_manufacturers():
            if m not in all_manufacturers:
                all_manufacturers.append(m)

        self._populate_submenu(
            mfg_menu,
            all_manufacturers,
            self._selected_manufacturers,
            self.toggle_manufacturer,
            self.clear_manufacturers
        )

        # Functions submenu
        func_label = "Função"
        if self._selected_functions:
            func_label += f" ({len(self._selected_functions)})"
        func_menu = menu.addMenu(func_label)
        func_menu.setStyleSheet(self.get_menu_style())

        all_functions = list(default_functions or [])
        for f in self._data_manager.get_functions():
            if f not in all_functions:
                all_functions.append(f)

        self._populate_submenu(
            func_menu,
            all_functions,
            self._selected_functions,
            self.toggle_function,
            self.clear_functions
        )

        # Groups submenu
        grp_label = "Grupos"
        if self._selected_groups:
            grp_label += f" ({len(self._selected_groups)})"
        grp_menu = menu.addMenu(grp_label)
        grp_menu.setStyleSheet(self.get_menu_style())
        self._populate_submenu(
            grp_menu,
            self._data_manager.get_groups(),
            self._selected_groups,
            self.toggle_group,
            self.clear_groups
        )

        return menu

    def _populate_submenu(
        self,
        menu: QMenu,
        available: List[str],
        selected: List[str],
        toggle_fn: Callable,
        clear_fn: Callable
    ) -> None:
        """Populate a filter submenu with checkable items."""
        if not available:
            action = menu.addAction("Nenhum disponível")
            action.setEnabled(False)
            return

        # Clear option
        if selected:
            clear_action = menu.addAction("✕ Limpar")
            clear_action.triggered.connect(clear_fn)
            menu.addSeparator()

        for item in available:
            action = menu.addAction(item)
            action.setCheckable(True)
            action.setChecked(item in selected)
            action.triggered.connect(lambda checked, i=item: toggle_fn(i, checked))

    def update_button_style(self, button: QPushButton) -> None:
        """Update filter button text and style based on active filters."""
        if self.total_filter_count > 0:
            button.setText(f"Filtros ({self.total_filter_count})")
            button.setStyleSheet("""
                QPushButton {
                    background-color: #0e639c;
                    border: 1px solid #007acc;
                    border-radius: 4px;
                    padding: 8px 16px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #1177bb;
                }
            """)
        else:
            button.setText("Filtros")
            button.setStyleSheet("""
                QPushButton {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 8px 16px;
                    color: #dcdcdc;
                }
                QPushButton:hover {
                    background-color: #4c4c4c;
                }
            """)
