"""
CameraCals - Camera Calibration Module

Comprehensive camera calibration toolkit for single and stereo camera systems.
"""

from .calibration_tool import (
    CalibrationPatternDetector,
    CameraCalibrator,
    StereoCalibrator,
    CameraMerger,
    IntrinsicCalibration,
    ExtrinsicCalibration,
    StereoCalibration,
    CalibrationDataManager,
    undistort_image,
    estimate_pose
)

__version__ = "1.0.0"
__all__ = [
    "CalibrationPatternDetector",
    "CameraCalibrator",
    "StereoCalibrator",
    "CameraMerger",
    "IntrinsicCalibration",
    "ExtrinsicCalibration",
    "StereoCalibration",
    "CalibrationDataManager",
    "undistort_image",
    "estimate_pose"
]
