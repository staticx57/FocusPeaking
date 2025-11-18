"""
Field Calibration Tools - Natural Feature-Based Camera Alignment

Provides calibration methods that work in the field without calibration patterns:
- Natural feature matching (SIFT, ORB, AKAZE)
- Landmark-based alignment
- FOV calculation and matching
- Focal length recommendations
- Adaptive alignment with selectable source camera
"""

import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum


class FeatureDetectorType(Enum):
    """Feature detector algorithms for natural feature matching."""
    SIFT = "SIFT"
    ORB = "ORB"
    AKAZE = "AKAZE"
    BRISK = "BRISK"


@dataclass
class CameraSpec:
    """Camera specifications for FOV and focal length calculations."""
    name: str
    sensor_width_mm: float  # Sensor width in mm
    sensor_height_mm: float  # Sensor height in mm
    image_width_px: int  # Image width in pixels
    image_height_px: int  # Image height in pixels
    focal_length_mm: Optional[float] = None  # Known focal length (if available)

    @property
    def crop_factor(self) -> float:
        """Calculate crop factor relative to full-frame (36mm)."""
        sensor_diagonal = np.sqrt(self.sensor_width_mm**2 + self.sensor_height_mm**2)
        fullframe_diagonal = np.sqrt(36**2 + 24**2)  # 35mm full-frame
        return fullframe_diagonal / sensor_diagonal

    @property
    def pixel_pitch_um(self) -> float:
        """Calculate pixel pitch in micrometers."""
        return (self.sensor_width_mm * 1000) / self.image_width_px

    def calculate_fov(self, focal_length_mm: float) -> Tuple[float, float]:
        """
        Calculate horizontal and vertical FOV for a given focal length.

        Args:
            focal_length_mm: Focal length in millimeters

        Returns:
            (horizontal_fov_deg, vertical_fov_deg): FOV in degrees
        """
        h_fov = 2 * np.arctan(self.sensor_width_mm / (2 * focal_length_mm))
        v_fov = 2 * np.arctan(self.sensor_height_mm / (2 * focal_length_mm))
        return np.degrees(h_fov), np.degrees(v_fov)

    def calculate_focal_length_for_fov(self, target_fov_h_deg: float) -> float:
        """
        Calculate required focal length to achieve target horizontal FOV.

        Args:
            target_fov_h_deg: Target horizontal FOV in degrees

        Returns:
            Required focal length in mm
        """
        target_fov_h_rad = np.radians(target_fov_h_deg)
        focal_length = self.sensor_width_mm / (2 * np.tan(target_fov_h_rad / 2))
        return focal_length


# Common camera specifications database
CAMERA_SPECS_DB = {
    "FLIR Boson 320": CameraSpec(
        name="FLIR Boson 320x240",
        sensor_width_mm=4.8,  # 15μm pixel pitch × 320
        sensor_height_mm=3.6,  # 15μm pixel pitch × 240
        image_width_px=320,
        image_height_px=240,
        focal_length_mm=4.3  # 4.3mm variant
    ),
    "FLIR Boson 640": CameraSpec(
        name="FLIR Boson 640x512",
        sensor_width_mm=7.68,  # 12μm pixel pitch × 640
        sensor_height_mm=6.14,  # 12μm pixel pitch × 512
        image_width_px=640,
        image_height_px=512,
        focal_length_mm=8.6  # 8.6mm variant
    ),
    "FLIR Firefly": CameraSpec(
        name="FLIR Firefly (typical)",
        sensor_width_mm=7.1,  # Sony IMX273 (typical)
        sensor_height_mm=5.3,
        image_width_px=1440,
        image_height_px=1080,
        focal_length_mm=None  # C-mount, variable
    ),
    "Generic C-Mount": CameraSpec(
        name="Generic C-Mount Camera",
        sensor_width_mm=7.1,  # Typical 1/1.8" sensor
        sensor_height_mm=5.3,
        image_width_px=1920,
        image_height_px=1080,
        focal_length_mm=None  # Variable
    ),
}


class NaturalFeatureMatcher:
    """Matches natural features between two images for alignment."""

    def __init__(self, detector_type: FeatureDetectorType = FeatureDetectorType.AKAZE):
        """
        Initialize feature matcher.

        Args:
            detector_type: Feature detection algorithm to use
        """
        self.detector_type = detector_type
        self.detector = self._create_detector()
        self.matcher = self._create_matcher()

    def _create_detector(self):
        """Create feature detector based on type."""
        if self.detector_type == FeatureDetectorType.SIFT:
            return cv2.SIFT_create()
        elif self.detector_type == FeatureDetectorType.ORB:
            return cv2.ORB_create(nfeatures=5000)
        elif self.detector_type == FeatureDetectorType.AKAZE:
            return cv2.AKAZE_create()
        elif self.detector_type == FeatureDetectorType.BRISK:
            return cv2.BRISK_create()
        else:
            raise ValueError(f"Unknown detector type: {self.detector_type}")

    def _create_matcher(self):
        """Create matcher appropriate for detector type."""
        if self.detector_type == FeatureDetectorType.SIFT:
            # SIFT uses FLANN with KD-Tree
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            return cv2.FlannBasedMatcher(index_params, search_params)
        else:
            # ORB, AKAZE, BRISK use Hamming distance
            return cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def match_features(self, img1: np.ndarray, img2: np.ndarray,
                      ratio_threshold: float = 0.75) -> Tuple[np.ndarray, np.ndarray, List]:
        """
        Match features between two images using Lowe's ratio test.

        Args:
            img1: First image (source/reference)
            img2: Second image (target)
            ratio_threshold: Ratio test threshold (0.7-0.8 typical)

        Returns:
            (pts1, pts2, good_matches): Matched point arrays and match list
        """
        # Convert to grayscale if needed
        if len(img1.shape) == 3:
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        else:
            gray1 = img1

        if len(img2.shape) == 3:
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        else:
            gray2 = img2

        # Detect keypoints and compute descriptors
        kp1, desc1 = self.detector.detectAndCompute(gray1, None)
        kp2, desc2 = self.detector.detectAndCompute(gray2, None)

        if desc1 is None or desc2 is None or len(kp1) < 10 or len(kp2) < 10:
            return np.array([]), np.array([]), []

        # Match features
        matches = self.matcher.knnMatch(desc1, desc2, k=2)

        # Apply Lowe's ratio test
        good_matches = []
        pts1 = []
        pts2 = []

        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < ratio_threshold * n.distance:
                    good_matches.append(m)
                    pts1.append(kp1[m.queryIdx].pt)
                    pts2.append(kp2[m.trainIdx].pt)

        return np.float32(pts1), np.float32(pts2), good_matches

    def draw_matches(self, img1: np.ndarray, img2: np.ndarray,
                    pts1: np.ndarray, pts2: np.ndarray) -> np.ndarray:
        """
        Draw matched points between two images.

        Args:
            img1: First image
            img2: Second image
            pts1: Points in first image
            pts2: Points in second image

        Returns:
            Visualization image showing matches
        """
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        # Create side-by-side image
        h = max(h1, h2)
        vis = np.zeros((h, w1 + w2, 3), dtype=np.uint8)

        # Place images
        vis[:h1, :w1] = img1 if len(img1.shape) == 3 else cv2.cvtColor(img1, cv2.COLOR_GRAY2BGR)
        vis[:h2, w1:w1+w2] = img2 if len(img2.shape) == 3 else cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)

        # Draw matches
        for pt1, pt2 in zip(pts1, pts2):
            pt1 = tuple(map(int, pt1))
            pt2 = tuple(map(int, (pt2[0] + w1, pt2[1])))

            color = tuple(np.random.randint(0, 255, 3).tolist())
            cv2.circle(vis, pt1, 4, color, -1)
            cv2.circle(vis, pt2, 4, color, -1)
            cv2.line(vis, pt1, pt2, color, 1)

        return vis


class FieldAlignmentCalculator:
    """Calculate alignment between two cameras using natural features."""

    def __init__(self, source_camera_spec: CameraSpec, target_camera_spec: CameraSpec):
        """
        Initialize alignment calculator.

        Args:
            source_camera_spec: Specifications of the source/reference camera
            target_camera_spec: Specifications of the target camera to align
        """
        self.source_spec = source_camera_spec
        self.target_spec = target_camera_spec
        self.matcher = NaturalFeatureMatcher(FeatureDetectorType.AKAZE)

    def compute_alignment(self, source_img: np.ndarray, target_img: np.ndarray,
                         min_matches: int = 10) -> Optional[Dict[str, Any]]:
        """
        Compute alignment between source and target images.

        Args:
            source_img: Image from source camera
            target_img: Image from target camera
            min_matches: Minimum number of matches required

        Returns:
            Dictionary containing alignment parameters or None if failed
        """
        # Match features
        pts_src, pts_tgt, matches = self.matcher.match_features(source_img, target_img)

        if len(matches) < min_matches:
            return None

        # Compute homography
        H, mask = cv2.findHomography(pts_tgt, pts_src, cv2.RANSAC, 5.0)

        if H is None:
            return None

        # Compute alignment metrics
        inlier_ratio = np.sum(mask) / len(mask)

        # Decompose homography to extract rotation and scale
        # This is a simplified extraction; full camera pose would need intrinsics
        scale_x = np.sqrt(H[0, 0]**2 + H[1, 0]**2)
        scale_y = np.sqrt(H[0, 1]**2 + H[1, 1]**2)
        avg_scale = (scale_x + scale_y) / 2

        # Rotation angle (approximate)
        rotation_deg = np.degrees(np.arctan2(H[1, 0], H[0, 0]))

        # Translation
        translation_x = H[0, 2]
        translation_y = H[1, 2]

        return {
            'homography': H,
            'num_matches': len(matches),
            'num_inliers': int(np.sum(mask)),
            'inlier_ratio': float(inlier_ratio),
            'scale_factor': float(avg_scale),
            'rotation_deg': float(rotation_deg),
            'translation': (float(translation_x), float(translation_y)),
            'matched_points_source': pts_src,
            'matched_points_target': pts_tgt,
            'inlier_mask': mask
        }

    def warp_target_to_source(self, target_img: np.ndarray, alignment: Dict[str, Any]) -> np.ndarray:
        """
        Warp target image to align with source image using computed homography.

        Args:
            target_img: Target camera image
            alignment: Alignment parameters from compute_alignment()

        Returns:
            Warped target image aligned to source
        """
        H = alignment['homography']
        h, w = self.source_spec.image_height_px, self.source_spec.image_width_px
        warped = cv2.warpPerspective(target_img, H, (w, h))
        return warped


class FocalLengthOptimizer:
    """Recommends optimal focal lengths for camera alignment."""

    @staticmethod
    def recommend_focal_length_for_fov_match(
        source_spec: CameraSpec,
        source_focal_mm: float,
        target_spec: CameraSpec
    ) -> Dict[str, Any]:
        """
        Recommend focal length for target camera to match source camera's FOV.

        Args:
            source_spec: Source camera specifications
            source_focal_mm: Source camera focal length
            target_spec: Target camera specifications

        Returns:
            Dictionary with recommendations and FOV analysis
        """
        # Calculate source FOV
        src_fov_h, src_fov_v = source_spec.calculate_fov(source_focal_mm)

        # Calculate required target focal length to match horizontal FOV
        target_focal_mm = target_spec.calculate_focal_length_for_fov(src_fov_h)

        # Calculate resulting FOVs
        tgt_fov_h, tgt_fov_v = target_spec.calculate_fov(target_focal_mm)

        # Calculate FOV mismatches
        fov_h_diff = abs(src_fov_h - tgt_fov_h)
        fov_v_diff = abs(src_fov_v - tgt_fov_v)

        # Calculate field of view overlap percentage
        overlap_h = min(src_fov_h, tgt_fov_h) / max(src_fov_h, tgt_fov_h) * 100
        overlap_v = min(src_fov_v, tgt_fov_v) / max(src_fov_v, tgt_fov_v) * 100

        return {
            'recommended_focal_length_mm': target_focal_mm,
            'source_fov': {
                'horizontal_deg': src_fov_h,
                'vertical_deg': src_fov_v,
                'focal_length_mm': source_focal_mm
            },
            'target_fov_matched': {
                'horizontal_deg': tgt_fov_h,
                'vertical_deg': tgt_fov_v,
                'focal_length_mm': target_focal_mm
            },
            'fov_differences': {
                'horizontal_deg': fov_h_diff,
                'vertical_deg': fov_v_diff
            },
            'overlap_percentage': {
                'horizontal': overlap_h,
                'vertical': overlap_v
            }
        }

    @staticmethod
    def calculate_magnification_ratio(focal1_mm: float, focal2_mm: float) -> float:
        """
        Calculate magnification ratio between two focal lengths.

        Args:
            focal1_mm: First focal length
            focal2_mm: Second focal length

        Returns:
            Magnification ratio (focal1 / focal2)
        """
        return focal1_mm / focal2_mm


class LandmarkAlignmentTool:
    """Manual landmark-based alignment for field calibration."""

    def __init__(self):
        self.source_landmarks = []
        self.target_landmarks = []

    def add_landmark_pair(self, source_point: Tuple[float, float],
                         target_point: Tuple[float, float]):
        """
        Add a pair of corresponding landmarks.

        Args:
            source_point: (x, y) in source image
            target_point: (x, y) in target image
        """
        self.source_landmarks.append(source_point)
        self.target_landmarks.append(target_point)

    def clear_landmarks(self):
        """Clear all landmarks."""
        self.source_landmarks = []
        self.target_landmarks = []

    def compute_alignment(self, method: str = 'affine') -> Optional[np.ndarray]:
        """
        Compute transformation matrix from landmarks.

        Args:
            method: 'affine', 'perspective', or 'similarity'

        Returns:
            Transformation matrix or None if insufficient points
        """
        if len(self.source_landmarks) < 4 and method == 'perspective':
            return None
        if len(self.source_landmarks) < 3:
            return None

        src_pts = np.float32(self.source_landmarks)
        tgt_pts = np.float32(self.target_landmarks)

        if method == 'affine':
            if len(src_pts) >= 3:
                M = cv2.getAffineTransform(tgt_pts[:3], src_pts[:3])
                return M
        elif method == 'perspective':
            if len(src_pts) >= 4:
                M = cv2.getPerspectiveTransform(tgt_pts[:4], src_pts[:4])
                return M
        elif method == 'similarity':
            # Use least squares for similarity transform (rotation + scale + translation)
            # Implemented using cv2.estimateAffinePartial2D for robustness
            M, _ = cv2.estimateAffinePartial2D(tgt_pts, src_pts)
            return M

        return None


def create_fov_visualization(spec: CameraSpec, focal_length_mm: float,
                             canvas_size: Tuple[int, int] = (800, 600)) -> np.ndarray:
    """
    Create a visualization of camera FOV.

    Args:
        spec: Camera specification
        focal_length_mm: Focal length to visualize
        canvas_size: Output canvas size (width, height)

    Returns:
        Visualization image
    """
    canvas = np.ones((canvas_size[1], canvas_size[0], 3), dtype=np.uint8) * 255

    # Calculate FOV
    fov_h, fov_v = spec.calculate_fov(focal_length_mm)

    # Draw FOV cone from center
    center_x, center_y = canvas_size[0] // 2, canvas_size[1] // 2

    # Calculate cone dimensions
    distance = 300  # Arbitrary distance for visualization
    half_width = int(distance * np.tan(np.radians(fov_h / 2)))
    half_height = int(distance * np.tan(np.radians(fov_v / 2)))

    # Draw FOV cone
    pts = np.array([
        [center_x, center_y],
        [center_x - half_width, center_y - half_height + distance],
        [center_x + half_width, center_y - half_height + distance],
    ], dtype=np.int32)

    cv2.fillPoly(canvas, [pts], (200, 200, 255))
    cv2.polylines(canvas, [pts], True, (100, 100, 200), 2)

    # Add text annotations
    cv2.putText(canvas, f"{spec.name}", (20, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.putText(canvas, f"Focal Length: {focal_length_mm:.2f}mm", (20, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    cv2.putText(canvas, f"FOV H: {fov_h:.1f}°", (20, 90),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    cv2.putText(canvas, f"FOV V: {fov_v:.1f}°", (20, 120),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

    return canvas
