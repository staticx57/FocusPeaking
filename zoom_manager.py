#!/usr/bin/env python3
"""
Zoom Manager for FLIR Boson Focus Utility

Provides manual and automatic zooming capabilities for ROI inspection.
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ZoomMode(Enum):
    """Zoom mode enumeration."""
    OFF = "Off"
    MANUAL = "Manual"
    AUTO_ROI = "Auto-ROI"
    AUTO_ALL_ROIS = "Auto-All-ROIs"


class ZoomManager:
    """
    Manages zooming functionality for video display.

    Supports manual zoom (user-defined rectangle) and automatic zoom
    (based on ROIs). Provides smooth zooming and panning controls.
    """

    def __init__(self):
        """Initialize the zoom manager."""
        self.mode = ZoomMode.OFF
        self.zoom_level = 1.0
        self.min_zoom = 1.0
        self.max_zoom = 4.0

        # Manual zoom rectangle (x1, y1, x2, y2) in frame coordinates
        self.manual_zoom_rect: Optional[List[int]] = None

        # Auto-zoom settings
        self.target_roi_id: Optional[int] = None  # For AUTO_ROI mode
        self.padding_percent = 10  # Padding around ROIs (percentage)

        # Pan offset for manual mode (dx, dy)
        self.pan_offset = [0, 0]

        logger.debug("ZoomManager initialized")

    def set_mode(self, mode: ZoomMode) -> None:
        """
        Set the zoom mode.

        Args:
            mode: ZoomMode enum value
        """
        if self.mode != mode:
            self.mode = mode
            self.pan_offset = [0, 0]  # Reset pan when changing modes
            logger.info(f"Zoom mode set to: {mode.value}")

    def set_zoom_level(self, level: float) -> None:
        """
        Set the zoom level.

        Args:
            level: Zoom level (1.0 = no zoom, 4.0 = 4x zoom)
        """
        self.zoom_level = max(self.min_zoom, min(self.max_zoom, level))
        logger.debug(f"Zoom level set to: {self.zoom_level:.2f}x")

    def set_manual_zoom_rect(self, rect: Optional[List[int]]) -> None:
        """
        Set the manual zoom rectangle.

        Args:
            rect: [x1, y1, x2, y2] or None to clear
        """
        self.manual_zoom_rect = rect
        if rect:
            logger.debug(f"Manual zoom rect set to: {rect}")

    def set_target_roi(self, roi_id: Optional[int]) -> None:
        """
        Set the target ROI for AUTO_ROI mode.

        Args:
            roi_id: ROI ID to zoom to, or None for no target
        """
        self.target_roi_id = roi_id
        logger.debug(f"Target ROI set to: {roi_id}")

    def pan(self, dx: int, dy: int) -> None:
        """
        Pan the view (for manual zoom mode).

        Args:
            dx: Horizontal pan amount
            dy: Vertical pan amount
        """
        self.pan_offset[0] += dx
        self.pan_offset[1] += dy

    def reset_pan(self) -> None:
        """Reset pan offset to center."""
        self.pan_offset = [0, 0]

    def get_zoom_rect(
        self,
        frame_shape: Tuple[int, int],
        regions: Optional[List[Dict]] = None
    ) -> Tuple[int, int, int, int]:
        """
        Calculate the zoom rectangle based on current mode and settings.

        Args:
            frame_shape: (height, width) of the frame
            regions: List of ROI dictionaries (for auto modes)

        Returns:
            Tuple of (x1, y1, x2, y2) defining the zoom area
        """
        h, w = frame_shape

        if self.mode == ZoomMode.OFF:
            return (0, 0, w, h)

        elif self.mode == ZoomMode.MANUAL:
            if self.manual_zoom_rect:
                return self._apply_pan_and_zoom(self.manual_zoom_rect, w, h)
            else:
                # No manual rect set, zoom from center of frame
                center_rect = [0, 0, w, h]
                return self._apply_pan_and_zoom(center_rect, w, h)

        elif self.mode == ZoomMode.AUTO_ROI:
            if not regions or self.target_roi_id is None:
                return (0, 0, w, h)

            # Find target ROI
            target_roi = None
            for r in regions:
                if r.get("id") == self.target_roi_id:
                    target_roi = r
                    break

            if not target_roi:
                return (0, 0, w, h)

            # Get ROI rect with padding
            x1, y1, x2, y2 = target_roi["rect"]
            return self._add_padding(x1, y1, x2, y2, w, h)

        elif self.mode == ZoomMode.AUTO_ALL_ROIS:
            if not regions:
                return (0, 0, w, h)

            # Find bounding box of all ROIs
            all_x1 = min(r["rect"][0] for r in regions)
            all_y1 = min(r["rect"][1] for r in regions)
            all_x2 = max(r["rect"][2] for r in regions)
            all_y2 = max(r["rect"][3] for r in regions)

            return self._add_padding(all_x1, all_y1, all_x2, all_y2, w, h)

        return (0, 0, w, h)

    def _apply_pan_and_zoom(
        self,
        rect: List[int],
        frame_w: int,
        frame_h: int
    ) -> Tuple[int, int, int, int]:
        """
        Apply zoom level and pan offset to a rectangle.

        Args:
            rect: [x1, y1, x2, y2] base rectangle
            frame_w: Frame width
            frame_h: Frame height

        Returns:
            Adjusted (x1, y1, x2, y2)
        """
        x1, y1, x2, y2 = rect

        # Calculate center
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        # Apply pan offset
        cx += self.pan_offset[0]
        cy += self.pan_offset[1]

        # Calculate new dimensions based on zoom level
        w = x2 - x1
        h = y2 - y1

        new_w = int(w / self.zoom_level)
        new_h = int(h / self.zoom_level)

        # Calculate new rectangle
        new_x1 = max(0, cx - new_w // 2)
        new_y1 = max(0, cy - new_h // 2)
        new_x2 = min(frame_w, cx + new_w // 2)
        new_y2 = min(frame_h, cy + new_h // 2)

        return (new_x1, new_y1, new_x2, new_y2)

    def _add_padding(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        frame_w: int,
        frame_h: int
    ) -> Tuple[int, int, int, int]:
        """
        Add padding around a rectangle.

        Args:
            x1, y1, x2, y2: Original rectangle
            frame_w: Frame width
            frame_h: Frame height

        Returns:
            Padded (x1, y1, x2, y2)
        """
        w = x2 - x1
        h = y2 - y1

        pad_x = int(w * self.padding_percent / 100)
        pad_y = int(h * self.padding_percent / 100)

        new_x1 = max(0, x1 - pad_x)
        new_y1 = max(0, y1 - pad_y)
        new_x2 = min(frame_w, x2 + pad_x)
        new_y2 = min(frame_h, y2 + pad_y)

        return (new_x1, new_y1, new_x2, new_y2)

    def apply_zoom(
        self,
        frame: np.ndarray,
        regions: Optional[List[Dict]] = None
    ) -> np.ndarray:
        """
        Apply zoom to a frame.

        Args:
            frame: Input frame
            regions: Optional list of ROIs (for auto modes)

        Returns:
            Zoomed frame
        """
        if self.mode == ZoomMode.OFF:
            return frame

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self.get_zoom_rect((h, w), regions)

        # Validate coordinates
        x1 = max(0, min(w - 1, x1))
        x2 = max(x1 + 1, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(y1 + 1, min(h, y2))

        # Crop to zoom area
        zoomed = frame[y1:y2, x1:x2].copy()

        # Scale to original frame size
        if zoomed.size > 0:
            zoomed = cv2.resize(zoomed, (w, h), interpolation=cv2.INTER_LINEAR)
            return zoomed
        else:
            return frame

    def get_status(self) -> Dict[str, any]:
        """
        Get current zoom status.

        Returns:
            Dictionary with status information
        """
        return {
            'mode': self.mode.value,
            'zoom_level': self.zoom_level,
            'manual_rect': self.manual_zoom_rect,
            'target_roi_id': self.target_roi_id,
            'pan_offset': self.pan_offset.copy(),
        }
