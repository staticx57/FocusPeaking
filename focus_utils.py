"""
Focus metric utilities for FLIR Boson Focus Peaking.

This module provides focus calculation functions using various methods
including Laplacian variance, gradient magnitude, and frequency domain analysis.
"""

import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Focus Metric Calculations
# ============================================================================

def laplacian_focus_metric(gray: np.ndarray) -> float:
    """
    Calculate focus metric using Laplacian variance.

    Higher values indicate better focus. This is a fast, reliable metric
    suitable for real-time applications.

    Args:
        gray: Grayscale image (numpy array)

    Returns:
        Focus score (higher = better focus)
    """
    if gray.size == 0:
        logger.warning("Empty image provided to laplacian_focus_metric")
        return 0.0

    try:
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = float(laplacian.var())
        return variance
    except Exception as e:
        logger.error(f"Error calculating Laplacian focus: {e}")
        return 0.0


def gradient_focus_metric(gray: np.ndarray) -> float:
    """
    Calculate focus metric using gradient magnitude.

    Uses Sobel operators to compute gradients in x and y directions.

    Args:
        gray: Grayscale image (numpy array)

    Returns:
        Focus score (higher = better focus)
    """
    if gray.size == 0:
        return 0.0

    try:
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        return float(gradient_magnitude.var())
    except Exception as e:
        logger.error(f"Error calculating gradient focus: {e}")
        return 0.0


def normalized_variance_focus(gray: np.ndarray) -> float:
    """
    Calculate normalized variance focus metric.

    Simple variance-based metric normalized by mean intensity.

    Args:
        gray: Grayscale image (numpy array)

    Returns:
        Normalized focus score
    """
    if gray.size == 0:
        return 0.0

    try:
        mean = gray.mean()
        if mean == 0:
            return 0.0
        variance = gray.var()
        return float(variance / mean)
    except Exception as e:
        logger.error(f"Error calculating normalized variance: {e}")
        return 0.0


def tenengrad_focus_metric(gray: np.ndarray, ksize: int = 3) -> float:
    """
    Calculate focus metric using Tenengrad (Sobel-based gradient).

    Tenengrad is excellent for fine detail detection and is one of the
    best-performing focus measures according to research. It uses Sobel
    gradients with magnitude thresholding to reduce noise influence.

    Args:
        gray: Grayscale image (numpy array)
        ksize: Sobel kernel size (3, 5, or 7)

    Returns:
        Focus score (higher = better focus)
    """
    if gray.size == 0:
        logger.warning("Empty image provided to tenengrad_focus_metric")
        return 0.0

    try:
        # Compute Sobel gradients
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=ksize)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=ksize)

        # Compute gradient magnitude
        magnitude = np.sqrt(gx**2 + gy**2)

        # Apply threshold to reduce noise influence
        threshold = np.mean(magnitude)
        magnitude_thresholded = magnitude[magnitude > threshold]

        # Return mean of thresholded magnitudes
        if magnitude_thresholded.size > 0:
            return float(np.mean(magnitude_thresholded))
        else:
            return 0.0

    except Exception as e:
        logger.error(f"Error calculating Tenengrad focus: {e}")
        return 0.0


def brenner_gradient_metric(gray: np.ndarray) -> float:
    """
    Calculate focus metric using Brenner gradient.

    Brenner gradient is a fast, simple focus measure that uses
    horizontal differences with 2-pixel spacing. It's computationally
    efficient and suitable for real-time applications.

    Args:
        gray: Grayscale image (numpy array)

    Returns:
        Focus score (higher = better focus)
    """
    if gray.size == 0:
        return 0.0

    try:
        # Compute horizontal gradient with 2-pixel spacing
        # This is more robust to noise than 1-pixel spacing
        if gray.shape[1] < 3:
            return 0.0

        diff = gray[:, 2:].astype(np.float64) - gray[:, :-2].astype(np.float64)

        # Return sum of squared differences
        return float(np.sum(diff**2))

    except Exception as e:
        logger.error(f"Error calculating Brenner gradient: {e}")
        return 0.0


def variance_of_laplacian_metric(gray: np.ndarray) -> float:
    """
    Alternative implementation of Laplacian variance with additional filtering.

    This variant applies slight Gaussian blur before Laplacian to reduce
    noise sensitivity while maintaining edge detection capability.

    Args:
        gray: Grayscale image (numpy array)

    Returns:
        Focus score (higher = better focus)
    """
    if gray.size == 0:
        return 0.0

    try:
        # Apply slight Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # Compute Laplacian
        laplacian = cv2.Laplacian(blurred, cv2.CV_64F)

        # Return variance
        return float(laplacian.var())

    except Exception as e:
        logger.error(f"Error calculating variance of Laplacian: {e}")
        return 0.0


# ============================================================================
# Thermal Preprocessing
# ============================================================================

def thermal_preprocess(
    frame: np.ndarray,
    enhance_contrast: bool = True,
    reduce_noise: bool = False
) -> np.ndarray:
    """
    Preprocess thermal frame for better focus detection.

    Thermal images often have lower contrast than visible light images.
    This function enhances contrast using CLAHE (Contrast Limited Adaptive
    Histogram Equalization) which is particularly effective for thermal imagery.

    Args:
        frame: Input frame (BGR or grayscale)
        enhance_contrast: Apply CLAHE contrast enhancement
        reduce_noise: Apply Gaussian blur for noise reduction

    Returns:
        Preprocessed grayscale frame optimized for focus detection
    """
    try:
        # Convert to grayscale if needed
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        if enhance_contrast:
            # Apply CLAHE for contrast enhancement
            # clipLimit controls the contrast enhancement amount
            # tileGridSize is the size of the local regions
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        if reduce_noise:
            # Apply Gaussian blur to reduce thermal noise
            # Small kernel to maintain edge sharpness
            gray = cv2.GaussianBlur(gray, (3, 3), 0.5)

        return gray

    except Exception as e:
        logger.error(f"Error in thermal preprocessing: {e}")
        # Return original frame if preprocessing fails
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame


# ============================================================================
# Focus Quality Assessment
# ============================================================================

class FocusQualityIndicator:
    """
    Provides real-time focus quality assessment and feedback.

    This class tracks focus scores over time and provides quality ratings
    (excellent, good, fair, poor) based on recent performance. It helps
    users understand when they have achieved optimal focus.
    """

    # Quality thresholds (normalized scores)
    THRESHOLDS = {
        "excellent": 0.85,
        "good": 0.70,
        "fair": 0.50,
        "poor": 0.0
    }

    def __init__(self, history_size: int = 50):
        """
        Initialize focus quality indicator.

        Args:
            history_size: Number of recent scores to track
        """
        self.history: List[float] = []
        self.history_size = history_size
        self.baseline_max = 0.0

    def update(self, focus_score: float) -> None:
        """
        Update with new focus score.

        Args:
            focus_score: Current focus metric value
        """
        self.history.append(focus_score)

        # Trim history to size limit
        if len(self.history) > self.history_size:
            self.history.pop(0)

        # Update baseline maximum
        if focus_score > self.baseline_max:
            self.baseline_max = focus_score

    def get_quality(self) -> Tuple[str, float]:
        """
        Get current focus quality level and normalized score.

        Returns:
            Tuple of (quality_level, normalized_score)
            quality_level: "excellent", "good", "fair", "poor", or "calibrating"
            normalized_score: 0.0 to 1.0
        """
        if len(self.history) < 10:
            return "calibrating", 0.0

        current = self.history[-1]

        # Use recent maximum for normalization (last 20 samples)
        recent_samples = self.history[-20:] if len(self.history) >= 20 else self.history
        recent_max = max(recent_samples)

        # Normalize to recent maximum
        if recent_max > 0:
            normalized = current / recent_max
        else:
            normalized = 0.0

        # Determine quality level
        for level in ["excellent", "good", "fair", "poor"]:
            if normalized >= self.THRESHOLDS[level]:
                return level, normalized

        return "poor", normalized

    def should_refocus(self) -> bool:
        """
        Determine if user should consider refocusing.

        Returns:
            True if focus quality is poor and refocusing recommended
        """
        if len(self.history) < 10:
            return False

        quality, score = self.get_quality()

        # Recommend refocus if quality is poor or fair with low score
        return quality in ["poor", "fair"] and score < 0.6

    def get_quality_percentage(self) -> int:
        """
        Get quality as percentage (0-100).

        Returns:
            Quality percentage
        """
        quality, normalized = self.get_quality()
        if quality == "calibrating":
            return 0
        return int(normalized * 100)

    def reset(self) -> None:
        """Reset the quality indicator."""
        self.history.clear()
        self.baseline_max = 0.0


# ============================================================================
# ROI-Based Focus Calculations
# ============================================================================

def compute_weighted_focus(
    gray: np.ndarray,
    regions: List[Dict],
    metric_func=None
) -> float:
    """
    Compute weighted average focus across multiple ROIs.

    Args:
        gray: Grayscale image
        regions: List of region dicts with keys:
                 - 'rect': [x1, y1, x2, y2]
                 - 'weight': float weight value
        metric_func: Focus metric function to use (default: laplacian_focus_metric)

    Returns:
        Weighted average focus score
    """
    if metric_func is None:
        metric_func = laplacian_focus_metric

    total_score = 0.0
    total_weight = 0.0

    for region in regions:
        try:
            x1, y1, x2, y2 = [int(v) for v in region['rect']]
            weight = float(region.get('weight', 1.0))

            # Validate bounds
            h, w = gray.shape
            x1 = max(0, min(w - 1, x1))
            x2 = max(x1 + 1, min(w, x2))
            y1 = max(0, min(h - 1, y1))
            y2 = max(y1 + 1, min(h, y2))

            roi = gray[y1:y2, x1:x2]

            if roi.size == 0:
                logger.warning(f"Empty ROI at {region['rect']}")
                continue

            score = metric_func(roi)
            total_score += score * weight
            total_weight += weight

        except Exception as e:
            logger.error(f"Error processing region {region}: {e}")
            continue

    if total_weight == 0:
        return 0.0

    return total_score / total_weight


def compute_roi_scores(
    gray: np.ndarray,
    regions: List[Dict],
    metric_func=None
) -> List[float]:
    """
    Compute individual focus scores for each ROI.

    Args:
        gray: Grayscale image
        regions: List of region dicts with 'rect' key
        metric_func: Focus metric function to use

    Returns:
        List of focus scores (one per region)
    """
    if metric_func is None:
        metric_func = laplacian_focus_metric

    scores = []
    h, w = gray.shape

    for region in regions:
        try:
            x1, y1, x2, y2 = [int(v) for v in region['rect']]

            # Validate and clip bounds
            x1 = max(0, min(w - 1, x1))
            x2 = max(x1 + 1, min(w, x2))
            y1 = max(0, min(h - 1, y1))
            y2 = max(y1 + 1, min(h, y2))

            roi = gray[y1:y2, x1:x2]

            if roi.size == 0:
                scores.append(0.0)
            else:
                score = metric_func(roi)
                scores.append(score)

        except Exception as e:
            logger.error(f"Error calculating score for region: {e}")
            scores.append(0.0)

    return scores


# ============================================================================
# Focus Peaking Visualization
# ============================================================================

def create_focus_peaking_overlay(
    frame: np.ndarray,
    edge_threshold: int = 100,
    peaking_color: Tuple[int, int, int] = (0, 0, 255),
    blend_alpha: float = 0.5
) -> np.ndarray:
    """
    Create focus peaking overlay with colored edge highlights.

    Args:
        frame: Input BGR frame
        edge_threshold: Threshold for edge detection (1-300)
        peaking_color: BGR color for edge highlights
        blend_alpha: Overlay transparency (0.0-1.0)

    Returns:
        Frame with focus peaking overlay
    """
    try:
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply Laplacian edge detection
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        abs_laplacian = np.uint8(np.absolute(laplacian))

        # Threshold to create binary mask
        _, edge_mask = cv2.threshold(
            abs_laplacian,
            edge_threshold,
            255,
            cv2.THRESH_BINARY
        )

        # Create colored overlay
        overlay = frame.copy()
        overlay[edge_mask > 0] = peaking_color

        # Blend with original frame
        result = cv2.addWeighted(
            frame,
            1.0 - blend_alpha,
            overlay,
            blend_alpha,
            0
        )

        return result

    except Exception as e:
        logger.error(f"Error creating focus peaking overlay: {e}")
        return frame


# ============================================================================
# Statistics and Analysis
# ============================================================================

class FocusStatistics:
    """Track and compute focus statistics over time."""

    def __init__(self, window_size: int = 100):
        """
        Initialize focus statistics tracker.

        Args:
            window_size: Number of samples to keep in rolling window
        """
        self.window_size = window_size
        self.scores: List[float] = []

    def add_score(self, score: float) -> None:
        """Add a new focus score to the tracker."""
        self.scores.append(score)
        if len(self.scores) > self.window_size:
            self.scores.pop(0)

    def get_current(self) -> float:
        """Get the most recent score."""
        return self.scores[-1] if self.scores else 0.0

    def get_min(self) -> float:
        """Get minimum score in window."""
        return min(self.scores) if self.scores else 0.0

    def get_max(self) -> float:
        """Get maximum score in window."""
        return max(self.scores) if self.scores else 0.0

    def get_mean(self) -> float:
        """Get mean score in window."""
        return np.mean(self.scores) if self.scores else 0.0

    def get_std(self) -> float:
        """Get standard deviation in window."""
        return np.std(self.scores) if self.scores else 0.0

    def get_all_stats(self) -> Dict[str, float]:
        """Get all statistics as a dictionary."""
        return {
            'current': self.get_current(),
            'min': self.get_min(),
            'max': self.get_max(),
            'mean': self.get_mean(),
            'std': self.get_std(),
            'count': len(self.scores)
        }

    def clear(self) -> None:
        """Clear all tracked scores."""
        self.scores.clear()


# ============================================================================
# Validation Utilities
# ============================================================================

def validate_roi(
    rect: List[int],
    frame_width: int,
    frame_height: int
) -> Tuple[bool, Optional[List[int]]]:
    """
    Validate and clip ROI coordinates to frame bounds.

    Args:
        rect: [x1, y1, x2, y2] coordinates
        frame_width: Frame width
        frame_height: Frame height

    Returns:
        Tuple of (is_valid, clipped_rect or None)
    """
    try:
        x1, y1, x2, y2 = [int(v) for v in rect]

        # Clip to bounds
        x1 = max(0, min(frame_width - 1, x1))
        x2 = max(x1 + 1, min(frame_width, x2))
        y1 = max(0, min(frame_height - 1, y1))
        y2 = max(y1 + 1, min(frame_height, y2))

        # Check if ROI has area
        if x2 <= x1 or y2 <= y1:
            return False, None

        return True, [x1, y1, x2, y2]

    except Exception as e:
        logger.error(f"Error validating ROI: {e}")
        return False, None
