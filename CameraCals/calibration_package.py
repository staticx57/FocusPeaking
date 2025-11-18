"""
Industry-Standard Calibration Package Manager

Implements world-class calibration file format following best practices from:
- ADAS (ISO 26262, OpenX)
- Machine Vision (GenICam, EMVA)
- Professional Videography (OpenFX, LUT)

Package Structure:
  calibration_package/
  ├── metadata.json (cameras, timestamps, environment)
  ├── camera1_intrinsic.yaml (OpenCV format)
  ├── camera2_intrinsic.yaml
  ├── stereo_calibration.yaml
  ├── alignment_transforms.json (field calibration results)
  ├── rectification_maps.npz (optional, binary)
  └── validation_report.json (error metrics, quality)
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import cv2

from CameraCals.calibration_tool import (
    IntrinsicCalibration,
    StereoCalibration,
    ExtrinsicCalibration
)
from CameraCals.field_calibration import CameraSpec


class CalibrationPackage:
    """
    Complete calibration package following industry standards.

    Supports:
    - OpenCV-compatible YAML for camera parameters
    - JSON for metadata and high-level configuration
    - Binary NPZ for large datasets (rectification maps)
    - Validation and quality metrics
    """

    def __init__(self, package_dir: Path):
        """
        Initialize calibration package.

        Args:
            package_dir: Directory to store calibration package
        """
        self.package_dir = Path(package_dir)
        self.metadata = {
            'package_version': '1.0',
            'created_date': datetime.now().isoformat(),
            'application': 'FLIR Focus & Calibration Utility',
            'calibration_type': None,  # 'single', 'stereo', 'multi'
            'cameras': [],
            'environment': {},
            'coordinate_systems': {}
        }

    def create_package(self) -> None:
        """Create calibration package directory structure."""
        self.package_dir.mkdir(parents=True, exist_ok=True)
        (self.package_dir / 'validation').mkdir(exist_ok=True)

    def save_metadata(self, metadata_updates: Dict[str, Any]) -> None:
        """
        Save package metadata.

        Args:
            metadata_updates: Dictionary of metadata to add/update
        """
        self.metadata.update(metadata_updates)
        metadata_path = self.package_dir / 'metadata.json'

        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def save_camera_intrinsic(self, calibration: IntrinsicCalibration,
                              camera_id: str,
                              camera_spec: Optional[CameraSpec] = None) -> None:
        """
        Save camera intrinsic calibration in OpenCV YAML format.

        Args:
            calibration: Intrinsic calibration data
            camera_id: Unique camera identifier
            camera_spec: Optional camera specifications
        """
        # Save OpenCV YAML format (industry standard)
        yaml_path = self.package_dir / f'{camera_id}_intrinsic.yaml'

        fs = cv2.FileStorage(str(yaml_path), cv2.FILE_STORAGE_WRITE)
        fs.write('camera_matrix', calibration.camera_matrix)
        fs.write('distortion_coefficients', calibration.dist_coeffs)
        fs.write('image_width', calibration.image_size[0])
        fs.write('image_height', calibration.image_size[1])
        fs.write('reprojection_error', calibration.reprojection_error)
        fs.write('calibration_date', calibration.calibration_date)
        fs.write('num_calibration_images', calibration.num_images)

        if camera_spec:
            fs.write('sensor_width_mm', camera_spec.sensor_width_mm)
            fs.write('sensor_height_mm', camera_spec.sensor_height_mm)
            fs.write('pixel_pitch_um', camera_spec.pixel_pitch_um)

        fs.release()

        # Also save JSON version for easy reading
        json_path = self.package_dir / f'{camera_id}_intrinsic.json'
        with open(json_path, 'w') as f:
            data = calibration.to_dict()
            if camera_spec:
                data['camera_spec'] = {
                    'sensor_width_mm': camera_spec.sensor_width_mm,
                    'sensor_height_mm': camera_spec.sensor_height_mm,
                    'pixel_pitch_um': camera_spec.pixel_pitch_um,
                    'crop_factor': camera_spec.crop_factor
                }
            json.dump(data, f, indent=2)

    def save_stereo_calibration(self, calibration: StereoCalibration) -> None:
        """
        Save stereo calibration parameters.

        Args:
            calibration: Stereo calibration data
        """
        # OpenCV YAML format
        yaml_path = self.package_dir / 'stereo_calibration.yaml'

        fs = cv2.FileStorage(str(yaml_path), cv2.FILE_STORAGE_WRITE)
        fs.write('rotation_matrix', calibration.rotation_matrix)
        fs.write('translation_vector', calibration.translation_vector)
        fs.write('essential_matrix', calibration.essential_matrix)
        fs.write('fundamental_matrix', calibration.fundamental_matrix)
        fs.write('reprojection_error', calibration.reprojection_error)
        fs.write('calibration_date', calibration.calibration_date)
        fs.release()

        # JSON version
        json_path = self.package_dir / 'stereo_calibration.json'
        with open(json_path, 'w') as f:
            json.dump(calibration.to_dict(), f, indent=2)

    def save_alignment_transforms(self, transforms: Dict[str, Any]) -> None:
        """
        Save alignment transformation data from field calibration.

        Args:
            transforms: Dictionary containing alignment parameters
        """
        json_path = self.package_dir / 'alignment_transforms.json'

        # Convert numpy arrays to lists for JSON serialization
        def convert_numpy(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: convert_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(item) for item in obj]
            else:
                return obj

        transforms_serializable = convert_numpy(transforms)

        with open(json_path, 'w') as f:
            json.dump(transforms_serializable, f, indent=2)

    def save_rectification_maps(self, map1_x: np.ndarray, map1_y: np.ndarray,
                                map2_x: np.ndarray, map2_y: np.ndarray) -> None:
        """
        Save rectification maps in binary format for fast loading.

        Args:
            map1_x: X rectification map for camera 1
            map1_y: Y rectification map for camera 1
            map2_x: X rectification map for camera 2
            map2_y: Y rectification map for camera 2
        """
        npz_path = self.package_dir / 'rectification_maps.npz'

        np.savez_compressed(
            npz_path,
            map1_x=map1_x,
            map1_y=map1_y,
            map2_x=map2_x,
            map2_y=map2_y
        )

    def save_validation_report(self, validation_data: Dict[str, Any]) -> None:
        """
        Save calibration validation report.

        Args:
            validation_data: Validation metrics and quality assessment
        """
        report_path = self.package_dir / 'validation' / 'validation_report.json'

        report = {
            'validation_date': datetime.now().isoformat(),
            'metrics': validation_data,
            'pass_criteria': {
                'max_reprojection_error_px': 1.0,
                'min_inlier_ratio': 0.8,
                'fov_alignment_tolerance_deg': 2.0
            }
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

    def save_environment_data(self, environment: Dict[str, Any]) -> None:
        """
        Save environment and setup information (ADAS best practice).

        Args:
            environment: Environmental conditions, camera mounting, etc.
        """
        env_path = self.package_dir / 'environment.json'

        environment_data = {
            'timestamp': datetime.now().isoformat(),
            'temperature_c': environment.get('temperature_c'),
            'lighting_conditions': environment.get('lighting_conditions'),
            'camera_mounting': {
                'camera1': environment.get('camera1_mounting', {}),
                'camera2': environment.get('camera2_mounting', {})
            },
            'coordinate_system': environment.get('coordinate_system', 'camera1_centered'),
            'notes': environment.get('notes', '')
        }

        with open(env_path, 'w') as f:
            json.dump(environment_data, f, indent=2)

    def load_camera_intrinsic(self, camera_id: str) -> Optional[IntrinsicCalibration]:
        """
        Load camera intrinsic calibration.

        Args:
            camera_id: Camera identifier

        Returns:
            IntrinsicCalibration object or None if not found
        """
        json_path = self.package_dir / f'{camera_id}_intrinsic.json'

        if not json_path.exists():
            return None

        with open(json_path, 'r') as f:
            data = json.load(f)

        return IntrinsicCalibration.from_dict(data)

    def load_stereo_calibration(self) -> Optional[StereoCalibration]:
        """
        Load stereo calibration.

        Returns:
            StereoCalibration object or None if not found
        """
        json_path = self.package_dir / 'stereo_calibration.json'

        if not json_path.exists():
            return None

        with open(json_path, 'r') as f:
            data = json.load(f)

        return StereoCalibration.from_dict(data)

    def load_rectification_maps(self) -> Optional[Dict[str, np.ndarray]]:
        """
        Load rectification maps.

        Returns:
            Dictionary containing rectification maps or None if not found
        """
        npz_path = self.package_dir / 'rectification_maps.npz'

        if not npz_path.exists():
            return None

        data = np.load(npz_path)
        return {
            'map1_x': data['map1_x'],
            'map1_y': data['map1_y'],
            'map2_x': data['map2_x'],
            'map2_y': data['map2_y']
        }

    def export_to_ros_format(self, output_dir: Path) -> None:
        """
        Export calibration to ROS camera_info format.

        Args:
            output_dir: Directory to save ROS format files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load calibrations
        camera1 = self.load_camera_intrinsic('camera1')
        camera2 = self.load_camera_intrinsic('camera2')

        if camera1:
            ros_yaml = self._generate_ros_camera_info(camera1, 'camera1')
            with open(output_dir / 'camera1_camera_info.yaml', 'w') as f:
                f.write(ros_yaml)

        if camera2:
            ros_yaml = self._generate_ros_camera_info(camera2, 'camera2')
            with open(output_dir / 'camera2_camera_info.yaml', 'w') as f:
                f.write(ros_yaml)

    def _generate_ros_camera_info(self, calibration: IntrinsicCalibration,
                                   camera_name: str) -> str:
        """Generate ROS camera_info YAML format."""
        K = calibration.camera_matrix
        D = calibration.dist_coeffs

        yaml_content = f"""image_width: {calibration.image_size[0]}
image_height: {calibration.image_size[1]}
camera_name: {camera_name}
camera_matrix:
  rows: 3
  cols: 3
  data: [{K[0,0]}, {K[0,1]}, {K[0,2]}, {K[1,0]}, {K[1,1]}, {K[1,2]}, {K[2,0]}, {K[2,1]}, {K[2,2]}]
distortion_model: plumb_bob
distortion_coefficients:
  rows: 1
  cols: 5
  data: [{D[0,0]}, {D[0,1]}, {D[0,2]}, {D[0,3]}, {D[0,4]}]
rectification_matrix:
  rows: 3
  cols: 3
  data: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
projection_matrix:
  rows: 3
  cols: 4
  data: [{K[0,0]}, 0.0, {K[0,2]}, 0.0, 0.0, {K[1,1]}, {K[1,2]}, 0.0, 0.0, 0.0, 1.0, 0.0]
"""
        return yaml_content

    def generate_summary_report(self) -> str:
        """
        Generate a human-readable summary report of the calibration package.

        Returns:
            Formatted summary string
        """
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("CALIBRATION PACKAGE SUMMARY")
        report_lines.append("=" * 70)
        report_lines.append(f"Package Location: {self.package_dir}")
        report_lines.append(f"Created: {self.metadata.get('created_date', 'Unknown')}")
        report_lines.append(f"Application: {self.metadata.get('application', 'Unknown')}")
        report_lines.append("")

        # List all files in package
        report_lines.append("Package Contents:")
        for file in sorted(self.package_dir.rglob('*')):
            if file.is_file():
                rel_path = file.relative_to(self.package_dir)
                size_kb = file.stat().st_size / 1024
                report_lines.append(f"  {rel_path} ({size_kb:.1f} KB)")

        report_lines.append("")
        report_lines.append("=" * 70)

        return "\n".join(report_lines)


def create_calibration_package_from_data(
    output_dir: Path,
    camera1_intrinsic: Optional[IntrinsicCalibration] = None,
    camera2_intrinsic: Optional[IntrinsicCalibration] = None,
    stereo_calibration: Optional[StereoCalibration] = None,
    alignment_transforms: Optional[Dict] = None,
    environment_data: Optional[Dict] = None
) -> CalibrationPackage:
    """
    Create a complete calibration package from calibration data.

    Args:
        output_dir: Output directory for package
        camera1_intrinsic: Camera 1 intrinsic calibration
        camera2_intrinsic: Camera 2 intrinsic calibration
        stereo_calibration: Stereo calibration
        alignment_transforms: Field alignment data
        environment_data: Environmental conditions

    Returns:
        CalibrationPackage object
    """
    package = CalibrationPackage(output_dir)
    package.create_package()

    # Determine calibration type
    if stereo_calibration:
        calib_type = 'stereo'
    elif camera1_intrinsic and camera2_intrinsic:
        calib_type = 'dual_independent'
    elif camera1_intrinsic or camera2_intrinsic:
        calib_type = 'single'
    else:
        calib_type = 'unknown'

    # Save metadata
    metadata = {
        'calibration_type': calib_type,
        'cameras': []
    }

    if camera1_intrinsic:
        metadata['cameras'].append({
            'id': 'camera1',
            'resolution': f"{camera1_intrinsic.image_size[0]}x{camera1_intrinsic.image_size[1]}",
            'calibration_date': camera1_intrinsic.calibration_date,
            'reprojection_error': camera1_intrinsic.reprojection_error
        })

    if camera2_intrinsic:
        metadata['cameras'].append({
            'id': 'camera2',
            'resolution': f"{camera2_intrinsic.image_size[0]}x{camera2_intrinsic.image_size[1]}",
            'calibration_date': camera2_intrinsic.calibration_date,
            'reprojection_error': camera2_intrinsic.reprojection_error
        })

    package.save_metadata(metadata)

    # Save calibrations
    if camera1_intrinsic:
        package.save_camera_intrinsic(camera1_intrinsic, 'camera1')

    if camera2_intrinsic:
        package.save_camera_intrinsic(camera2_intrinsic, 'camera2')

    if stereo_calibration:
        package.save_stereo_calibration(stereo_calibration)

    if alignment_transforms:
        package.save_alignment_transforms(alignment_transforms)

    if environment_data:
        package.save_environment_data(environment_data)

    return package
