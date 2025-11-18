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
        # This is a placeholder - actual implementation would need dual camera support
        QtWidgets.QMessageBox.information(
            self, "Stereo Capture",
            "Stereo pair capture requires two camera sources.\n"
            "This feature will capture from both cameras simultaneously."
        )

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
        QtWidgets.QMessageBox.information(
            self, "Stereo Calibration",
            "Stereo calibration will be performed using the captured stereo pairs."
        )

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
                if self.field_source_combo.count() > 1:
                    self.field_source_combo.setCurrentIndex(0)  # Default to first non-custom option
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
                if self.field_target_combo.count() > 2:
                    self.field_target_combo.setCurrentIndex(2)  # Default to Firefly
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
        QtWidgets.QMessageBox.information(
            self, "Feature Matching",
            "Natural feature matching requires live camera feeds from both cameras.\n"
            "This will detect and match features like corners, edges, and textures\n"
            "to compute alignment without calibration patterns."
        )

    def _add_landmark_pair(self):
        """Add a manual landmark pair."""
        QtWidgets.QMessageBox.information(
            self, "Add Landmark",
            "Click corresponding points in source and target camera views.\n"
            "Points should represent the same physical location in the scene."
        )

    def _clear_landmarks(self):
        """Clear all manual landmarks."""
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Clear",
            "Clear all landmark pairs?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.landmark_count_label.setText("Landmarks: 0 pairs")

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
