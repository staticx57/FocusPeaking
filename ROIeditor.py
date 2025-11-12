#!/usr/bin/env python3
"""
FLIR Boson Focus Utility - Enhanced ROI Editor v2.0

Professional focus peaking tool with advanced ROI management, theming,
camera controls, and comprehensive export capabilities.
"""

import sys
import os
import cv2
import numpy as np
import json
from collections import deque
from typing import List, Dict, Optional, Tuple
from PyQt5 import QtWidgets, QtGui, QtCore
from datetime import datetime

# Import custom modules
from config import *
from logger_setup import setup_logging, get_logger
from camera_manager import CameraManager, CameraDevice
from focus_utils import (
    laplacian_focus_metric,
    tenengrad_focus_metric,
    brenner_gradient_metric,
    normalized_variance_focus,
    variance_of_laplacian_metric,
    compute_roi_scores,
    compute_weighted_focus,
    create_focus_peaking_overlay,
    thermal_preprocess,
    FocusStatistics,
    FocusQualityIndicator,
    FocusEnsemble,
    validate_roi,
)
from theme_manager import ThemeManager
from data_export import FocusDataExporter, generate_default_export_filename
from boson_control import BosonController, GainMode, AGCMode, FFCMode, apply_palette_software, SmartPaletteSwitcher
from boson_ui import BosonControlPanel
from zoom_manager import ZoomManager, ZoomMode

# Setup logging
logger = setup_logging()
app_logger = get_logger(__name__)


# ============================================================================
# ROI-Aware Video Label
# ============================================================================

class VideoLabel(QtWidgets.QLabel):
    """Custom video display label with ROI drawing and interaction."""

    roiCreated = QtCore.pyqtSignal(tuple)
    roiSelected = QtCore.pyqtSignal(int)
    roiMoved = QtCore.pyqtSignal(int, tuple)
    mouseOver = QtCore.pyqtSignal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._pixmap = None
        self.drawing = False
        self.start = None
        self.current_rect = None
        self.rois = []
        self.selected_id = None
        self.moving = False
        self.move_offset = (0, 0)
        self.logger = get_logger(self.__class__.__name__)

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._pixmap = pixmap
        # Scale pixmap to fit label while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            self.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        super().setPixmap(scaled_pixmap)

    def map_to_frame(self, x: int, y: int) -> Tuple[int, int]:
        """Map QLabel coordinates to frame coordinates."""
        if self._pixmap is None:
            return 0, 0

        lbl_w, lbl_h = self.width(), self.height()
        pm_w, pm_h = self._pixmap.width(), self._pixmap.height()
        scale = min(lbl_w / pm_w, lbl_h / pm_h)
        disp_w, disp_h = int(pm_w * scale), int(pm_h * scale)
        x0 = (lbl_w - disp_w) // 2
        y0 = (lbl_h - disp_h) // 2

        if x < x0 or x > x0 + disp_w or y < y0 or y > y0 + disp_h:
            x = max(x0, min(x, x0 + disp_w))
            y = max(y0, min(y, y0 + disp_h))

        fx = int((x - x0) * (FRAME_WIDTH / disp_w))
        fy = int((y - y0) * (FRAME_HEIGHT / disp_h))
        fx = max(0, min(FRAME_WIDTH - 1, fx))
        fy = max(0, min(FRAME_HEIGHT - 1, fy))
        return fx, fy

    def map_from_frame(self, rect: List[int]) -> List[int]:
        """Map frame rect to QLabel coordinates."""
        if self._pixmap is None:
            return rect

        x1, y1, x2, y2 = rect
        lbl_w, lbl_h = self.width(), self.height()
        pm_w, pm_h = self._pixmap.width(), self._pixmap.height()
        scale = min(lbl_w / pm_w, lbl_h / pm_h)
        disp_w, disp_h = int(pm_w * scale), int(pm_h * scale)
        x0 = (lbl_w - disp_w) // 2
        y0 = (lbl_h - disp_h) // 2
        sx = disp_w / FRAME_WIDTH
        sy = disp_h / FRAME_HEIGHT

        return [
            int(x0 + x1 * sx),
            int(y0 + y1 * sy),
            int(x0 + x2 * sx),
            int(y0 + y2 * sy),
        ]

    def mousePressEvent(self, ev):
        x, y = ev.x(), ev.y()
        if ev.button() == QtCore.Qt.LeftButton:
            fx, fy = self.map_to_frame(x, y)

            # Check if clicking inside existing ROI
            for r in reversed(self.rois):
                x1, y1, x2, y2 = r["rect"]
                if x1 <= fx <= x2 and y1 <= fy <= y2:
                    self.selected_id = r["id"]
                    self.roiSelected.emit(self.selected_id)
                    self.moving = True
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    self.move_offset = (fx - cx, fy - cy)
                    return

            # Start drawing new ROI
            self.drawing = True
            self.start = (fx, fy)
            self.current_rect = (fx, fy, fx, fy)

    def mouseMoveEvent(self, ev):
        x, y = ev.x(), ev.y()
        fx, fy = self.map_to_frame(x, y)
        self.mouseOver.emit((fx, fy))

        if self.drawing and self.start:
            x0, y0 = self.start
            self.current_rect = (x0, y0, fx, fy)
            self.update()
        elif self.moving and self.selected_id is not None:
            idx = next((i for i, r in enumerate(self.rois) if r["id"] == self.selected_id), None)
            if idx is None:
                return

            r = self.rois[idx]
            x1, y1, x2, y2 = r["rect"]
            w = x2 - x1
            h = y2 - y1
            cx = fx - self.move_offset[0]
            cy = fy - self.move_offset[1]
            nx1 = max(0, min(FRAME_WIDTH - w, cx - w // 2))
            ny1 = max(0, min(FRAME_HEIGHT - h, cy - h // 2))
            new_rect = [int(nx1), int(ny1), int(nx1 + w), int(ny1 + h)]
            r["rect"] = new_rect
            self.roiMoved.emit(self.selected_id, tuple(new_rect))
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            if self.drawing and self.current_rect is not None:
                x1, y1, x2, y2 = self.current_rect
                if abs(x2 - x1) > MIN_ROI_WIDTH and abs(y2 - y1) > MIN_ROI_HEIGHT:
                    norm_rect = [
                        int(min(x1, x2)),
                        int(min(y1, y2)),
                        int(max(x1, x2)),
                        int(max(y1, y2)),
                    ]
                    self.roiCreated.emit(tuple(norm_rect))
                self.current_rect = None
                self.start = None
            if self.moving:
                self.moving = False
            self.drawing = False
            self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._pixmap is None:
            return

        qp = QtGui.QPainter(self)
        pen_sel = QtGui.QPen(QtGui.QColor(*ROI_COLOR_SELECTED), 2)
        pen_reg = QtGui.QPen(QtGui.QColor(*ROI_COLOR_NORMAL), 1)

        # Draw existing ROIs
        for r in self.rois:
            rect_disp = self.map_from_frame(r["rect"])
            pen = pen_sel if r.get("id") == self.selected_id else pen_reg
            qp.setPen(pen)
            color = QtGui.QColor(*ROI_COLOR_NORMAL, int(ROI_FILL_ALPHA * r.get("weight", 1.0)))
            qp.setBrush(QtGui.QBrush(color))
            x1, y1, x2, y2 = rect_disp
            qp.drawRect(x1, y1, x2 - x1, y2 - y1)

        # Draw current drawing rect
        if self.current_rect:
            rect_disp = self.map_from_frame([
                int(self.current_rect[0]),
                int(self.current_rect[1]),
                int(self.current_rect[2]),
                int(self.current_rect[3]),
            ])
            qp.setPen(QtGui.QPen(QtGui.QColor(*ROI_COLOR_DRAWING), 2, QtCore.Qt.DashLine))
            qp.setBrush(QtCore.Qt.NoBrush)
            x1, y1, x2, y2 = rect_disp
            qp.drawRect(x1, y1, x2 - x1, y2 - y1)

        qp.end()

    def resizeEvent(self, event):
        """Handle resize events to rescale pixmap."""
        super().resizeEvent(event)
        if self._pixmap:
            scaled_pixmap = self._pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            super(VideoLabel, self).setPixmap(scaled_pixmap)
        self.update()


# ============================================================================
# Main Application Window
# ============================================================================

class BosonFocusGUI(QtWidgets.QWidget):
    """Main application window with enhanced features."""

    def __init__(self):
        super().__init__()
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing Boson Focus GUI v2.0")

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Initialize managers
        self.camera_manager = CameraManager()
        self.exporter = FocusDataExporter()
        # Initialize and connect to Boson camera
        self.boson_controller = BosonController()
        if self.boson_controller.sdk_available:
            self.boson_controller.connect()
        self.stats_tracker = FocusStatistics(window_size=STATS_WINDOW_SIZE)

        # State
        self.regions = []
        self.next_id = 1
        self.current_weight = DEFAULT_ROI_WEIGHT
        self.focus_color = DEFAULT_PEAKING_COLOR
        self.edge_threshold = DEFAULT_EDGE_THRESHOLD
        self.focus_history = deque(maxlen=FOCUS_HISTORY_LENGTH)
        self.selected_id = None
        self.paused = False

        # Auto-scaling graph (optimized for thermal cameras)
        self.graph_min = 0
        self.graph_max = DEFAULT_GRAPH_MAX_FOCUS
        self.graph_adaptive = True  # Enable auto-scaling by default

        # Focus algorithm selection
        self.current_algorithm = DEFAULT_FOCUS_ALGORITHM
        self.algorithm_map = {
            "Laplacian Variance": laplacian_focus_metric,
            "Tenengrad": tenengrad_focus_metric,
            "Brenner Gradient": brenner_gradient_metric,
            "Normalized Variance": normalized_variance_focus,
            "Variance of Laplacian": variance_of_laplacian_metric,
        }

        # Thermal preprocessing
        self.thermal_preprocessing_enabled = False

        # Focus quality indicator
        self.focus_quality = FocusQualityIndicator()

        # Multi-algorithm ensemble (Phase 3)
        self.ensemble_voting_enabled = ENABLE_ENSEMBLE_VOTING
        self.show_all_algorithms = SHOW_ALL_ALGORITHM_SCORES
        self.focus_ensemble = FocusEnsemble(
            algorithms=FOCUS_ALGORITHMS,
            weights=ENSEMBLE_ALGORITHM_WEIGHTS,
            history_size=ENSEMBLE_HISTORY_SIZE
        )

        # Smart palette switcher (Phase 6)
        self.palette_switcher = SmartPaletteSwitcher(self.boson_controller)
        self.auto_palette_switch_enabled = False  # Default off

        # Zoom manager (New Feature)
        self.zoom_manager = ZoomManager()

        # Setup UI
        self._create_ui()
        self._setup_timer()
        self._setup_shortcuts()
        self._load_config_if_exists()
        self._connect_camera()

        self.logger.info("GUI initialization complete")

    def _create_ui(self):
        """Create the user interface."""
        main_layout = QtWidgets.QHBoxLayout(self)

        # Left panel - Video
        left_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_layout, 3)

        self.video_label = VideoLabel()
        self.video_label.setMinimumSize(400, 300)
        self.video_label.setStyleSheet("border: 2px solid #3f3f3f;")
        self.video_label.setScaledContents(False)
        self.video_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        left_layout.addWidget(self.video_label, 1)

        # Status bar at bottom
        self.status_label = QtWidgets.QLabel("Initializing...")
        left_layout.addWidget(self.status_label)

        # Right panel - Controls
        right_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_layout, 1)

        self._create_camera_controls(right_layout)
        self._create_boson_controls(right_layout)
        self._create_roi_controls(right_layout)
        self._create_peaking_controls(right_layout)
        self._create_roi_table(right_layout)
        self._create_statistics_panel(right_layout)
        self._create_graph(right_layout)
        self._create_action_buttons(right_layout)

        # Connect signals
        self.video_label.roiCreated.connect(self._on_roi_created)
        self.video_label.roiSelected.connect(self._on_roi_selected)
        self.video_label.roiMoved.connect(self._on_roi_moved)

    def _create_camera_controls(self, layout):
        """Create camera control section."""
        group = QtWidgets.QGroupBox("Camera")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Device selector
        device_layout = QtWidgets.QHBoxLayout()
        device_layout.addWidget(QtWidgets.QLabel("Device:"))
        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        device_layout.addWidget(self.device_combo)
        self.refresh_btn = QtWidgets.QPushButton("🔄")
        self.refresh_btn.setMaximumWidth(40)
        self.refresh_btn.clicked.connect(self._refresh_cameras)
        device_layout.addWidget(self.refresh_btn)
        group_layout.addLayout(device_layout)

        # Camera info
        self.camera_info_label = QtWidgets.QLabel("No camera connected")
        self.camera_info_label.setWordWrap(True)
        self.camera_info_label.setStyleSheet("font-size: 8pt; color: #888;")
        group_layout.addWidget(self.camera_info_label)

        layout.addWidget(group)

    def _create_boson_controls(self, layout):
        """Create FLIR Boson control section."""
        self.boson_panel = BosonControlPanel()
        self.boson_panel.set_controller(self.boson_controller)
        layout.addWidget(self.boson_panel)

    def _create_roi_controls(self, layout):
        """Create ROI control section."""
        group = QtWidgets.QGroupBox("ROI Weight")
        group_layout = QtWidgets.QVBoxLayout(group)

        self.weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.weight_slider.setRange(WEIGHT_SLIDER_MIN, WEIGHT_SLIDER_MAX)
        self.weight_slider.setValue(WEIGHT_SLIDER_DEFAULT)
        self.weight_slider.valueChanged.connect(self._weight_changed)
        group_layout.addWidget(self.weight_slider)

        self.weight_label = QtWidgets.QLabel(f"Weight: {DEFAULT_ROI_WEIGHT:.2f}")
        group_layout.addWidget(self.weight_label)

        layout.addWidget(group)

    def _create_peaking_controls(self, layout):
        """Create focus peaking control section."""
        group = QtWidgets.QGroupBox("Focus Peaking")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Edge threshold
        group_layout.addWidget(QtWidgets.QLabel("Edge Threshold:"))
        self.th_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.th_slider.setRange(MIN_EDGE_THRESHOLD, MAX_EDGE_THRESHOLD)
        self.th_slider.setValue(self.edge_threshold)
        self.th_slider.valueChanged.connect(self._edge_changed)
        group_layout.addWidget(self.th_slider)

        self.th_label = QtWidgets.QLabel(f"Threshold: {self.edge_threshold}")
        group_layout.addWidget(self.th_label)

        # Color picker
        self.color_btn = QtWidgets.QPushButton("Peaking Color")
        self.color_btn.clicked.connect(self._pick_color)
        group_layout.addWidget(self.color_btn)

        # Focus algorithm selector
        group_layout.addWidget(QtWidgets.QLabel("Focus Algorithm:"))
        self.algorithm_combo = QtWidgets.QComboBox()
        self.algorithm_combo.addItems(FOCUS_ALGORITHMS)
        self.algorithm_combo.setCurrentText(self.current_algorithm)
        self.algorithm_combo.setToolTip("Select focus detection algorithm")
        self.algorithm_combo.currentTextChanged.connect(self._on_algorithm_changed)
        group_layout.addWidget(self.algorithm_combo)

        # Thermal preprocessing toggle
        self.thermal_preprocessing_checkbox = QtWidgets.QCheckBox("Thermal Enhancement (CLAHE)")
        self.thermal_preprocessing_checkbox.setChecked(self.thermal_preprocessing_enabled)
        self.thermal_preprocessing_checkbox.setToolTip("Enable contrast enhancement for thermal cameras")
        self.thermal_preprocessing_checkbox.stateChanged.connect(self._toggle_thermal_preprocessing)
        group_layout.addWidget(self.thermal_preprocessing_checkbox)

        layout.addWidget(group)

        # Focus quality indicator
        if ENABLE_FOCUS_QUALITY_INDICATOR:
            quality_group = QtWidgets.QGroupBox("Focus Quality")
            quality_layout = QtWidgets.QVBoxLayout(quality_group)

            self.quality_status_label = QtWidgets.QLabel("● Calibrating...")
            self.quality_status_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
            quality_layout.addWidget(self.quality_status_label)

            self.quality_score_label = QtWidgets.QLabel("Score: -- / 100")
            self.quality_score_label.setStyleSheet("font-size: 9pt; color: #888;")
            quality_layout.addWidget(self.quality_score_label)

            layout.addWidget(quality_group)

        # Multi-algorithm ensemble (Phase 3)
        ensemble_group = QtWidgets.QGroupBox("Algorithm Ensemble (Phase 3)")
        ensemble_layout = QtWidgets.QVBoxLayout(ensemble_group)

        # Enable ensemble voting checkbox
        self.ensemble_voting_checkbox = QtWidgets.QCheckBox("Enable Multi-Algorithm Voting")
        self.ensemble_voting_checkbox.setChecked(self.ensemble_voting_enabled)
        self.ensemble_voting_checkbox.setToolTip("Combine all algorithms for robust focus detection")
        self.ensemble_voting_checkbox.stateChanged.connect(self._toggle_ensemble_voting)
        ensemble_layout.addWidget(self.ensemble_voting_checkbox)

        # Confidence indicator
        if SHOW_CONFIDENCE_INDICATOR:
            self.ensemble_confidence_label = QtWidgets.QLabel("Confidence: --")
            self.ensemble_confidence_label.setStyleSheet("font-size: 9pt; font-weight: bold;")
            ensemble_layout.addWidget(self.ensemble_confidence_label)

        # Show all algorithms checkbox
        self.show_algorithms_checkbox = QtWidgets.QCheckBox("Show All Algorithm Scores")
        self.show_algorithms_checkbox.setChecked(self.show_all_algorithms)
        self.show_algorithms_checkbox.setToolTip("Display individual scores from each algorithm")
        self.show_algorithms_checkbox.stateChanged.connect(self._toggle_show_algorithms)
        ensemble_layout.addWidget(self.show_algorithms_checkbox)

        # Algorithm scores display (collapsible)
        self.algorithm_scores_widget = QtWidgets.QWidget()
        self.algorithm_scores_layout = QtWidgets.QVBoxLayout(self.algorithm_scores_widget)
        self.algorithm_scores_layout.setContentsMargins(10, 5, 10, 5)

        # Create labels for each algorithm
        self.algorithm_score_labels = {}
        for algo_name in FOCUS_ALGORITHMS:
            label = QtWidgets.QLabel(f"{algo_name}: --")
            label.setStyleSheet("font-size: 8pt; font-family: monospace;")
            self.algorithm_scores_layout.addWidget(label)
            self.algorithm_score_labels[algo_name] = label

        self.algorithm_scores_widget.setVisible(self.show_all_algorithms)
        ensemble_layout.addWidget(self.algorithm_scores_widget)

        layout.addWidget(ensemble_group)

        # Smart palette switcher (Phase 6)
        palette_group = QtWidgets.QGroupBox("Smart Palette (Phase 6)")
        palette_layout = QtWidgets.QVBoxLayout(palette_group)

        # Auto-switch checkbox
        self.auto_palette_checkbox = QtWidgets.QCheckBox("Auto-switch to WhiteHot when Focusing")
        self.auto_palette_checkbox.setChecked(self.auto_palette_switch_enabled)
        self.auto_palette_checkbox.setToolTip(
            "Automatically switch to WhiteHot palette during focus adjustment\n"
            "(Industry best practice for thermal cameras)"
        )
        self.auto_palette_checkbox.stateChanged.connect(self._toggle_auto_palette_switch)
        palette_layout.addWidget(self.auto_palette_checkbox)

        # Manual focus mode button
        self.focus_mode_btn = QtWidgets.QPushButton("Enter Focus Mode")
        self.focus_mode_btn.setCheckable(True)
        self.focus_mode_btn.setToolTip("Manually switch to WhiteHot for easier focusing")
        self.focus_mode_btn.clicked.connect(self._toggle_focus_mode_manual)
        palette_layout.addWidget(self.focus_mode_btn)

        # Status label
        self.palette_status_label = QtWidgets.QLabel("Focus Mode: Inactive")
        self.palette_status_label.setStyleSheet("font-size: 8pt; color: #888;")
        palette_layout.addWidget(self.palette_status_label)

        layout.addWidget(palette_group)

    def _create_roi_table(self, layout):
        """Create ROI table."""
        layout.addWidget(QtWidgets.QLabel("<b>Regions of Interest</b>"))

        self.table = QtWidgets.QTableWidget(0, TABLE_COLUMN_COUNT)
        self.table.setHorizontalHeaderLabels(TABLE_HEADER_LABELS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.cellClicked.connect(self._table_clicked)
        layout.addWidget(self.table, 1)

    def _create_statistics_panel(self, layout):
        """Create statistics display panel."""
        group = QtWidgets.QGroupBox("Statistics")
        group_layout = QtWidgets.QVBoxLayout(group)

        self.stats_label = QtWidgets.QLabel("No data")
        self.stats_label.setStyleSheet("font-family: monospace; font-size: 8pt;")
        group_layout.addWidget(self.stats_label)

        layout.addWidget(group)

    def _create_graph(self, layout):
        """Create focus graph."""
        layout.addWidget(QtWidgets.QLabel("<b>Focus Trend</b>"))

        self.graph_label = QtWidgets.QLabel()
        self.graph_label.setFixedHeight(GRAPH_HEIGHT)
        self.graph_label.setStyleSheet(f"background:#{GRAPH_BACKGROUND_COLOR[0]:02x}{GRAPH_BACKGROUND_COLOR[1]:02x}{GRAPH_BACKGROUND_COLOR[2]:02x};")
        layout.addWidget(self.graph_label)

    def _create_action_buttons(self, layout):
        """Create action buttons."""
        # Row 1
        row1 = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("Save Config")
        self.save_btn.clicked.connect(self._save_config)
        row1.addWidget(self.save_btn)

        self.load_btn = QtWidgets.QPushButton("Load Config")
        self.load_btn.clicked.connect(self._load_config)
        row1.addWidget(self.load_btn)
        layout.addLayout(row1)

        # Row 2
        row2 = QtWidgets.QHBoxLayout()
        self.export_btn = QtWidgets.QPushButton("Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        row2.addWidget(self.export_btn)

        self.del_btn = QtWidgets.QPushButton("Delete ROI")
        self.del_btn.clicked.connect(self._delete_selected)
        row2.addWidget(self.del_btn)
        layout.addLayout(row2)

        # Row 3 - Theme selector
        row3 = QtWidgets.QHBoxLayout()
        row3.addWidget(QtWidgets.QLabel("Theme:"))
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(AVAILABLE_THEMES)
        self.theme_combo.setCurrentText(DEFAULT_THEME)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        row3.addWidget(self.theme_combo)
        layout.addLayout(row3)

        # Auto-scale graph checkbox
        self.auto_scale_checkbox = QtWidgets.QCheckBox("Auto-scale Graph (Thermal)")
        self.auto_scale_checkbox.setChecked(True)
        self.auto_scale_checkbox.stateChanged.connect(self._toggle_auto_scale)
        layout.addWidget(self.auto_scale_checkbox)

    def _setup_timer(self):
        """Setup update timer."""
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(TIMER_INTERVAL_MS)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Delete ROI
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["delete_roi"]),
            self,
            self._delete_selected
        )

        # Save/Load
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["save_config"]),
            self,
            self._save_config
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["load_config"]),
            self,
            self._load_config
        )

        # Export
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["export_csv"]),
            self,
            self._export_csv
        )

        # Pause
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["toggle_pause"]),
            self,
            self._toggle_pause
        )

        # Threshold adjustment
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["increase_threshold"]),
            self,
            lambda: self.th_slider.setValue(self.th_slider.value() + 5)
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence(SHORTCUTS["decrease_threshold"]),
            self,
            lambda: self.th_slider.setValue(self.th_slider.value() - 5)
        )

    # ========================================================================
    # Camera Management
    # ========================================================================

    def _connect_camera(self):
        """Connect to camera and populate device list."""
        self._refresh_cameras()

    def _refresh_cameras(self):
        """Refresh available cameras."""
        self.logger.info("Refreshing camera list...")
        self.device_combo.clear()

        cameras = CameraManager.detect_cameras()

        if not cameras:
            self.device_combo.addItem("No cameras found", -1)
            self.camera_info_label.setText("No cameras detected")
            self.logger.warning("No cameras detected")
            return

        for camera in cameras:
            self.device_combo.addItem(str(camera), camera.index)

        # Auto-connect to first camera
        if len(cameras) > 0:
            self._on_device_changed(0)

    def _on_device_changed(self, index):
        """Handle camera device selection change."""
        device_index = self.device_combo.itemData(index)

        if device_index is None or device_index == -1:
            return

        self.logger.info(f"Connecting to camera {device_index}...")

        if self.camera_manager.connect(device_index):
            info = self.camera_manager.get_camera_info()
            info_text = f"Connected: {info['width']}x{info['height']} @ {info['backend']}"
            self.camera_info_label.setText(info_text)
            self.status_label.setText(f"Camera {device_index} connected")
            self.logger.info(f"Successfully connected to camera {device_index}")
        else:
            self.camera_info_label.setText("Connection failed")
            self.status_label.setText("Camera connection failed")
            self.logger.error(f"Failed to connect to camera {device_index}")

    # ========================================================================
    # ROI Management
    # ========================================================================

    def _on_roi_created(self, rect):
        """Handle new ROI creation."""
        x1, y1, x2, y2 = rect
        r = {
            "id": self.next_id,
            "rect": [x1, y1, x2, y2],
            "weight": self.current_weight,
            "score": 0.0,
        }
        self.regions.append(r)
        self.logger.info(f"Created ROI {self.next_id}: {rect}")
        self.next_id += 1
        self._sync_rois_to_label()
        self._refresh_table()

    def _on_roi_selected(self, rid):
        """Handle ROI selection."""
        self.selected_id = rid
        for row in range(self.table.rowCount()):
            if int(self.table.item(row, 0).text()) == rid:
                self.table.selectRow(row)

        reg = self._find_region(rid)
        if reg:
            self.weight_slider.setValue(int(reg["weight"] * 100))

    def _on_roi_moved(self, rid, rect):
        """Handle ROI movement."""
        reg = self._find_region(rid)
        if reg:
            reg["rect"] = list(rect)
            self._sync_rois_to_label()
            self._refresh_table()

    def _find_region(self, rid):
        """Find region by ID."""
        return next((r for r in self.regions if r["id"] == rid), None)

    def _delete_selected(self):
        """Delete selected ROI."""
        if self.selected_id is None:
            return

        self.regions = [r for r in self.regions if r["id"] != self.selected_id]
        self.logger.info(f"Deleted ROI {self.selected_id}")
        self.selected_id = None
        self._sync_rois_to_label()
        self._refresh_table()

    def _sync_rois_to_label(self):
        """Sync ROIs to video label for display."""
        rois_for_label = []
        for r in self.regions:
            rois_for_label.append({
                "id": r["id"],
                "rect": r["rect"],
                "weight": r["weight"],
            })
        self.video_label.rois = rois_for_label
        self.video_label.selected_id = self.selected_id
        self.video_label.update()

    def _refresh_table(self):
        """Refresh ROI table display."""
        self.table.setRowCount(0)
        for r in self.regions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{r['weight']:.2f}"))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{r.get('score', 0):.0f}"))

            btn = QtWidgets.QPushButton("Select")
            btn.clicked.connect(lambda _, rid=r["id"]: self._select_from_table(rid))
            self.table.setCellWidget(row, 3, btn)

    def _select_from_table(self, rid):
        """Select ROI from table click."""
        self.selected_id = rid
        self._on_roi_selected(rid)
        self._sync_rois_to_label()

    def _table_clicked(self, row, col):
        """Handle table cell click."""
        if col == 0:
            rid = int(self.table.item(row, 0).text())
            self._select_from_table(rid)

    # ========================================================================
    # UI Events
    # ========================================================================

    def _weight_changed(self, val):
        """Handle weight slider change."""
        w = val / 100.0
        self.current_weight = w
        self.weight_label.setText(f"Weight: {w:.2f}")

        if self.selected_id:
            r = self._find_region(self.selected_id)
            if r:
                r["weight"] = w
                self._sync_rois_to_label()
                self._refresh_table()

    def _edge_changed(self, val):
        """Handle edge threshold change."""
        self.edge_threshold = val
        self.th_label.setText(f"Threshold: {val}")

    def _pick_color(self):
        """Open color picker dialog."""
        qcolor = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self.focus_color[2], self.focus_color[1], self.focus_color[0])
        )
        if qcolor.isValid():
            self.focus_color = (qcolor.blue(), qcolor.green(), qcolor.red())
            self.logger.info(f"Peaking color changed to {self.focus_color}")

    def _on_theme_changed(self, theme_name):
        """Handle theme change."""
        # This requires reference to ThemeManager from main()
        pass

    def _on_algorithm_changed(self, algorithm_name):
        """Handle focus algorithm change."""
        self.current_algorithm = algorithm_name
        self.logger.info(f"Focus algorithm changed to: {algorithm_name}")

    def _toggle_thermal_preprocessing(self, state):
        """Toggle thermal preprocessing."""
        self.thermal_preprocessing_enabled = (state == QtCore.Qt.Checked)
        self.logger.info(f"Thermal preprocessing: {'enabled' if self.thermal_preprocessing_enabled else 'disabled'}")

    def _toggle_ensemble_voting(self, state):
        """Toggle ensemble voting system."""
        self.ensemble_voting_enabled = (state == QtCore.Qt.Checked)
        self.logger.info(f"Ensemble voting: {'enabled' if self.ensemble_voting_enabled else 'disabled'}")

        # Reset ensemble history when toggling
        if self.ensemble_voting_enabled:
            self.focus_ensemble.reset_history()

    def _toggle_show_algorithms(self, state):
        """Toggle display of all algorithm scores."""
        self.show_all_algorithms = (state == QtCore.Qt.Checked)
        if hasattr(self, 'algorithm_scores_widget'):
            self.algorithm_scores_widget.setVisible(self.show_all_algorithms)
        self.logger.debug(f"Show all algorithms: {self.show_all_algorithms}")

    def _toggle_auto_palette_switch(self, state):
        """Toggle automatic palette switching."""
        self.auto_palette_switch_enabled = (state == QtCore.Qt.Checked)
        self.palette_switcher.enable_auto_switch(self.auto_palette_switch_enabled)
        self.logger.info(f"Auto palette switch: {'enabled' if self.auto_palette_switch_enabled else 'disabled'}")

    def _toggle_focus_mode_manual(self, checked):
        """Manually toggle focus mode on/off."""
        if checked:
            # Enter focus mode
            success = self.palette_switcher.enter_focus_mode(manual=True)
            if success:
                self.focus_mode_btn.setText("Exit Focus Mode")
                self.palette_status_label.setText("Focus Mode: Active (Manual)")
                self.palette_status_label.setStyleSheet("font-size: 8pt; color: #51cf66; font-weight: bold;")
            else:
                self.focus_mode_btn.setChecked(False)
                self.palette_status_label.setText("Focus Mode: Failed to activate")
                self.palette_status_label.setStyleSheet("font-size: 8pt; color: #ff6b6b;")
        else:
            # Exit focus mode
            self.palette_switcher.exit_focus_mode(force=True)
            self.focus_mode_btn.setText("Enter Focus Mode")
            self.palette_status_label.setText("Focus Mode: Inactive")
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: #888;")

    def _toggle_pause(self):
        """Toggle video pause."""
        self.paused = not self.paused
        status = "paused" if self.paused else "running"
        self.status_label.setText(f"Video {status}")
        self.logger.info(f"Video {status}")

    def _toggle_auto_scale(self, state):
        """Toggle graph auto-scaling."""
        self.graph_adaptive = (state == QtCore.Qt.Checked)
        if not self.graph_adaptive:
            # Reset to default when disabled
            self.graph_max = DEFAULT_GRAPH_MAX_FOCUS
            self.graph_min = 0

    # ========================================================================
    # Config Management
    # ========================================================================

    def _save_config(self):
        """Save configuration to file."""
        try:
            config = {
                "focus_color": list(self.focus_color),
                "edge_threshold": self.edge_threshold,
                "regions": [
                    {"id": r["id"], "rect": r["rect"], "weight": r["weight"]}
                    for r in self.regions
                ],
                "graph_adaptive": self.graph_adaptive,
                "boson": self.boson_panel.get_settings(),
                "focus_algorithm": self.current_algorithm,
                "thermal_preprocessing": self.thermal_preprocessing_enabled,
                "ensemble_voting_enabled": self.ensemble_voting_enabled,
                "show_all_algorithms": self.show_all_algorithms,
                "auto_palette_switch_enabled": self.auto_palette_switch_enabled,
            }

            with open(get_config_path(), "w") as f:
                json.dump(config, f, indent=2)

            QtWidgets.QMessageBox.information(
                self, "Saved", f"Configuration saved to {CONFIG_FILE}"
            )
            self.logger.info("Configuration saved")

        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save: {e}")

    def _load_config(self):
        """Load configuration from file."""
        try:
            with open(get_config_path()) as f:
                config = json.load(f)

            self.focus_color = tuple(config.get("focus_color", DEFAULT_PEAKING_COLOR))
            self.edge_threshold = int(config.get("edge_threshold", DEFAULT_EDGE_THRESHOLD))
            self.th_slider.setValue(self.edge_threshold)
            self.graph_adaptive = config.get("graph_adaptive", True)
            self.auto_scale_checkbox.setChecked(self.graph_adaptive)

            # Load Boson settings
            if "boson" in config:
                self.boson_panel.apply_settings(config["boson"])

            # Load focus algorithm settings
            if "focus_algorithm" in config and config["focus_algorithm"] in FOCUS_ALGORITHMS:
                self.current_algorithm = config["focus_algorithm"]
                self.algorithm_combo.setCurrentText(self.current_algorithm)
            if "thermal_preprocessing" in config:
                self.thermal_preprocessing_enabled = config["thermal_preprocessing"]
                self.thermal_preprocessing_checkbox.setChecked(self.thermal_preprocessing_enabled)

            # Load ensemble voting settings
            if "ensemble_voting_enabled" in config:
                self.ensemble_voting_enabled = config["ensemble_voting_enabled"]
                self.ensemble_voting_checkbox.setChecked(self.ensemble_voting_enabled)
            if "show_all_algorithms" in config:
                self.show_all_algorithms = config["show_all_algorithms"]
                self.show_algorithms_checkbox.setChecked(self.show_all_algorithms)
                if hasattr(self, 'algorithm_scores_widget'):
                    self.algorithm_scores_widget.setVisible(self.show_all_algorithms)

            # Load smart palette switcher settings (Phase 6)
            if "auto_palette_switch_enabled" in config:
                self.auto_palette_switch_enabled = config["auto_palette_switch_enabled"]
                self.auto_palette_checkbox.setChecked(self.auto_palette_switch_enabled)
                self.palette_switcher.enable_auto_switch(self.auto_palette_switch_enabled)

            self.regions = [
                {
                    "id": r["id"],
                    "rect": r["rect"],
                    "weight": r.get("weight", 1.0),
                    "score": 0.0,
                }
                for r in config.get("regions", [])
            ]

            self.next_id = max((r["id"] for r in self.regions), default=0) + 1

            self._sync_rois_to_label()
            self._refresh_table()

            QtWidgets.QMessageBox.information(
                self, "Loaded", f"Loaded {len(self.regions)} regions"
            )
            self.logger.info(f"Configuration loaded: {len(self.regions)} regions")

        except FileNotFoundError:
            QtWidgets.QMessageBox.information(self, "Info", "No config file found")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to load: {e}")

    def _load_config_if_exists(self):
        """Silently load config if it exists."""
        if get_config_path().exists():
            try:
                self._load_config()
            except:
                pass

    # ========================================================================
    # Data Export
    # ========================================================================

    def _export_csv(self):
        """Export focus data to CSV."""
        if len(self.focus_history) == 0:
            QtWidgets.QMessageBox.information(self, "Info", "No data to export")
            return

        filename = generate_default_export_filename("focus_data", "csv")

        success = self.exporter.export_to_csv(
            filename,
            list(self.focus_history),
            self.regions,
            metadata={
                "app_version": APP_VERSION,
                "edge_threshold": self.edge_threshold,
                "roi_count": len(self.regions),
            },
        )

        if success:
            QtWidgets.QMessageBox.information(
                self, "Exported", f"Data exported to {filename}"
            )
            self.logger.info(f"Data exported to {filename}")
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Export failed")

    # ========================================================================
    # Main Update Loop
    # ========================================================================

    def _tick(self):
        """Main update tick."""
        if self.paused:
            return

        # Read frame
        ret, frame = self.camera_manager.read_frame()

        if not ret:
            return

        # Apply software palette if Boson is connected
        if hasattr(self, 'boson_controller') and self.boson_controller:
            if self.boson_controller.is_connected:
                palette = self.boson_controller.current_palette or "WhiteHot"
                frame = apply_palette_software(frame, palette)

        # Apply focus peaking
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply thermal preprocessing if enabled
        if self.thermal_preprocessing_enabled:
            gray = thermal_preprocess(gray, enhance_contrast=True, reduce_noise=False)

        displayed = create_focus_peaking_overlay(
            frame, self.edge_threshold, self.focus_color, PEAKING_ALPHA
        )

        # Choose focus computation method: ensemble or single algorithm
        if self.ensemble_voting_enabled:
            # Use ensemble voting system
            global_score, details = self.focus_ensemble.compute_ensemble_focus(gray, return_details=True)

            # Update ensemble UI
            if hasattr(self, 'ensemble_confidence_label') and SHOW_CONFIDENCE_INDICATOR:
                confidence = details['confidence']
                quality = details['consensus_quality']
                self.ensemble_confidence_label.setText(
                    f"Confidence: {confidence*100:.0f}% ({quality.title()})"
                )

                # Color code by quality
                quality_color = QUALITY_COLORS.get(quality, "#868e96")
                self.ensemble_confidence_label.setStyleSheet(
                    f"font-size: 9pt; font-weight: bold; color: {quality_color};"
                )

            # Update individual algorithm scores display
            if self.show_all_algorithms and hasattr(self, 'algorithm_score_labels'):
                all_scores = details['all_scores']
                best_algo = details['best_algorithm']

                for algo_name, score in all_scores.items():
                    if algo_name in self.algorithm_score_labels:
                        marker = " ⭐" if algo_name == best_algo else ""
                        self.algorithm_score_labels[algo_name].setText(
                            f"{algo_name}: {score:.1f}{marker}"
                        )

            # For ROI scores, still use the currently selected algorithm
            if self.regions:
                if self.current_algorithm in self.algorithm_map:
                    metric_func = self.algorithm_map[self.current_algorithm]
                else:
                    metric_func = laplacian_focus_metric

                scores = compute_roi_scores(gray, self.regions, metric_func)
                for roi, score in zip(self.regions, scores):
                    roi["score"] = score

        else:
            # Use single selected algorithm
            if self.current_algorithm in self.algorithm_map:
                metric_func = self.algorithm_map[self.current_algorithm]
            else:
                metric_func = laplacian_focus_metric

            # Compute ROI scores
            if self.regions:
                scores = compute_roi_scores(gray, self.regions, metric_func)
                for roi, score in zip(self.regions, scores):
                    roi["score"] = score

                global_score = compute_weighted_focus(gray, self.regions, metric_func)
            else:
                global_score = metric_func(gray)

        self.focus_history.append(global_score)
        self.stats_tracker.add_score(global_score)

        # Update focus quality indicator
        if ENABLE_FOCUS_QUALITY_INDICATOR:
            self.focus_quality.update(global_score)
            quality_level, normalized_score = self.focus_quality.get_quality()
            quality_percentage = self.focus_quality.get_quality_percentage()

            # Update quality display
            quality_color = QUALITY_COLORS.get(quality_level, "#868e96")
            self.quality_status_label.setText(f"● {quality_level.title()}")
            self.quality_status_label.setStyleSheet(f"font-size: 10pt; font-weight: bold; color: {quality_color};")
            self.quality_score_label.setText(f"Score: {quality_percentage} / 100")

        # Draw ROI overlays
        for r in self.regions:
            x1, y1, x2, y2 = [int(v) for v in r["rect"]]
            color = ROI_COLOR_SELECTED if (self.selected_id and r["id"] == self.selected_id) else ROI_COLOR_NORMAL
            cv2.rectangle(displayed, (x1, y1), (x2, y2), color, 2)
            label = f"ID{r['id']} W{r['weight']:.2f} S{r['score']:.0f}"
            cv2.putText(displayed, label, (x1 + 4, y1 + 18),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Draw global focus
        cv2.putText(
            displayed,
            f"Focus: {global_score:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

        # Update display
        rgb = cv2.cvtColor(displayed, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        self.video_label.setPixmap(QtGui.QPixmap.fromImage(qimg))

        # Update table scores
        for row in range(self.table.rowCount()):
            rid = int(self.table.item(row, 0).text())
            r = self._find_region(rid)
            if r:
                self.table.item(row, 2).setText(f"{r.get('score', 0):.0f}")

        # Update statistics
        stats = self.stats_tracker.get_all_stats()
        stats_text = (
            f"Current: {stats['current']:7.1f}\n"
            f"Min:     {stats['min']:7.1f}\n"
            f"Max:     {stats['max']:7.1f}\n"
            f"Mean:    {stats['mean']:7.1f}\n"
            f"Std:     {stats['std']:7.1f}"
        )
        self.stats_label.setText(stats_text)

        # Update smart palette switcher (Phase 6)
        self.palette_switcher.update(self.focus_history)

        # Update UI status based on palette switcher state
        if self.palette_switcher.is_active() and not self.focus_mode_btn.isChecked():
            # Auto-mode is active
            self.palette_status_label.setText("Focus Mode: Active (Auto)")
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: #ffa94d; font-weight: bold;")
        elif not self.palette_switcher.is_active() and not self.focus_mode_btn.isChecked():
            # Inactive
            self.palette_status_label.setText("Focus Mode: Inactive")
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: #888;")
        # If manual button is checked, keep manual status (set in _toggle_focus_mode_manual)

        # Update graph
        self._update_graph()

    def _update_graph(self):
        """Update focus trend graph with auto-scaling."""
        graph = np.zeros((GRAPH_HEIGHT, GRAPH_WIDTH, 3), dtype=np.uint8)

        # Update auto-scaling range for thermal cameras
        if self.graph_adaptive and len(self.focus_history) > 10:
            hist_list = list(self.focus_history)
            current_min = min(hist_list)
            current_max = max(hist_list)

            # Add 10% padding for better visualization
            padding = (current_max - current_min) * 0.1
            self.graph_min = max(0, current_min - padding)
            self.graph_max = current_max + padding

            # Ensure minimum range for visibility
            if self.graph_max - self.graph_min < 10:
                self.graph_max = self.graph_min + 10

        if len(self.focus_history) > 1:
            # Auto-scaled plotting
            graph_range = self.graph_max - self.graph_min

            if graph_range > 0:
                pts = np.array(
                    [
                        [
                            int(i * GRAPH_WIDTH / max(1, len(self.focus_history) - 1)),
                            GRAPH_HEIGHT - int(((v - self.graph_min) / graph_range) * GRAPH_HEIGHT),
                        ]
                        for i, v in enumerate(self.focus_history)
                    ],
                    np.int32,
                )

                # Clamp Y values to graph bounds (prevents overflow)
                pts[:, 1] = np.clip(pts[:, 1], 0, GRAPH_HEIGHT - 1)

                # Draw the line
                cv2.polylines(graph, [pts], False, GRAPH_LINE_COLOR, 1)

        # Draw border
        cv2.rectangle(graph, (0, 0), (GRAPH_WIDTH - 1, GRAPH_HEIGHT - 1), (100, 100, 100), 1)

        # Add scale markers to show current range
        cv2.putText(graph, f"{self.graph_max:.0f}", (5, 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        cv2.putText(graph, f"{self.graph_min:.0f}", (5, GRAPH_HEIGHT - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        qg = QtGui.QImage(
            graph.data,
            GRAPH_WIDTH,
            GRAPH_HEIGHT,
            GRAPH_WIDTH * 3,
            QtGui.QImage.Format_BGR888,
        )
        self.graph_label.setPixmap(QtGui.QPixmap.fromImage(qg))

    # ========================================================================
    # Cleanup
    # ========================================================================

    def closeEvent(self, ev):
        """Handle window close."""
        self.logger.info("Application closing...")
        try:
            self.camera_manager.disconnect()
            if self.boson_controller:
                self.boson_controller.disconnect()
        except:
            pass
        ev.accept()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main application entry point."""
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Setup theme
    from theme_manager import setup_theme
    theme_manager = setup_theme(app, DEFAULT_THEME)

    # Create and show window
    window = BosonFocusGUI()

    # Connect theme change
    window.theme_combo.currentTextChanged.connect(theme_manager.apply_theme)

    window.show()

    app_logger.info(f"{APP_NAME} v{APP_VERSION} started")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
