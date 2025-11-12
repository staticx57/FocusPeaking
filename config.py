"""
Configuration constants and settings for FLIR Boson Focus Peaking.

This module centralizes all configurable parameters, making it easy to
customize the application behavior without modifying core code.
"""

from typing import Tuple
from pathlib import Path

# ============================================================================
# Application Settings
# ============================================================================

APP_NAME = "FLIR Boson Focus Utility"
APP_VERSION = "3.0.0"
CONFIG_FILE = "focus_config.json"
LOG_FILE = "flir_focus.log"

# ============================================================================
# Video/Camera Settings
# ============================================================================

# Default camera device
# - On Windows: typically 0, 1, 2, etc.
# - On Linux: /dev/video0, /dev/video1, etc.
# - Set to None to auto-detect first available camera
DEFAULT_CAMERA_DEVICE = None

# Frame dimensions
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Video processing
DEFAULT_FPS = 20  # Target frames per second
TIMER_INTERVAL_MS = int(1000 / DEFAULT_FPS)  # Timer interval in milliseconds

# Camera reconnection
CAMERA_RETRY_INTERVAL_MS = 5000  # Try to reconnect every 5 seconds
MAX_CAMERA_RETRY_ATTEMPTS = 10   # Give up after 10 attempts

# ============================================================================
# Focus Peaking Settings
# ============================================================================

# Edge detection threshold range (1-100)
# Lower values = more sensitive (shows more edges, including fine details)
# Higher values = less sensitive (shows only strong edges)
# Optimal range for most use cases: 30-80
DEFAULT_EDGE_THRESHOLD = 50
MIN_EDGE_THRESHOLD = 1
MAX_EDGE_THRESHOLD = 100  # Adjusted from 300 for better slider usability

# Default focus peaking color (BGR format)
DEFAULT_PEAKING_COLOR: Tuple[int, int, int] = (0, 0, 255)  # Red

# Overlay blending
PEAKING_ALPHA = 0.5  # Focus peaking overlay transparency (0.0-1.0)
FRAME_BLEND_WEIGHT = 0.8  # Original frame weight in blend

# Alternative focus peaking colors (BGR)
PEAKING_COLORS = {
    "Red": (0, 0, 255),
    "Green": (0, 255, 0),
    "Blue": (255, 0, 0),
    "Yellow": (0, 255, 255),
    "Cyan": (255, 255, 0),
    "Magenta": (255, 0, 255),
    "White": (255, 255, 255),
}

# ============================================================================
# Focus Algorithm Settings (Enhanced Features)
# ============================================================================

# Available focus measurement algorithms
FOCUS_ALGORITHMS = [
    "Laplacian Variance",      # Current default - good general purpose
    "Tenengrad",               # Best for fine details
    "Brenner Gradient",        # Fastest computation
    "Normalized Variance",     # Simple and fast
    "Variance of Laplacian",   # Noise-reduced Laplacian
]

DEFAULT_FOCUS_ALGORITHM = "Laplacian Variance"

# Enable multi-algorithm comparison mode
ENABLE_ALGORITHM_COMPARISON = False  # Show all algorithms side-by-side

# ============================================================================
# Multi-Algorithm Voting System (Phase 3)
# ============================================================================

# Enable ensemble voting system
ENABLE_ENSEMBLE_VOTING = False  # User can enable via UI

# Ensemble algorithm weights (higher = more influence)
ENSEMBLE_ALGORITHM_WEIGHTS = {
    "Laplacian Variance": 1.0,
    "Tenengrad": 1.2,           # Slightly favor Tenengrad (best for details)
    "Brenner Gradient": 0.8,
    "Normalized Variance": 0.9,
    "Variance of Laplacian": 1.0,
}

# Confidence thresholds
ENSEMBLE_CONFIDENCE_THRESHOLDS = {
    "excellent": 0.85,  # Algorithms strongly agree
    "good": 0.70,       # Good agreement
    "fair": 0.50,       # Moderate agreement
    "poor": 0.0         # Poor agreement / conflicting
}

# History size for ensemble normalization
ENSEMBLE_HISTORY_SIZE = 10

# Display settings
SHOW_ALL_ALGORITHM_SCORES = False  # Show individual algorithm scores in UI
SHOW_CONFIDENCE_INDICATOR = True   # Show consensus confidence

# ============================================================================
# Thermal Preprocessing Settings
# ============================================================================

# Enable thermal-specific preprocessing
ENABLE_THERMAL_PREPROCESSING = False  # User must enable explicitly
THERMAL_AUTO_DETECT = False  # Auto-detect thermal camera and enable

# CLAHE (Contrast Limited Adaptive Histogram Equalization) settings
THERMAL_CLAHE_CLIP_LIMIT = 2.0  # Controls contrast enhancement (1.0-4.0)
THERMAL_CLAHE_TILE_SIZE = (8, 8)  # Size of local regions

# Noise reduction
ENABLE_THERMAL_NOISE_REDUCTION = False  # Gaussian blur for noise

# ============================================================================
# Focus Quality Indicator Settings
# ============================================================================

# Enable focus quality assessment
ENABLE_FOCUS_QUALITY_INDICATOR = True

# History size for quality calculation
FOCUS_QUALITY_HISTORY_SIZE = 50

# Quality thresholds (normalized scores 0.0-1.0)
FOCUS_QUALITY_THRESHOLDS = {
    "excellent": 0.85,
    "good": 0.70,
    "fair": 0.50,
    "poor": 0.0
}

# Quality level colors (for UI indicators)
QUALITY_COLORS = {
    "excellent": "#51cf66",  # Green
    "good": "#94d82d",       # Light green
    "fair": "#ffa94d",       # Orange
    "poor": "#ff6b6b",       # Red
    "calibrating": "#868e96" # Gray
}

# ============================================================================
# ROI Settings
# ============================================================================

# Default ROI weight
DEFAULT_ROI_WEIGHT = 1.0
MIN_ROI_WEIGHT = 0.01
MAX_ROI_WEIGHT = 3.0

# ROI weight slider settings
WEIGHT_SLIDER_MIN = 1
WEIGHT_SLIDER_MAX = 300
WEIGHT_SLIDER_DEFAULT = 100

# Minimum ROI size (pixels)
MIN_ROI_WIDTH = 10
MIN_ROI_HEIGHT = 10

# ROI visualization colors (BGR)
ROI_COLOR_NORMAL = (0, 255, 0)      # Green
ROI_COLOR_SELECTED = (0, 255, 255)  # Yellow
ROI_COLOR_DRAWING = (255, 255, 0)   # Cyan
ROI_FILL_ALPHA = 60                 # ROI fill transparency

# ============================================================================
# Focus Graph Settings
# ============================================================================

# Graph dimensions
GRAPH_WIDTH = 300
GRAPH_HEIGHT = 180

# History tracking
FOCUS_HISTORY_LENGTH = 400  # Number of samples to keep

# Graph scaling
DEFAULT_GRAPH_MAX_FOCUS = 5000  # Maximum focus value on Y-axis
GRAPH_LINE_COLOR = (0, 255, 0)  # Green
GRAPH_BACKGROUND_COLOR = (17, 17, 17)  # Dark gray

# ============================================================================
# UI Settings
# ============================================================================

# Window dimensions
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700

# Video display size
VIDEO_DISPLAY_WIDTH = 800
VIDEO_DISPLAY_HEIGHT = 600

# Font settings
FONT_FAMILY = "Arial"
FONT_SIZE_NORMAL = 9
FONT_SIZE_SMALL = 8
FONT_SIZE_LARGE = 11

# Table settings
TABLE_COLUMN_COUNT = 4
TABLE_HEADER_LABELS = ["ID", "Weight", "Score", "Actions"]

# ============================================================================
# Statistics Settings
# ============================================================================

# Statistics window size for rolling calculations
STATS_WINDOW_SIZE = 100

# Export settings
CSV_EXPORT_DELIMITER = ","
CSV_EXPORT_DECIMAL = "."

# ============================================================================
# Keyboard Shortcuts
# ============================================================================

SHORTCUTS = {
    "delete_roi": "Delete",
    "delete_roi_alt": "Backspace",
    "save_config": "Ctrl+S",
    "load_config": "Ctrl+O",
    "export_csv": "Ctrl+E",
    "toggle_pause": "Space",
    "increase_threshold": "+",
    "decrease_threshold": "-",
    "increase_threshold_alt": "=",  # No shift needed
    "toggle_fullscreen": "F11",
    "quit": "Ctrl+Q",
}

# Quick ROI selection (1-9)
QUICK_SELECT_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]

# ============================================================================
# Theme Settings
# ============================================================================

# Available themes
AVAILABLE_THEMES = [
    "Light",
    "Dark",
    "Breeze Dark",
    "Nord",
    "Dracula",
    "Monokai",
    "Solarized Dark",
    "Solarized Light",
]

DEFAULT_THEME = "Dark"

# Theme-specific color palettes
THEME_COLORS = {
    "Dark": {
        "background": "#1e1e1e",
        "foreground": "#ffffff",
        "accent": "#0078d4",
        "border": "#3f3f3f",
    },
    "Light": {
        "background": "#ffffff",
        "foreground": "#000000",
        "accent": "#0078d4",
        "border": "#cccccc",
    },
    "Nord": {
        "background": "#2e3440",
        "foreground": "#eceff4",
        "accent": "#88c0d0",
        "border": "#4c566a",
    },
    "Dracula": {
        "background": "#282a36",
        "foreground": "#f8f8f2",
        "accent": "#bd93f9",
        "border": "#44475a",
    },
    "Monokai": {
        "background": "#272822",
        "foreground": "#f8f8f2",
        "accent": "#66d9ef",
        "border": "#3e3d32",
    },
    "Solarized Dark": {
        "background": "#002b36",
        "foreground": "#839496",
        "accent": "#268bd2",
        "border": "#073642",
    },
    "Solarized Light": {
        "background": "#fdf6e3",
        "foreground": "#657b83",
        "accent": "#268bd2",
        "border": "#eee8d5",
    },
}

# ============================================================================
# FLIR Boson Settings
# ============================================================================

# Boson communication settings
BOSON_DEFAULT_INTERFACE = "USB"  # USB or UART
BOSON_UART_BAUDRATE = 921600
BOSON_COMMAND_TIMEOUT = 1000  # milliseconds

# Boson gain modes
BOSON_GAIN_MODES = {
    "High": 0,
    "Low": 1,
    "Auto": 2,
}

# Boson AGC modes
BOSON_AGC_MODES = {
    "Manual": 0,
    "Auto": 1,
    "Linear": 2,
}

# Boson FFC (Flat Field Correction) modes
BOSON_FFC_MODES = {
    "Manual": 0,
    "Auto": 1,
    "External": 2,
}

# Boson color palettes (LUT - Look Up Tables)
BOSON_PALETTES = {
    "WhiteHot": 0,
    "BlackHot": 1,
    "Rainbow": 2,
    "RainbowHC": 3,
    "Ironbow": 4,
    "Lava": 5,
    "Arctic": 6,
    "Globow": 7,
    "Gradedfire": 8,
    "Hottest": 9,
}

# ============================================================================
# Logging Settings
# ============================================================================

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5  # Keep 5 backup log files

# Console logging
ENABLE_CONSOLE_LOGGING = True

# ============================================================================
# Development/Debug Settings
# ============================================================================

# Enable debug features
DEBUG_MODE = False

# Show performance metrics
SHOW_PERFORMANCE_METRICS = False

# Mock camera for testing (when no real camera available)
ENABLE_MOCK_CAMERA = False

# ============================================================================
# Path Helpers
# ============================================================================

def get_config_path() -> Path:
    """Get the full path to the configuration file."""
    return Path(__file__).parent / CONFIG_FILE


def get_log_path() -> Path:
    """Get the full path to the log file."""
    return Path(__file__).parent / LOG_FILE
