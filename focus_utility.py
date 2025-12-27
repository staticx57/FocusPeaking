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
import winsound
from collections import deque
from typing import List, Dict, Optional, Tuple
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtMultimedia import QSoundEffect
from datetime import datetime
from pathlib import Path

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
    AdaptiveEdgeDetector,
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
    zoomRectCreated = QtCore.pyqtSignal(tuple)  # Signal for zoom rectangle drawing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._image = None  # Using QImage instead of QPixmap for performance
        self.drawing = False
        self.start = None
        self.current_rect = None
        self.rois = []
        self.selected_id = None
        self.moving = False
        self.move_offset = (0, 0)

        # Zoom rectangle drawing
        self.zoom_drawing = False
        self.zoom_start = None
        self.current_zoom_rect = None

        self.logger = get_logger(self.__class__.__name__)

    def setImage(self, image: QtGui.QImage) -> None:
        """Set the current frame image directly from QImage."""
        self._image = image
        self.update()  # Trigger repaint directly
        # No more expensive pre-scaling here; handled in paintEvent via QPainter

    def map_to_frame(self, x: int, y: int) -> Tuple[int, int]:
        """Map QLabel coordinates to frame coordinates."""
        if self._image is None:
            return 0, 0

        lbl_w, lbl_h = self.width(), self.height()
        # QImage vs QPixmap confusion? QImage has width()/height() too.
        pm_w, pm_h = self._image.width(), self._image.height()
        
        # Calculate aspect-ratio preserved display dimensions
        scale = min(lbl_w / pm_w, lbl_h / pm_h)
        disp_w, disp_h = int(pm_w * scale), int(pm_h * scale)
        
        # Calculate offsets
        x0 = (lbl_w - disp_w) // 2
        y0 = (lbl_h - disp_h) // 2

        # Clip mouse coordinates to display area
        if x < x0 or x > x0 + disp_w or y < y0 or y > y0 + disp_h:
            x = max(x0, min(x, x0 + disp_w))
            y = max(y0, min(y, y0 + disp_h))

        # Map to frame coordinates
        frame_w = self._image.width()
        frame_h = self._image.height()
        
        fx = int((x - x0) * (frame_w / disp_w))
        fy = int((y - y0) * (frame_h / disp_h))
        
        fx = max(0, min(frame_w - 1, fx))
        fy = max(0, min(frame_h - 1, fy))
        return fx, fy

    def map_from_frame(self, rect: List[int]) -> List[int]:
        """Map frame rect to QLabel coordinates."""
        if self._image is None:
            return rect

        x1, y1, x2, y2 = rect
        lbl_w, lbl_h = self.width(), self.height()
        pm_w, pm_h = self._image.width(), self._image.height()
        
        scale = min(lbl_w / pm_w, lbl_h / pm_h)
        disp_w, disp_h = int(pm_w * scale), int(pm_h * scale)
        x0 = (lbl_w - disp_w) // 2
        y0 = (lbl_h - disp_h) // 2
        
        frame_w = self._image.width()
        frame_h = self._image.height()
        
        sx = disp_w / frame_w
        sy = disp_h / frame_h

        return [
            int(x0 + x1 * sx),
            int(y0 + y1 * sy),
            int(x0 + x2 * sx),
            int(y0 + y2 * sy),
        ]



    def set_zoom_drawing_mode(self, enabled: bool) -> None:
        """Enable or disable zoom rectangle drawing mode."""
        self.zoom_drawing = enabled
        # Clear any existing zoom rectangle when disabling
        if not enabled:
            self.current_zoom_rect = None
            self.zoom_start = None
            self.update()  # Trigger repaint to clear visual feedback
        self.logger.debug(f"Zoom drawing mode: {'enabled' if enabled else 'disabled'}")

    def mousePressEvent(self, ev):
        x, y = ev.x(), ev.y()
        if ev.button() == QtCore.Qt.LeftButton:
            fx, fy = self.map_to_frame(x, y)

            # If in zoom drawing mode, start drawing zoom rect
            if self.zoom_drawing:
                self.zoom_start = (fx, fy)
                self.current_zoom_rect = (fx, fy, fx, fy)
                self.logger.debug("Started zoom rectangle drawing")
                return

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

        # Handle zoom rectangle drawing
        if self.zoom_drawing and self.zoom_start:
            x0, y0 = self.zoom_start
            self.current_zoom_rect = (x0, y0, fx, fy)
            self.update()
        elif self.drawing and self.start:
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
            
            frame_w = self._image.width() if self._image else DEFAULT_FRAME_WIDTH
            frame_h = self._image.height() if self._image else DEFAULT_FRAME_HEIGHT
            
            nx1 = max(0, min(frame_w - w, cx - w // 2))
            ny1 = max(0, min(frame_h - h, cy - h // 2))
            new_rect = [int(nx1), int(ny1), int(nx1 + w), int(ny1 + h)]
            r["rect"] = new_rect
            self.roiMoved.emit(self.selected_id, tuple(new_rect))
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            # Handle zoom rectangle completion
            if self.zoom_drawing and self.current_zoom_rect is not None:
                x1, y1, x2, y2 = self.current_zoom_rect
                if abs(x2 - x1) > MIN_ROI_WIDTH and abs(y2 - y1) > MIN_ROI_HEIGHT:
                    norm_rect = [
                        int(min(x1, x2)),
                        int(min(y1, y2)),
                        int(max(x1, x2)),
                        int(max(y1, y2)),
                    ]
                    self.zoomRectCreated.emit(tuple(norm_rect))
                    self.logger.info(f"Zoom rectangle created: {norm_rect}")
                self.current_zoom_rect = None
                self.zoom_start = None
                self.update()
                return

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
        # Override default paintEvent to avoid clearing/redrawing background unnecessarily if we cover it
        # super().paintEvent(ev) # Optional: skip super paint if we draw full rect
        
        if self._image is None:
            super().paintEvent(ev)
            return

        qp = QtGui.QPainter(self)
        
        # Draw image scaled
        lbl_w, lbl_h = self.width(), self.height()
        img_w, img_h = self._image.width(), self._image.height()
        
        # Calculate aspect-ratio preserved display dimensions
        scale = min(lbl_w / img_w, lbl_h / img_h)
        disp_w, disp_h = int(img_w * scale), int(img_h * scale)
        x0 = (lbl_w - disp_w) // 2
        y0 = (lbl_h - disp_h) // 2
        
        # Define target rect
        target_rect = QtCore.QRect(x0, y0, disp_w, disp_h)
        
        # Draw the image
        qp.drawImage(target_rect, self._image)

        # Draw border/overlays
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

        # Draw current zoom rectangle (use blue color to distinguish from ROIs)
        if self.current_zoom_rect:
            rect_disp = self.map_from_frame([
                int(self.current_zoom_rect[0]),
                int(self.current_zoom_rect[1]),
                int(self.current_zoom_rect[2]),
                int(self.current_zoom_rect[3]),
            ])
            # Blue dashed line with thicker pen
            qp.setPen(QtGui.QPen(QtGui.QColor(0, 150, 255), 3, QtCore.Qt.DashLine))
            qp.setBrush(QtCore.Qt.NoBrush)
            x1, y1, x2, y2 = rect_disp
            qp.drawRect(x1, y1, x2 - x1, y2 - y1)

        qp.end()

    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)
        self.update() # Just trigger repaint, scaling is handled in paintEvent


# ============================================================================
# Audio Focus Feedback
# ============================================================================

class AudioFeedbackManager:
    """Manages audio feedback based on focus quality."""

    def __init__(self):
        self.enabled = False
        self.last_beep_time = 0
        self.min_freq = AUDIO_MIN_FREQUENCY
        self.max_freq = AUDIO_MAX_FREQUENCY
        self.interval_ms = AUDIO_FEEDBACK_INTERVAL_MS
        self.duration_ms = AUDIO_BEEP_DURATION_MS
        self.logger = get_logger(self.__class__.__name__)

    def set_enabled(self, enabled: bool):
        """Enable or disable audio feedback."""
        self.enabled = enabled
        self.logger.info(f"Audio feedback {'enabled' if enabled else 'disabled'}")

    def play_feedback(self, normalized_score: float):
        """Play audio feedback based on normalized focus score (0.0-1.0)."""
        if not self.enabled:
            return

        current_time = QtCore.QDateTime.currentMSecsSinceEpoch()

        # Check if enough time has passed since last beep
        if current_time - self.last_beep_time < self.interval_ms:
            return

        self.last_beep_time = current_time

        # Calculate frequency based on score
        # Higher score = higher pitch
        freq = int(self.min_freq + (self.max_freq - self.min_freq) * normalized_score)
        freq = max(self.min_freq, min(self.max_freq, freq))

        try:
            # Use Windows winsound for simple beep (non-blocking with SND_ASYNC)
            winsound.Beep(freq, self.duration_ms)
        except Exception as e:
            self.logger.debug(f"Audio beep failed: {e}")


# ============================================================================
# Focus Peak Detector
# ============================================================================

class FocusPeakDetector:
    """Detects when focus reaches a peak (optimal focus achieved)."""

    def __init__(self):
        self.history = deque(maxlen=PEAK_DETECTION_WINDOW)
        self.max_observed = 0.0
        self.peak_detected = False
        self.peak_start_time = 0
        self.stable_count = 0
        self.logger = get_logger(self.__class__.__name__)

    def update(self, focus_score: float) -> bool:
        """
        Update with new focus score and check if peak is detected.
        Returns True if currently at peak focus.
        """
        self.history.append(focus_score)

        # Update maximum observed
        if focus_score > self.max_observed:
            self.max_observed = focus_score
            self.stable_count = 0
            self.peak_detected = False
            return False

        # Check if score is near the maximum
        if self.max_observed > 0:
            ratio = focus_score / self.max_observed

            if ratio >= PEAK_DETECTION_THRESHOLD:
                self.stable_count += 1

                if self.stable_count >= PEAK_STABILITY_FRAMES:
                    if not self.peak_detected:
                        self.peak_detected = True
                        self.peak_start_time = QtCore.QDateTime.currentMSecsSinceEpoch()
                        self.logger.info(f"Focus peak detected! Score: {focus_score:.1f}")
                    return True
            else:
                self.stable_count = 0
                self.peak_detected = False

        return False

    def is_peak_active(self) -> bool:
        """Check if peak indicator should still be shown."""
        if not self.peak_detected:
            return False

        elapsed = QtCore.QDateTime.currentMSecsSinceEpoch() - self.peak_start_time
        return elapsed < PEAK_FLASH_DURATION_MS

    def reset(self):
        """Reset peak detection state."""
        self.history.clear()
        self.max_observed = 0.0
        self.peak_detected = False
        self.stable_count = 0


# ============================================================================
# Screenshot Manager
# ============================================================================

class ScreenshotManager:
    """Manages screenshot capture and saving."""

    def __init__(self):
        self.last_frame = None
        self.last_frame_with_overlay = None
        self.logger = get_logger(self.__class__.__name__)

    def update_frames(self, original: np.ndarray, with_overlay: np.ndarray):
        """Store the latest frames for screenshot capture."""
        self.last_frame = original.copy() if original is not None else None
        self.last_frame_with_overlay = with_overlay.copy() if with_overlay is not None else None

    def capture(self, include_overlay: bool = True) -> Optional[str]:
        """
        Capture and save a screenshot.
        Returns the filename if successful, None otherwise.
        """
        frame = self.last_frame_with_overlay if include_overlay else self.last_frame

        if frame is None:
            self.logger.warning("No frame available for screenshot")
            return None

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{SCREENSHOT_PREFIX}_{timestamp}.{SCREENSHOT_FORMAT}"
        filepath = get_screenshots_path() / filename

        try:
            # Save based on format
            if SCREENSHOT_FORMAT.lower() == 'jpg' or SCREENSHOT_FORMAT.lower() == 'jpeg':
                cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, SCREENSHOT_JPEG_QUALITY])
            else:
                cv2.imwrite(str(filepath), frame)

            self.logger.info(f"Screenshot saved: {filepath}")
            return str(filepath)

        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")
            return None


# ============================================================================
# Configuration Profile Manager
# ============================================================================

class ProfileManager:
    """Manages configuration profiles (save/load named presets)."""

    def __init__(self):
        self.current_profile = "Default"
        self.logger = get_logger(self.__class__.__name__)
        self._ensure_default_profiles()

    def _ensure_default_profiles(self):
        """Create default profile files if they don't exist."""
        profiles_path = get_profiles_path()
        default_profile = profiles_path / "Default.json"

        if not default_profile.exists():
            # Create a minimal default profile
            default_config = {
                "name": "Default",
                "focus_color": list(DEFAULT_PEAKING_COLOR),
                "edge_threshold": DEFAULT_EDGE_THRESHOLD,
                "regions": [],
                "focus_algorithm": DEFAULT_FOCUS_ALGORITHM,
                "thermal_preprocessing": False,
                "ensemble_voting_enabled": False,
                "adaptive_edge_enabled": False,
            }
            try:
                with open(default_profile, 'w') as f:
                    json.dump(default_config, f, indent=2)
                self.logger.info("Created default profile")
            except Exception as e:
                self.logger.error(f"Failed to create default profile: {e}")

    def list_profiles(self) -> List[str]:
        """Get list of available profile names."""
        profiles_path = get_profiles_path()
        profiles = []

        try:
            for f in profiles_path.glob("*.json"):
                profiles.append(f.stem)
        except Exception as e:
            self.logger.error(f"Failed to list profiles: {e}")

        return sorted(profiles) if profiles else ["Default"]

    def save_profile(self, name: str, config: dict) -> bool:
        """Save configuration to a named profile."""
        profiles_path = get_profiles_path()
        filepath = profiles_path / f"{name}.json"

        try:
            config['name'] = name
            with open(filepath, 'w') as f:
                json.dump(config, f, indent=2)
            self.current_profile = name
            self.logger.info(f"Profile saved: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save profile {name}: {e}")
            return False

    def load_profile(self, name: str) -> Optional[dict]:
        """Load configuration from a named profile."""
        profiles_path = get_profiles_path()
        filepath = profiles_path / f"{name}.json"

        if not filepath.exists():
            self.logger.warning(f"Profile not found: {name}")
            return None

        try:
            with open(filepath) as f:
                config = json.load(f)
            self.current_profile = name
            self.logger.info(f"Profile loaded: {name}")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load profile {name}: {e}")
            return None

    def delete_profile(self, name: str) -> bool:
        """Delete a profile by name."""
        if name == "Default":
            self.logger.warning("Cannot delete Default profile")
            return False

        profiles_path = get_profiles_path()
        filepath = profiles_path / f"{name}.json"

        try:
            if filepath.exists():
                filepath.unlink()
                self.logger.info(f"Profile deleted: {name}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to delete profile {name}: {e}")

        return False


# ============================================================================
# Histogram Generator
# ============================================================================

class HistogramGenerator:
    """Generates live histogram from video frames."""

    def __init__(self):
        self.enabled = ENABLE_HISTOGRAM
        self.show_rgb = HISTOGRAM_SHOW_RGB
        self.logger = get_logger(self.__class__.__name__)

    def set_enabled(self, enabled: bool):
        """Enable or disable histogram generation."""
        self.enabled = enabled

    def generate(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Generate histogram image from frame.
        Returns BGR image of histogram or None if disabled.
        """
        if not self.enabled or frame is None:
            return None

        # Create histogram canvas
        hist_img = np.zeros((HISTOGRAM_HEIGHT, HISTOGRAM_WIDTH, 3), dtype=np.uint8)
        hist_img[:] = HISTOGRAM_BACKGROUND_COLOR

        if self.show_rgb and len(frame.shape) == 3:
            # Calculate and draw RGB histograms
            colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # BGR
            for i, color in enumerate(colors):
                hist = cv2.calcHist([frame], [i], None, [256], [0, 256])
                cv2.normalize(hist, hist, 0, HISTOGRAM_HEIGHT - 5, cv2.NORM_MINMAX)

                for x in range(256):
                    y = int(hist[x][0])
                    if y > 0:
                        cv2.line(hist_img, (x, HISTOGRAM_HEIGHT), (x, HISTOGRAM_HEIGHT - y), color, 1)
        else:
            # Calculate luminance histogram
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame

            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            cv2.normalize(hist, hist, 0, HISTOGRAM_HEIGHT - 5, cv2.NORM_MINMAX)

            # Draw filled histogram
            for x in range(256):
                y = int(hist[x][0])
                if y > 0:
                    cv2.line(hist_img, (x, HISTOGRAM_HEIGHT), (x, HISTOGRAM_HEIGHT - y),
                            HISTOGRAM_LINE_COLOR, 1)

        # Draw border
        cv2.rectangle(hist_img, (0, 0), (HISTOGRAM_WIDTH - 1, HISTOGRAM_HEIGHT - 1),
                     (80, 80, 80), 1)

        return hist_img


# ============================================================================
# Background Workers
# ============================================================================

class CameraConnectionThread(QtCore.QThread):
    """Thread for asynchronous camera connection."""
    finished = QtCore.pyqtSignal(bool, object, str)  # success, device, message

    def __init__(self, camera_manager, device):
        super().__init__()
        self.camera_manager = camera_manager
        self.device = device

    def run(self):
        try:
            if self.device:
                success = self.camera_manager.connect(self.device)
                if success:
                    self.finished.emit(True, self.device, "Connected successfully")
                else:
                    self.finished.emit(False, self.device, "Connection failed")
            else:
                self.finished.emit(False, None, "No device specified")
        except Exception as e:
            self.finished.emit(False, None, str(e))


class FocusWorker(QtCore.QThread):
    """
    Background worker for image processing and focus calculations.
    Detaches heavy CV2 operations from the main GUI thread.
    """
    frame_processed = QtCore.pyqtSignal(object, object, float, list, dict, dict) 
    # args: (original_frame, display_frame, global_score, roi_scores, stats, debug_info)

    def __init__(self, camera_manager):
        super().__init__()
        self.camera_manager = camera_manager
        self.running = True
        self.paused = False
        self.settings = {}
        self.mutex = QtCore.QMutex()
        
        # Internal state
        self.stripe_offset = 0
        self.focus_ensemble = FocusEnsemble()
        self.adaptive_edge_detector = AdaptiveEdgeDetector()
        self.focus_quality = FocusQualityIndicator()
        
        # Algorithm map (local to thread to avoid conflicts)
        self.algorithm_map = {
            "Laplacian Variance": laplacian_focus_metric,
            "Tenengrad": tenengrad_focus_metric,
            "Brenner Gradient": brenner_gradient_metric,
            "Normalized Variance": normalized_variance_focus,
            "Variance of Laplacian": variance_of_laplacian_metric,
        }

    def update_settings(self, settings):
        """Thread-safe settings update."""
        self.mutex.lock()
        self.settings = settings.copy()
        self.mutex.unlock()

    def stop(self):
        self.running = False
        self.wait()

    def run(self):
        while self.running:
            if self.paused or not self.camera_manager.is_connected:
                self.msleep(50)
                continue

            # Read frame
            ret, frame = self.camera_manager.read_frame()
            if not ret or frame is None:
                self.msleep(10)
                continue

            # Get current settings
            self.mutex.lock()
            cfg = self.settings.copy()
            self.mutex.unlock()
            
            if not cfg:
                self.msleep(50)
                continue

            try:
                # Apply software palette if needed
                if cfg.get('boson_connected') and cfg.get('palette'):
                    frame = apply_palette_software(frame, cfg['palette'])

                # Convert to gray
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Thermal preprocessing
                if cfg.get('thermal_preprocessing'):
                    gray = thermal_preprocess(gray, enhance_contrast=True, reduce_noise=False)

                # Animate stripes
                if cfg.get('stripes_enabled'):
                    self.stripe_offset = (self.stripe_offset + 1) % 8

                # Edge Detection & Peaking Overlay
                if cfg.get('adaptive_edge_enabled'):
                    scene_type = cfg.get('adaptive_scene_type', 'auto')
                    displayed = self.adaptive_edge_detector.create_adaptive_focus_peaking(
                        frame, gray, cfg['edge_threshold'], cfg['focus_color'], 
                        PEAKING_ALPHA, scene_type, cfg.get('stripes_enabled'), self.stripe_offset
                    )
                    scene_info = self.adaptive_edge_detector.get_scene_info(gray)
                else:
                    displayed = create_focus_peaking_overlay(
                        frame, cfg['edge_threshold'], cfg['focus_color'], 
                        PEAKING_ALPHA, cfg.get('stripes_enabled'), self.stripe_offset
                    )
                    scene_info = {}

                # Focus Calculations
                global_score = 0.0
                roi_scores = []
                ensemble_details = {}
                regions = cfg.get('regions', [])

                if cfg.get('ensemble_voting_enabled'):
                    global_score, ensemble_details = self.focus_ensemble.compute_ensemble_focus(
                        gray, return_details=True
                    )
                    # ROI scores use selected algorithm as fallback or ensemble? 
                    # Existing logic used selected algorithm for ROIs even in ensemble mode
                    algo_name = cfg.get('current_algorithm', DEFAULT_FOCUS_ALGORITHM)
                    metric_func = self.algorithm_map.get(algo_name, laplacian_focus_metric)
                    if regions:
                        roi_scores = compute_roi_scores(gray, regions, metric_func)
                else:
                    algo_name = cfg.get('current_algorithm', DEFAULT_FOCUS_ALGORITHM)
                    metric_func = self.algorithm_map.get(algo_name, laplacian_focus_metric)
                    
                    if regions:
                        roi_scores = compute_roi_scores(gray, regions, metric_func)
                        global_score = compute_weighted_focus(gray, regions, metric_func)
                    else:
                        global_score = metric_func(gray)

                # Focus Quality Update
                self.focus_quality.update(global_score)
                quality_level, _ = self.focus_quality.get_quality()
                quality_pct = self.focus_quality.get_quality_percentage()

                # Pack stats
                stats = {
                    'quality_level': quality_level,
                    'quality_pct': quality_pct,
                    'scene_info': scene_info,
                    'ensemble_details': ensemble_details
                }

                # Emit results
                self.frame_processed.emit(frame, displayed, global_score, roi_scores, stats, {})

            except Exception as e:
                # Log error but keep running
                print(f"Worker Error: {e}")

            # Cap frame rate
            self.msleep(TIMER_INTERVAL_MS)


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
        # Window size will be set after UI creation for auto-scaling

        # Initialize managers
        self.camera_manager = CameraManager()
        self.exporter = FocusDataExporter()
        # Initialize and connect to Boson camera
        self.boson_controller = BosonController()
        if self.boson_controller.sdk_available:
            self.boson_controller.connect()
        self.stats_tracker = FocusStatistics(window_size=STATS_WINDOW_SIZE)

        # Install event filter to intercept arrow keys and WASD before child widgets get them
        self.installEventFilter(self)

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

        # Adaptive edge detection (Phase 5)
        self.adaptive_edge_detector = AdaptiveEdgeDetector()
        self.adaptive_edge_enabled = False  # Default off
        self.adaptive_scene_type = "auto"  # auto, low_contrast, high_detail, thermal
        self.adaptive_multi_scale = True  # Use multi-scale detection

        # Stripe pattern for focus peaking
        self.stripes_enabled = False
        self.stripe_offset = 0  # Animation counter (0-7)

        # New Feature Managers
        self.audio_feedback = AudioFeedbackManager()
        self.peak_detector = FocusPeakDetector()
        self.screenshot_manager = ScreenshotManager()
        self.profile_manager = ProfileManager()
        self.histogram_generator = HistogramGenerator()

        # Audio feedback state
        self.audio_feedback_enabled = ENABLE_AUDIO_FEEDBACK

        # Histogram state
        self.histogram_enabled = ENABLE_HISTOGRAM

        # Peak indicator state
        self.peak_indicator_enabled = ENABLE_PEAK_INDICATOR

        # Store last original frame for screenshots
        self.last_original_frame = None

        # Background Worker for Image Processing
        self.focus_worker = FocusWorker(self.camera_manager)
        self.focus_worker.frame_processed.connect(self._on_frame_processed)
        self.focus_worker.start()  # Start the thread loop (it handles pausing internally)

        # Setup UI
        self._create_ui()

        # Auto-scale window to fit content
        self._auto_scale_window()

        self._setup_timer()
        self._setup_shortcuts()
        self._load_config_if_exists()
        
        # Initial settings sync
        self._sync_settings_to_worker()
        self._setup_shortcuts()
        self._load_config_if_exists()
        self._connect_camera()

        self.logger.info("GUI initialization complete")

    def _create_ui(self):
        """Create the user interface with tabbed settings and mode selector."""
        # Main vertical layout for entire application
        app_main_layout = QtWidgets.QVBoxLayout(self)

        # ====================================================================
        # TOP: Mode Selector Bar
        # ====================================================================
        mode_bar = QtWidgets.QWidget()
        mode_bar_layout = QtWidgets.QHBoxLayout(mode_bar)
        mode_bar_layout.setContentsMargins(10, 5, 10, 5)
        mode_bar.setStyleSheet("background-color: palette(dark); border-bottom: 2px solid palette(mid);")

        mode_label = QtWidgets.QLabel("Application Mode:")
        mode_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        mode_bar_layout.addWidget(mode_label)

        # Mode selector buttons (radio button style)
        self.mode_button_group = QtWidgets.QButtonGroup()

        self.mode_focus_btn = QtWidgets.QPushButton("🎯 Focus Peaking")
        self.mode_focus_btn.setCheckable(True)
        self.mode_focus_btn.setChecked(True)
        self.mode_focus_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                font-size: 11pt;
                font-weight: bold;
                border: 2px solid palette(mid);
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                border-color: #0078d4;
            }
        """)
        self.mode_button_group.addButton(self.mode_focus_btn, 0)
        mode_bar_layout.addWidget(self.mode_focus_btn)

        self.mode_calibration_btn = QtWidgets.QPushButton("📐 Camera Calibration")
        self.mode_calibration_btn.setCheckable(True)
        self.mode_calibration_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                font-size: 11pt;
                font-weight: bold;
                border: 2px solid palette(mid);
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                border-color: #0078d4;
            }
        """)
        self.mode_button_group.addButton(self.mode_calibration_btn, 1)
        mode_bar_layout.addWidget(self.mode_calibration_btn)

        mode_bar_layout.addStretch()

        app_main_layout.addWidget(mode_bar)

        # ====================================================================
        # MIDDLE: Stacked Widget for Different Modes
        # ====================================================================
        self.mode_stack = QtWidgets.QStackedWidget()

        # Create Focus Mode Widget
        self.focus_mode_widget = QtWidgets.QWidget()
        self._create_focus_mode_ui(self.focus_mode_widget)
        self.mode_stack.addWidget(self.focus_mode_widget)

        # Create Calibration Mode Widget
        self.calibration_mode_widget = QtWidgets.QWidget()
        self._create_calibration_mode_ui(self.calibration_mode_widget)
        self.mode_stack.addWidget(self.calibration_mode_widget)

        app_main_layout.addWidget(self.mode_stack, 1)

        # Connect mode switching
        self.mode_focus_btn.clicked.connect(lambda: self._switch_mode(0))
        self.mode_calibration_btn.clicked.connect(lambda: self._switch_mode(1))

    def _create_focus_mode_ui(self, parent_widget):
        """Create the original focus peaking UI."""
        main_layout = QtWidgets.QHBoxLayout(parent_widget)

        # Left panel - Video (increased from 3 to 5 for more screen real estate)
        left_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_layout, 5)

        self.video_label = VideoLabel()
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("border: 2px solid palette(mid);")
        self.video_label.setScaledContents(False)
        self.video_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        left_layout.addWidget(self.video_label, 1)

        # Status bar at bottom
        self.status_label = QtWidgets.QLabel("Initializing...")
        left_layout.addWidget(self.status_label)

        # Right panel - Tabbed Controls
        right_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_layout, 2)

        # Create tabbed interface for settings with scroll areas
        self.settings_tabs = QtWidgets.QTabWidget()

        # Tab 1: Camera
        camera_tab_widget = QtWidgets.QWidget()
        camera_layout = QtWidgets.QVBoxLayout(camera_tab_widget)
        camera_layout.setContentsMargins(5, 5, 5, 5)
        self._create_camera_controls(camera_layout)
        self._create_boson_controls(camera_layout)
        camera_layout.addStretch()

        camera_scroll = QtWidgets.QScrollArea()
        camera_scroll.setWidget(camera_tab_widget)
        camera_scroll.setWidgetResizable(True)
        camera_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        camera_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.settings_tabs.addTab(camera_scroll, "📷 Camera")

        # Tab 2: Focus
        focus_tab_widget = QtWidgets.QWidget()
        focus_layout = QtWidgets.QVBoxLayout(focus_tab_widget)
        focus_layout.setContentsMargins(5, 5, 5, 5)
        self._create_focus_algorithm_controls(focus_layout)
        self._create_focus_quality_controls(focus_layout)
        self._create_ensemble_controls(focus_layout)
        focus_layout.addStretch()

        focus_scroll = QtWidgets.QScrollArea()
        focus_scroll.setWidget(focus_tab_widget)
        focus_scroll.setWidgetResizable(True)
        focus_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        focus_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.settings_tabs.addTab(focus_scroll, "🎯 Focus")

        # Tab 3: Edge Detection
        edge_tab_widget = QtWidgets.QWidget()
        edge_layout = QtWidgets.QVBoxLayout(edge_tab_widget)
        edge_layout.setContentsMargins(5, 5, 5, 5)
        self._create_edge_threshold_controls(edge_layout)
        self._create_adaptive_edge_controls(edge_layout)
        edge_layout.addStretch()

        edge_scroll = QtWidgets.QScrollArea()
        edge_scroll.setWidget(edge_tab_widget)
        edge_scroll.setWidgetResizable(True)
        edge_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        edge_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.settings_tabs.addTab(edge_scroll, "🔍 Edges")

        # Tab 4: Advanced
        advanced_tab_widget = QtWidgets.QWidget()
        advanced_layout = QtWidgets.QVBoxLayout(advanced_tab_widget)
        advanced_layout.setContentsMargins(5, 5, 5, 5)
        self._create_palette_controls(advanced_layout)
        self._create_zoom_controls(advanced_layout)
        self._create_audio_feedback_controls(advanced_layout)
        self._create_histogram_controls(advanced_layout)
        self._create_peak_indicator_controls(advanced_layout)
        self._create_theme_controls(advanced_layout)
        advanced_layout.addStretch()

        advanced_scroll = QtWidgets.QScrollArea()
        advanced_scroll.setWidget(advanced_tab_widget)
        advanced_scroll.setWidgetResizable(True)
        advanced_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        advanced_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.settings_tabs.addTab(advanced_scroll, "⚙️ Advanced")

        right_layout.addWidget(self.settings_tabs)

        # Always visible: ROI controls
        self._create_roi_controls(right_layout)

        # Always visible: ROI table, stats, graph, histogram, profiles, buttons
        self._create_roi_table(right_layout)
        self._create_statistics_panel(right_layout)
        self._create_graph(right_layout)
        self._create_histogram_display(right_layout)
        self._create_profile_controls(right_layout)
        self._create_action_buttons(right_layout)

        # Connect signals
        self.video_label.roiCreated.connect(self._on_roi_created)
        self.video_label.roiSelected.connect(self._on_roi_selected)
        self.video_label.roiMoved.connect(self._on_roi_moved)
        self.video_label.zoomRectCreated.connect(self._on_zoom_rect_created)

    def _create_calibration_mode_ui(self, parent_widget):
        """Create the camera calibration UI."""
        main_layout = QtWidgets.QHBoxLayout(parent_widget)

        # Left panel - Video display for calibration (shared with focus mode visually)
        left_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_layout, 5)

        # Create a separate video label for calibration mode (to show pattern detection)
        self.cal_video_label = QtWidgets.QLabel()
        self.cal_video_label.setMinimumSize(640, 480)
        self.cal_video_label.setStyleSheet("border: 2px solid palette(mid);")
        self.cal_video_label.setScaledContents(False)
        self.cal_video_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        self.cal_video_label.setAlignment(QtCore.Qt.AlignCenter)
        left_layout.addWidget(self.cal_video_label, 1)

        # Status bar for calibration mode
        self.cal_status_label = QtWidgets.QLabel("Calibration Mode - Ready")
        self.cal_status_label.setStyleSheet("padding: 5px; background-color: palette(dark);")
        left_layout.addWidget(self.cal_status_label)

        # Right panel - Calibration controls
        right_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_layout, 2)

        # Import and create calibration GUI
        try:
            from CameraCals.gui import CalibrationGUI
            self.calibration_gui = CalibrationGUI(self.camera_manager, parent=parent_widget)
            right_layout.addWidget(self.calibration_gui)
        except Exception as e:
            self.logger.error(f"Failed to load calibration GUI: {e}")
            error_label = QtWidgets.QLabel(
                f"Failed to load calibration module:\n{str(e)}\n\n"
                "Please ensure CameraCals module is properly installed."
            )
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #ff6b6b; padding: 20px;")
            right_layout.addWidget(error_label)
            self.calibration_gui = None

    def _switch_mode(self, mode_index: int):
        """Switch between Focus Mode and Calibration Mode."""
        self.mode_stack.setCurrentIndex(mode_index)

        if mode_index == 0:
            # Focus Mode
            self.logger.info("Switched to Focus Mode")
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - Focus Peaking")
        elif mode_index == 1:
            # Calibration Mode
            self.logger.info("Switched to Calibration Mode")
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - Camera Calibration")

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
        self.refresh_btn = QtWidgets.QPushButton("🔄 Detect")
        self.refresh_btn.setToolTip("Detect and refresh all connected cameras (Boson, Spinnaker, UVC)")
        self.refresh_btn.setStyleSheet("padding: 4px 8px; font-weight: bold;")
        self.refresh_btn.clicked.connect(self._refresh_cameras)
        device_layout.addWidget(self.refresh_btn)
        group_layout.addLayout(device_layout)

        # Camera info
        self.camera_info_label = QtWidgets.QLabel("No camera connected")
        self.camera_info_label.setWordWrap(True)
        self.camera_info_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        group_layout.addWidget(self.camera_info_label)

        # Thermal Camera Toggle
        self.thermal_checkbox = QtWidgets.QCheckBox("Treat as Thermal Camera")
        self.thermal_checkbox.setToolTip("Enable thermal-specific features (Palettes, Preprocessing)")
        self.thermal_checkbox.stateChanged.connect(self._on_thermal_toggle)
        group_layout.addWidget(self.thermal_checkbox)

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

    def _create_focus_algorithm_controls(self, layout):
        """Create focus algorithm control section (Focus tab)."""
        group = QtWidgets.QGroupBox("Focus Algorithm")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Focus algorithm selector
        group_layout.addWidget(QtWidgets.QLabel("Algorithm:"))
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

    def _create_focus_quality_controls(self, layout):
        """Create focus quality indicator section (Focus tab)."""
        if ENABLE_FOCUS_QUALITY_INDICATOR:
            quality_group = QtWidgets.QGroupBox("Focus Quality")
            quality_layout = QtWidgets.QVBoxLayout(quality_group)

            self.quality_status_label = QtWidgets.QLabel("● Calibrating...")
            self.quality_status_label.setStyleSheet("font-size: 10pt; font-weight: bold;")
            quality_layout.addWidget(self.quality_status_label)

            self.quality_score_label = QtWidgets.QLabel("Score: -- / 100")
            self.quality_score_label.setStyleSheet("font-size: 9pt; color: palette(mid);")
            quality_layout.addWidget(self.quality_score_label)

            layout.addWidget(quality_group)

    def _create_ensemble_controls(self, layout):
        """Create multi-algorithm ensemble controls (Focus tab)."""
        ensemble_group = QtWidgets.QGroupBox("Multi-Algorithm Voting")
        ensemble_layout = QtWidgets.QVBoxLayout(ensemble_group)

        # Enable ensemble voting checkbox
        self.ensemble_voting_checkbox = QtWidgets.QCheckBox("Enable Ensemble Voting")
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

    def _create_edge_threshold_controls(self, layout):
        """Create edge threshold control section (Edges tab)."""
        group = QtWidgets.QGroupBox("Edge Threshold")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Edge threshold slider
        group_layout.addWidget(QtWidgets.QLabel("Threshold (1-100):"))
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

        # Striping pattern checkbox
        self.stripes_checkbox = QtWidgets.QCheckBox("Enable Stripe Pattern")
        self.stripes_checkbox.setChecked(False)
        self.stripes_checkbox.setToolTip("Diagonal stripe pattern for better edge visibility (animated)")
        self.stripes_checkbox.stateChanged.connect(self._toggle_stripes)
        group_layout.addWidget(self.stripes_checkbox)

        layout.addWidget(group)

    def _create_adaptive_edge_controls(self, layout):
        """Create adaptive edge detection controls (Edges tab)."""
        adaptive_group = QtWidgets.QGroupBox("Adaptive Edge Detection")
        adaptive_layout = QtWidgets.QVBoxLayout(adaptive_group)

        # Enable adaptive edge detection checkbox
        self.adaptive_edge_checkbox = QtWidgets.QCheckBox("Enable Adaptive Detection")
        self.adaptive_edge_checkbox.setChecked(self.adaptive_edge_enabled)
        self.adaptive_edge_checkbox.setToolTip("Scene-aware edge detection with multi-scale support")
        self.adaptive_edge_checkbox.stateChanged.connect(self._toggle_adaptive_edge)
        adaptive_layout.addWidget(self.adaptive_edge_checkbox)

        # Scene type selector
        adaptive_layout.addWidget(QtWidgets.QLabel("Scene Type:"))
        self.scene_type_combo = QtWidgets.QComboBox()
        self.scene_type_combo.addItems(["Auto", "Low Contrast", "High Detail", "Thermal"])
        self.scene_type_combo.setCurrentText("Auto")
        self.scene_type_combo.setToolTip(
            "Auto: Automatic scene detection\n"
            "Low Contrast: Low-contrast scenes (aggressive enhancement)\n"
            "High Detail: High-detail scenes (sensitive detection)\n"
            "Thermal: Optimized for thermal cameras"
        )
        self.scene_type_combo.currentTextChanged.connect(self._on_scene_type_changed)
        adaptive_layout.addWidget(self.scene_type_combo)

        # Multi-scale checkbox
        self.multi_scale_checkbox = QtWidgets.QCheckBox("Use Multi-Scale Detection")
        self.multi_scale_checkbox.setChecked(self.adaptive_multi_scale)
        self.multi_scale_checkbox.setToolTip("Combine multiple scales for robust edge detection")
        self.multi_scale_checkbox.stateChanged.connect(self._toggle_multi_scale)
        adaptive_layout.addWidget(self.multi_scale_checkbox)

        # Scene info label
        self.scene_info_label = QtWidgets.QLabel("Detected: --")
        self.scene_info_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        adaptive_layout.addWidget(self.scene_info_label)

        layout.addWidget(adaptive_group)

    def _create_palette_controls(self, layout):
        """Create smart palette switcher controls (Advanced tab)."""
        palette_group = QtWidgets.QGroupBox("Smart Palette Switching")
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
        self.palette_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        palette_layout.addWidget(self.palette_status_label)

        layout.addWidget(palette_group)

    def _create_zoom_controls(self, layout):
        """Create zoom/ROI inspector controls (Advanced tab)."""
        zoom_group = QtWidgets.QGroupBox("Zoom / ROI Inspector")
        zoom_layout = QtWidgets.QVBoxLayout(zoom_group)

        # Zoom mode selector
        zoom_layout.addWidget(QtWidgets.QLabel("Zoom Mode:"))
        self.zoom_mode_combo = QtWidgets.QComboBox()
        self.zoom_mode_combo.addItems([mode.value for mode in ZoomMode])
        self.zoom_mode_combo.setCurrentText(ZoomMode.OFF.value)
        self.zoom_mode_combo.setToolTip(
            "Off: Normal view\n"
            "Manual: Draw zoom rectangle\n"
            "Auto-ROI: Zoom to selected ROI\n"
            "Auto-All-ROIs: Zoom to all ROIs"
        )
        self.zoom_mode_combo.currentTextChanged.connect(self._on_zoom_mode_changed)
        zoom_layout.addWidget(self.zoom_mode_combo)

        # ROI selector (for Auto-ROI mode)
        roi_selector_layout = QtWidgets.QHBoxLayout()
        roi_selector_layout.addWidget(QtWidgets.QLabel("Target ROI:"))
        self.zoom_roi_combo = QtWidgets.QComboBox()
        self.zoom_roi_combo.addItem("None", None)
        self.zoom_roi_combo.setToolTip("Select ROI to zoom to (Auto-ROI mode)")
        self.zoom_roi_combo.currentIndexChanged.connect(self._on_zoom_roi_changed)
        roi_selector_layout.addWidget(self.zoom_roi_combo)
        zoom_layout.addLayout(roi_selector_layout)

        # Zoom level slider (for Manual mode)
        zoom_layout.addWidget(QtWidgets.QLabel("Zoom Level:"))
        self.zoom_level_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.zoom_level_slider.setRange(10, 40)  # 1.0x to 4.0x
        self.zoom_level_slider.setValue(10)  # 1.0x default
        self.zoom_level_slider.valueChanged.connect(self._on_zoom_level_changed)
        zoom_layout.addWidget(self.zoom_level_slider)

        self.zoom_level_label = QtWidgets.QLabel("Level: 1.0x")
        self.zoom_level_label.setStyleSheet("font-size: 8pt;")
        zoom_layout.addWidget(self.zoom_level_label)

        # Control buttons
        zoom_buttons_layout = QtWidgets.QHBoxLayout()

        self.zoom_reset_btn = QtWidgets.QPushButton("Reset View")
        self.zoom_reset_btn.setToolTip("Reset zoom and pan to defaults (or press R key)")
        self.zoom_reset_btn.clicked.connect(self._reset_zoom_and_pan)
        zoom_buttons_layout.addWidget(self.zoom_reset_btn)

        self.zoom_draw_btn = QtWidgets.QPushButton("Draw Zoom Area")
        self.zoom_draw_btn.setCheckable(True)
        self.zoom_draw_btn.setToolTip(
            "Click and drag on video to define custom zoom area\n"
            "Automatically switches to Manual zoom mode\n"
            "Draw area shown in blue"
        )
        self.zoom_draw_btn.clicked.connect(self._toggle_zoom_drawing)
        zoom_buttons_layout.addWidget(self.zoom_draw_btn)

        zoom_layout.addLayout(zoom_buttons_layout)

        # Status label
        self.zoom_status_label = QtWidgets.QLabel("Zoom: Off")
        self.zoom_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        zoom_layout.addWidget(self.zoom_status_label)

        # Pan controls hint
        pan_hint = QtWidgets.QLabel("Pan: W A S D  |  Zoom: +/-  |  Reset: R")
        pan_hint.setStyleSheet("font-size: 8pt; font-style: italic; color: palette(mid);")
        pan_hint.setWordWrap(True)
        zoom_layout.addWidget(pan_hint)

        layout.addWidget(zoom_group)

    def _create_theme_controls(self, layout):
        """Create theme selector controls (Advanced tab)."""
        group = QtWidgets.QGroupBox("Theme")
        group_layout = QtWidgets.QVBoxLayout(group)

        theme_layout = QtWidgets.QHBoxLayout()
        theme_layout.addWidget(QtWidgets.QLabel("Theme:"))
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(AVAILABLE_THEMES)
        self.theme_combo.setCurrentText(DEFAULT_THEME)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(self.theme_combo)
        group_layout.addLayout(theme_layout)

        layout.addWidget(group)

    def _create_audio_feedback_controls(self, layout):
        """Create audio feedback controls (Advanced tab)."""
        group = QtWidgets.QGroupBox("Audio Focus Feedback")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Enable checkbox
        self.audio_feedback_checkbox = QtWidgets.QCheckBox("Enable Audio Feedback")
        self.audio_feedback_checkbox.setChecked(self.audio_feedback_enabled)
        self.audio_feedback_checkbox.setToolTip(
            "Play tones that increase in pitch as focus improves\n"
            "Useful for hands-free focusing"
        )
        self.audio_feedback_checkbox.stateChanged.connect(self._toggle_audio_feedback)
        group_layout.addWidget(self.audio_feedback_checkbox)

        # Status label
        self.audio_status_label = QtWidgets.QLabel("Audio: Off")
        self.audio_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        group_layout.addWidget(self.audio_status_label)

        layout.addWidget(group)

    def _create_histogram_controls(self, layout):
        """Create histogram display controls (Advanced tab)."""
        group = QtWidgets.QGroupBox("Live Histogram")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Enable checkbox
        self.histogram_checkbox = QtWidgets.QCheckBox("Show Live Histogram")
        self.histogram_checkbox.setChecked(self.histogram_enabled)
        self.histogram_checkbox.setToolTip("Display real-time image histogram")
        self.histogram_checkbox.stateChanged.connect(self._toggle_histogram)
        group_layout.addWidget(self.histogram_checkbox)

        # RGB mode checkbox
        self.histogram_rgb_checkbox = QtWidgets.QCheckBox("Show RGB Channels")
        self.histogram_rgb_checkbox.setChecked(False)
        self.histogram_rgb_checkbox.setToolTip("Show separate R, G, B histograms")
        self.histogram_rgb_checkbox.stateChanged.connect(self._toggle_histogram_rgb)
        group_layout.addWidget(self.histogram_rgb_checkbox)

        layout.addWidget(group)

    def _create_peak_indicator_controls(self, layout):
        """Create peak focus indicator controls (Advanced tab)."""
        group = QtWidgets.QGroupBox("Focus Peak Indicator")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Enable checkbox
        self.peak_indicator_checkbox = QtWidgets.QCheckBox("Enable Peak Detection")
        self.peak_indicator_checkbox.setChecked(self.peak_indicator_enabled)
        self.peak_indicator_checkbox.setToolTip(
            "Flash green border when optimal focus is achieved\n"
            "Automatically detects when focus stabilizes at maximum"
        )
        self.peak_indicator_checkbox.stateChanged.connect(self._toggle_peak_indicator)
        group_layout.addWidget(self.peak_indicator_checkbox)

        # Peak status label
        self.peak_status_label = QtWidgets.QLabel("Peak: Searching...")
        self.peak_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        group_layout.addWidget(self.peak_status_label)

        layout.addWidget(group)

    def _create_histogram_display(self, layout):
        """Create histogram display widget."""
        # Histogram container (hidden by default)
        self.histogram_container = QtWidgets.QWidget()
        histogram_layout = QtWidgets.QVBoxLayout(self.histogram_container)
        histogram_layout.setContentsMargins(0, 0, 0, 0)

        histogram_layout.addWidget(QtWidgets.QLabel("<b>Histogram</b>"))

        self.histogram_label = QtWidgets.QLabel()
        self.histogram_label.setFixedHeight(HISTOGRAM_HEIGHT)
        self.histogram_label.setStyleSheet(f"background:#{HISTOGRAM_BACKGROUND_COLOR[0]:02x}{HISTOGRAM_BACKGROUND_COLOR[1]:02x}{HISTOGRAM_BACKGROUND_COLOR[2]:02x};")
        histogram_layout.addWidget(self.histogram_label)

        self.histogram_container.setVisible(self.histogram_enabled)
        layout.addWidget(self.histogram_container)

    def _create_profile_controls(self, layout):
        """Create configuration profile controls."""
        group = QtWidgets.QGroupBox("Profiles")
        group_layout = QtWidgets.QVBoxLayout(group)

        # Profile selector
        profile_row = QtWidgets.QHBoxLayout()
        profile_row.addWidget(QtWidgets.QLabel("Profile:"))
        self.profile_combo = QtWidgets.QComboBox()
        self._refresh_profiles()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self.profile_combo)
        group_layout.addLayout(profile_row)

        # Buttons row
        btn_row = QtWidgets.QHBoxLayout()

        self.profile_save_btn = QtWidgets.QPushButton("Save As...")
        self.profile_save_btn.setToolTip("Save current settings to a new profile")
        self.profile_save_btn.clicked.connect(self._save_profile_as)
        btn_row.addWidget(self.profile_save_btn)

        self.profile_delete_btn = QtWidgets.QPushButton("Delete")
        self.profile_delete_btn.setToolTip("Delete the selected profile")
        self.profile_delete_btn.clicked.connect(self._delete_profile)
        btn_row.addWidget(self.profile_delete_btn)

        group_layout.addLayout(btn_row)

        layout.addWidget(group)

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
        # Row 1: Save/Load
        row1 = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("💾 Save Config")
        self.save_btn.clicked.connect(self._save_config)
        row1.addWidget(self.save_btn)

        self.load_btn = QtWidgets.QPushButton("📂 Load Config")
        self.load_btn.clicked.connect(self._load_config)
        row1.addWidget(self.load_btn)
        layout.addLayout(row1)

        # Row 2: Export/Delete
        row2 = QtWidgets.QHBoxLayout()
        self.export_btn = QtWidgets.QPushButton("📊 Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        row2.addWidget(self.export_btn)

        self.del_btn = QtWidgets.QPushButton("🗑️ Delete ROI")
        self.del_btn.clicked.connect(self._delete_selected)
        row2.addWidget(self.del_btn)
        layout.addLayout(row2)

        # Row 3: Screenshot
        row3 = QtWidgets.QHBoxLayout()
        self.screenshot_btn = QtWidgets.QPushButton("📷 Screenshot (F12)")
        self.screenshot_btn.setToolTip("Capture current frame (F12)\nHold Shift for raw frame without overlay")
        self.screenshot_btn.clicked.connect(self._take_screenshot)
        row3.addWidget(self.screenshot_btn)
        layout.addLayout(row3)

        # Auto-scale graph checkbox
        self.auto_scale_checkbox = QtWidgets.QCheckBox("Auto-scale Graph (Thermal)")
        self.auto_scale_checkbox.setChecked(True)
        self.auto_scale_checkbox.setToolTip("Automatically adjust graph Y-axis to data range")
        self.auto_scale_checkbox.stateChanged.connect(self._toggle_auto_scale)
        layout.addWidget(self.auto_scale_checkbox)

    def _auto_scale_window(self):
        """Auto-scale window to fit content on startup."""
        # Process events to let layout calculate sizes
        QtWidgets.QApplication.processEvents()

        # Get screen geometry using QScreen (more reliable)
        screen = QtWidgets.QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()
        screen_width = screen_rect.width()
        screen_height = screen_rect.height()

        # Log screen info
        self.logger.info(f"Screen size: {screen_width}x{screen_height}")

        # Calculate optimal size based on screen size
        # Use 85% of screen width and 90% of screen height
        optimal_width = int(screen_width * 0.85)
        optimal_height = int(screen_height * 0.90)

        # Apply minimum sizes but don't exceed screen
        optimal_width = max(min(optimal_width, screen_width - 100), 1200)
        optimal_height = max(min(optimal_height, screen_height - 100), 750)

        # Set the window size
        self.resize(optimal_width, optimal_height)

        # Center the window on screen
        self.move(
            screen_rect.x() + (screen_width - optimal_width) // 2,
            screen_rect.y() + (screen_height - optimal_height) // 2
        )

        self.logger.info(f"Window auto-scaled to {optimal_width}x{optimal_height}")

    def _setup_timer(self):
        """Setup video update timer (now used for sync)."""
        self.timer = QtCore.QTimer()
        # Periodically sync settings to ensure thread is up to date (backup to event-driven sync)
        self.timer.timeout.connect(self._sync_settings_to_worker)
        # Note: Thread runs at its own rate, this timer just ensures state consistency
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

        # Screenshot (F12)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("F12"),
            self,
            self._take_screenshot
        )

        # Screenshot without overlay (Shift+F12)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Shift+F12"),
            self,
            lambda: self._take_screenshot(include_overlay=False)
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

        self.available_cameras = CameraManager.detect_cameras()

        if not self.available_cameras:
            self.device_combo.addItem("No cameras found", None)
            self.camera_info_label.setText("No cameras detected")
            self.logger.warning("No cameras detected")
            return

        # Block signals to prevent double-connection during population
        self.device_combo.blockSignals(True)

        # Store camera objects with their combo box index
        for i, camera in enumerate(self.available_cameras):
            self.device_combo.addItem(str(camera), i)

        # Re-enable signals
        self.device_combo.blockSignals(False)

        # Auto-connect to first camera (will only trigger once now)
        if len(self.available_cameras) > 0:
            self._on_device_changed(0)

    def _on_device_changed(self, combo_index):
        """Handle camera device selection change (Async)."""
        camera_list_index = self.device_combo.itemData(combo_index)

        if camera_list_index is None:
            return

        # Get the CameraDevice object from our stored list
        if not hasattr(self, 'available_cameras') or camera_list_index >= len(self.available_cameras):
            self.logger.error("Invalid camera index")
            return

        camera_device = self.available_cameras[camera_list_index]
        self.logger.info(f"Initiating connection to {camera_device}...")

        # Disable UI during connection
        self.device_combo.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        
        # Show status
        self.status_label.setText(f"Connecting to {camera_device.name}...")
        
        # Display loading in video label
        self.video_label.setText("Connecting...\nPlease Wait")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setStyleSheet("QLabel { background-color: #202020; color: white; font-size: 16px; }")

        # Stop existing connection/timer first
        if self.timer.isActive():
            self.timer.stop()
        self.camera_manager.disconnect()

        # Start background thread
        self.connect_thread = CameraConnectionThread(self.camera_manager, camera_device)
        self.connect_thread.finished.connect(self._on_camera_connected)
        self.connect_thread.start()

    def _on_camera_connected(self, success, camera_device, message):
        """Handle camera connection completion."""
        # Re-enable UI
        self.device_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.video_label.setText("") # Clear text (will be replaced by pixmap)
        self.video_label.setStyleSheet("") # Reset style
        
        if success:
            info = self.camera_manager.get_camera_info()
            
            # Determine camera type icon and description
            if camera_device.camera_type == "spinnaker":
                type_icon = "🎥"
                type_desc = "Spinnaker SDK"
                # Spinnaker cameras (Firefly, Blackfly) are usually visible light
                self.thermal_checkbox.blockSignals(True)
                self.thermal_checkbox.setChecked(False) 
                self.thermal_checkbox.blockSignals(False)
            elif "Boson" in camera_device.name:
                type_icon = "🌡️"
                type_desc = "Thermal"
                self.thermal_checkbox.blockSignals(True)
                self.thermal_checkbox.setChecked(True)
                self.thermal_checkbox.blockSignals(False)
            else:
                type_icon = "📹"
                type_desc = "UVC Webcam"
                self.thermal_checkbox.blockSignals(True)
                self.thermal_checkbox.setChecked(False)
                self.thermal_checkbox.blockSignals(False)

            info_text = f"{type_icon} {type_desc} | {info['width']}x{info['height']} @ {info['backend']}"
            self.camera_info_label.setText(info_text)
            self.status_label.setText(f"{camera_device.name} connected")
            # self.status_bar.showMessage(f"Connected to {camera_device.name}", 3000)
            self.logger.info(f"Successfully connected to {camera_device}")
            
            # Start timer
            self.timer.start(TIMER_INTERVAL_MS)
            
            # Update window title
            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - {camera_device.name}")
            
            # Try to connect Boson control if applicable (could be threaded too, but usually fast if port is known)
            if "Boson" in camera_device.name or "FLIR" in camera_device.name:
                # Give a brief pause for serial port to stabilize
                QtCore.QTimer.singleShot(500, self._connect_boson)
                
        else:
            self.camera_info_label.setText("Connection failed")
            self.status_label.setText("Camera connection failed")
            # self.status_bar.showMessage(f"Connection failed: {message}", 5000)
            self.video_label.setText(f"Connection Failed\n{message}\n\nTry selecting another camera.")
            self.logger.error(f"Failed to connect to {camera_device}: {message}")

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

    def _on_zoom_rect_created(self, rect):
        """Handle zoom rectangle creation."""
        # Set the manual zoom rectangle
        self.zoom_manager.set_manual_zoom_rect(list(rect))

        # Switch to manual zoom mode
        self.zoom_mode_combo.setCurrentText(ZoomMode.MANUAL.value)

        # Disable zoom drawing mode
        if self.zoom_draw_btn.isChecked():
            self.zoom_draw_btn.setChecked(False)

        self.logger.info(f"Zoom rectangle set: {rect}")
        self.zoom_status_label.setText(f"Zoom: Manual (rect set)")
        self.zoom_status_label.setStyleSheet("font-size: 8pt; color: #51cf66;")

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

        # Also update zoom ROI combo
        self._refresh_zoom_roi_combo()

    def _refresh_zoom_roi_combo(self):
        """Refresh zoom ROI selector combo box."""
        current_id = self.zoom_roi_combo.currentData()
        self.zoom_roi_combo.clear()
        self.zoom_roi_combo.addItem("None", None)

        for r in self.regions:
            self.zoom_roi_combo.addItem(f"ROI #{r['id']}", r['id'])

        # Try to restore previous selection
        if current_id is not None:
            for i in range(self.zoom_roi_combo.count()):
                if self.zoom_roi_combo.itemData(i) == current_id:
                    self.zoom_roi_combo.setCurrentIndex(i)
                    break

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

    def _sync_settings_to_worker(self):
        """Sync current settings to the worker thread."""
        if not hasattr(self, 'focus_worker'):
            return
            
        settings = {
            # Basic settings
            'paused': self.paused,
            'regions': [r.copy() for r in self.regions], # Send copy to avoid race
            'edge_threshold': self.edge_threshold,
            'focus_color': self.focus_color,
            'current_algorithm': self.current_algorithm,
            
            # Feature flags
            'thermal_preprocessing': self.thermal_preprocessing_enabled,
            'stripes_enabled': self.stripes_enabled,
            'ensemble_voting_enabled': self.ensemble_voting_enabled,
            'adaptive_edge_enabled': self.adaptive_edge_enabled,
            
            # Adaptive / Advanced settings
            'adaptive_scene_type': self.adaptive_scene_type,
            'adaptive_multi_scale': self.adaptive_multi_scale,
            
            # Boson specific (simple flags)
            'boson_connected': self.boson_controller.is_connected if self.boson_controller else False,
            'palette': self.boson_controller.current_palette if (self.boson_controller and self.thermal_checkbox.isChecked()) else None,
            'is_thermal': self.thermal_checkbox.isChecked()
        }
        self.focus_worker.update_settings(settings)

    def _on_frame_processed(self, original_frame, displayed_frame, global_score, roi_scores, stats, debug_info):
        """Handle processed frame from worker thread."""
        
        # 1. Update Focus History and Stats
        self.focus_history.append(global_score)
        self.stats_tracker.add_score(global_score)
        
        # 2. Update ROI scores (in main thread model)
        # Note: Worker sends us scores in order of regions
        if len(roi_scores) == len(self.regions):
            for i, score in enumerate(roi_scores):
                self.regions[i]['score'] = score
        
        # 3. Update Quality Indicator
        if ENABLE_FOCUS_QUALITY_INDICATOR:
            quality_level = stats.get('quality_level', 'poor')
            quality_percentage = stats.get('quality_pct', 0)
            
            quality_color = QUALITY_COLORS.get(quality_level, "#868e96")
            self.quality_status_label.setText(f"● {quality_level.title()}")
            self.quality_status_label.setStyleSheet(f"font-size: 10pt; font-weight: bold; color: {quality_color};")
            self.quality_score_label.setText(f"Score: {quality_percentage} / 100")

        # 4. Burn ROIs into display (if not already done by worker? Worker doesn't draw ROIs)
        # We need to draw ROIs here before Zoom
        # Using cv2 to draw on the 'displayed_frame' (which has peaking)
        # Make a copy if we don't want to modify the one from worker (but worker sends new object)
        final_display = displayed_frame 
        
        for r in self.regions:
            x1, y1, x2, y2 = [int(v) for v in r["rect"]]
            color = ROI_COLOR_SELECTED if (self.selected_id and r["id"] == self.selected_id) else ROI_COLOR_NORMAL
            cv2.rectangle(final_display, (x1, y1), (x2, y2), color, 2)
            label = f"ID{r['id']} W{r['weight']:.2f} S{r['score']:.0f}"
            cv2.putText(final_display, label, (x1 + 4, y1 + 18),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 5. Draw Global Focus Score
        cv2.putText(
            final_display,
            f"Focus: {global_score:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

        # 5a. Peak Detection and Indicator
        if self.peak_indicator_enabled:
            peak_detected = self.peak_detector.update(global_score)
            if self.peak_detector.is_peak_active():
                # Draw green border to indicate peak focus
                h, w = final_display.shape[:2]
                border_width = PEAK_BORDER_WIDTH
                cv2.rectangle(final_display, (0, 0), (w-1, h-1), PEAK_BORDER_COLOR, border_width)
                # Add "PEAK FOCUS" text
                cv2.putText(final_display, "PEAK FOCUS", (10, h - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, PEAK_BORDER_COLOR, 2)
                self.peak_status_label.setText("Peak: ACHIEVED!")
                self.peak_status_label.setStyleSheet("font-size: 8pt; color: #51cf66; font-weight: bold;")
            else:
                self.peak_status_label.setText("Peak: Searching...")
                self.peak_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")

        # 5b. Audio Feedback
        if self.audio_feedback_enabled:
            # Get normalized score from focus quality
            quality_pct = stats.get('quality_pct', 50)
            normalized = quality_pct / 100.0
            self.audio_feedback.play_feedback(normalized)

        # 5c. Store frames for screenshots
        self.screenshot_manager.update_frames(original_frame, final_display)

        # 6. Apply Zoom (Main thread operation)
        # ZoomManager applies zoom to the image
        final_display = self.zoom_manager.apply_zoom(final_display, self.regions)

        # 7. Update Video Label
        rgb = cv2.cvtColor(final_display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        # Create QImage directly
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        # Copy the data to ensure it persists (optional but safer for signals/async, 
        # though this runs in main thread so reference is fine till next frame)
        # Using copy() here avoids issues if underlying numpy array is recycled immediately
        self.video_label.setImage(qimg.copy())

        # 8. Update Table
        self._update_table_scores()

        # 9. Update Statistics Label
        current_stats = self.stats_tracker.get_all_stats()
        stats_text = (
            f"Current: {current_stats['current']:7.1f}\n"
            f"Min:     {current_stats['min']:7.1f}\n"
            f"Max:     {current_stats['max']:7.1f}\n"
            f"Mean:    {current_stats['mean']:7.1f}\n"
            f"Std:     {current_stats['std']:7.1f}"
        )
        self.stats_label.setText(stats_text)

        # 10. Update Ensemble UI
        if self.ensemble_voting_enabled and 'ensemble_details' in stats:
            details = stats['ensemble_details']
            if details:
                # Update confidence label
                if hasattr(self, 'ensemble_confidence_label') and SHOW_CONFIDENCE_INDICATOR:
                    confidence = details.get('confidence', 0)
                    quality = details.get('consensus_quality', 'unknown')
                    self.ensemble_confidence_label.setText(
                        f"Confidence: {confidence*100:.0f}% ({quality.title()})"
                    )
                    quality_color = QUALITY_COLORS.get(quality, "#868e96")
                    self.ensemble_confidence_label.setStyleSheet(
                        f"font-size: 9pt; font-weight: bold; color: {quality_color};"
                    )

                # Update individual scores
                if self.show_all_algorithms and hasattr(self, 'algorithm_score_labels'):
                    all_scores = details.get('all_scores', {})
                    best_algo = details.get('best_algorithm', '')
                    for algo_name, score in all_scores.items():
                        if algo_name in self.algorithm_score_labels:
                            marker = " ⭐" if algo_name == best_algo else ""
                            self.algorithm_score_labels[algo_name].setText(
                                f"{algo_name}: {score:.1f}{marker}"
                            )

        # 11. Update Graph
        self._update_graph()

        # 12. Update Histogram
        if self.histogram_enabled and original_frame is not None:
            self._update_histogram(original_frame)

        # 13. Update Smart Palette Switcher
        self.palette_switcher.update(self.focus_history)
        self._update_palette_status()

    def _update_histogram(self, frame: np.ndarray):
        """Update the histogram display."""
        hist_img = self.histogram_generator.generate(frame)
        if hist_img is not None:
            qg = QtGui.QImage(
                hist_img.data,
                HISTOGRAM_WIDTH,
                HISTOGRAM_HEIGHT,
                HISTOGRAM_WIDTH * 3,
                QtGui.QImage.Format_BGR888,
            )
            self.histogram_label.setPixmap(QtGui.QPixmap.fromImage(qg))

    def _update_table_scores(self):
        """Helper to update scores in the table."""
        for row in range(self.table.rowCount()):
            rid = int(self.table.item(row, 0).text())
            r = self._find_region(rid)
            if r:
                self.table.item(row, 2).setText(f"{r.get('score', 0):.0f}")

    def _update_palette_status(self):
        """Update palette status label."""
        if self.palette_switcher.is_active() and not self.focus_mode_btn.isChecked():
            self.palette_status_label.setText("Focus Mode: Active (Auto)")
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: #ffa94d; font-weight: bold;")
        elif not self.palette_switcher.is_active() and not self.focus_mode_btn.isChecked():
            self.palette_status_label.setText("Focus Mode: Inactive")
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")

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
        
        self._sync_settings_to_worker()

    def _edge_changed(self, val):
        """Handle edge threshold change."""
        self.edge_threshold = val
        self.th_label.setText(f"Threshold: {val}")
        self._sync_settings_to_worker()

    def _pick_color(self):
        """Open color picker dialog."""
        qcolor = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self.focus_color[2], self.focus_color[1], self.focus_color[0])
        )
        if qcolor.isValid():
            self.focus_color = (qcolor.blue(), qcolor.green(), qcolor.red())
            self.logger.info(f"Peaking color changed to {self.focus_color}")
            self._sync_settings_to_worker()

    def _on_theme_changed(self, theme_name):
        """Handle theme change."""
        # This requires reference to ThemeManager from main()
        pass

    def _on_algorithm_changed(self, algorithm_name):
        """Handle focus algorithm change."""
        self.current_algorithm = algorithm_name
        self.logger.info(f"Focus algorithm changed to: {algorithm_name}")
        self._sync_settings_to_worker()

    def _toggle_thermal_preprocessing(self, state):
        """Toggle thermal preprocessing."""
        self.thermal_preprocessing_enabled = (state == QtCore.Qt.Checked)
        self.logger.info(f"Thermal preprocessing: {'enabled' if self.thermal_preprocessing_enabled else 'disabled'}")
        self._sync_settings_to_worker()

    def _toggle_adaptive_edge(self, state):
        """Toggle adaptive edge detection."""
        self.adaptive_edge_enabled = (state == QtCore.Qt.Checked)
        self.logger.info(f"Adaptive edge detection: {'enabled' if self.adaptive_edge_enabled else 'disabled'}")
        self._sync_settings_to_worker()

    def _on_thermal_toggle(self, state):
        """Handle thermal camera checkbox toggle."""
        is_thermal = (state == QtCore.Qt.Checked)
        self.logger.info(f"Thermal mode {'enabled' if is_thermal else 'disabled'}")
        self._sync_settings_to_worker()

    def _toggle_stripes(self, state):
        """Toggle stripe pattern for focus peaking."""
        self.stripes_enabled = (state == QtCore.Qt.Checked)
        self.logger.info(f"Stripe pattern: {'enabled' if self.stripes_enabled else 'disabled'}")
        self._sync_settings_to_worker()

    def _on_scene_type_changed(self, scene_type_text):
        """Handle scene type selection change."""
        # Map UI text to internal scene type
        scene_type_map = {
            "Auto": "auto",
            "Low Contrast": "low_contrast",
            "High Detail": "high_detail",
            "Thermal": "thermal"
        }
        self.adaptive_scene_type = scene_type_map.get(scene_type_text, "auto")
        self.adaptive_edge_detector.set_scene_type(self.adaptive_scene_type)
        self.logger.info(f"Adaptive scene type changed to: {self.adaptive_scene_type}")
        self._sync_settings_to_worker()

    def _toggle_multi_scale(self, state):
        """Toggle multi-scale detection."""
        self.adaptive_multi_scale = (state == QtCore.Qt.Checked)
        self.adaptive_edge_detector.set_multi_scale(self.adaptive_multi_scale)
        self.logger.info(f"Multi-scale detection: {'enabled' if self.adaptive_multi_scale else 'disabled'}")
        self._sync_settings_to_worker()

    def _toggle_ensemble_voting(self, state):
        """Toggle ensemble voting system."""
        self.ensemble_voting_enabled = (state == QtCore.Qt.Checked)
        self.logger.info(f"Ensemble voting: {'enabled' if self.ensemble_voting_enabled else 'disabled'}")
        if self.ensemble_voting_enabled:
            self.focus_ensemble.reset_history()
        self._sync_settings_to_worker()

    def _toggle_show_algorithms(self, state):
        """Toggle display of all algorithm scores."""
        self.show_all_algorithms = (state == QtCore.Qt.Checked)
        if hasattr(self, 'algorithm_scores_widget'):
            self.algorithm_scores_widget.setVisible(self.show_all_algorithms)
        self.logger.debug(f"Show all algorithms: {self.show_all_algorithms}")
        # Not needed to sync to worker, purely UI

    def _toggle_auto_palette_switch(self, state):
        """Toggle automatic palette switching."""
        self.auto_palette_switch_enabled = (state == QtCore.Qt.Checked)
        self.palette_switcher.enable_auto_switch(self.auto_palette_switch_enabled)
        self.logger.info(f"Auto palette switch: {'enabled' if self.auto_palette_switch_enabled else 'disabled'}")
        # Syncing might be needed if switching palette happens in worker? 
        # Palette switching logic (SmartPaletteSwitcher) is in main thread (update called in _on_frame_processed)
        # But applying the palette happens in worker. 
        # The worker uses 'palette' from settings.
        # So we should sync.
        self._sync_settings_to_worker()

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
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        self._sync_settings_to_worker()

    def _toggle_pause(self):
        """Toggle video pause."""
        self.paused = not self.paused
        status = "paused" if self.paused else "running"
        self.status_label.setText(f"Video {status}")
        self.logger.info(f"Video {status}")
        self._sync_settings_to_worker()

    def _on_zoom_mode_changed(self, mode_text):
        """Handle zoom mode change."""
        mode = ZoomMode(mode_text)
        self.zoom_manager.set_mode(mode)
        self.zoom_status_label.setText(f"Zoom: {mode.value}")
        self.logger.info(f"Zoom mode changed to: {mode.value}")

        # Update UI state based on mode
        self.zoom_draw_btn.setEnabled(mode == ZoomMode.MANUAL)
        self.zoom_roi_combo.setEnabled(mode == ZoomMode.AUTO_ROI)
        self.zoom_level_slider.setEnabled(mode == ZoomMode.MANUAL)
        # Zoom happens in main thread, so no sync necessary?
        # Actually worker doesn't need zoom info.

    def _on_zoom_level_changed(self, value):
        """Handle zoom level slider change."""
        level = value / 10.0  # Convert 10-40 to 1.0-4.0
        self.zoom_manager.set_zoom_level(level)
        self.zoom_level_label.setText(f"Level: {level:.1f}x")

    def _on_zoom_roi_changed(self, index):
        """Handle zoom ROI selection change."""
        roi_id = self.zoom_roi_combo.itemData(index)
        self.zoom_manager.set_target_roi(roi_id)
        if roi_id:
            self.logger.debug(f"Zoom target set to ROI {roi_id}")

    def _zoom_reset_pan(self):
        """Reset zoom pan to center (legacy - use _reset_zoom_and_pan instead)."""
        # Just call the full reset function
        self._reset_zoom_and_pan()

    def _reset_zoom_and_pan(self):
        """Reset both zoom level and pan to defaults (R key)."""
        # Reset pan
        self.zoom_manager.reset_pan()

        # Clear any manual zoom rectangle
        self.zoom_manager.set_manual_zoom_rect(None)

        # Reset zoom level to 1.0x
        self.zoom_level_slider.setValue(10)  # 10 = 1.0x

        # Clear any zoom drawing
        if self.zoom_draw_btn.isChecked():
            self.zoom_draw_btn.setChecked(False)
        else:
            self.video_label.set_zoom_drawing_mode(False)

        self.logger.info("Zoom and pan reset to defaults (R key)")

    def _adjust_zoom(self, delta: float):
        """Adjust zoom level by delta (+/- keys)."""
        current_value = self.zoom_level_slider.value()
        new_value = current_value + int(delta * 10)  # delta * 10 because slider is in 0.1x increments

        # Clamp to valid range
        new_value = max(10, min(40, new_value))

        self.zoom_level_slider.setValue(new_value)
        level = new_value / 10.0
        self.logger.debug(f"Zoom adjusted to {level:.1f}x")

    def _toggle_zoom_drawing(self, checked):
        """Toggle zoom rectangle drawing mode."""
        if checked:
            self.zoom_draw_btn.setText("Cancel Drawing")
            self.video_label.set_zoom_drawing_mode(True)
            self.logger.info("Zoom drawing mode activated - click and drag to define zoom area")
        else:
            self.zoom_draw_btn.setText("Draw Zoom Area")
            self.video_label.set_zoom_drawing_mode(False)
            self.logger.info("Zoom drawing mode deactivated")

    def _toggle_auto_scale(self, state):
        """Toggle graph auto-scaling."""
        self.graph_adaptive = (state == QtCore.Qt.Checked)
        if not self.graph_adaptive:
            # Reset to default when disabled
            self.graph_max = DEFAULT_GRAPH_MAX_FOCUS
            self.graph_min = 0

    # ========================================================================
    # New Feature Handlers
    # ========================================================================

    def _toggle_audio_feedback(self, state):
        """Toggle audio focus feedback."""
        self.audio_feedback_enabled = (state == QtCore.Qt.Checked)
        self.audio_feedback.set_enabled(self.audio_feedback_enabled)

        if self.audio_feedback_enabled:
            self.audio_status_label.setText("Audio: Active")
            self.audio_status_label.setStyleSheet("font-size: 8pt; color: #51cf66;")
        else:
            self.audio_status_label.setText("Audio: Off")
            self.audio_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")

        self.logger.info(f"Audio feedback {'enabled' if self.audio_feedback_enabled else 'disabled'}")

    def _toggle_histogram(self, state):
        """Toggle live histogram display."""
        self.histogram_enabled = (state == QtCore.Qt.Checked)
        self.histogram_generator.set_enabled(self.histogram_enabled)
        self.histogram_container.setVisible(self.histogram_enabled)
        self.logger.info(f"Histogram {'enabled' if self.histogram_enabled else 'disabled'}")

    def _toggle_histogram_rgb(self, state):
        """Toggle RGB histogram mode."""
        self.histogram_generator.show_rgb = (state == QtCore.Qt.Checked)
        self.logger.debug(f"Histogram RGB mode: {self.histogram_generator.show_rgb}")

    def _toggle_peak_indicator(self, state):
        """Toggle focus peak indicator."""
        self.peak_indicator_enabled = (state == QtCore.Qt.Checked)
        if not self.peak_indicator_enabled:
            self.peak_detector.reset()
            self.peak_status_label.setText("Peak: Disabled")
            self.peak_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        else:
            self.peak_status_label.setText("Peak: Searching...")
            self.peak_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        self.logger.info(f"Peak indicator {'enabled' if self.peak_indicator_enabled else 'disabled'}")

    def _take_screenshot(self, include_overlay: bool = True):
        """Take a screenshot of the current frame."""
        filepath = self.screenshot_manager.capture(include_overlay=include_overlay)

        if filepath:
            self.status_label.setText(f"Screenshot saved: {Path(filepath).name}")
            QtWidgets.QMessageBox.information(
                self, "Screenshot Saved",
                f"Screenshot saved to:\n{filepath}"
            )
        else:
            self.status_label.setText("Screenshot failed - no frame available")
            QtWidgets.QMessageBox.warning(
                self, "Screenshot Failed",
                "No frame available to capture"
            )

    def _refresh_profiles(self):
        """Refresh the profiles combo box."""
        current = self.profile_combo.currentText() if hasattr(self, 'profile_combo') else None

        if hasattr(self, 'profile_combo'):
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            profiles = self.profile_manager.list_profiles()
            self.profile_combo.addItems(profiles)

            # Restore selection
            if current and current in profiles:
                self.profile_combo.setCurrentText(current)
            self.profile_combo.blockSignals(False)

    def _on_profile_selected(self, profile_name):
        """Handle profile selection from combo box."""
        if not profile_name:
            return

        config = self.profile_manager.load_profile(profile_name)
        if config:
            self._apply_profile_config(config)
            self.status_label.setText(f"Profile loaded: {profile_name}")

    def _save_profile_as(self):
        """Save current settings to a new profile."""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Profile",
            "Enter profile name:",
            QtWidgets.QLineEdit.Normal,
            ""
        )

        if ok and name:
            # Sanitize name
            name = name.strip().replace("/", "_").replace("\\", "_")

            config = self._get_current_config()
            if self.profile_manager.save_profile(name, config):
                self._refresh_profiles()
                self.profile_combo.setCurrentText(name)
                QtWidgets.QMessageBox.information(
                    self, "Profile Saved",
                    f"Profile '{name}' saved successfully"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Save Failed",
                    f"Failed to save profile '{name}'"
                )

    def _delete_profile(self):
        """Delete the currently selected profile."""
        profile_name = self.profile_combo.currentText()

        if profile_name == "Default":
            QtWidgets.QMessageBox.warning(
                self, "Cannot Delete",
                "Cannot delete the Default profile"
            )
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{profile_name}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            if self.profile_manager.delete_profile(profile_name):
                self._refresh_profiles()
                self.status_label.setText(f"Profile deleted: {profile_name}")
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Delete Failed",
                    f"Failed to delete profile '{profile_name}'"
                )

    def _get_current_config(self) -> dict:
        """Get current settings as a config dictionary."""
        return {
            "focus_color": list(self.focus_color),
            "edge_threshold": self.edge_threshold,
            "regions": [
                {"id": r["id"], "rect": r["rect"], "weight": r["weight"]}
                for r in self.regions
            ],
            "graph_adaptive": self.graph_adaptive,
            "focus_algorithm": self.current_algorithm,
            "thermal_preprocessing": self.thermal_preprocessing_enabled,
            "ensemble_voting_enabled": self.ensemble_voting_enabled,
            "show_all_algorithms": self.show_all_algorithms,
            "auto_palette_switch_enabled": self.auto_palette_switch_enabled,
            "adaptive_edge_enabled": self.adaptive_edge_enabled,
            "adaptive_scene_type": self.adaptive_scene_type,
            "adaptive_multi_scale": self.adaptive_multi_scale,
            "stripes_enabled": self.stripes_enabled,
            "audio_feedback_enabled": self.audio_feedback_enabled,
            "histogram_enabled": self.histogram_enabled,
            "peak_indicator_enabled": self.peak_indicator_enabled,
        }

    def _apply_profile_config(self, config: dict):
        """Apply a configuration profile to the UI."""
        try:
            # Apply basic settings
            if "focus_color" in config:
                self.focus_color = tuple(config["focus_color"])
            if "edge_threshold" in config:
                self.edge_threshold = config["edge_threshold"]
                self.th_slider.setValue(self.edge_threshold)
            if "graph_adaptive" in config:
                self.graph_adaptive = config["graph_adaptive"]
                self.auto_scale_checkbox.setChecked(self.graph_adaptive)

            # Focus algorithm
            if "focus_algorithm" in config and config["focus_algorithm"] in FOCUS_ALGORITHMS:
                self.current_algorithm = config["focus_algorithm"]
                self.algorithm_combo.setCurrentText(self.current_algorithm)

            # Feature toggles
            if "thermal_preprocessing" in config:
                self.thermal_preprocessing_enabled = config["thermal_preprocessing"]
                self.thermal_preprocessing_checkbox.setChecked(self.thermal_preprocessing_enabled)
            if "ensemble_voting_enabled" in config:
                self.ensemble_voting_enabled = config["ensemble_voting_enabled"]
                self.ensemble_voting_checkbox.setChecked(self.ensemble_voting_enabled)
            if "adaptive_edge_enabled" in config:
                self.adaptive_edge_enabled = config["adaptive_edge_enabled"]
                self.adaptive_edge_checkbox.setChecked(self.adaptive_edge_enabled)
            if "stripes_enabled" in config:
                self.stripes_enabled = config["stripes_enabled"]
                self.stripes_checkbox.setChecked(self.stripes_enabled)

            # New features
            if "audio_feedback_enabled" in config:
                self.audio_feedback_enabled = config["audio_feedback_enabled"]
                self.audio_feedback_checkbox.setChecked(self.audio_feedback_enabled)
                self.audio_feedback.set_enabled(self.audio_feedback_enabled)
            if "histogram_enabled" in config:
                self.histogram_enabled = config["histogram_enabled"]
                self.histogram_checkbox.setChecked(self.histogram_enabled)
                self.histogram_generator.set_enabled(self.histogram_enabled)
                self.histogram_container.setVisible(self.histogram_enabled)
            if "peak_indicator_enabled" in config:
                self.peak_indicator_enabled = config["peak_indicator_enabled"]
                self.peak_indicator_checkbox.setChecked(self.peak_indicator_enabled)

            # Load regions
            if "regions" in config:
                self.regions = [
                    {
                        "id": r["id"],
                        "rect": r["rect"],
                        "weight": r.get("weight", 1.0),
                        "score": 0.0,
                    }
                    for r in config["regions"]
                ]
                self.next_id = max((r["id"] for r in self.regions), default=0) + 1
                self._sync_rois_to_label()
                self._refresh_table()

            self._sync_settings_to_worker()
            self.logger.info("Profile configuration applied")

        except Exception as e:
            self.logger.error(f"Failed to apply profile config: {e}")

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
                "adaptive_edge_enabled": self.adaptive_edge_enabled,
                "adaptive_scene_type": self.adaptive_scene_type,
                "adaptive_multi_scale": self.adaptive_multi_scale,
                "stripes_enabled": self.stripes_enabled,
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

            # Load adaptive edge detection settings (Phase 5)
            if "adaptive_edge_enabled" in config:
                self.adaptive_edge_enabled = config["adaptive_edge_enabled"]
                self.adaptive_edge_checkbox.setChecked(self.adaptive_edge_enabled)
            if "adaptive_scene_type" in config:
                self.adaptive_scene_type = config["adaptive_scene_type"]

            # Load stripe pattern setting
            if "stripes_enabled" in config:
                self.stripes_enabled = config["stripes_enabled"]
                self.stripes_checkbox.setChecked(self.stripes_enabled)
                # Map internal type back to UI text
                scene_type_ui_map = {
                    "auto": "Auto",
                    "low_contrast": "Low Contrast",
                    "high_detail": "High Detail",
                    "thermal": "Thermal"
                }
                ui_text = scene_type_ui_map.get(self.adaptive_scene_type, "Auto")
                self.scene_type_combo.setCurrentText(ui_text)
                self.adaptive_edge_detector.set_scene_type(self.adaptive_scene_type)
            if "adaptive_multi_scale" in config:
                self.adaptive_multi_scale = config["adaptive_multi_scale"]
                self.multi_scale_checkbox.setChecked(self.adaptive_multi_scale)
                self.adaptive_edge_detector.set_multi_scale(self.adaptive_multi_scale)

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

        # Handle different modes
        current_mode = self.mode_stack.currentIndex()

        if current_mode == 1:
            # Calibration Mode
            self._update_calibration_mode(frame)
            return

        # Focus Mode (original behavior) - currentIndex == 0

        # Apply focus peaking
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply thermal preprocessing if enabled
        if self.thermal_preprocessing_enabled:
            gray = thermal_preprocess(gray, enhance_contrast=True, reduce_noise=False)

        # Animate stripe pattern (increment offset each frame, wrap at 8)
        if self.stripes_enabled:
            self.stripe_offset = (self.stripe_offset + 1) % 8

        # Choose edge detection method: adaptive or standard
        if self.adaptive_edge_enabled:
            # Use adaptive edge detection
            displayed = self.adaptive_edge_detector.create_adaptive_focus_peaking(
                frame, gray, self.edge_threshold, self.focus_color, PEAKING_ALPHA,
                self.adaptive_scene_type, self.stripes_enabled, self.stripe_offset
            )

            # Update scene info display
            if hasattr(self, 'scene_info_label'):
                scene_info = self.adaptive_edge_detector.get_scene_info(gray)
                detected_type = scene_info.get('detected_scene', 'unknown')
                contrast = scene_info.get('contrast', 0)
                self.scene_info_label.setText(f"Detected: {detected_type} (σ={contrast:.1f})")
        else:
            # Use standard focus peaking
            displayed = create_focus_peaking_overlay(
                frame, self.edge_threshold, self.focus_color, PEAKING_ALPHA,
                self.stripes_enabled, self.stripe_offset
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

        # Apply zoom before display
        displayed = self.zoom_manager.apply_zoom(displayed, self.regions)

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
            self.palette_status_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        # If manual button is checked, keep manual status (set in _toggle_focus_mode_manual)

        # Update graph
        self._update_graph()

    def _update_calibration_mode(self, frame: np.ndarray):
        """Update calibration mode display and processing."""
        # Update calibration GUI with current frame
        if hasattr(self, 'calibration_gui') and self.calibration_gui is not None:
            self.calibration_gui.update_frame(frame)

            # Display frame with pattern detection overlay
            displayed = frame.copy()

            # If pattern is detected, draw it
            if self.calibration_gui.pattern_detected and self.calibration_gui.detected_corners is not None:
                displayed = self.calibration_gui.pattern_detector.draw_pattern(
                    displayed,
                    self.calibration_gui.detected_corners,
                    True
                )

                # Add status text
                cv2.putText(
                    displayed,
                    "Pattern Detected - Ready to Capture",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )
            else:
                cv2.putText(
                    displayed,
                    "No Pattern Detected",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2
                )

            # Update calibration video display
            rgb = cv2.cvtColor(displayed, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)

            # Scale to fit label
            pixmap = QtGui.QPixmap.fromImage(qimg)
            scaled_pixmap = pixmap.scaled(
                self.cal_video_label.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            self.cal_video_label.setPixmap(scaled_pixmap)

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
    # Event Handlers
    # ========================================================================

    def eventFilter(self, obj, event):
        """
        Event filter to intercept keyboard events before child widgets receive them.
        This ensures pan/zoom shortcuts work even when sliders/tables have focus.
        """
        if event.type() == QtCore.QEvent.KeyPress and self.zoom_manager.mode != ZoomMode.OFF:
            key = event.key()

            # Pan step size (in pixels)
            pan_step = 20

            # WASD for panning (no arrow keys to avoid GUI conflicts)
            if key == QtCore.Qt.Key_A:
                self.zoom_manager.pan(-pan_step, 0)
                self.logger.debug("Panned left (A)")
                return True  # Event handled
            elif key == QtCore.Qt.Key_D:
                self.zoom_manager.pan(pan_step, 0)
                self.logger.debug("Panned right (D)")
                return True
            elif key == QtCore.Qt.Key_W:
                self.zoom_manager.pan(0, -pan_step)
                self.logger.debug("Panned up (W)")
                return True
            elif key == QtCore.Qt.Key_S:
                self.zoom_manager.pan(0, pan_step)
                self.logger.debug("Panned down (S)")
                return True
            elif key == QtCore.Qt.Key_R:
                # Reset both zoom and pan
                self._reset_zoom_and_pan()
                return True
            elif key == QtCore.Qt.Key_Equal or key == QtCore.Qt.Key_Plus:
                # Zoom in
                self._adjust_zoom(0.2)
                return True
            elif key == QtCore.Qt.Key_Minus or key == QtCore.Qt.Key_Underscore:
                # Zoom out
                self._adjust_zoom(-0.2)
                return True

        # Pass event to base class
        return super().eventFilter(obj, event)

    def keyPressEvent(self, ev):
        """Handle keyboard input - kept for compatibility."""
        # Most keys are now handled by eventFilter
        # This is kept as a fallback
        super().keyPressEvent(ev)

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
