"""
Theme management system for FLIR Boson Focus Peaking.

Provides modern UI themes with consistent styling across the application.
Includes multiple built-in themes and support for custom themes.
"""

import logging
from typing import Dict, Optional
from PyQt5 import QtWidgets, QtGui, QtCore

from config import AVAILABLE_THEMES, DEFAULT_THEME, THEME_COLORS

logger = logging.getLogger(__name__)


class Theme:
    """Represents a UI theme with colors and styling."""

    def __init__(self, name: str, stylesheet: str, colors: Dict[str, str]):
        """
        Initialize theme.

        Args:
            name: Theme name
            stylesheet: Qt stylesheet string
            colors: Dictionary of theme colors
        """
        self.name = name
        self.stylesheet = stylesheet
        self.colors = colors


class ThemeManager:
    """
    Manages application themes and provides theme switching functionality.
    """

    def __init__(self, app: QtWidgets.QApplication):
        """
        Initialize theme manager.

        Args:
            app: QApplication instance
        """
        self.app = app
        self.current_theme_name = DEFAULT_THEME
        self.themes = self._create_themes()

    def _create_themes(self) -> Dict[str, Theme]:
        """Create all available themes."""
        themes = {}

        # Dark Theme
        themes["Dark"] = Theme(
            name="Dark",
            stylesheet=self._generate_dark_theme(),
            colors=THEME_COLORS.get("Dark", {})
        )

        # Light Theme
        themes["Light"] = Theme(
            name="Light",
            stylesheet=self._generate_light_theme(),
            colors=THEME_COLORS.get("Light", {})
        )

        # Breeze Dark (KDE-inspired)
        themes["Breeze Dark"] = Theme(
            name="Breeze Dark",
            stylesheet=self._generate_breeze_dark_theme(),
            colors=THEME_COLORS.get("Dark", {})
        )

        # Nord Theme
        themes["Nord"] = Theme(
            name="Nord",
            stylesheet=self._generate_nord_theme(),
            colors=THEME_COLORS.get("Nord", {})
        )

        # Dracula Theme
        themes["Dracula"] = Theme(
            name="Dracula",
            stylesheet=self._generate_dracula_theme(),
            colors=THEME_COLORS.get("Dracula", {})
        )

        # Monokai Theme
        themes["Monokai"] = Theme(
            name="Monokai",
            stylesheet=self._generate_monokai_theme(),
            colors=THEME_COLORS.get("Monokai", {})
        )

        # Solarized Dark
        themes["Solarized Dark"] = Theme(
            name="Solarized Dark",
            stylesheet=self._generate_solarized_dark_theme(),
            colors=THEME_COLORS.get("Solarized Dark", {})
        )

        # Solarized Light
        themes["Solarized Light"] = Theme(
            name="Solarized Light",
            stylesheet=self._generate_solarized_light_theme(),
            colors=THEME_COLORS.get("Solarized Light", {})
        )

        return themes

    def apply_theme(self, theme_name: str) -> bool:
        """
        Apply a theme to the application.

        Args:
            theme_name: Name of theme to apply

        Returns:
            True if successful, False if theme not found
        """
        if theme_name not in self.themes:
            logger.error(f"Theme '{theme_name}' not found")
            return False

        try:
            theme = self.themes[theme_name]
            self.app.setStyleSheet(theme.stylesheet)
            self.current_theme_name = theme_name
            logger.info(f"Applied theme: {theme_name}")
            return True

        except Exception as e:
            logger.error(f"Error applying theme '{theme_name}': {e}")
            return False

    def get_available_themes(self) -> list:
        """Get list of available theme names."""
        return list(self.themes.keys())

    def get_current_theme(self) -> str:
        """Get name of currently applied theme."""
        return self.current_theme_name

    # ========================================================================
    # Theme Generators
    # ========================================================================

    def _generate_dark_theme(self) -> str:
        """Generate modern dark theme stylesheet."""
        return """
        QWidget {
            background-color: #1e1e1e;
            color: #ffffff;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }

        QMainWindow, QDialog {
            background-color: #1e1e1e;
        }

        QPushButton {
            background-color: #0078d4;
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
            min-height: 20px;
        }

        QPushButton:hover {
            background-color: #106ebe;
        }

        QPushButton:pressed {
            background-color: #005a9e;
        }

        QPushButton:disabled {
            background-color: #3f3f3f;
            color: #888888;
        }

        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #2d2d2d;
            border: 1px solid #3f3f3f;
            border-radius: 3px;
            padding: 4px;
            color: #ffffff;
            selection-background-color: #0078d4;
        }

        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #0078d4;
        }

        QSlider::groove:horizontal {
            background: #3f3f3f;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #0078d4;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QSlider::handle:horizontal:hover {
            background: #106ebe;
        }

        QTableWidget {
            background-color: #252526;
            alternate-background-color: #2d2d2d;
            gridline-color: #3f3f3f;
            border: 1px solid #3f3f3f;
            border-radius: 4px;
        }

        QTableWidget::item {
            padding: 4px;
        }

        QTableWidget::item:selected {
            background-color: #0078d4;
        }

        QHeaderView::section {
            background-color: #2d2d2d;
            color: #ffffff;
            padding: 6px;
            border: none;
            border-bottom: 1px solid #3f3f3f;
            font-weight: bold;
        }

        QLabel {
            background-color: transparent;
            color: #ffffff;
        }

        QComboBox {
            background-color: #2d2d2d;
            border: 1px solid #3f3f3f;
            border-radius: 3px;
            padding: 4px 8px;
            min-height: 20px;
        }

        QComboBox:hover {
            border: 1px solid #0078d4;
        }

        QComboBox::drop-down {
            border: none;
            width: 20px;
        }

        QComboBox QAbstractItemView {
            background-color: #2d2d2d;
            border: 1px solid #3f3f3f;
            selection-background-color: #0078d4;
        }

        QScrollBar:vertical {
            background: #2d2d2d;
            width: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical {
            background: #555555;
            border-radius: 6px;
            min-height: 20px;
        }

        QScrollBar::handle:vertical:hover {
            background: #666666;
        }

        QScrollBar:horizontal {
            background: #2d2d2d;
            height: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:horizontal {
            background: #555555;
            border-radius: 6px;
            min-width: 20px;
        }

        QMessageBox {
            background-color: #1e1e1e;
        }

        QMenuBar {
            background-color: #2d2d2d;
            color: #ffffff;
        }

        QMenuBar::item:selected {
            background-color: #0078d4;
        }

        QMenu {
            background-color: #2d2d2d;
            border: 1px solid #3f3f3f;
        }

        QMenu::item:selected {
            background-color: #0078d4;
        }
        """

    def _generate_light_theme(self) -> str:
        """Generate modern light theme stylesheet."""
        return """
        QWidget {
            background-color: #ffffff;
            color: #000000;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }

        QPushButton {
            background-color: #0078d4;
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
            min-height: 20px;
        }

        QPushButton:hover {
            background-color: #106ebe;
        }

        QPushButton:pressed {
            background-color: #005a9e;
        }

        QLineEdit, QTextEdit {
            background-color: #ffffff;
            border: 1px solid #cccccc;
            border-radius: 3px;
            padding: 4px;
            selection-background-color: #0078d4;
        }

        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #0078d4;
        }

        QSlider::groove:horizontal {
            background: #e0e0e0;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #0078d4;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QTableWidget {
            background-color: #ffffff;
            alternate-background-color: #f5f5f5;
            gridline-color: #e0e0e0;
            border: 1px solid #cccccc;
            border-radius: 4px;
        }

        QTableWidget::item:selected {
            background-color: #0078d4;
            color: white;
        }

        QHeaderView::section {
            background-color: #f5f5f5;
            color: #000000;
            padding: 6px;
            border: none;
            border-bottom: 1px solid #cccccc;
            font-weight: bold;
        }

        QComboBox {
            background-color: #ffffff;
            border: 1px solid #cccccc;
            border-radius: 3px;
            padding: 4px 8px;
        }

        QComboBox QAbstractItemView {
            background-color: #ffffff;
            border: 1px solid #cccccc;
            selection-background-color: #0078d4;
        }
        """

    def _generate_breeze_dark_theme(self) -> str:
        """Generate Breeze Dark theme (KDE-inspired)."""
        return """
        QWidget {
            background-color: #31363b;
            color: #eff0f1;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }

        QPushButton {
            background-color: #3daee9;
            color: #eff0f1;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
        }

        QPushButton:hover {
            background-color: #45b8f4;
        }

        QSlider::groove:horizontal {
            background: #4d545e;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #3daee9;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QTableWidget {
            background-color: #232629;
            gridline-color: #4d545e;
            border: 1px solid #4d545e;
        }
        """

    def _generate_nord_theme(self) -> str:
        """Generate Nord theme."""
        colors = THEME_COLORS.get("Nord", {})
        bg = colors.get("background", "#2e3440")
        fg = colors.get("foreground", "#eceff4")
        accent = colors.get("accent", "#88c0d0")
        border = colors.get("border", "#4c566a")

        return f"""
        QWidget {{
            background-color: {bg};
            color: {fg};
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }}

        QPushButton {{
            background-color: {accent};
            color: {bg};
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
        }}

        QPushButton:hover {{
            background-color: #8fbcbb;
        }}

        QLineEdit, QTextEdit {{
            background-color: #3b4252;
            border: 1px solid {border};
            border-radius: 3px;
            padding: 4px;
            color: {fg};
        }}

        QSlider::groove:horizontal {{
            background: {border};
            height: 6px;
            border-radius: 3px;
        }}

        QSlider::handle:horizontal {{
            background: {accent};
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}

        QTableWidget {{
            background-color: #3b4252;
            gridline-color: {border};
            border: 1px solid {border};
        }}

        QTableWidget::item:selected {{
            background-color: {accent};
            color: {bg};
        }}
        """

    def _generate_dracula_theme(self) -> str:
        """Generate Dracula theme."""
        return """
        QWidget {
            background-color: #282a36;
            color: #f8f8f2;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }

        QPushButton {
            background-color: #bd93f9;
            color: #282a36;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
        }

        QPushButton:hover {
            background-color: #c9a9ff;
        }

        QLineEdit, QTextEdit {
            background-color: #44475a;
            border: 1px solid #6272a4;
            border-radius: 3px;
            padding: 4px;
            color: #f8f8f2;
        }

        QSlider::groove:horizontal {
            background: #44475a;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #bd93f9;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QTableWidget {
            background-color: #44475a;
            gridline-color: #6272a4;
            border: 1px solid #6272a4;
        }

        QTableWidget::item:selected {
            background-color: #bd93f9;
            color: #282a36;
        }
        """

    def _generate_monokai_theme(self) -> str:
        """Generate Monokai theme."""
        return """
        QWidget {
            background-color: #272822;
            color: #f8f8f2;
            font-family: "Consolas", "Monaco", monospace;
            font-size: 9pt;
        }

        QPushButton {
            background-color: #66d9ef;
            color: #272822;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
        }

        QPushButton:hover {
            background-color: #7ee5ff;
        }

        QLineEdit, QTextEdit {
            background-color: #3e3d32;
            border: 1px solid #49483e;
            border-radius: 3px;
            padding: 4px;
            color: #f8f8f2;
        }

        QSlider::groove:horizontal {
            background: #49483e;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #66d9ef;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QTableWidget {
            background-color: #3e3d32;
            gridline-color: #49483e;
            border: 1px solid #49483e;
        }
        """

    def _generate_solarized_dark_theme(self) -> str:
        """Generate Solarized Dark theme."""
        return """
        QWidget {
            background-color: #002b36;
            color: #839496;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }

        QPushButton {
            background-color: #268bd2;
            color: #fdf6e3;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
        }

        QPushButton:hover {
            background-color: #2aa198;
        }

        QLineEdit, QTextEdit {
            background-color: #073642;
            border: 1px solid #586e75;
            border-radius: 3px;
            padding: 4px;
            color: #839496;
        }

        QSlider::groove:horizontal {
            background: #073642;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #268bd2;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QTableWidget {
            background-color: #073642;
            gridline-color: #586e75;
            border: 1px solid #586e75;
        }
        """

    def _generate_solarized_light_theme(self) -> str:
        """Generate Solarized Light theme."""
        return """
        QWidget {
            background-color: #fdf6e3;
            color: #657b83;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
        }

        QPushButton {
            background-color: #268bd2;
            color: #fdf6e3;
            border: none;
            padding: 6px 16px;
            border-radius: 4px;
        }

        QPushButton:hover {
            background-color: #2aa198;
        }

        QLineEdit, QTextEdit {
            background-color: #eee8d5;
            border: 1px solid #93a1a1;
            border-radius: 3px;
            padding: 4px;
            color: #657b83;
        }

        QSlider::groove:horizontal {
            background: #eee8d5;
            height: 6px;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #268bd2;
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }

        QTableWidget {
            background-color: #eee8d5;
            gridline-color: #93a1a1;
            border: 1px solid #93a1a1;
        }
        """


def setup_theme(app: QtWidgets.QApplication, theme_name: str = DEFAULT_THEME) -> ThemeManager:
    """
    Setup theme manager and apply initial theme.

    Args:
        app: QApplication instance
        theme_name: Initial theme to apply

    Returns:
        ThemeManager instance
    """
    theme_manager = ThemeManager(app)
    theme_manager.apply_theme(theme_name)
    return theme_manager
