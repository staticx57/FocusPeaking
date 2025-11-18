"""
Camera Calibration GUI - PyQt5 Interface

Provides a tabbed GUI for camera calibration workflows integrated into the main application.
"""

import cv2
import numpy as np
from typing import Optional, List, Tuple
from PyQt5 import QtWidgets, QtGui, QtCore
from pathlib import Path
import json

from CameraCals.calibration_tool import (
    CalibrationPatternDetector,
    CameraCalibrator,
    StereoCalibrator,
    CameraMerger,
    IntrinsicCalibration,
    StereoCalibration,
    CalibrationDataManager,
    undistort_image
)
from CameraCals.custom_camera_dialog import CustomCameraDialog

from logger_setup import get_logger


class CalibrationGUI(QtWidgets.QWidget):
    """Main calibration interface widget."""

    def __init__(self, camera_manager, parent=None):
        super().__init__(parent)
        self.camera_manager = camera_manager
        self.logger = get_logger(self.__class__.__name__)

        # Calibration state
        self.pattern_detector = CalibrationPatternDetector("chessboard", (9, 6))
        self.camera_calibrator = CameraCalibrator()
        self.stereo_calibrator = StereoCalibrator()

        # Calibration results
        self.camera1_calibration: Optional[IntrinsicCalibration] = None
        self.camera2_calibration: Optional[IntrinsicCalibration] = None
        self.stereo_calibration: Optional[StereoCalibration] = None
        self.camera_merger: Optional[CameraMerger] = None

        # Captured images for calibration
        self.captured_images = []
        self.captured_corners = []
        self.stereo_pairs = []  # List of (img1, corners1, img2, corners2) tuples
        self.landmark_pairs = []  # List of (pt1, pt2) tuples for manual correspondence

        # Current frame for display
        self.current_frame = None
        self.pattern_detected = False
        self.detected_corners = None

        # UI state
        self.calibration_mode = "single"  # "single" or "stereo"
        self.current_camera_index = 0  # For stereo mode

        # Custom camera specifications and flange distances
        self.custom_source_spec = None
        self.custom_source_flange_distance = None
        self.custom_target_spec = None
        self.custom_target_flange_distance = None

        self._create_ui()

    def _create_ui(self):
        """Create the calibration UI with tabs."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Camera detection panel
        self._create_camera_detection_panel(main_layout)

        # Create tabbed interface for calibration workflows
        self.cal_tabs = QtWidgets.QTabWidget()

        # Tab 1: Pattern Detection
        pattern_tab = self._create_pattern_tab()
        self.cal_tabs.addTab(pattern_tab, "Pattern Detection")

        # Tab 2: Single Camera Calibration
        single_cal_tab = self._create_single_calibration_tab()
        self.cal_tabs.addTab(single_cal_tab, "Single Camera")

        # Tab 3: Stereo Calibration
        stereo_cal_tab = self._create_stereo_calibration_tab()
        self.cal_tabs.addTab(stereo_cal_tab, "Stereo Calibration")

        # Tab 4: Camera Merge/Alignment
        merge_tab = self._create_merge_tab()
        self.cal_tabs.addTab(merge_tab, "Camera Merge")

        # Tab 5: Field Calibration (Natural Features)
        field_tab = self._create_field_calibration_tab()
        self.cal_tabs.addTab(field_tab, "Field Calibration")

        main_layout.addWidget(self.cal_tabs)

    def _create_camera_detection_panel(self, layout):
        """Create camera detection and status panel."""
        detection_group = QtWidgets.QGroupBox("Connected Cameras")
        detection_layout = QtWidgets.QVBoxLayout(detection_group)

        # Header with refresh button
        header_layout = QtWidgets.QHBoxLayout()

        refresh_btn = QtWidgets.QPushButton("🔄 Detect Cameras")
        refresh_btn.setToolTip("Scan for all connected cameras (Boson, Spinnaker, UVC)")
        refresh_btn.setStyleSheet("padding: 6px 12px; font-weight: bold; background-color: #0078d4; color: white;")
        refresh_btn.clicked.connect(self._detect_cameras)
        header_layout.addWidget(refresh_btn)

        header_layout.addStretch()
        detection_layout.addLayout(header_layout)

        # Camera list display
        self.camera_list_text = QtWidgets.QTextEdit()
        self.camera_list_text.setReadOnly(True)
        self.camera_list_text.setMaximumHeight(80)
        self.camera_list_text.setPlainText("Click 'Detect Cameras' to scan for connected cameras...")
        detection_layout.addWidget(self.camera_list_text)

        layout.addWidget(detection_group)

        # Auto-detect on startup
        QtCore.QTimer.singleShot(500, self._detect_cameras)

    def _detect_cameras(self):
        """Detect all connected cameras and update display."""
        try:
            from camera_manager import CameraManager

            self.camera_list_text.setPlainText("Scanning for cameras...")
            QtWidgets.QApplication.processEvents()  # Update UI immediately

            cameras = CameraManager.detect_cameras()

            if not cameras:
                self.camera_list_text.setPlainText("❌ No cameras detected\n\nTroubleshooting:\n- Check USB connections\n- Verify camera drivers installed\n- Try unplugging and reconnecting cameras")
                self.logger.warning("No cameras detected during calibration scan")
                return

            # Build camera list text with icons
            camera_text = f"✓ Found {len(cameras)} camera(s):\n\n"

            for i, cam in enumerate(cameras):
                # Determine camera type icon
                if cam.camera_type == "spinnaker":
                    icon = "🎥"
                    cam_type = "Spinnaker SDK"
                elif "Boson" in cam.name or "FLIR" in cam.name:
                    icon = "🌡️"
                    cam_type = "Thermal"
                else:
                    icon = "📹"
                    cam_type = "UVC Webcam"

                camera_text += f"{icon} {cam.name} ({cam_type})\n"
                camera_text += f"   Backend: {cam.backend}\n"

            self.camera_list_text.setPlainText(camera_text)
            self.logger.info(f"Detected {len(cameras)} cameras in calibration mode")

        except Exception as e:
            self.logger.error(f"Camera detection failed: {e}")
            self.camera_list_text.setPlainText(f"❌ Detection error: {str(e)}")

    def _create_pattern_tab(self) -> QtWidgets.QWidget:
        """Create pattern detection configuration tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Pattern configuration group
        pattern_group = QtWidgets.QGroupBox("Pattern Configuration")
        pattern_layout = QtWidgets.QVBoxLayout(pattern_group)

        # Pattern type selector
        type_layout = QtWidgets.QHBoxLayout()
        type_layout.addWidget(QtWidgets.QLabel("Pattern Type:"))
        self.pattern_type_combo = QtWidgets.QComboBox()
        self.pattern_type_combo.addItems(["Chessboard", "Circles Grid", "Asymmetric Circles"])
        self.pattern_type_combo.currentTextChanged.connect(self._on_pattern_type_changed)
        type_layout.addWidget(self.pattern_type_combo)
        pattern_layout.addLayout(type_layout)

        # Pattern size
        size_layout = QtWidgets.QHBoxLayout()
        size_layout.addWidget(QtWidgets.QLabel("Columns:"))
        self.pattern_cols_spin = QtWidgets.QSpinBox()
        self.pattern_cols_spin.setRange(3, 20)
        self.pattern_cols_spin.setValue(9)
        self.pattern_cols_spin.valueChanged.connect(self._on_pattern_size_changed)
        size_layout.addWidget(self.pattern_cols_spin)

        size_layout.addWidget(QtWidgets.QLabel("Rows:"))
        self.pattern_rows_spin = QtWidgets.QSpinBox()
        self.pattern_rows_spin.setRange(3, 20)
        self.pattern_rows_spin.setValue(6)
        self.pattern_rows_spin.valueChanged.connect(self._on_pattern_size_changed)
        size_layout.addWidget(self.pattern_rows_spin)
        pattern_layout.addLayout(size_layout)

        # Square size
        square_layout = QtWidgets.QHBoxLayout()
        square_layout.addWidget(QtWidgets.QLabel("Square Size (mm):"))
        self.square_size_spin = QtWidgets.QDoubleSpinBox()
        self.square_size_spin.setRange(0.1, 1000.0)
        self.square_size_spin.setValue(25.0)
        self.square_size_spin.setSuffix(" mm")
        self.square_size_spin.valueChanged.connect(self._on_square_size_changed)
        square_layout.addWidget(self.square_size_spin)
        pattern_layout.addLayout(square_layout)

        layout.addWidget(pattern_group)

        # Detection status
        status_group = QtWidgets.QGroupBox("Detection Status")
        status_layout = QtWidgets.QVBoxLayout(status_group)

        self.pattern_status_label = QtWidgets.QLabel("No pattern detected")
        self.pattern_status_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
        status_layout.addWidget(self.pattern_status_label)

        self.corners_count_label = QtWidgets.QLabel("Corners: 0")
        status_layout.addWidget(self.corners_count_label)

        layout.addWidget(status_group)

        layout.addStretch()
        return tab

    def _create_single_calibration_tab(self) -> QtWidgets.QWidget:
        """Create single camera calibration tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Capture controls
        capture_group = QtWidgets.QGroupBox("Image Capture")
        capture_layout = QtWidgets.QVBoxLayout(capture_group)

        # Capture button
        self.capture_btn = QtWidgets.QPushButton("Capture Image for Calibration")
        self.capture_btn.clicked.connect(self._capture_calibration_image)
        self.capture_btn.setStyleSheet("font-size: 12pt; padding: 10px;")
        capture_layout.addWidget(self.capture_btn)

        # Captured images count
        self.captured_count_label = QtWidgets.QLabel("Captured: 0 images (minimum 10 recommended)")
        self.captured_count_label.setStyleSheet("font-size: 9pt;")
        capture_layout.addWidget(self.captured_count_label)

        # Progress bar
        self.capture_progress = QtWidgets.QProgressBar()
        self.capture_progress.setRange(0, 10)
        self.capture_progress.setValue(0)
        capture_layout.addWidget(self.capture_progress)

        # Clear captures button
        self.clear_captures_btn = QtWidgets.QPushButton("Clear All Captures")
        self.clear_captures_btn.clicked.connect(self._clear_captures)
        capture_layout.addWidget(self.clear_captures_btn)

        layout.addWidget(capture_group)

        # Calibration controls
        calibrate_group = QtWidgets.QGroupBox("Calibration")
        calibrate_layout = QtWidgets.QVBoxLayout(calibrate_group)

        # Calibration options
        self.fix_aspect_cb = QtWidgets.QCheckBox("Fix Aspect Ratio (fx/fy)")
        self.fix_aspect_cb.setChecked(True)
        calibrate_layout.addWidget(self.fix_aspect_cb)

        self.zero_tangential_cb = QtWidgets.QCheckBox("Zero Tangential Distortion")
        calibrate_layout.addWidget(self.zero_tangential_cb)

        self.fix_principal_cb = QtWidgets.QCheckBox("Fix Principal Point")
        calibrate_layout.addWidget(self.fix_principal_cb)

        # Calibrate button
        self.calibrate_btn = QtWidgets.QPushButton("Run Calibration")
        self.calibrate_btn.clicked.connect(self._run_single_calibration)
        self.calibrate_btn.setStyleSheet("font-size: 12pt; padding: 10px; background-color: #0078d4; color: white;")
        self.calibrate_btn.setEnabled(False)
        calibrate_layout.addWidget(self.calibrate_btn)

        layout.addWidget(calibrate_group)

        # Results display
        results_group = QtWidgets.QGroupBox("Calibration Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)

        self.cal_results_text = QtWidgets.QTextEdit()
        self.cal_results_text.setReadOnly(True)
        self.cal_results_text.setMaximumHeight(200)
        self.cal_results_text.setPlainText("No calibration performed yet")
        results_layout.addWidget(self.cal_results_text)

        # Save/Load buttons
        save_load_layout = QtWidgets.QHBoxLayout()
        self.save_cal_btn = QtWidgets.QPushButton("Save Calibration")
        self.save_cal_btn.clicked.connect(self._save_calibration)
        self.save_cal_btn.setEnabled(False)
        save_load_layout.addWidget(self.save_cal_btn)

        self.load_cal_btn = QtWidgets.QPushButton("Load Calibration")
        self.load_cal_btn.clicked.connect(self._load_calibration)
        save_load_layout.addWidget(self.load_cal_btn)
        results_layout.addLayout(save_load_layout)

        layout.addWidget(results_group)

        layout.addStretch()
        return tab

    def _create_stereo_calibration_tab(self) -> QtWidgets.QWidget:
        """Create stereo calibration tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Camera selection
        camera_group = QtWidgets.QGroupBox("Stereo Pair Capture")
        camera_layout = QtWidgets.QVBoxLayout(camera_group)

        info_label = QtWidgets.QLabel(
            "Stereo calibration requires capturing synchronized image pairs from two cameras.\n"
            "Ensure both cameras can see the calibration pattern simultaneously."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-style: italic; color: palette(mid);")
        camera_layout.addWidget(info_label)

        # Camera index selectors
        cam_select_layout = QtWidgets.QHBoxLayout()
        cam_select_layout.addWidget(QtWidgets.QLabel("Camera 1:"))
        self.stereo_cam1_spin = QtWidgets.QSpinBox()
        self.stereo_cam1_spin.setRange(0, 10)
        self.stereo_cam1_spin.setValue(0)
        cam_select_layout.addWidget(self.stereo_cam1_spin)

        cam_select_layout.addWidget(QtWidgets.QLabel("Camera 2:"))
        self.stereo_cam2_spin = QtWidgets.QSpinBox()
        self.stereo_cam2_spin.setRange(0, 10)
        self.stereo_cam2_spin.setValue(1)
        cam_select_layout.addWidget(self.stereo_cam2_spin)
        camera_layout.addLayout(cam_select_layout)

        # Capture stereo pair button
        self.capture_stereo_btn = QtWidgets.QPushButton("Capture Stereo Pair")
        self.capture_stereo_btn.clicked.connect(self._capture_stereo_pair)
        self.capture_stereo_btn.setStyleSheet("font-size: 12pt; padding: 10px;")
        camera_layout.addWidget(self.capture_stereo_btn)

        # Stereo pairs count
        self.stereo_count_label = QtWidgets.QLabel("Captured: 0 stereo pairs (minimum 10 recommended)")
        camera_layout.addWidget(self.stereo_count_label)

        # Progress
        self.stereo_progress = QtWidgets.QProgressBar()
        self.stereo_progress.setRange(0, 10)
        self.stereo_progress.setValue(0)
        camera_layout.addWidget(self.stereo_progress)

        # Clear button
        self.clear_stereo_btn = QtWidgets.QPushButton("Clear All Stereo Pairs")
        self.clear_stereo_btn.clicked.connect(self._clear_stereo_pairs)
        camera_layout.addWidget(self.clear_stereo_btn)

        layout.addWidget(camera_group)

        # Stereo calibration controls
        stereo_cal_group = QtWidgets.QGroupBox("Stereo Calibration")
        stereo_cal_layout = QtWidgets.QVBoxLayout(stereo_cal_group)

        # Option to use pre-calibrated intrinsics
        self.use_precal_cb = QtWidgets.QCheckBox("Use Pre-calibrated Camera Intrinsics")
        self.use_precal_cb.setToolTip("Use previously saved individual camera calibrations")
        stereo_cal_layout.addWidget(self.use_precal_cb)

        # Run stereo calibration button
        self.run_stereo_cal_btn = QtWidgets.QPushButton("Run Stereo Calibration")
        self.run_stereo_cal_btn.clicked.connect(self._run_stereo_calibration)
        self.run_stereo_cal_btn.setStyleSheet("font-size: 12pt; padding: 10px; background-color: #0078d4; color: white;")
        self.run_stereo_cal_btn.setEnabled(False)
        stereo_cal_layout.addWidget(self.run_stereo_cal_btn)

        layout.addWidget(stereo_cal_group)

        # Stereo results
        stereo_results_group = QtWidgets.QGroupBox("Stereo Calibration Results")
        stereo_results_layout = QtWidgets.QVBoxLayout(stereo_results_group)

        self.stereo_results_text = QtWidgets.QTextEdit()
        self.stereo_results_text.setReadOnly(True)
        self.stereo_results_text.setMaximumHeight(200)
        self.stereo_results_text.setPlainText("No stereo calibration performed yet")
        stereo_results_layout.addWidget(self.stereo_results_text)

        # Save/Load
        stereo_save_layout = QtWidgets.QHBoxLayout()
        self.save_stereo_btn = QtWidgets.QPushButton("Save Stereo Calibration")
        self.save_stereo_btn.clicked.connect(self._save_stereo_calibration)
        self.save_stereo_btn.setEnabled(False)
        stereo_save_layout.addWidget(self.save_stereo_btn)

        self.load_stereo_btn = QtWidgets.QPushButton("Load Stereo Calibration")
        self.load_stereo_btn.clicked.connect(self._load_stereo_calibration)
        stereo_save_layout.addWidget(self.load_stereo_btn)
        stereo_results_layout.addLayout(stereo_save_layout)

        layout.addWidget(stereo_results_group)

        layout.addStretch()
        return tab

    def _create_merge_tab(self) -> QtWidgets.QWidget:
        """Create camera merge/alignment tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Info
        info_group = QtWidgets.QGroupBox("Camera Merge and Alignment")
        info_layout = QtWidgets.QVBoxLayout(info_group)

        info_text = QtWidgets.QLabel(
            "This tool analyzes stereo calibration data to compute optical alignment parameters,\n"
            "field-of-view matching, and camera merge transformations.\n\n"
            "Requires: Completed stereo calibration"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        # FOV alignment analysis
        fov_group = QtWidgets.QGroupBox("Field of View Alignment")
        fov_layout = QtWidgets.QVBoxLayout(fov_group)

        self.fov_results_text = QtWidgets.QTextEdit()
        self.fov_results_text.setReadOnly(True)
        self.fov_results_text.setMaximumHeight(250)
        self.fov_results_text.setPlainText("Load or compute stereo calibration first")
        fov_layout.addWidget(self.fov_results_text)

        # Compute FOV alignment button
        self.compute_fov_btn = QtWidgets.QPushButton("Compute FOV Alignment")
        self.compute_fov_btn.clicked.connect(self._compute_fov_alignment)
        self.compute_fov_btn.setEnabled(False)
        fov_layout.addWidget(self.compute_fov_btn)

        layout.addWidget(fov_group)

        # Rectification and overlay
        rect_group = QtWidgets.QGroupBox("Image Rectification and Overlay")
        rect_layout = QtWidgets.QVBoxLayout(rect_group)

        rect_info = QtWidgets.QLabel(
            "Rectification aligns stereo images to have parallel optical axes.\n"
            "Overlay visualization helps verify camera alignment quality."
        )
        rect_info.setWordWrap(True)
        rect_info.setStyleSheet("font-style: italic; color: palette(mid);")
        rect_layout.addWidget(rect_info)

        # Overlay alpha slider
        alpha_layout = QtWidgets.QHBoxLayout()
        alpha_layout.addWidget(QtWidgets.QLabel("Overlay Blend:"))
        self.overlay_alpha_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.overlay_alpha_slider.setRange(0, 100)
        self.overlay_alpha_slider.setValue(50)
        alpha_layout.addWidget(self.overlay_alpha_slider)
        self.overlay_alpha_label = QtWidgets.QLabel("50%")
        alpha_layout.addWidget(self.overlay_alpha_label)
        self.overlay_alpha_slider.valueChanged.connect(
            lambda v: self.overlay_alpha_label.setText(f"{v}%")
        )
        rect_layout.addLayout(alpha_layout)

        # Enable rectification checkbox (for live view)
        self.enable_rectification_cb = QtWidgets.QCheckBox("Enable Live Rectification")
        self.enable_rectification_cb.setToolTip("Apply rectification to live camera feeds")
        rect_layout.addWidget(self.enable_rectification_cb)

        layout.addWidget(rect_group)

        # Export alignment data
        export_group = QtWidgets.QGroupBox("Export Alignment Data")
        export_layout = QtWidgets.QVBoxLayout(export_group)

        self.export_alignment_btn = QtWidgets.QPushButton("Export Alignment Report (JSON)")
        self.export_alignment_btn.clicked.connect(self._export_alignment_report)
        self.export_alignment_btn.setEnabled(False)
        export_layout.addWidget(self.export_alignment_btn)

        layout.addWidget(export_group)

        layout.addStretch()
        return tab

    def _create_field_calibration_tab(self) -> QtWidgets.QWidget:
        """Create field calibration tab for natural feature-based alignment."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Info
        info_group = QtWidgets.QGroupBox("Field Calibration - Natural Feature Alignment")
        info_layout = QtWidgets.QVBoxLayout(info_group)

        info_text = QtWidgets.QLabel(
            "Field calibration uses natural features and landmarks for camera alignment\n"
            "without requiring calibration patterns. Ideal for outdoor/field scenarios.\n\n"
            "Methods: Natural feature matching (SIFT/ORB/AKAZE), Manual landmarks"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        # Camera specifications
        spec_group = QtWidgets.QGroupBox("Camera Specifications")
        spec_layout = QtWidgets.QVBoxLayout(spec_group)

        # Source camera selection
        source_layout = QtWidgets.QHBoxLayout()
        source_layout.addWidget(QtWidgets.QLabel("Source Camera (Reference):"))
        self.field_source_combo = QtWidgets.QComboBox()
        self.field_source_combo.addItems([
            "FLIR Boson 320",
            "FLIR Boson 640",
            "FLIR Firefly",
            "UVC Webcam 1080p",
            "UVC Webcam 720p",
            "Logitech C920",
            "Generic C-Mount",
            "Custom..."
        ])
        self.field_source_combo.currentTextChanged.connect(self._on_field_source_changed)
        source_layout.addWidget(self.field_source_combo)
        spec_layout.addLayout(source_layout)

        # Source focal length
        source_focal_layout = QtWidgets.QHBoxLayout()
        source_focal_layout.addWidget(QtWidgets.QLabel("Source Focal Length (mm):"))
        self.field_source_focal_spin = QtWidgets.QDoubleSpinBox()
        self.field_source_focal_spin.setRange(1.0, 500.0)
        self.field_source_focal_spin.setValue(4.3)
        self.field_source_focal_spin.setSingleStep(0.1)
        self.field_source_focal_spin.valueChanged.connect(self._on_focal_length_changed)
        source_focal_layout.addWidget(self.field_source_focal_spin)
        spec_layout.addLayout(source_focal_layout)

        # Target camera selection
        target_layout = QtWidgets.QHBoxLayout()
        target_layout.addWidget(QtWidgets.QLabel("Target Camera (Align):"))
        self.field_target_combo = QtWidgets.QComboBox()
        self.field_target_combo.addItems([
            "FLIR Boson 320",
            "FLIR Boson 640",
            "FLIR Firefly",
            "UVC Webcam 1080p",
            "UVC Webcam 720p",
            "Logitech C920",
            "Generic C-Mount",
            "Custom..."
        ])
        self.field_target_combo.setCurrentIndex(2)  # Default to Firefly
        self.field_target_combo.currentTextChanged.connect(self._on_field_target_changed)
        target_layout.addWidget(self.field_target_combo)
        spec_layout.addLayout(target_layout)

        # Target focal length
        target_focal_layout = QtWidgets.QHBoxLayout()
        target_focal_layout.addWidget(QtWidgets.QLabel("Target Focal Length (mm):"))
        self.field_target_focal_spin = QtWidgets.QDoubleSpinBox()
        self.field_target_focal_spin.setRange(1.0, 500.0)
        self.field_target_focal_spin.setValue(16.0)
        self.field_target_focal_spin.setSingleStep(0.1)
        self.field_target_focal_spin.valueChanged.connect(self._on_focal_length_changed)
        target_focal_layout.addWidget(self.field_target_focal_spin)
        spec_layout.addLayout(target_focal_layout)

        layout.addWidget(spec_group)

        # FOV Analysis
        fov_group = QtWidgets.QGroupBox("Field of View Analysis")
        fov_layout = QtWidgets.QVBoxLayout(fov_group)

        self.fov_analysis_text = QtWidgets.QTextEdit()
        self.fov_analysis_text.setReadOnly(True)
        self.fov_analysis_text.setMaximumHeight(150)
        self.fov_analysis_text.setPlainText("Select cameras and focal lengths to see FOV analysis")
        fov_layout.addWidget(self.fov_analysis_text)

        # Recommend focal length button
        recommend_layout = QtWidgets.QHBoxLayout()
        self.recommend_focal_btn = QtWidgets.QPushButton("Recommend Target Focal Length for FOV Match")
        self.recommend_focal_btn.clicked.connect(self._recommend_focal_length)
        self.recommend_focal_btn.setStyleSheet("padding: 8px; background-color: #0078d4; color: white;")
        recommend_layout.addWidget(self.recommend_focal_btn)
        fov_layout.addLayout(recommend_layout)

        layout.addWidget(fov_group)

        # Natural feature matching
        feature_group = QtWidgets.QGroupBox("Natural Feature Matching")
        feature_layout = QtWidgets.QVBoxLayout(feature_group)

        # Feature detector selection
        detector_layout = QtWidgets.QHBoxLayout()
        detector_layout.addWidget(QtWidgets.QLabel("Detector:"))
        self.feature_detector_combo = QtWidgets.QComboBox()
        self.feature_detector_combo.addItems(["AKAZE", "SIFT", "ORB", "BRISK"])
        detector_layout.addWidget(self.feature_detector_combo)
        feature_layout.addLayout(detector_layout)

        # Match features button
        self.match_features_btn = QtWidgets.QPushButton("Match Features Between Cameras")
        self.match_features_btn.clicked.connect(self._match_natural_features)
        self.match_features_btn.setStyleSheet("padding: 8px; font-size: 11pt;")
        feature_layout.addWidget(self.match_features_btn)

        # Match results
        self.match_results_label = QtWidgets.QLabel("No matching performed yet")
        self.match_results_label.setStyleSheet("padding: 8px; background-color: palette(dark);")
        feature_layout.addWidget(self.match_results_label)

        layout.addWidget(feature_group)

        # Manual landmarks
        landmark_group = QtWidgets.QGroupBox("Manual Landmark Alignment")
        landmark_layout = QtWidgets.QVBoxLayout(landmark_group)

        landmark_info = QtWidgets.QLabel(
            "Click corresponding points in both camera views to manually align.\n"
            "Minimum 4 points required for perspective alignment."
        )
        landmark_info.setWordWrap(True)
        landmark_info.setStyleSheet("font-style: italic; color: palette(mid);")
        landmark_layout.addWidget(landmark_info)

        # Landmark controls
        landmark_btn_layout = QtWidgets.QHBoxLayout()
        self.add_landmark_btn = QtWidgets.QPushButton("Add Landmark Pair")
        self.add_landmark_btn.clicked.connect(self._add_landmark_pair)
        landmark_btn_layout.addWidget(self.add_landmark_btn)

        self.clear_landmarks_btn = QtWidgets.QPushButton("Clear All")
        self.clear_landmarks_btn.clicked.connect(self._clear_landmarks)
        landmark_btn_layout.addWidget(self.clear_landmarks_btn)
        landmark_layout.addLayout(landmark_btn_layout)

        # Landmark count
        self.landmark_count_label = QtWidgets.QLabel("Landmarks: 0 pairs")
        landmark_layout.addWidget(self.landmark_count_label)

        layout.addWidget(landmark_group)

        layout.addStretch()
        return tab

    # ========================================================================
    # Event Handlers - Pattern Detection
    # ========================================================================

    def _on_pattern_type_changed(self, pattern_type: str):
        """Handle pattern type change."""
        type_map = {
            "Chessboard": "chessboard",
            "Circles Grid": "circles",
            "Asymmetric Circles": "asymmetric_circles"
        }
        self.pattern_detector.pattern_type = type_map[pattern_type]
        self.logger.info(f"Pattern type changed to: {pattern_type}")

    def _on_pattern_size_changed(self):
        """Handle pattern size change."""
        cols = self.pattern_cols_spin.value()
        rows = self.pattern_rows_spin.value()
        self.pattern_detector.pattern_size = (cols, rows)
        self.logger.info(f"Pattern size changed to: {cols}x{rows}")

    def _on_square_size_changed(self, size: float):
        """Handle square size change."""
        self.pattern_detector.square_size = size
        self.logger.info(f"Square size changed to: {size} mm")

    # ========================================================================
    # Event Handlers - Single Camera Calibration
    # ========================================================================

    def _capture_calibration_image(self):
        """Capture current frame for calibration."""
        if self.current_frame is None:
            QtWidgets.QMessageBox.warning(self, "Error", "No camera frame available")
            return

        if not self.pattern_detected or self.detected_corners is None:
            QtWidgets.QMessageBox.warning(
                self, "Error",
                "No calibration pattern detected in current frame.\n"
                "Please position the calibration pattern clearly in view."
            )
            return

        # Store the image and corners
        self.captured_images.append(self.current_frame.copy())
        self.captured_corners.append(self.detected_corners.copy())

        # Update UI
        count = len(self.captured_images)
        self.captured_count_label.setText(f"Captured: {count} images (minimum 10 recommended)")
        self.capture_progress.setValue(min(count, 10))

        # Enable calibration button if we have enough images
        self.calibrate_btn.setEnabled(count >= 3)

        self.logger.info(f"Captured calibration image {count}")
        QtWidgets.QMessageBox.information(
            self, "Success",
            f"Image {count} captured successfully!"
        )

    def _clear_captures(self):
        """Clear all captured calibration images."""
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Clear",
            "Are you sure you want to clear all captured images?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.captured_images = []
            self.captured_corners = []
            self.camera_calibrator.reset()
            self.captured_count_label.setText("Captured: 0 images (minimum 10 recommended)")
            self.capture_progress.setValue(0)
            self.calibrate_btn.setEnabled(False)
            self.logger.info("Cleared all captured images")

    def _run_single_calibration(self):
        """Run camera calibration with captured images."""
        try:
            # Add all captured images to calibrator
            self.camera_calibrator.reset()
            objp = self.pattern_detector.get_object_points()

            for corners, img in zip(self.captured_corners, self.captured_images):
                h, w = img.shape[:2]
                self.camera_calibrator.add_calibration_image(corners, objp, (w, h))

            # Run calibration
            self.camera1_calibration = self.camera_calibrator.calibrate(
                fix_aspect_ratio=self.fix_aspect_cb.isChecked(),
                zero_tangential_dist=self.zero_tangential_cb.isChecked(),
                fix_principal_point=self.fix_principal_cb.isChecked()
            )

            # Display results
            self._display_calibration_results(self.camera1_calibration)

            # Enable save button
            self.save_cal_btn.setEnabled(True)

            QtWidgets.QMessageBox.information(
                self, "Success",
                f"Calibration completed!\nReprojection Error: {self.camera1_calibration.reprojection_error:.3f}"
            )

        except Exception as e:
            self.logger.error(f"Calibration failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Calibration failed:\n{str(e)}")

    def _display_calibration_results(self, cal: IntrinsicCalibration):
        """Display calibration results in text box."""
        K = cal.camera_matrix
        D = cal.dist_coeffs

        results_text = f"""Camera Calibration Results
{'=' * 50}

Image Size: {cal.image_size[0]} x {cal.image_size[1]}
Number of Images: {cal.num_images}
Reprojection Error: {cal.reprojection_error:.4f} pixels
Calibration Date: {cal.calibration_date}

Camera Matrix (K):
  fx = {K[0,0]:.2f}    0        cx = {K[0,2]:.2f}
  0        fy = {K[1,1]:.2f}    cy = {K[1,2]:.2f}
  0        0        1

Distortion Coefficients:
  k1 = {D[0,0]:.6f}
  k2 = {D[0,1]:.6f}
  p1 = {D[0,2]:.6f}
  p2 = {D[0,3]:.6f}
  k3 = {D[0,4]:.6f}

Focal Length: fx={K[0,0]:.2f}, fy={K[1,1]:.2f}
Principal Point: ({K[0,2]:.2f}, {K[1,2]:.2f})
Aspect Ratio: {K[0,0]/K[1,1]:.4f}

Field of View:
  Horizontal: {2 * np.arctan(cal.image_size[0] / (2 * K[0,0])) * 180 / np.pi:.2f}°
  Vertical: {2 * np.arctan(cal.image_size[1] / (2 * K[1,1])) * 180 / np.pi:.2f}°
"""

        self.cal_results_text.setPlainText(results_text)

    def _save_calibration(self):
        """Save calibration to file."""
        if self.camera1_calibration is None:
            QtWidgets.QMessageBox.warning(self, "Error", "No calibration to save")
            return

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Calibration",
            "camera_calibration.json",
            "JSON Files (*.json)"
        )

        if filename:
            try:
                CalibrationDataManager.save_intrinsic(
                    self.camera1_calibration,
                    Path(filename)
                )
                QtWidgets.QMessageBox.information(
                    self, "Success",
                    f"Calibration saved to {filename}"
                )
                self.logger.info(f"Calibration saved to {filename}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def _load_calibration(self):
        """Load calibration from file."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Calibration",
            "",
            "JSON Files (*.json)"
        )

        if filename:
            try:
                self.camera1_calibration = CalibrationDataManager.load_intrinsic(Path(filename))
                self._display_calibration_results(self.camera1_calibration)
                self.save_cal_btn.setEnabled(True)
                QtWidgets.QMessageBox.information(self, "Success", "Calibration loaded successfully")
                self.logger.info(f"Calibration loaded from {filename}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")

    # ========================================================================
    # Event Handlers - Stereo Calibration
    # ========================================================================

    def _capture_stereo_pair(self):
        """Capture synchronized stereo pair."""
        # Check if we have current frame (from primary camera)
        if self.current_frame is None:
            QtWidgets.QMessageBox.warning(
                self, "Error",
                "No camera frame available.\nPlease ensure camera is connected."
            )
            return

        # Check if pattern is detected in current frame
        if not self.pattern_detected or self.detected_corners is None:
            QtWidgets.QMessageBox.warning(
                self, "Pattern Not Detected",
                "Calibration pattern must be visible in BOTH cameras.\n\n"
                "Current frame (Camera 1): Pattern NOT detected\n\n"
                "Please position the calibration pattern so it's clearly visible\n"
                "in both camera views before capturing."
            )
            return

        # Detect available cameras
        from camera_manager import CameraManager
        available_cameras = CameraManager.detect_cameras()

        if len(available_cameras) < 2:
            QtWidgets.QMessageBox.warning(
                self, "Insufficient Cameras",
                f"Stereo calibration requires 2 cameras.\n"
                f"Currently detected: {len(available_cameras)} camera(s)\n\n"
                "Please connect a second camera and click 'Detect Cameras' to refresh."
            )
            return

        # Show dialog to select second camera
        camera_names = [str(cam) for cam in available_cameras]
        camera2_name, ok = QtWidgets.QInputDialog.getItem(
            self, "Select Second Camera",
            "Choose the second camera for stereo pair:",
            camera_names,
            0,
            False
        )

        if not ok:
            return

        # Get selected camera index
        camera2_index = camera_names.index(camera2_name)
        camera2_device = available_cameras[camera2_index]

        # Temporarily connect to second camera and capture
        temp_camera_manager = CameraManager()
        if not temp_camera_manager.connect(device=camera2_device):
            QtWidgets.QMessageBox.critical(
                self, "Connection Failed",
                f"Failed to connect to {camera2_device.name}\n\n"
                "The camera may be in use by another application."
            )
            return

        # Capture frame from second camera
        ret, frame2 = temp_camera_manager.read_frame()
        temp_camera_manager.disconnect()

        if not ret or frame2 is None:
            QtWidgets.QMessageBox.critical(
                self, "Capture Failed",
                "Failed to capture frame from second camera."
            )
            return

        # Detect pattern in second camera frame
        success2, corners2 = self.pattern_detector.detect(frame2)

        if not success2 or corners2 is None:
            QtWidgets.QMessageBox.warning(
                self, "Pattern Not Detected in Camera 2",
                "Calibration pattern detected in Camera 1, but NOT in Camera 2.\n\n"
                "Both cameras must see the pattern clearly.\n\n"
                "Tips:\n"
                "- Ensure pattern is in view of both cameras\n"
                "- Check lighting conditions\n"
                "- Make sure pattern is flat and not distorted"
            )
            return

        # Check if patterns have same number of corners (sanity check)
        if len(self.detected_corners) != len(corners2):
            QtWidgets.QMessageBox.warning(
                self, "Pattern Mismatch",
                f"Pattern detection mismatch:\n"
                f"Camera 1: {len(self.detected_corners)} corners\n"
                f"Camera 2: {len(corners2)} corners\n\n"
                "Both cameras must detect the same pattern."
            )
            return

        # Estimate alignment quality (basic check)
        # Compare corner positions to detect if cameras are grossly misaligned
        import numpy as np
        corners1_mean = np.mean(self.detected_corners, axis=0)
        corners2_mean = np.mean(corners2, axis=0)
        corner_offset = np.linalg.norm(corners1_mean - corners2_mean)

        # Frame diagonal for reference
        frame_diag = np.sqrt(self.current_frame.shape[0]**2 + self.current_frame.shape[1]**2)
        offset_ratio = corner_offset / frame_diag

        alignment_status = "Good"
        if offset_ratio > 0.5:
            alignment_status = "Poor - cameras may be very misaligned"
        elif offset_ratio > 0.3:
            alignment_status = "Fair - significant offset detected"

        # Store the stereo pair
        self.stereo_pairs.append((
            self.current_frame.copy(),
            self.detected_corners.copy(),
            frame2.copy(),
            corners2.copy()
        ))

        # Update UI
        count = len(self.stereo_pairs)
        self.stereo_count_label.setText(f"Captured: {count} stereo pairs (minimum 10 recommended)")
        self.stereo_progress.setValue(min(100, (count * 100) // 10))

        if count >= 10:
            self.run_stereo_cal_btn.setEnabled(True)

        # Show success message with alignment info
        QtWidgets.QMessageBox.information(
            self, "Stereo Pair Captured",
            f"Successfully captured stereo pair #{count}\n\n"
            f"Alignment Status: {alignment_status}\n"
            f"Pattern Offset: {corner_offset:.1f} pixels ({offset_ratio*100:.1f}% of frame)\n\n"
            f"{'Ready to calibrate!' if count >= 10 else f'Capture {10-count} more pairs for calibration'}"
        )

        self.logger.info(f"Captured stereo pair {count}, alignment status: {alignment_status}")

    def _clear_stereo_pairs(self):
        """Clear all captured stereo pairs."""
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Clear",
            "Are you sure you want to clear all stereo pairs?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.stereo_pairs = []
            self.stereo_calibrator.reset()
            self.stereo_count_label.setText("Captured: 0 stereo pairs (minimum 10 recommended)")
            self.stereo_progress.setValue(0)
            self.run_stereo_cal_btn.setEnabled(False)

    def _run_stereo_calibration(self):
        """Run stereo calibration."""
        if len(self.stereo_pairs) < 10:
            QtWidgets.QMessageBox.warning(
                self, "Insufficient Data",
                f"Need at least 10 stereo pairs for calibration.\n"
                f"Currently have: {len(self.stereo_pairs)} pairs\n\n"
                "Capture more stereo pairs before running calibration."
            )
            return

        # Confirm calibration
        reply = QtWidgets.QMessageBox.question(
            self, "Run Stereo Calibration",
            f"Run stereo calibration with {len(self.stereo_pairs)} pairs?\n\n"
            "This may take a moment...",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            # Extract images and corners from stereo pairs
            images1 = [pair[0] for pair in self.stereo_pairs]
            corners1_list = [pair[1] for pair in self.stereo_pairs]
            images2 = [pair[2] for pair in self.stereo_pairs]
            corners2_list = [pair[3] for pair in self.stereo_pairs]

            # Add pairs to stereo calibrator
            for img1, corners1, img2, corners2 in zip(images1, corners1_list, images2, corners2_list):
                self.stereo_calibrator.add_stereo_pair(
                    img1, corners1,
                    img2, corners2,
                    self.pattern_detector.object_points
                )

            # Run calibration
            self.logger.info(f"Starting stereo calibration with {len(self.stereo_pairs)} pairs...")
            self.stereo_calibration = self.stereo_calibrator.calibrate_stereo(
                image_size=(images1[0].shape[1], images1[0].shape[0])
            )

            # Create camera merger
            self.camera_merger = CameraMerger(self.stereo_calibration)

            # Enable export buttons
            self.save_stereo_btn.setEnabled(True)
            self.compute_fov_btn.setEnabled(True)
            self.export_alignment_btn.setEnabled(True)

            # Show results
            result_text = f"""Stereo Calibration Complete!
{'=' * 50}

Reprojection Error: {self.stereo_calibration.reprojection_error:.3f} pixels

Camera 1:
  RMS Error: {self.stereo_calibration.camera1.reprojection_error:.3f} pixels

Camera 2:
  RMS Error: {self.stereo_calibration.camera2.reprojection_error:.3f} pixels

Baseline Distance: {self.stereo_calibration.baseline_distance:.2f} units

Quality Assessment:
{self._assess_calibration_quality(self.stereo_calibration.reprojection_error)}

You can now:
- Compute FOV alignment
- Export calibration data
- Use for camera merging
"""

            QtWidgets.QMessageBox.information(
                self, "Calibration Success", result_text
            )

            self.logger.info(f"Stereo calibration completed with RMS error: {self.stereo_calibration.reprojection_error:.3f}")

        except Exception as e:
            self.logger.error(f"Stereo calibration failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self, "Calibration Failed",
                f"Stereo calibration failed:\n\n{str(e)}\n\n"
                "Tips:\n"
                "- Ensure pattern was visible in both cameras\n"
                "- Check that cameras were stable during capture\n"
                "- Try recapturing with better lighting\n"
                "- Ensure pattern is flat and not distorted"
            )

    def _assess_calibration_quality(self, rms_error: float) -> str:
        """Assess calibration quality based on RMS error."""
        if rms_error < 0.3:
            return "✓ Excellent (RMS < 0.3)"
        elif rms_error < 0.5:
            return "✓ Good (RMS < 0.5)"
        elif rms_error < 1.0:
            return "⚠ Fair (RMS < 1.0) - Consider recapturing"
        else:
            return "✗ Poor (RMS ≥ 1.0) - Recapture recommended"

    def _save_stereo_calibration(self):
        """Save stereo calibration."""
        if self.stereo_calibration is None:
            QtWidgets.QMessageBox.warning(self, "Error", "No stereo calibration to save")
            return

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Stereo Calibration",
            "stereo_calibration.json",
            "JSON Files (*.json)"
        )

        if filename:
            try:
                CalibrationDataManager.save_stereo(self.stereo_calibration, Path(filename))
                QtWidgets.QMessageBox.information(self, "Success", f"Stereo calibration saved")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def _load_stereo_calibration(self):
        """Load stereo calibration."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Stereo Calibration",
            "",
            "JSON Files (*.json)"
        )

        if filename:
            try:
                self.stereo_calibration = CalibrationDataManager.load_stereo(Path(filename))
                self.camera_merger = CameraMerger(self.stereo_calibration)
                self.save_stereo_btn.setEnabled(True)
                self.compute_fov_btn.setEnabled(True)
                self.export_alignment_btn.setEnabled(True)
                QtWidgets.QMessageBox.information(self, "Success", "Stereo calibration loaded")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")

    # ========================================================================
    # Event Handlers - Camera Merge
    # ========================================================================

    def _compute_fov_alignment(self):
        """Compute and display FOV alignment parameters."""
        if self.camera_merger is None:
            QtWidgets.QMessageBox.warning(self, "Error", "Load stereo calibration first")
            return

        try:
            alignment = self.camera_merger.compute_fov_alignment()

            results_text = f"""Camera FOV and Alignment Analysis
{'=' * 60}

Camera 1 Field of View:
  Horizontal: {alignment['camera1_fov']['horizontal']:.2f}°
  Vertical: {alignment['camera1_fov']['vertical']:.2f}°

Camera 2 Field of View:
  Horizontal: {alignment['camera2_fov']['horizontal']:.2f}°
  Vertical: {alignment['camera2_fov']['vertical']:.2f}°

Relative Rotation (Camera 2 w.r.t. Camera 1):
  Roll:  {alignment['relative_rotation']['roll_deg']:.2f}°
  Pitch: {alignment['relative_rotation']['pitch_deg']:.2f}°
  Yaw:   {alignment['relative_rotation']['yaw_deg']:.2f}°

Baseline Distance: {alignment['baseline_distance']:.2f} units

Translation Vector (Camera 2 w.r.t. Camera 1):
  X: {alignment['translation_vector'][0]:.4f}
  Y: {alignment['translation_vector'][1]:.4f}
  Z: {alignment['translation_vector'][2]:.4f}

Alignment Quality:
  FOV Difference (H): {abs(alignment['camera1_fov']['horizontal'] - alignment['camera2_fov']['horizontal']):.2f}°
  FOV Difference (V): {abs(alignment['camera1_fov']['vertical'] - alignment['camera2_fov']['vertical']):.2f}°
"""

            self.fov_results_text.setPlainText(results_text)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to compute alignment:\n{str(e)}")

    def _export_alignment_report(self):
        """Export alignment report to JSON."""
        if self.camera_merger is None:
            QtWidgets.QMessageBox.warning(self, "Error", "No alignment data to export")
            return

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Alignment Report",
            "camera_alignment.json",
            "JSON Files (*.json)"
        )

        if filename:
            try:
                alignment = self.camera_merger.compute_fov_alignment()
                with open(filename, 'w') as f:
                    json.dump(alignment, f, indent=2)
                QtWidgets.QMessageBox.information(self, "Success", "Alignment report exported")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to export:\n{str(e)}")

    # ========================================================================
    # Event Handlers - Field Calibration
    # ========================================================================

    def _on_field_source_changed(self, camera_name: str):
        """Handle source camera selection change."""
        if camera_name == "Custom...":
            # Open custom camera spec dialog
            result = CustomCameraDialog.get_custom_camera(
                parent=self,
                initial_spec=self.custom_source_spec
            )

            if result:
                self.custom_source_spec = result['spec']
                self.custom_source_flange_distance = result['flange_distance_mm']
                self.field_source_focal_spin.setValue(self.custom_source_spec.focal_length_mm)
                self.logger.info(f"Custom source camera configured: {self.custom_source_spec.name}")
            else:
                # User cancelled - revert to previous selection
                # Default to FLIR Boson 320 (index 0)
                self.field_source_combo.setCurrentIndex(0)
                return
        else:
            # Update UI with known specs
            from CameraCals.field_calibration import CAMERA_SPECS_DB
            self.custom_source_spec = None  # Clear custom spec
            if camera_name in CAMERA_SPECS_DB:
                spec = CAMERA_SPECS_DB[camera_name]
                if spec.focal_length_mm:
                    self.field_source_focal_spin.setValue(spec.focal_length_mm)

        self._update_fov_analysis()

    def _on_field_target_changed(self, camera_name: str):
        """Handle target camera selection change."""
        if camera_name == "Custom...":
            # Open custom camera spec dialog
            result = CustomCameraDialog.get_custom_camera(
                parent=self,
                initial_spec=self.custom_target_spec
            )

            if result:
                self.custom_target_spec = result['spec']
                self.custom_target_flange_distance = result['flange_distance_mm']
                self.field_target_focal_spin.setValue(self.custom_target_spec.focal_length_mm)
                self.logger.info(f"Custom target camera configured: {self.custom_target_spec.name}")
            else:
                # User cancelled - revert to previous selection
                # Default to FLIR Firefly (index 2)
                self.field_target_combo.setCurrentIndex(2)
                return
        else:
            # Update UI with known specs
            from CameraCals.field_calibration import CAMERA_SPECS_DB
            self.custom_target_spec = None  # Clear custom spec
            if camera_name in CAMERA_SPECS_DB:
                spec = CAMERA_SPECS_DB[camera_name]
                if spec.focal_length_mm:
                    self.field_target_focal_spin.setValue(spec.focal_length_mm)

        self._update_fov_analysis()

    def _on_focal_length_changed(self):
        """Handle focal length change for either camera."""
        self._update_fov_analysis()

    def _update_fov_analysis(self):
        """Update FOV analysis display."""
        try:
            from CameraCals.field_calibration import CAMERA_SPECS_DB

            source_name = self.field_source_combo.currentText()
            target_name = self.field_target_combo.currentText()

            # Get source spec (custom or predefined)
            if source_name == "Custom..." and self.custom_source_spec:
                source_spec = self.custom_source_spec
            elif source_name in CAMERA_SPECS_DB:
                source_spec = CAMERA_SPECS_DB[source_name]
            else:
                self.fov_analysis_text.setPlainText("Please select or configure source camera")
                return

            # Get target spec (custom or predefined)
            if target_name == "Custom..." and self.custom_target_spec:
                target_spec = self.custom_target_spec
            elif target_name in CAMERA_SPECS_DB:
                target_spec = CAMERA_SPECS_DB[target_name]
            else:
                self.fov_analysis_text.setPlainText("Please select or configure target camera")
                return

            source_focal = self.field_source_focal_spin.value()
            target_focal = self.field_target_focal_spin.value()

            # Calculate FOVs
            src_fov_h, src_fov_v = source_spec.calculate_fov(source_focal)
            tgt_fov_h, tgt_fov_v = target_spec.calculate_fov(target_focal)

            analysis_text = f"""Field of View Analysis
{'=' * 50}

Source Camera: {source_spec.name}
  Sensor: {source_spec.sensor_width_mm:.2f}mm × {source_spec.sensor_height_mm:.2f}mm
  Resolution: {source_spec.image_width_px} × {source_spec.image_height_px}
  Focal Length: {source_focal:.2f}mm
  FOV Horizontal: {src_fov_h:.2f}°
  FOV Vertical: {src_fov_v:.2f}°

Target Camera: {target_spec.name}
  Sensor: {target_spec.sensor_width_mm:.2f}mm × {target_spec.sensor_height_mm:.2f}mm
  Resolution: {target_spec.image_width_px} × {target_spec.image_height_px}
  Focal Length: {target_focal:.2f}mm
  FOV Horizontal: {tgt_fov_h:.2f}°
  FOV Vertical: {tgt_fov_v:.2f}°

FOV Mismatch:
  Horizontal: {abs(src_fov_h - tgt_fov_h):.2f}°
  Vertical: {abs(src_fov_v - tgt_fov_v):.2f}°

Magnification Ratio: {source_focal / target_focal:.3f}x
"""

            self.fov_analysis_text.setPlainText(analysis_text)

        except Exception as e:
            self.logger.error(f"FOV analysis failed: {e}")
            self.fov_analysis_text.setPlainText(f"Analysis failed: {str(e)}")

    def _recommend_focal_length(self):
        """Recommend optimal focal length for FOV matching."""
        try:
            from CameraCals.field_calibration import CAMERA_SPECS_DB, FocalLengthOptimizer

            source_name = self.field_source_combo.currentText()
            target_name = self.field_target_combo.currentText()

            # Get source spec (custom or predefined)
            if source_name == "Custom..." and self.custom_source_spec:
                source_spec = self.custom_source_spec
            elif source_name in CAMERA_SPECS_DB:
                source_spec = CAMERA_SPECS_DB[source_name]
            else:
                QtWidgets.QMessageBox.warning(self, "Error", "Please configure source camera first")
                return

            # Get target spec (custom or predefined)
            if target_name == "Custom..." and self.custom_target_spec:
                target_spec = self.custom_target_spec
            elif target_name in CAMERA_SPECS_DB:
                target_spec = CAMERA_SPECS_DB[target_name]
            else:
                QtWidgets.QMessageBox.warning(self, "Error", "Please configure target camera first")
                return

            source_focal = self.field_source_focal_spin.value()

            # Get recommendation
            recommendation = FocalLengthOptimizer.recommend_focal_length_for_fov_match(
                source_spec, source_focal, target_spec
            )

            # Update target focal length
            recommended_focal = recommendation['recommended_focal_length_mm']
            self.field_target_focal_spin.setValue(recommended_focal)

            # Show detailed results
            result_text = f"""Focal Length Recommendation
{'=' * 50}

Recommended Target Focal Length: {recommended_focal:.2f}mm

This will match the horizontal FOV of the source camera.

Source FOV:
  Horizontal: {recommendation['source_fov']['horizontal_deg']:.2f}°
  Vertical: {recommendation['source_fov']['vertical_deg']:.2f}°

Target FOV (with recommended focal length):
  Horizontal: {recommendation['target_fov_matched']['horizontal_deg']:.2f}°
  Vertical: {recommendation['target_fov_matched']['vertical_deg']:.2f}°

FOV Differences:
  Horizontal: {recommendation['fov_differences']['horizontal_deg']:.3f}°
  Vertical: {recommendation['fov_differences']['vertical_deg']:.3f}°

Overlap:
  Horizontal: {recommendation['overlap_percentage']['horizontal']:.1f}%
  Vertical: {recommendation['overlap_percentage']['vertical']:.1f}%
"""

            QtWidgets.QMessageBox.information(
                self, "Focal Length Recommendation", result_text
            )

        except Exception as e:
            self.logger.error(f"Focal length recommendation failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Recommendation failed:\n{str(e)}")

    def _match_natural_features(self):
        """Match natural features between cameras."""
        # Check if we have current frame
        if self.current_frame is None:
            QtWidgets.QMessageBox.warning(
                self, "Error",
                "No camera frame available.\nPlease ensure camera is connected."
            )
            return

        # Detect available cameras
        from camera_manager import CameraManager
        available_cameras = CameraManager.detect_cameras()

        if len(available_cameras) < 2:
            QtWidgets.QMessageBox.warning(
                self, "Insufficient Cameras",
                f"Feature matching requires 2 cameras.\n"
                f"Currently detected: {len(available_cameras)} camera(s)\n\n"
                "Please connect a second camera."
            )
            return

        # Select second camera
        camera_names = [str(cam) for cam in available_cameras]
        camera2_name, ok = QtWidgets.QInputDialog.getItem(
            self, "Select Second Camera",
            "Choose the second camera for feature matching:",
            camera_names,
            0,
            False
        )

        if not ok:
            return

        camera2_index = camera_names.index(camera2_name)
        camera2_device = available_cameras[camera2_index]

        # Capture from second camera
        temp_camera_manager = CameraManager()
        if not temp_camera_manager.connect(device=camera2_device):
            QtWidgets.QMessageBox.critical(
                self, "Connection Failed",
                f"Failed to connect to {camera2_device.name}"
            )
            return

        ret, frame2 = temp_camera_manager.read_frame()
        temp_camera_manager.disconnect()

        if not ret or frame2 is None:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to capture from second camera")
            return

        # Perform feature matching
        try:
            from CameraCals.field_calibration import NaturalFeatureMatcher, FeatureDetectorType
            import numpy as np

            matcher = NaturalFeatureMatcher(FeatureDetectorType.SIFT)
            pts1, pts2, matches = matcher.match_features(self.current_frame, frame2)

            if len(matches) < 10:
                QtWidgets.QMessageBox.warning(
                    self, "Insufficient Matches",
                    f"Only found {len(matches)} feature matches.\n\n"
                    "Need at least 10 matches for reliable alignment.\n\n"
                    "Tips:\n"
                    "- Ensure both cameras see the same scene\n"
                    "- Add more visual texture/features to the scene\n"
                    "- Improve lighting conditions"
                )
                return

            # Compute homography
            H, mask = matcher.compute_homography(pts1, pts2)
            inliers = np.sum(mask)
            inlier_ratio = inliers / len(matches)

            # Assess quality
            quality = "Good"
            if inlier_ratio < 0.5:
                quality = "Poor - cameras may be too misaligned"
            elif inlier_ratio < 0.7:
                quality = "Fair - some outliers detected"

            QtWidgets.QMessageBox.information(
                self, "Feature Matching Results",
                f"Feature Matching Complete!\n\n"
                f"Total Matches: {len(matches)}\n"
                f"Inliers: {inliers}\n"
                f"Inlier Ratio: {inlier_ratio*100:.1f}%\n\n"
                f"Quality: {quality}\n\n"
                f"Homography computed successfully.\n"
                f"You can use this for image alignment and FOV analysis."
            )

        except Exception as e:
            self.logger.error(f"Feature matching failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self, "Error",
                f"Feature matching failed:\n\n{str(e)}"
            )

    def _add_landmark_pair(self):
        """Add a manual landmark pair."""
        # Check if we have current frame
        if self.current_frame is None:
            QtWidgets.QMessageBox.warning(
                self, "Error",
                "No camera frame available.\nPlease ensure camera is connected."
            )
            return

        # Detect available cameras
        from camera_manager import CameraManager
        available_cameras = CameraManager.detect_cameras()

        if len(available_cameras) < 2:
            QtWidgets.QMessageBox.warning(
                self, "Insufficient Cameras",
                f"Landmark matching requires 2 cameras.\n"
                f"Currently detected: {len(available_cameras)} camera(s)\n\n"
                "Please connect a second camera."
            )
            return

        # Select second camera
        camera_names = [str(cam) for cam in available_cameras]
        camera2_name, ok = QtWidgets.QInputDialog.getItem(
            self, "Select Second Camera",
            "Choose the second camera for landmark matching:",
            camera_names,
            0,
            False
        )

        if not ok:
            return

        camera2_index = camera_names.index(camera2_name)
        camera2_device = available_cameras[camera2_index]

        # Capture from second camera
        temp_camera_manager = CameraManager()
        if not temp_camera_manager.connect(device=camera2_device):
            QtWidgets.QMessageBox.critical(
                self, "Connection Failed",
                f"Failed to connect to {camera2_device.name}"
            )
            return

        ret, frame2 = temp_camera_manager.read_frame()
        temp_camera_manager.disconnect()

        if not ret or frame2 is None:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to capture from second camera")
            return

        # Show landmark picker dialog
        dialog = LandmarkPickerDialog(self.current_frame, frame2, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            landmarks = dialog.get_landmarks()

            if len(landmarks) > 0:
                # Add landmarks to our list
                for pt1, pt2 in landmarks:
                    self.landmark_pairs.append((pt1, pt2))

                # Update UI
                total_pairs = len(self.landmark_pairs)
                self.landmark_count_label.setText(f"Landmarks: {total_pairs} pairs")

                QtWidgets.QMessageBox.information(
                    self, "Landmarks Added",
                    f"Added {len(landmarks)} landmark pair(s).\n"
                    f"Total: {total_pairs} pairs\n\n"
                    "These can be used for manual alignment and\n"
                    "homography estimation."
                )

                self.logger.info(f"Added {len(landmarks)} landmark pairs, total: {total_pairs}")
            else:
                QtWidgets.QMessageBox.information(
                    self, "No Landmarks",
                    "No landmark pairs were selected."
                )

    def _clear_landmarks(self):
        """Clear all manual landmarks."""
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Clear",
            "Clear all landmark pairs?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.landmark_pairs = []
            self.landmark_count_label.setText("Landmarks: 0 pairs")
            self.logger.info("Cleared all landmark pairs")

    # ========================================================================
    # Frame Update (called from main application)
    # ========================================================================

    def update_frame(self, frame: np.ndarray):
        """Update current frame and detect pattern."""
        self.current_frame = frame.copy()

        # Detect calibration pattern
        success, corners = self.pattern_detector.detect(frame)

        self.pattern_detected = success
        self.detected_corners = corners

        # Update status
        if success:
            self.pattern_status_label.setText("✓ Pattern Detected")
            self.pattern_status_label.setStyleSheet("font-size: 10pt; font-weight: bold; color: #51cf66;")
            self.corners_count_label.setText(f"Corners: {len(corners)}")
        else:
            self.pattern_status_label.setText("✗ No Pattern")
            self.pattern_status_label.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ff6b6b;")
            self.corners_count_label.setText("Corners: 0")


class ClickableLabel(QtWidgets.QLabel):
    """QLabel that emits click signals with pixel coordinates."""
    clicked = QtCore.pyqtSignal(int, int)

    def mousePressEvent(self, event):
        """Handle mouse click events."""
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(event.x(), event.y())


class LandmarkPickerDialog(QtWidgets.QDialog):
    """Dialog for manually selecting corresponding landmark points in two images."""

    def __init__(self, image1: np.ndarray, image2: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual Landmark Selection")
        self.image1 = image1.copy()
        self.image2 = image2.copy()

        self.landmarks = []  # List of (pt1, pt2) tuples
        self.temp_pt1 = None  # Temporary storage for first point

        self._create_ui()
        self._update_displays()

    def _create_ui(self):
        """Create the dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)

        # Instructions
        instructions = QtWidgets.QLabel(
            "Click corresponding points in both images:\n"
            "1. Click a point in Image 1 (left)\n"
            "2. Click the SAME physical point in Image 2 (right)\n"
            "3. Repeat to add more landmark pairs\n\n"
            "The points will be connected and numbered."
        )
        instructions.setStyleSheet("background-color: #e7f5ff; padding: 10px; border-radius: 5px;")
        layout.addWidget(instructions)

        # Image display area
        images_layout = QtWidgets.QHBoxLayout()

        # Image 1 panel
        img1_panel = QtWidgets.QVBoxLayout()
        img1_panel.addWidget(QtWidgets.QLabel("<b>Image 1 (Source)</b>"))
        self.img1_label = ClickableLabel()
        self.img1_label.setScaledContents(True)
        self.img1_label.setMinimumSize(400, 300)
        self.img1_label.clicked.connect(self._on_image1_clicked)
        img1_panel.addWidget(self.img1_label)
        images_layout.addLayout(img1_panel)

        # Image 2 panel
        img2_panel = QtWidgets.QVBoxLayout()
        img2_panel.addWidget(QtWidgets.QLabel("<b>Image 2 (Target)</b>"))
        self.img2_label = ClickableLabel()
        self.img2_label.setScaledContents(True)
        self.img2_label.setMinimumSize(400, 300)
        self.img2_label.clicked.connect(self._on_image2_clicked)
        img2_panel.addWidget(self.img2_label)
        images_layout.addLayout(img2_panel)

        layout.addLayout(images_layout)

        # Status label
        self.status_label = QtWidgets.QLabel("Click a point in Image 1 to start")
        self.status_label.setStyleSheet("font-weight: bold; color: #228be6;")
        layout.addWidget(self.status_label)

        # Landmark list
        list_layout = QtWidgets.QHBoxLayout()
        list_layout.addWidget(QtWidgets.QLabel("Landmark Pairs:"))
        self.landmark_list = QtWidgets.QListWidget()
        self.landmark_list.setMaximumHeight(100)
        list_layout.addWidget(self.landmark_list)
        layout.addLayout(list_layout)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()

        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_landmarks)
        button_layout.addWidget(self.clear_btn)

        self.undo_btn = QtWidgets.QPushButton("Undo Last")
        self.undo_btn.clicked.connect(self._undo_last)
        self.undo_btn.setEnabled(False)
        button_layout.addWidget(self.undo_btn)

        button_layout.addStretch()

        self.done_btn = QtWidgets.QPushButton("Done")
        self.done_btn.clicked.connect(self.accept)
        self.done_btn.setStyleSheet("background-color: #51cf66; color: white; font-weight: bold; padding: 8px;")
        button_layout.addWidget(self.done_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _on_image1_clicked(self, x: int, y: int):
        """Handle click on image 1."""
        if self.temp_pt1 is not None:
            self.status_label.setText("⚠ Please click Image 2 to complete the pair")
            return

        # Store the first point
        self.temp_pt1 = (x, y)
        self.status_label.setText(f"Point selected in Image 1: ({x}, {y}). Now click corresponding point in Image 2")
        self._update_displays()

    def _on_image2_clicked(self, x: int, y: int):
        """Handle click on image 2."""
        if self.temp_pt1 is None:
            self.status_label.setText("⚠ Please click Image 1 first")
            return

        # Complete the landmark pair
        pt2 = (x, y)
        self.landmarks.append((self.temp_pt1, pt2))

        # Update UI
        pair_num = len(self.landmarks)
        self.landmark_list.addItem(f"Pair {pair_num}: {self.temp_pt1} ↔ {pt2}")
        self.status_label.setText(f"✓ Landmark pair {pair_num} added! Click Image 1 for next pair")

        self.temp_pt1 = None
        self.undo_btn.setEnabled(True)
        self._update_displays()

    def _clear_landmarks(self):
        """Clear all landmarks."""
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Clear",
            "Clear all landmark pairs?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.landmarks = []
            self.temp_pt1 = None
            self.landmark_list.clear()
            self.undo_btn.setEnabled(False)
            self.status_label.setText("Click a point in Image 1 to start")
            self._update_displays()

    def _undo_last(self):
        """Undo the last landmark pair."""
        if len(self.landmarks) > 0:
            self.landmarks.pop()
            self.landmark_list.takeItem(len(self.landmarks))
            self.status_label.setText(f"Undone. {len(self.landmarks)} pairs remaining")

            if len(self.landmarks) == 0:
                self.undo_btn.setEnabled(False)

            self._update_displays()

    def _update_displays(self):
        """Update both image displays with landmarks."""
        # Draw on image 1
        img1_display = self.image1.copy()
        for i, (pt1, pt2) in enumerate(self.landmarks):
            cv2.circle(img1_display, pt1, 5, (0, 255, 0), -1)
            cv2.putText(img1_display, str(i+1), (pt1[0]+8, pt1[1]+8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Draw temp point if exists
        if self.temp_pt1 is not None:
            cv2.circle(img1_display, self.temp_pt1, 7, (255, 255, 0), 2)
            cv2.putText(img1_display, "?", (self.temp_pt1[0]+8, self.temp_pt1[1]+8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        # Draw on image 2
        img2_display = self.image2.copy()
        for i, (pt1, pt2) in enumerate(self.landmarks):
            cv2.circle(img2_display, pt2, 5, (0, 255, 0), -1)
            cv2.putText(img2_display, str(i+1), (pt2[0]+8, pt2[1]+8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Convert to QPixmap and display
        self.img1_label.setPixmap(self._cv_to_pixmap(img1_display))
        self.img2_label.setPixmap(self._cv_to_pixmap(img2_display))

    def _cv_to_pixmap(self, cv_img: np.ndarray) -> QtGui.QPixmap:
        """Convert OpenCV image to QPixmap."""
        height, width, channel = cv_img.shape
        bytes_per_line = 3 * width
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        q_img = QtGui.QImage(rgb_image.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)
        return QtGui.QPixmap.fromImage(q_img)

    def get_landmarks(self):
        """Get the selected landmark pairs."""
        return self.landmarks
