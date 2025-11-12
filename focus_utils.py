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
    edge_threshold: int = 50,
    peaking_color: Tuple[int, int, int] = (0, 0, 255),
    blend_alpha: float = 0.5
) -> np.ndarray:
    """
    Create focus peaking overlay with colored edge highlights.

    Args:
        frame: Input BGR frame
        edge_threshold: Threshold for edge detection (1-100)
                       Lower = more sensitive, Higher = only strong edges
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
# Adaptive Edge Detection (Phase 5)
# ============================================================================

class AdaptiveEdgeDetector:
    """
    Scene-adaptive edge detection for improved focus peaking.

    Automatically detects scene characteristics and applies optimal
    edge detection parameters. Supports multi-scale detection for
    better visualization across varying content types.
    """

    # Scene type enumeration
    SCENE_TYPES = ["auto", "low_contrast", "high_detail", "thermal"]

    # Contrast thresholds for auto-detection
    LOW_CONTRAST_THRESHOLD = 20
    HIGH_DETAIL_THRESHOLD = 60

    def __init__(self):
        """Initialize the adaptive edge detector."""
        self.scene_type = "auto"
        self.multi_scale = True
        self.enhance_low_contrast = True
        logger.debug("AdaptiveEdgeDetector initialized")

    def detect_scene_type(self, gray: np.ndarray) -> str:
        """
        Auto-detect scene type based on image statistics.

        Args:
            gray: Grayscale image

        Returns:
            Scene type: "low_contrast", "high_detail", or "thermal"
        """
        try:
            # Calculate contrast as standard deviation
            contrast = float(np.std(gray))

            if contrast < self.LOW_CONTRAST_THRESHOLD:
                return "low_contrast"
            elif contrast > self.HIGH_DETAIL_THRESHOLD:
                return "high_detail"
            else:
                return "thermal"

        except Exception as e:
            logger.error(f"Error detecting scene type: {e}")
            return "thermal"  # Default fallback

    def adaptive_edge_detection(
        self,
        gray: np.ndarray,
        scene_type: str = "auto"
    ) -> np.ndarray:
        """
        Perform adaptive edge detection based on scene characteristics.

        Args:
            gray: Grayscale input image
            scene_type: Scene type ("auto", "low_contrast", "high_detail", "thermal")

        Returns:
            Binary edge mask optimized for the scene
        """
        try:
            # Auto-detect scene type if requested
            if scene_type == "auto":
                scene_type = self.detect_scene_type(gray)

            if scene_type == "low_contrast":
                # Enhanced sensitivity for low contrast scenes
                # Lower thresholds to detect subtle edges
                edges = cv2.Canny(gray, threshold1=10, threshold2=30)

                # Dilate to connect broken edges
                kernel = np.ones((3, 3), np.uint8)
                edges = cv2.dilate(edges, kernel, iterations=1)

            elif scene_type == "high_detail":
                # Standard Canny with higher thresholds
                # Reduces noise in detailed scenes
                edges = cv2.Canny(gray, threshold1=50, threshold2=150)

            else:  # thermal or default
                if self.enhance_low_contrast:
                    # Apply CLAHE for contrast enhancement
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    enhanced = clahe.apply(gray)
                else:
                    enhanced = gray

                if self.multi_scale:
                    # Multi-scale Canny for better edge detection
                    edges1 = cv2.Canny(enhanced, threshold1=20, threshold2=60)
                    edges2 = cv2.Canny(enhanced, threshold1=40, threshold2=120)

                    # Combine scales (union of edges)
                    edges = cv2.bitwise_or(edges1, edges2)
                else:
                    # Single scale
                    edges = cv2.Canny(enhanced, threshold1=30, threshold2=90)

            return edges

        except Exception as e:
            logger.error(f"Error in adaptive edge detection: {e}")
            # Fallback to basic Canny
            return cv2.Canny(gray, threshold1=50, threshold2=150)

    def create_adaptive_focus_peaking(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        threshold: int,
        peaking_color: Tuple[int, int, int],
        blend_alpha: float = 0.5,
        scene_type: str = "auto"
    ) -> np.ndarray:
        """
        Create focus peaking overlay with adaptive edge detection.

        Args:
            frame: Input BGR frame
            gray: Grayscale version of frame
            threshold: User threshold (used for intensity scaling)
            peaking_color: BGR color for edge highlights
            blend_alpha: Overlay transparency (0.0-1.0)
            scene_type: Scene type for edge detection

        Returns:
            Frame with adaptive focus peaking overlay
        """
        try:
            # Detect edges using adaptive method
            edges = self.adaptive_edge_detection(gray, scene_type)

            # Apply user threshold by scaling edge intensity
            # Higher user threshold = only show stronger edges
            if threshold > 100:
                # Threshold the edge mask
                threshold_val = int((threshold - 100) * 2.5)  # Scale to 0-500 range
                _, edges = cv2.threshold(edges, threshold_val, 255, cv2.THRESH_BINARY)

            # Create colored overlay
            overlay = frame.copy()
            overlay[edges > 0] = peaking_color

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
            logger.error(f"Error creating adaptive focus peaking: {e}")
            return frame

    def create_multi_scale_peaking(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        peaking_color: Tuple[int, int, int],
        blend_alpha: float = 0.5
    ) -> np.ndarray:
        """
        Create multi-scale focus peaking with intensity-based colors.

        Fine edges are shown in full color, coarse edges in dimmed color.

        Args:
            frame: Input BGR frame
            gray: Grayscale version of frame
            peaking_color: BGR color for edge highlights
            blend_alpha: Overlay transparency

        Returns:
            Frame with multi-scale focus peaking overlay
        """
        try:
            # Detect edges at multiple scales
            edges_fine = self.adaptive_edge_detection(gray, "high_detail")
            edges_coarse = self.adaptive_edge_detection(gray, "thermal")

            # Create overlay with intensity-based colors
            overlay = frame.copy()

            # Coarse edges (50% intensity) - background edges
            coarse_color = tuple(int(c * 0.5) for c in peaking_color)
            overlay[edges_coarse > 0] = coarse_color

            # Fine edges (full intensity) - foreground edges
            overlay[edges_fine > 0] = peaking_color

            # Blend with original
            result = cv2.addWeighted(
                frame,
                1.0 - blend_alpha,
                overlay,
                blend_alpha,
                0
            )

            return result

        except Exception as e:
            logger.error(f"Error creating multi-scale peaking: {e}")
            return frame

    def set_scene_type(self, scene_type: str) -> None:
        """
        Set the scene type manually.

        Args:
            scene_type: One of "auto", "low_contrast", "high_detail", "thermal"
        """
        if scene_type in self.SCENE_TYPES:
            self.scene_type = scene_type
            logger.info(f"Scene type set to: {scene_type}")
        else:
            logger.warning(f"Invalid scene type: {scene_type}")

    def set_multi_scale(self, enabled: bool) -> None:
        """Enable or disable multi-scale edge detection."""
        self.multi_scale = enabled
        logger.debug(f"Multi-scale edge detection: {'enabled' if enabled else 'disabled'}")

    def set_enhance_low_contrast(self, enabled: bool) -> None:
        """Enable or disable contrast enhancement."""
        self.enhance_low_contrast = enabled
        logger.debug(f"Contrast enhancement: {'enabled' if enabled else 'disabled'}")

    def get_scene_info(self, gray: np.ndarray) -> Dict[str, any]:
        """
        Get scene information and statistics.

        Args:
            gray: Grayscale image

        Returns:
            Dictionary with scene information
        """
        try:
            contrast = float(np.std(gray))
            detected_scene = self.detect_scene_type(gray)

            return {
                'contrast': contrast,
                'detected_scene': detected_scene,
                'current_scene_type': self.scene_type,
                'multi_scale_enabled': self.multi_scale,
                'enhancement_enabled': self.enhance_low_contrast,
            }
        except Exception as e:
            logger.error(f"Error getting scene info: {e}")
            return {}


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


# ============================================================================
# Multi-Algorithm Ensemble (Phase 3)
# ============================================================================

class FocusEnsemble:
    """
    Multi-algorithm voting system for robust focus detection.

    This ensemble combines multiple focus measurement algorithms to provide
    more reliable focus detection in varying conditions. It computes scores
    from all algorithms, calculates consensus, and provides confidence metrics.
    """

    # Algorithm function mapping
    ALGORITHM_FUNCTIONS = {
        "Laplacian Variance": laplacian_focus_metric,
        "Tenengrad": tenengrad_focus_metric,
        "Brenner Gradient": brenner_gradient_metric,
        "Normalized Variance": normalized_variance_focus,
        "Variance of Laplacian": variance_of_laplacian_metric,
    }

    def __init__(
        self,
        algorithms: Optional[List[str]] = None,
        weights: Optional[Dict[str, float]] = None,
        history_size: int = 10
    ):
        """
        Initialize the focus ensemble.

        Args:
            algorithms: List of algorithm names to use (default: all available)
            weights: Dictionary of algorithm weights (default: equal weights)
            history_size: Number of recent scores to track per algorithm
        """
        # Use all algorithms if none specified
        if algorithms is None:
            algorithms = list(self.ALGORITHM_FUNCTIONS.keys())

        self.algorithms = algorithms

        # Set equal weights if none provided
        if weights is None:
            weights = {name: 1.0 for name in algorithms}
        self.weights = weights

        # History tracking for each algorithm
        self.history: Dict[str, List[float]] = {
            name: [] for name in algorithms
        }
        self.history_size = history_size

        logger.info(f"FocusEnsemble initialized with {len(algorithms)} algorithms")

    def compute_all_scores(self, gray: np.ndarray) -> Dict[str, float]:
        """
        Compute focus scores using all enabled algorithms.

        Args:
            gray: Grayscale image

        Returns:
            Dictionary of algorithm name -> focus score
        """
        scores = {}

        for name in self.algorithms:
            try:
                func = self.ALGORITHM_FUNCTIONS.get(name)
                if func is None:
                    logger.warning(f"Unknown algorithm: {name}")
                    scores[name] = 0.0
                    continue

                score = func(gray)
                scores[name] = score

                # Update history
                self.history[name].append(score)
                if len(self.history[name]) > self.history_size:
                    self.history[name].pop(0)

            except Exception as e:
                logger.error(f"Algorithm {name} failed: {e}")
                scores[name] = 0.0

        return scores

    def get_weighted_score(self, scores: Dict[str, float]) -> float:
        """
        Compute weighted average of all algorithm scores.

        Args:
            scores: Dictionary of algorithm scores

        Returns:
            Weighted average score
        """
        total = 0.0
        total_weight = 0.0

        for name, score in scores.items():
            weight = self.weights.get(name, 1.0)
            total += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return total / total_weight

    def get_normalized_scores(
        self,
        scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Normalize scores to 0-1 range based on recent history.

        Args:
            scores: Current algorithm scores

        Returns:
            Dictionary of normalized scores
        """
        normalized = {}

        for name, score in scores.items():
            history = self.history.get(name, [])

            if len(history) < 3:
                # Not enough history for normalization
                normalized[name] = 0.0
                continue

            recent_max = max(history)
            recent_min = min(history)

            # Normalize to 0-1 range
            if recent_max > recent_min:
                normalized[name] = (score - recent_min) / (recent_max - recent_min)
            else:
                normalized[name] = 0.5  # All values are the same

        return normalized

    def get_consensus(
        self,
        scores: Dict[str, float]
    ) -> Tuple[str, float, float]:
        """
        Determine consensus algorithm and confidence level.

        Confidence is based on agreement between algorithms. Low variance
        in normalized scores indicates high agreement (high confidence).

        Args:
            scores: Dictionary of algorithm scores

        Returns:
            Tuple of (best_algorithm, confidence, best_score)
            - best_algorithm: Name of algorithm with highest score
            - confidence: 0.0-1.0 (higher = more agreement)
            - best_score: The actual score value
        """
        if not scores:
            return "", 0.0, 0.0

        # Find best algorithm
        best_algorithm = max(scores.items(), key=lambda x: x[1])

        # Get normalized scores for variance calculation
        normalized = self.get_normalized_scores(scores)

        if not normalized or len(normalized) < 2:
            # Not enough data for confidence
            return best_algorithm[0], 0.5, best_algorithm[1]

        # Calculate variance (low variance = high agreement = high confidence)
        values = list(normalized.values())
        variance = float(np.var(values))

        # Convert variance to confidence (inverse relationship)
        # Variance ranges from 0 (perfect agreement) to ~0.25 (max disagreement)
        # Map to confidence: 0 var -> 1.0 confidence, 0.25 var -> 0.0 confidence
        confidence = max(0.0, min(1.0, 1.0 - (variance * 4.0)))

        return best_algorithm[0], confidence, best_algorithm[1]

    def get_consensus_quality(self, confidence: float) -> str:
        """
        Get quality rating for consensus confidence.

        Args:
            confidence: Confidence value (0.0-1.0)

        Returns:
            Quality string: "excellent", "good", "fair", or "poor"
        """
        if confidence >= 0.85:
            return "excellent"
        elif confidence >= 0.70:
            return "good"
        elif confidence >= 0.50:
            return "fair"
        else:
            return "poor"

    def compute_ensemble_focus(
        self,
        gray: np.ndarray,
        return_details: bool = False
    ) -> float:
        """
        Compute ensemble focus score (main interface method).

        Args:
            gray: Grayscale image
            return_details: If True, returns (score, details_dict)

        Returns:
            Weighted ensemble focus score, or tuple if return_details=True
        """
        scores = self.compute_all_scores(gray)
        weighted_score = self.get_weighted_score(scores)

        if return_details:
            best_algo, confidence, best_score = self.get_consensus(scores)
            details = {
                'all_scores': scores,
                'weighted_score': weighted_score,
                'best_algorithm': best_algo,
                'confidence': confidence,
                'best_score': best_score,
                'consensus_quality': self.get_consensus_quality(confidence),
                'normalized_scores': self.get_normalized_scores(scores)
            }
            return weighted_score, details

        return weighted_score

    def set_algorithm_weight(self, algorithm: str, weight: float) -> None:
        """
        Update weight for a specific algorithm.

        Args:
            algorithm: Algorithm name
            weight: New weight value
        """
        if algorithm in self.algorithms:
            self.weights[algorithm] = weight
            logger.debug(f"Updated {algorithm} weight to {weight}")
        else:
            logger.warning(f"Unknown algorithm: {algorithm}")

    def reset_history(self) -> None:
        """Clear all algorithm history."""
        for name in self.algorithms:
            self.history[name].clear()
        logger.debug("Ensemble history reset")

    def get_algorithm_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Get statistics for each algorithm.

        Returns:
            Dictionary of algorithm -> stats dict
        """
        stats = {}

        for name in self.algorithms:
            history = self.history.get(name, [])

            if not history:
                stats[name] = {
                    'current': 0.0,
                    'min': 0.0,
                    'max': 0.0,
                    'mean': 0.0,
                    'std': 0.0,
                    'count': 0
                }
            else:
                stats[name] = {
                    'current': history[-1],
                    'min': float(np.min(history)),
                    'max': float(np.max(history)),
                    'mean': float(np.mean(history)),
                    'std': float(np.std(history)),
                    'count': len(history)
                }

        return stats
