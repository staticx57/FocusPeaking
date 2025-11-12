#!/usr/bin/env python3
"""
FLIR Boson Focus Utility - Simple Version with ROI Editor

Streamlined focus peaking tool with interactive ROI editing and
auto-scaling graph optimized for thermal cameras.
"""

import sys
import cv2
import numpy as np
import json
from collections import deque
from typing import List, Dict, Tuple
from PyQt5 import QtWidgets, QtGui, QtCore

# Import enhanced modules
try:
    from config import *
    from logger_setup import setup_logging, get_logger
    from camera_manager import CameraManager
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
        FocusQualityIndicator,
    )
    from theme_manager import setup_theme
    from boson_control import BosonController, apply_palette_software
    from boson_ui import BosonControlPanel

    ENHANCED_MODE = True
    logger = setup_logging()
    app_logger = get_logger(__name__)

except ImportError:
    # Fallback to basic mode if enhanced modules not available
    ENHANCED_MODE = False
    CONFIG_FILE = "focus_config.json"
    FRAME_WIDTH = 640
    FRAME_HEIGHT = 480
    DEFAULT_PEAKING_COLOR = (0, 0, 255)
    DEFAULT_EDGE_THRESHOLD = 100
    FOCUS_HISTORY_LENGTH = 400
    GRAPH_WIDTH = 300
    GRAPH_HEIGHT = 180
    MIN_ROI_WIDTH = 10
    MIN_ROI_HEIGHT = 10
    ROI_COLOR_NORMAL = (0, 255, 0)
    ROI_COLOR_SELECTED = (0, 255, 255)
    ROI_COLOR_DRAWING = (255, 255, 0)
    ROI_FILL_ALPHA = 60


# ============================================================================
# ROI-Aware Video Label (Integrated from ROIeditor.py)
# ============================================================================

class VideoLabel(QtWidgets.QLabel):
    """Interactive video label with ROI drawing and editing."""

    roiCreated = QtCore.pyqtSignal(tuple)
    roiSelected = QtCore.pyqtSignal(int)
    roiMoved = QtCore.pyqtSignal(int, tuple)

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
        self.frame_width = FRAME_WIDTH
        self.frame_height = FRAME_HEIGHT

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

        fx = int((x - x0) * (self.frame_width / disp_w))
        fy = int((y - y0) * (self.frame_height / disp_h))
        fx = max(0, min(self.frame_width - 1, fx))
        fy = max(0, min(self.frame_height - 1, fy))
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
        sx = disp_w / self.frame_width
        sy = disp_h / self.frame_height

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
            nx1 = max(0, min(self.frame_width - w, cx - w // 2))
            ny1 = max(0, min(self.frame_height - h, cy - h // 2))
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
# Main Application
# ============================================================================

class BosonFocusUtility(QtWidgets.QWidget):
    """Simple focus peaking utility with ROI support and auto-scaling graph."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FLIR Boson Focus Utility - Simple")
        # Window size will be set after UI creation for auto-scaling

        # Camera
        if ENHANCED_MODE:
            self.camera_manager = CameraManager()
            # Initialize and connect to Boson camera
            self.boson_controller = BosonController()
            if self.boson_controller.sdk_available:
                self.boson_controller.connect()
        else:
            self.cap = cv2.VideoCapture(0)
            self.boson_controller = None

        # State
        self.regions = []
        self.next_id = 1
        self.current_weight = 1.0
        self.focus_color = DEFAULT_PEAKING_COLOR
        self.edge_threshold = DEFAULT_EDGE_THRESHOLD
        self.focus_history = deque(maxlen=FOCUS_HISTORY_LENGTH)
        self.selected_id = None

        # Auto-scaling for graph
        self.graph_min = 0
        self.graph_max = 1000  # Initial guess
        self.graph_adaptive = True  # Enable auto-scaling

        # Focus algorithm selection (enhanced mode)
        self.current_algorithm = DEFAULT_FOCUS_ALGORITHM if ENHANCED_MODE else "Laplacian Variance"
        self.algorithm_map = {
            "Laplacian Variance": laplacian_focus_metric,
            "Tenengrad": tenengrad_focus_metric,
            "Brenner Gradient": brenner_gradient_metric,
            "Normalized Variance": normalized_variance_focus,
            "Variance of Laplacian": variance_of_laplacian_metric,
        } if ENHANCED_MODE else {}

        # Thermal preprocessing
        self.thermal_preprocessing_enabled = False

        # Focus quality indicator
        self.focus_quality = FocusQualityIndicator() if ENHANCED_MODE else None

        # Setup UI
        self._create_ui()

        # Auto-scale window to fit content
        self._auto_scale_window()

        # Timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(50)  # 20 fps

        # Connect camera if enhanced mode
        if ENHANCED_MODE:
            self._connect_camera()

    def _create_ui(self):
        """Create user interface with tabbed settings."""
        layout = QtWidgets.QHBoxLayout(self)

        # Video display with ROI editing (increased from 3 to 5 for more space)
        self.video_label = VideoLabel()
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("border: 2px solid palette(mid);")
        self.video_label.setScaledContents(False)
        self.video_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        layout.addWidget(self.video_label, 5)

        # Connect ROI signals
        self.video_label.roiCreated.connect(self._on_roi_created)
        self.video_label.roiSelected.connect(self._on_roi_selected)
        self.video_label.roiMoved.connect(self._on_roi_moved)

        # Controls
        control_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(control_layout, 2)

        # Create tabbed interface for settings (if enhanced mode) or simple controls
        if ENHANCED_MODE:
            self.settings_tabs = QtWidgets.QTabWidget()

            # Tab 1: Camera & Focus
            main_tab_widget = QtWidgets.QWidget()
            main_tab_layout = QtWidgets.QVBoxLayout(main_tab_widget)
            main_tab_layout.setContentsMargins(5, 5, 5, 5)

            # Camera selector
            camera_group = QtWidgets.QGroupBox("Camera")
            camera_layout = QtWidgets.QVBoxLayout(camera_group)

            device_layout = QtWidgets.QHBoxLayout()
            device_layout.addWidget(QtWidgets.QLabel("Device:"))
            self.device_combo = QtWidgets.QComboBox()
            self.device_combo.currentIndexChanged.connect(self._on_device_changed)
            device_layout.addWidget(self.device_combo)

            self.refresh_btn = QtWidgets.QPushButton("🔄")
            self.refresh_btn.setMaximumWidth(40)
            self.refresh_btn.clicked.connect(self._refresh_cameras)
            device_layout.addWidget(self.refresh_btn)
            camera_layout.addLayout(device_layout)

            self.camera_info_label = QtWidgets.QLabel("No camera")
            self.camera_info_label.setWordWrap(True)
            self.camera_info_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
            camera_layout.addWidget(self.camera_info_label)

            main_tab_layout.addWidget(camera_group)

            # Boson controls
            self.boson_panel = BosonControlPanel()
            self.boson_panel.set_controller(self.boson_controller)
            main_tab_layout.addWidget(self.boson_panel)

            # Focus algorithm
            algo_group = QtWidgets.QGroupBox("Focus Algorithm")
            algo_layout = QtWidgets.QVBoxLayout(algo_group)
            algo_layout.addWidget(QtWidgets.QLabel("Algorithm:"))
            self.algorithm_combo = QtWidgets.QComboBox()
            self.algorithm_combo.addItems(FOCUS_ALGORITHMS)
            self.algorithm_combo.setCurrentText(self.current_algorithm)
            self.algorithm_combo.setToolTip("Select focus detection algorithm")
            self.algorithm_combo.currentTextChanged.connect(self._on_algorithm_changed)
            algo_layout.addWidget(self.algorithm_combo)

            self.thermal_preprocessing_checkbox = QtWidgets.QCheckBox("Thermal Enhancement (CLAHE)")
            self.thermal_preprocessing_checkbox.setChecked(self.thermal_preprocessing_enabled)
            self.thermal_preprocessing_checkbox.setToolTip("Enable contrast enhancement for thermal cameras")
            self.thermal_preprocessing_checkbox.stateChanged.connect(self._toggle_thermal_preprocessing)
            algo_layout.addWidget(self.thermal_preprocessing_checkbox)

            main_tab_layout.addWidget(algo_group)

            # Focus quality
            if ENABLE_FOCUS_QUALITY_INDICATOR:
                quality_group = QtWidgets.QGroupBox("Focus Quality")
                quality_layout = QtWidgets.QVBoxLayout(quality_group)

                self.quality_status_label = QtWidgets.QLabel("● Calibrating...")
                self.quality_status_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
                quality_layout.addWidget(self.quality_status_label)

                self.quality_score_label = QtWidgets.QLabel("Score: -- / 100")
                self.quality_score_label.setStyleSheet("font-size: 9pt; color: palette(mid);")
                quality_layout.addWidget(self.quality_score_label)

                main_tab_layout.addWidget(quality_group)

            main_tab_layout.addStretch()

            main_scroll = QtWidgets.QScrollArea()
            main_scroll.setWidget(main_tab_widget)
            main_scroll.setWidgetResizable(True)
            main_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            main_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.settings_tabs.addTab(main_scroll, "📷 Camera & Focus")

            # Tab 2: Settings
            settings_tab_widget = QtWidgets.QWidget()
            settings_tab_layout = QtWidgets.QVBoxLayout(settings_tab_widget)
            settings_tab_layout.setContentsMargins(5, 5, 5, 5)

            # Theme selector
            theme_group = QtWidgets.QGroupBox("Theme")
            theme_layout = QtWidgets.QVBoxLayout(theme_group)
            theme_selector_layout = QtWidgets.QHBoxLayout()
            theme_selector_layout.addWidget(QtWidgets.QLabel("Theme:"))
            self.theme_combo = QtWidgets.QComboBox()
            self.theme_combo.addItems(AVAILABLE_THEMES)
            self.theme_combo.setCurrentText(DEFAULT_THEME)
            self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
            theme_selector_layout.addWidget(self.theme_combo)
            theme_layout.addLayout(theme_selector_layout)
            settings_tab_layout.addWidget(theme_group)

            settings_tab_layout.addStretch()

            settings_scroll = QtWidgets.QScrollArea()
            settings_scroll.setWidget(settings_tab_widget)
            settings_scroll.setWidgetResizable(True)
            settings_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            settings_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.settings_tabs.addTab(settings_scroll, "⚙️ Settings")

            control_layout.addWidget(self.settings_tabs)

        # Always visible: ROI Weight
        weight_group = QtWidgets.QGroupBox("ROI Weight")
        weight_layout = QtWidgets.QVBoxLayout(weight_group)
        self.weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.weight_slider.setRange(1, 300)
        self.weight_slider.setValue(100)
        self.weight_slider.valueChanged.connect(self._weight_changed)
        weight_layout.addWidget(self.weight_slider)
        self.weight_label = QtWidgets.QLabel("Weight: 1.00")
        weight_layout.addWidget(self.weight_label)
        control_layout.addWidget(weight_group)

        # Always visible: Edge Threshold
        threshold_group = QtWidgets.QGroupBox("Edge Threshold")
        threshold_layout = QtWidgets.QVBoxLayout(threshold_group)
        threshold_layout.addWidget(QtWidgets.QLabel("Threshold (1-100):"))
        self.threshold_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.threshold_slider.setRange(MIN_EDGE_THRESHOLD, MAX_EDGE_THRESHOLD)
        self.threshold_slider.setValue(self.edge_threshold)
        self.threshold_slider.valueChanged.connect(self._threshold_changed)
        threshold_layout.addWidget(self.threshold_slider)
        self.threshold_label = QtWidgets.QLabel(f"Threshold: {self.edge_threshold}")
        threshold_layout.addWidget(self.threshold_label)
        control_layout.addWidget(threshold_group)

        # Always visible: Color picker & Delete
        self.color_btn = QtWidgets.QPushButton("Peaking Color")
        self.color_btn.clicked.connect(self._pick_color)
        control_layout.addWidget(self.color_btn)

        self.delete_btn = QtWidgets.QPushButton("🗑️ Delete Selected ROI")
        self.delete_btn.clicked.connect(self._delete_roi)
        control_layout.addWidget(self.delete_btn)

        # Always visible: Graph controls
        self.auto_scale_checkbox = QtWidgets.QCheckBox("Auto-scale Graph")
        self.auto_scale_checkbox.setChecked(True)
        self.auto_scale_checkbox.setToolTip("Automatically adjust graph Y-axis to data range")
        self.auto_scale_checkbox.stateChanged.connect(self._toggle_auto_scale)
        control_layout.addWidget(self.auto_scale_checkbox)

        # Always visible: Save/Load buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("💾 Save")
        self.save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_btn)

        self.load_btn = QtWidgets.QPushButton("📂 Load")
        self.load_btn.clicked.connect(self._load_config)
        btn_layout.addWidget(self.load_btn)
        control_layout.addLayout(btn_layout)

        # Always visible: Focus graph
        control_layout.addWidget(QtWidgets.QLabel("<b>Focus Trend</b>"))
        self.graph_label = QtWidgets.QLabel()
        self.graph_label.setFixedHeight(GRAPH_HEIGHT)
        self.graph_label.setStyleSheet("background-color: palette(base); border: 1px solid palette(mid);")
        control_layout.addWidget(self.graph_label)

        self.graph_range_label = QtWidgets.QLabel("Range: 0 - 1000")
        self.graph_range_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        control_layout.addWidget(self.graph_range_label)

        control_layout.addStretch()

        # Always visible: Status
        self.status_label = QtWidgets.QLabel("Ready")
        control_layout.addWidget(self.status_label)

    def _auto_scale_window(self):
        """Auto-scale window to fit content on startup."""
        # Process events to let layout calculate sizes
        QtWidgets.QApplication.processEvents()

        # Get screen geometry using QScreen (more reliable)
        screen = QtWidgets.QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()
        screen_width = screen_rect.width()
        screen_height = screen_rect.height()

        # Calculate optimal size based on screen size
        # Use 80% of screen width and 85% of screen height for simpler GUI
        optimal_width = int(screen_width * 0.80)
        optimal_height = int(screen_height * 0.85)

        # Apply minimum sizes but don't exceed screen
        optimal_width = max(min(optimal_width, screen_width - 100), 1100)
        optimal_height = max(min(optimal_height, screen_height - 100), 700)

        # Set the window size
        self.resize(optimal_width, optimal_height)

        # Center the window on screen
        self.move(
            screen_rect.x() + (screen_width - optimal_width) // 2,
            screen_rect.y() + (screen_height - optimal_height) // 2
        )

    def _connect_camera(self):
        """Connect to camera in enhanced mode."""
        if not ENHANCED_MODE:
            return

        self._refresh_cameras()

    def _refresh_cameras(self):
        """Refresh available cameras."""
        if not ENHANCED_MODE:
            return

        self.device_combo.clear()

        cameras = CameraManager.detect_cameras()

        if not cameras:
            self.device_combo.addItem("No cameras found", -1)
            self.camera_info_label.setText("No cameras detected")
            self.status_label.setText("No camera found")
            return

        for camera in cameras:
            self.device_combo.addItem(str(camera), camera.index)

        # Auto-connect to first camera
        if len(cameras) > 0:
            self._on_device_changed(0)

    def _on_device_changed(self, index):
        """Handle camera device selection change."""
        if not ENHANCED_MODE:
            return

        device_index = self.device_combo.itemData(index)

        if device_index is None or device_index == -1:
            return

        if self.camera_manager.connect(device_index):
            info = self.camera_manager.get_camera_info()
            info_text = f"{info['width']}x{info['height']} @ {info['backend']}"
            self.camera_info_label.setText(info_text)
            self.status_label.setText(f"Camera {device_index} connected")
        else:
            self.camera_info_label.setText("Connection failed")
            self.status_label.setText("Camera connection failed")

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
        self.next_id += 1
        self._sync_rois()

    def _on_roi_selected(self, rid):
        """Handle ROI selection."""
        self.selected_id = rid
        reg = next((r for r in self.regions if r["id"] == rid), None)
        if reg:
            self.weight_slider.setValue(int(reg["weight"] * 100))

    def _on_roi_moved(self, rid, rect):
        """Handle ROI movement."""
        reg = next((r for r in self.regions if r["id"] == rid), None)
        if reg:
            reg["rect"] = list(rect)
            self._sync_rois()

    def _delete_roi(self):
        """Delete selected ROI."""
        if self.selected_id is None:
            return
        self.regions = [r for r in self.regions if r["id"] != self.selected_id]
        self.selected_id = None
        self._sync_rois()

    def _sync_rois(self):
        """Sync ROIs to video label."""
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

    # ========================================================================
    # UI Events
    # ========================================================================

    def _weight_changed(self, val):
        """Handle weight change."""
        w = val / 100.0
        self.current_weight = w
        self.weight_label.setText(f"Weight: {w:.2f}")

        if self.selected_id:
            reg = next((r for r in self.regions if r["id"] == self.selected_id), None)
            if reg:
                reg["weight"] = w
                self._sync_rois()

    def _threshold_changed(self, val):
        """Handle threshold change."""
        self.edge_threshold = val
        self.threshold_label.setText(f"Threshold: {val}")

    def _pick_color(self):
        """Pick peaking color."""
        qcolor = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self.focus_color[2], self.focus_color[1], self.focus_color[0])
        )
        if qcolor.isValid():
            self.focus_color = (qcolor.blue(), qcolor.green(), qcolor.red())

    def _on_theme_changed(self, theme_name):
        """Handle theme change."""
        # This is handled in main() where theme_manager is accessible
        pass

    def _toggle_auto_scale(self, state):
        """Toggle graph auto-scaling."""
        self.graph_adaptive = (state == QtCore.Qt.Checked)

    def _on_algorithm_changed(self, algorithm_name):
        """Handle focus algorithm change."""
        self.current_algorithm = algorithm_name
        if ENHANCED_MODE:
            app_logger.info(f"Focus algorithm changed to: {algorithm_name}")

    def _toggle_thermal_preprocessing(self, state):
        """Toggle thermal preprocessing."""
        self.thermal_preprocessing_enabled = (state == QtCore.Qt.Checked)
        if ENHANCED_MODE:
            app_logger.info(f"Thermal preprocessing: {'enabled' if self.thermal_preprocessing_enabled else 'disabled'}")

    # ========================================================================
    # Config
    # ========================================================================

    def _save_config(self):
        """Save configuration."""
        try:
            config = {
                "focus_color": list(self.focus_color),
                "edge_threshold": self.edge_threshold,
                "regions": [
                    {"id": r["id"], "rect": r["rect"], "weight": r["weight"]}
                    for r in self.regions
                ],
                "graph_adaptive": self.graph_adaptive,
            }

            # Save theme if in enhanced mode
            if ENHANCED_MODE:
                config["theme"] = self.theme_combo.currentText()
                # Save Boson settings
                config["boson"] = self.boson_panel.get_settings()
                # Save focus algorithm settings
                config["focus_algorithm"] = self.current_algorithm
                config["thermal_preprocessing"] = self.thermal_preprocessing_enabled

            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
            QtWidgets.QMessageBox.information(self, "Saved", f"Config saved to {CONFIG_FILE}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", str(e))

    def _load_config(self):
        """Load configuration."""
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)

            self.focus_color = tuple(config.get("focus_color", DEFAULT_PEAKING_COLOR))
            self.edge_threshold = int(config.get("edge_threshold", DEFAULT_EDGE_THRESHOLD))
            self.threshold_slider.setValue(self.edge_threshold)

            # Load graph adaptive setting
            self.graph_adaptive = config.get("graph_adaptive", True)
            self.auto_scale_checkbox.setChecked(self.graph_adaptive)

            # Load theme if in enhanced mode
            if ENHANCED_MODE and "theme" in config:
                theme_name = config["theme"]
                if theme_name in AVAILABLE_THEMES:
                    self.theme_combo.setCurrentText(theme_name)

            # Load Boson settings
            if ENHANCED_MODE and "boson" in config:
                self.boson_panel.apply_settings(config["boson"])

            # Load focus algorithm settings
            if ENHANCED_MODE:
                if "focus_algorithm" in config and config["focus_algorithm"] in FOCUS_ALGORITHMS:
                    self.current_algorithm = config["focus_algorithm"]
                    self.algorithm_combo.setCurrentText(self.current_algorithm)
                if "thermal_preprocessing" in config:
                    self.thermal_preprocessing_enabled = config["thermal_preprocessing"]
                    self.thermal_preprocessing_checkbox.setChecked(self.thermal_preprocessing_enabled)

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
            self._sync_rois()

            QtWidgets.QMessageBox.information(self, "Loaded", f"Loaded {len(self.regions)} ROIs")
        except FileNotFoundError:
            QtWidgets.QMessageBox.information(self, "Info", "No config file found")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", str(e))

    # ========================================================================
    # Main Update Loop with Auto-Scaling Graph
    # ========================================================================

    def _update_frame(self):
        """Update frame with auto-scaling graph."""
        # Read frame
        if ENHANCED_MODE:
            ret, frame = self.camera_manager.read_frame()
        else:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

        if not ret:
            return

        # Apply software palette if Boson is connected
        if ENHANCED_MODE and hasattr(self, 'boson_controller') and self.boson_controller:
            if self.boson_controller.is_connected:
                palette = self.boson_controller.current_palette or "WhiteHot"
                frame = apply_palette_software(frame, palette)

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply thermal preprocessing if enabled
        if ENHANCED_MODE and self.thermal_preprocessing_enabled:
            gray = thermal_preprocess(gray, enhance_contrast=True, reduce_noise=False)

        # Apply focus peaking
        if ENHANCED_MODE:
            displayed = create_focus_peaking_overlay(
                frame, self.edge_threshold, self.focus_color, 0.5
            )
        else:
            lap = cv2.Laplacian(gray, cv2.CV_64F)
            abs_lap = np.uint8(np.absolute(lap))
            _, mask = cv2.threshold(abs_lap, self.edge_threshold, 255, cv2.THRESH_BINARY)
            overlay = frame.copy()
            overlay[mask > 0] = self.focus_color
            displayed = cv2.addWeighted(frame, 0.8, overlay, 0.5, 0)

        # Get selected focus metric function
        if ENHANCED_MODE and self.current_algorithm in self.algorithm_map:
            metric_func = self.algorithm_map[self.current_algorithm]
        else:
            metric_func = laplacian_focus_metric

        # Calculate focus score
        if self.regions:
            if ENHANCED_MODE:
                scores = compute_roi_scores(gray, self.regions, metric_func)
                for roi, score in zip(self.regions, scores):
                    roi["score"] = score
                global_score = compute_weighted_focus(gray, self.regions, metric_func)
            else:
                # Simple fallback
                total, weight_sum = 0.0, 0.0
                for r in self.regions:
                    x1, y1, x2, y2 = r["rect"]
                    roi = gray[y1:y2, x1:x2]
                    if roi.size > 0:
                        score = float(cv2.Laplacian(roi, cv2.CV_64F).var())
                        r["score"] = score
                        total += score * r["weight"]
                        weight_sum += r["weight"]
                global_score = total / weight_sum if weight_sum else 0.0
        else:
            if ENHANCED_MODE:
                global_score = metric_func(gray)
            else:
                global_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        self.focus_history.append(global_score)

        # Update focus quality indicator
        if ENHANCED_MODE and self.focus_quality and ENABLE_FOCUS_QUALITY_INDICATOR:
            self.focus_quality.update(global_score)
            quality_level, normalized_score = self.focus_quality.get_quality()
            quality_percentage = self.focus_quality.get_quality_percentage()

            # Update quality display
            quality_color = QUALITY_COLORS.get(quality_level, "#868e96")
            self.quality_status_label.setText(f"● {quality_level.title()}")
            self.quality_status_label.setStyleSheet(f"font-size: 10pt; font-weight: bold; color: {quality_color};")
            self.quality_score_label.setText(f"Score: {quality_percentage} / 100")

        # Update auto-scaling range
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

        # Draw ROI overlays
        for r in self.regions:
            x1, y1, x2, y2 = [int(v) for v in r["rect"]]
            color = ROI_COLOR_SELECTED if (self.selected_id and r["id"] == self.selected_id) else ROI_COLOR_NORMAL
            cv2.rectangle(displayed, (x1, y1), (x2, y2), color, 2)
            label = f"#{r['id']} W:{r['weight']:.1f} F:{r['score']:.0f}"
            cv2.putText(displayed, label, (x1 + 4, y1 + 18),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Draw global focus score
        cv2.putText(
            displayed,
            f"Focus: {global_score:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

        # Update video display
        rgb = cv2.cvtColor(displayed, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        self.video_label.setPixmap(QtGui.QPixmap.fromImage(qimg))

        # Update auto-scaled graph
        self._update_graph()

    def _update_graph(self):
        """Update focus trend graph with auto-scaling."""
        graph = np.zeros((GRAPH_HEIGHT, GRAPH_WIDTH, 3), dtype=np.uint8)

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

                # Clamp Y values to graph bounds
                pts[:, 1] = np.clip(pts[:, 1], 0, GRAPH_HEIGHT - 1)

                # Draw the line
                cv2.polylines(graph, [pts], False, (0, 255, 0), 1)

        # Draw border
        cv2.rectangle(graph, (0, 0), (GRAPH_WIDTH - 1, GRAPH_HEIGHT - 1), (100, 100, 100), 1)

        # Add scale markers
        cv2.putText(graph, f"{self.graph_max:.0f}", (5, 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        cv2.putText(graph, f"{self.graph_min:.0f}", (5, GRAPH_HEIGHT - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        # Update display
        qg = QtGui.QImage(
            graph.data,
            GRAPH_WIDTH,
            GRAPH_HEIGHT,
            GRAPH_WIDTH * 3,
            QtGui.QImage.Format_BGR888,
        )
        self.graph_label.setPixmap(QtGui.QPixmap.fromImage(qg))

        # Update range label
        self.graph_range_label.setText(f"Range: {self.graph_min:.0f} - {self.graph_max:.0f}")

    def closeEvent(self, event):
        """Cleanup on close."""
        if ENHANCED_MODE:
            self.camera_manager.disconnect()
        else:
            self.cap.release()
        event.accept()


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    # Apply theme if available
    if ENHANCED_MODE:
        theme_manager = setup_theme(app, DEFAULT_THEME)

    window = BosonFocusUtility()

    # Connect theme change if enhanced mode
    if ENHANCED_MODE:
        window.theme_combo.currentTextChanged.connect(theme_manager.apply_theme)

    window.show()

    sys.exit(app.exec_())
