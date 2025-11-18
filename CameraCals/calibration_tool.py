"""
Camera Calibration Tool - Core Calibration Engine

Provides comprehensive camera calibration functionality including:
- Intrinsic calibration (camera matrix, distortion coefficients)
- Extrinsic calibration (pose estimation)
- Stereo calibration (two-camera system alignment)
- Camera merging and FOV alignment
"""

import cv2
import numpy as np
import json
from typing import List, Tuple, Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime


@dataclass
class IntrinsicCalibration:
    """Intrinsic camera calibration parameters."""
    camera_matrix: np.ndarray  # 3x3 camera matrix
    dist_coeffs: np.ndarray    # Distortion coefficients
    image_size: Tuple[int, int]  # (width, height)
    reprojection_error: float
    calibration_date: str
    num_images: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'camera_matrix': self.camera_matrix.tolist(),
            'dist_coeffs': self.dist_coeffs.tolist(),
            'image_size': self.image_size,
            'reprojection_error': float(self.reprojection_error),
            'calibration_date': self.calibration_date,
            'num_images': self.num_images
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'IntrinsicCalibration':
        """Load from dictionary."""
        return cls(
            camera_matrix=np.array(data['camera_matrix']),
            dist_coeffs=np.array(data['dist_coeffs']),
            image_size=tuple(data['image_size']),
            reprojection_error=data['reprojection_error'],
            calibration_date=data['calibration_date'],
            num_images=data['num_images']
        )


@dataclass
class ExtrinsicCalibration:
    """Extrinsic camera calibration (pose relative to world/pattern)."""
    rotation_vector: np.ndarray  # 3x1 rotation vector
    translation_vector: np.ndarray  # 3x1 translation vector
    rotation_matrix: np.ndarray  # 3x3 rotation matrix

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'rotation_vector': self.rotation_vector.tolist(),
            'translation_vector': self.translation_vector.tolist(),
            'rotation_matrix': self.rotation_matrix.tolist()
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ExtrinsicCalibration':
        """Load from dictionary."""
        return cls(
            rotation_vector=np.array(data['rotation_vector']),
            translation_vector=np.array(data['translation_vector']),
            rotation_matrix=np.array(data['rotation_matrix'])
        )


@dataclass
class StereoCalibration:
    """Stereo calibration parameters for two-camera system."""
    camera1_intrinsic: IntrinsicCalibration
    camera2_intrinsic: IntrinsicCalibration
    rotation_matrix: np.ndarray  # Rotation from camera1 to camera2
    translation_vector: np.ndarray  # Translation from camera1 to camera2
    essential_matrix: np.ndarray
    fundamental_matrix: np.ndarray
    reprojection_error: float
    calibration_date: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'camera1_intrinsic': self.camera1_intrinsic.to_dict(),
            'camera2_intrinsic': self.camera2_intrinsic.to_dict(),
            'rotation_matrix': self.rotation_matrix.tolist(),
            'translation_vector': self.translation_vector.tolist(),
            'essential_matrix': self.essential_matrix.tolist(),
            'fundamental_matrix': self.fundamental_matrix.tolist(),
            'reprojection_error': float(self.reprojection_error),
            'calibration_date': self.calibration_date
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'StereoCalibration':
        """Load from dictionary."""
        return cls(
            camera1_intrinsic=IntrinsicCalibration.from_dict(data['camera1_intrinsic']),
            camera2_intrinsic=IntrinsicCalibration.from_dict(data['camera2_intrinsic']),
            rotation_matrix=np.array(data['rotation_matrix']),
            translation_vector=np.array(data['translation_vector']),
            essential_matrix=np.array(data['essential_matrix']),
            fundamental_matrix=np.array(data['fundamental_matrix']),
            reprojection_error=data['reprojection_error'],
            calibration_date=data['calibration_date']
        )


class CalibrationPatternDetector:
    """Detects calibration patterns (chessboard, circles, ArUco) in images."""

    def __init__(self, pattern_type: str = "chessboard", pattern_size: Tuple[int, int] = (9, 6)):
        """
        Initialize pattern detector.

        Args:
            pattern_type: Type of pattern ("chessboard", "circles", "asymmetric_circles")
            pattern_size: Pattern size (columns, rows) of inner corners/circles
        """
        self.pattern_type = pattern_type
        self.pattern_size = pattern_size
        self.square_size = 1.0  # Physical size of pattern squares (can be in any unit)

    def detect(self, image: np.ndarray, refine: bool = True) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Detect calibration pattern in image.

        Args:
            image: Input image (BGR or grayscale)
            refine: Whether to refine corner positions

        Returns:
            (success, corners): Detection success and corner positions
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        if self.pattern_type == "chessboard":
            # Chessboard detection
            flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
            ret, corners = cv2.findChessboardCorners(gray, self.pattern_size, flags)

            if ret and refine:
                # Refine corner positions to sub-pixel accuracy
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

            return ret, corners

        elif self.pattern_type == "circles":
            # Symmetric circles grid detection
            ret, centers = cv2.findCirclesGrid(gray, self.pattern_size,
                                              flags=cv2.CALIB_CB_SYMMETRIC_GRID)
            return ret, centers

        elif self.pattern_type == "asymmetric_circles":
            # Asymmetric circles grid detection
            ret, centers = cv2.findCirclesGrid(gray, self.pattern_size,
                                              flags=cv2.CALIB_CB_ASYMMETRIC_GRID)
            return ret, centers

        else:
            raise ValueError(f"Unknown pattern type: {self.pattern_type}")

    def draw_pattern(self, image: np.ndarray, corners: np.ndarray, found: bool) -> np.ndarray:
        """Draw detected pattern on image."""
        output = image.copy()
        cv2.drawChessboardCorners(output, self.pattern_size, corners, found)
        return output

    def get_object_points(self) -> np.ndarray:
        """
        Generate 3D object points for the calibration pattern.

        Returns:
            Object points array (N, 3) where N = pattern_size[0] * pattern_size[1]
        """
        objp = np.zeros((self.pattern_size[0] * self.pattern_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:self.pattern_size[0], 0:self.pattern_size[1]].T.reshape(-1, 2)
        objp *= self.square_size
        return objp


class CameraCalibrator:
    """Handles camera calibration operations."""

    def __init__(self):
        self.object_points = []  # 3D points in real world
        self.image_points = []   # 2D points in image plane
        self.image_size = None

    def add_calibration_image(self, corners: np.ndarray, object_points: np.ndarray,
                             image_size: Tuple[int, int]) -> None:
        """Add a calibration image's detected corners."""
        self.image_points.append(corners)
        self.object_points.append(object_points)
        self.image_size = image_size

    def calibrate(self, fix_aspect_ratio: bool = True,
                 zero_tangential_dist: bool = False,
                 fix_principal_point: bool = False) -> IntrinsicCalibration:
        """
        Perform camera calibration.

        Args:
            fix_aspect_ratio: Fix aspect ratio (fx/fy)
            zero_tangential_dist: Assume zero tangential distortion
            fix_principal_point: Fix principal point at image center

        Returns:
            IntrinsicCalibration object with calibration results
        """
        if len(self.image_points) < 3:
            raise ValueError("Need at least 3 calibration images")

        # Set calibration flags
        flags = 0
        if fix_aspect_ratio:
            flags |= cv2.CALIB_FIX_ASPECT_RATIO
        if zero_tangential_dist:
            flags |= cv2.CALIB_ZERO_TANGENT_DIST
        if fix_principal_point:
            flags |= cv2.CALIB_FIX_PRINCIPAL_POINT

        # Perform calibration
        ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            self.object_points,
            self.image_points,
            self.image_size,
            None,
            None,
            flags=flags
        )

        # Calculate reprojection error
        total_error = 0
        for i in range(len(self.object_points)):
            imgpoints2, _ = cv2.projectPoints(self.object_points[i], rvecs[i],
                                             tvecs[i], camera_matrix, dist_coeffs)
            error = cv2.norm(self.image_points[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
            total_error += error

        mean_error = total_error / len(self.object_points)

        return IntrinsicCalibration(
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            image_size=self.image_size,
            reprojection_error=mean_error,
            calibration_date=datetime.now().isoformat(),
            num_images=len(self.image_points)
        )

    def reset(self) -> None:
        """Reset calibration data."""
        self.object_points = []
        self.image_points = []
        self.image_size = None


class StereoCalibrator:
    """Handles stereo camera calibration for two-camera systems."""

    def __init__(self):
        self.object_points = []
        self.image_points_1 = []
        self.image_points_2 = []
        self.image_size = None

    def add_stereo_pair(self, corners1: np.ndarray, corners2: np.ndarray,
                       object_points: np.ndarray, image_size: Tuple[int, int]) -> None:
        """Add a pair of corresponding calibration images."""
        self.image_points_1.append(corners1)
        self.image_points_2.append(corners2)
        self.object_points.append(object_points)
        self.image_size = image_size

    def calibrate_stereo(self, camera1_intrinsic: Optional[IntrinsicCalibration] = None,
                        camera2_intrinsic: Optional[IntrinsicCalibration] = None) -> StereoCalibration:
        """
        Perform stereo calibration.

        Args:
            camera1_intrinsic: Pre-calibrated camera 1 intrinsics (optional)
            camera2_intrinsic: Pre-calibrated camera 2 intrinsics (optional)

        Returns:
            StereoCalibration object with stereo calibration results
        """
        if len(self.image_points_1) < 3:
            raise ValueError("Need at least 3 stereo pairs for calibration")

        # If no pre-calibration provided, perform individual calibrations first
        if camera1_intrinsic is None:
            cal1 = CameraCalibrator()
            for i in range(len(self.object_points)):
                cal1.add_calibration_image(self.image_points_1[i],
                                          self.object_points[i], self.image_size)
            camera1_intrinsic = cal1.calibrate()

        if camera2_intrinsic is None:
            cal2 = CameraCalibrator()
            for i in range(len(self.object_points)):
                cal2.add_calibration_image(self.image_points_2[i],
                                          self.object_points[i], self.image_size)
            camera2_intrinsic = cal2.calibrate()

        # Stereo calibration
        flags = cv2.CALIB_FIX_INTRINSIC
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5)

        ret, _, _, _, _, R, T, E, F = cv2.stereoCalibrate(
            self.object_points,
            self.image_points_1,
            self.image_points_2,
            camera1_intrinsic.camera_matrix,
            camera1_intrinsic.dist_coeffs,
            camera2_intrinsic.camera_matrix,
            camera2_intrinsic.dist_coeffs,
            self.image_size,
            criteria=criteria,
            flags=flags
        )

        return StereoCalibration(
            camera1_intrinsic=camera1_intrinsic,
            camera2_intrinsic=camera2_intrinsic,
            rotation_matrix=R,
            translation_vector=T,
            essential_matrix=E,
            fundamental_matrix=F,
            reprojection_error=ret,
            calibration_date=datetime.now().isoformat()
        )

    def reset(self) -> None:
        """Reset stereo calibration data."""
        self.object_points = []
        self.image_points_1 = []
        self.image_points_2 = []
        self.image_size = None


class CameraMerger:
    """Tools for merging and aligning two cameras optically."""

    def __init__(self, stereo_cal: StereoCalibration):
        """Initialize with stereo calibration data."""
        self.stereo_cal = stereo_cal

    def compute_fov_alignment(self) -> Dict[str, Any]:
        """
        Compute field-of-view alignment parameters.

        Returns:
            Dictionary containing FOV alignment information
        """
        # Extract focal lengths and image sizes
        K1 = self.stereo_cal.camera1_intrinsic.camera_matrix
        K2 = self.stereo_cal.camera2_intrinsic.camera_matrix
        w1, h1 = self.stereo_cal.camera1_intrinsic.image_size
        w2, h2 = self.stereo_cal.camera2_intrinsic.image_size

        # Calculate horizontal and vertical FOV for each camera
        fov1_h = 2 * np.arctan(w1 / (2 * K1[0, 0])) * 180 / np.pi
        fov1_v = 2 * np.arctan(h1 / (2 * K1[1, 1])) * 180 / np.pi
        fov2_h = 2 * np.arctan(w2 / (2 * K2[0, 0])) * 180 / np.pi
        fov2_v = 2 * np.arctan(h2 / (2 * K2[1, 1])) * 180 / np.pi

        # Calculate relative rotation angles
        R = self.stereo_cal.rotation_matrix
        # Convert rotation matrix to Euler angles (XYZ convention)
        sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)
        singular = sy < 1e-6

        if not singular:
            roll = np.arctan2(R[2, 1], R[2, 2])
            pitch = np.arctan2(-R[2, 0], sy)
            yaw = np.arctan2(R[1, 0], R[0, 0])
        else:
            roll = np.arctan2(-R[1, 2], R[1, 1])
            pitch = np.arctan2(-R[2, 0], sy)
            yaw = 0

        # Convert to degrees
        roll_deg = roll * 180 / np.pi
        pitch_deg = pitch * 180 / np.pi
        yaw_deg = yaw * 180 / np.pi

        # Calculate baseline (distance between cameras)
        baseline = np.linalg.norm(self.stereo_cal.translation_vector)

        return {
            'camera1_fov': {'horizontal': fov1_h, 'vertical': fov1_v},
            'camera2_fov': {'horizontal': fov2_h, 'vertical': fov2_v},
            'relative_rotation': {
                'roll_deg': roll_deg,
                'pitch_deg': pitch_deg,
                'yaw_deg': yaw_deg
            },
            'baseline_distance': baseline,
            'translation_vector': self.stereo_cal.translation_vector.tolist()
        }

    def compute_rectification_maps(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute rectification maps for stereo image alignment.

        Returns:
            (map1_x, map1_y, map2_x, map2_y): Rectification maps for both cameras
        """
        K1 = self.stereo_cal.camera1_intrinsic.camera_matrix
        D1 = self.stereo_cal.camera1_intrinsic.dist_coeffs
        K2 = self.stereo_cal.camera2_intrinsic.camera_matrix
        D2 = self.stereo_cal.camera2_intrinsic.dist_coeffs
        R = self.stereo_cal.rotation_matrix
        T = self.stereo_cal.translation_vector
        size = self.stereo_cal.camera1_intrinsic.image_size

        # Compute rectification transforms
        R1, R2, P1, P2, Q, _, _ = cv2.stereoRectify(
            K1, D1, K2, D2, size, R, T,
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0  # 0 = crop to valid pixels, 1 = keep all pixels
        )

        # Compute rectification maps
        map1_x, map1_y = cv2.initUndistortRectifyMap(K1, D1, R1, P1, size, cv2.CV_32FC1)
        map2_x, map2_y = cv2.initUndistortRectifyMap(K2, D2, R2, P2, size, cv2.CV_32FC1)

        return map1_x, map1_y, map2_x, map2_y

    def rectify_images(self, img1: np.ndarray, img2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Rectify stereo image pair for optical alignment.

        Args:
            img1: Image from camera 1
            img2: Image from camera 2

        Returns:
            (rectified_img1, rectified_img2): Rectified stereo pair
        """
        map1_x, map1_y, map2_x, map2_y = self.compute_rectification_maps()

        rect1 = cv2.remap(img1, map1_x, map1_y, cv2.INTER_LINEAR)
        rect2 = cv2.remap(img2, map2_x, map2_y, cv2.INTER_LINEAR)

        return rect1, rect2

    def create_aligned_overlay(self, img1: np.ndarray, img2: np.ndarray,
                              alpha: float = 0.5) -> np.ndarray:
        """
        Create an overlay visualization of aligned cameras.

        Args:
            img1: Rectified image from camera 1
            img2: Rectified image from camera 2
            alpha: Blending factor (0.0-1.0)

        Returns:
            Blended overlay image
        """
        rect1, rect2 = self.rectify_images(img1, img2)

        # Ensure same size and type
        if rect1.shape != rect2.shape:
            rect2 = cv2.resize(rect2, (rect1.shape[1], rect1.shape[0]))

        # Create blended overlay
        overlay = cv2.addWeighted(rect1, alpha, rect2, 1 - alpha, 0)

        return overlay


class CalibrationDataManager:
    """Manages saving and loading calibration data."""

    @staticmethod
    def save_intrinsic(calibration: IntrinsicCalibration, filepath: Path) -> None:
        """Save intrinsic calibration to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(calibration.to_dict(), f, indent=2)

    @staticmethod
    def load_intrinsic(filepath: Path) -> IntrinsicCalibration:
        """Load intrinsic calibration from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return IntrinsicCalibration.from_dict(data)

    @staticmethod
    def save_stereo(calibration: StereoCalibration, filepath: Path) -> None:
        """Save stereo calibration to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(calibration.to_dict(), f, indent=2)

    @staticmethod
    def load_stereo(filepath: Path) -> StereoCalibration:
        """Load stereo calibration from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return StereoCalibration.from_dict(data)


# Utility functions
def undistort_image(image: np.ndarray, calibration: IntrinsicCalibration) -> np.ndarray:
    """Undistort image using intrinsic calibration."""
    h, w = image.shape[:2]
    new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
        calibration.camera_matrix,
        calibration.dist_coeffs,
        (w, h),
        1,
        (w, h)
    )

    undistorted = cv2.undistort(
        image,
        calibration.camera_matrix,
        calibration.dist_coeffs,
        None,
        new_camera_matrix
    )

    # Crop to ROI
    x, y, w, h = roi
    undistorted = undistorted[y:y+h, x:x+w]

    return undistorted


def estimate_pose(corners: np.ndarray, object_points: np.ndarray,
                 calibration: IntrinsicCalibration) -> ExtrinsicCalibration:
    """Estimate camera pose from detected pattern."""
    ret, rvec, tvec = cv2.solvePnP(
        object_points,
        corners,
        calibration.camera_matrix,
        calibration.dist_coeffs
    )

    # Convert rotation vector to matrix
    rmat, _ = cv2.Rodrigues(rvec)

    return ExtrinsicCalibration(
        rotation_vector=rvec,
        translation_vector=tvec,
        rotation_matrix=rmat
    )
