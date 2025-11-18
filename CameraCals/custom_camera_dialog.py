"""
Custom Camera Specification Dialog

Allows users to input custom camera intrinsic parameters:
- Focal length
- Flange distance (for C-mount, CS-mount, etc.)
- Sensor dimensions (width, height in mm)
- Image resolution (pixels)
"""

from PyQt5 import QtWidgets, QtCore
from typing import Optional, Dict
from CameraCals.field_calibration import CameraSpec


class CustomCameraDialog(QtWidgets.QDialog):
    """Dialog for entering custom camera specifications."""

    def __init__(self, parent=None, initial_spec: Optional[CameraSpec] = None):
        super().__init__(parent)
        self.setWindowTitle("Custom Camera Specification")
        self.setModal(True)
        self.spec = initial_spec
        self._create_ui()

        # Populate with initial values if provided
        if initial_spec:
            self._populate_from_spec(initial_spec)

    def _create_ui(self):
        """Create the dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)

        # Camera name
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("Camera Name:"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Custom FLIR Camera")
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # Sensor dimensions group
        sensor_group = QtWidgets.QGroupBox("Sensor Physical Dimensions")
        sensor_layout = QtWidgets.QFormLayout(sensor_group)

        self.sensor_width_spin = QtWidgets.QDoubleSpinBox()
        self.sensor_width_spin.setRange(0.1, 100.0)
        self.sensor_width_spin.setValue(7.1)
        self.sensor_width_spin.setSuffix(" mm")
        self.sensor_width_spin.setDecimals(2)
        self.sensor_width_spin.setToolTip("Physical width of sensor in millimeters")
        sensor_layout.addRow("Sensor Width:", self.sensor_width_spin)

        self.sensor_height_spin = QtWidgets.QDoubleSpinBox()
        self.sensor_height_spin.setRange(0.1, 100.0)
        self.sensor_height_spin.setValue(5.3)
        self.sensor_height_spin.setSuffix(" mm")
        self.sensor_height_spin.setDecimals(2)
        self.sensor_height_spin.setToolTip("Physical height of sensor in millimeters")
        sensor_layout.addRow("Sensor Height:", self.sensor_height_spin)

        layout.addWidget(sensor_group)

        # Image resolution group
        resolution_group = QtWidgets.QGroupBox("Image Resolution")
        resolution_layout = QtWidgets.QFormLayout(resolution_group)

        self.image_width_spin = QtWidgets.QSpinBox()
        self.image_width_spin.setRange(1, 10000)
        self.image_width_spin.setValue(1920)
        self.image_width_spin.setSuffix(" px")
        self.image_width_spin.setToolTip("Image width in pixels")
        resolution_layout.addRow("Image Width:", self.image_width_spin)

        self.image_height_spin = QtWidgets.QSpinBox()
        self.image_height_spin.setRange(1, 10000)
        self.image_height_spin.setValue(1080)
        self.image_height_spin.setSuffix(" px")
        self.image_height_spin.setToolTip("Image height in pixels")
        resolution_layout.addRow("Image Height:", self.image_height_spin)

        layout.addWidget(resolution_group)

        # Lens parameters group
        lens_group = QtWidgets.QGroupBox("Lens Parameters")
        lens_layout = QtWidgets.QFormLayout(lens_group)

        self.focal_length_spin = QtWidgets.QDoubleSpinBox()
        self.focal_length_spin.setRange(1.0, 500.0)
        self.focal_length_spin.setValue(16.0)
        self.focal_length_spin.setSuffix(" mm")
        self.focal_length_spin.setDecimals(1)
        self.focal_length_spin.setToolTip("Lens focal length in millimeters")
        lens_layout.addRow("Focal Length:", self.focal_length_spin)

        self.flange_distance_spin = QtWidgets.QDoubleSpinBox()
        self.flange_distance_spin.setRange(0.0, 100.0)
        self.flange_distance_spin.setValue(17.526)  # C-mount standard
        self.flange_distance_spin.setSuffix(" mm")
        self.flange_distance_spin.setDecimals(3)
        self.flange_distance_spin.setToolTip(
            "Flange focal distance (back focal distance)\n"
            "C-mount: 17.526mm\n"
            "CS-mount: 12.5mm\n"
            "F-mount: 46.5mm"
        )
        lens_layout.addRow("Flange Distance:", self.flange_distance_spin)

        layout.addWidget(lens_group)

        # Mount type presets
        mount_group = QtWidgets.QGroupBox("Mount Type Presets")
        mount_layout = QtWidgets.QHBoxLayout(mount_group)

        self.mount_cmount_btn = QtWidgets.QPushButton("C-Mount (17.526mm)")
        self.mount_cmount_btn.clicked.connect(lambda: self.flange_distance_spin.setValue(17.526))
        mount_layout.addWidget(self.mount_cmount_btn)

        self.mount_csmount_btn = QtWidgets.QPushButton("CS-Mount (12.5mm)")
        self.mount_csmount_btn.clicked.connect(lambda: self.flange_distance_spin.setValue(12.5))
        mount_layout.addWidget(self.mount_csmount_btn)

        self.mount_fmount_btn = QtWidgets.QPushButton("F-Mount (46.5mm)")
        self.mount_fmount_btn.clicked.connect(lambda: self.flange_distance_spin.setValue(46.5))
        mount_layout.addWidget(self.mount_fmount_btn)

        layout.addWidget(mount_group)

        # Calculated parameters display
        calc_group = QtWidgets.QGroupBox("Calculated Parameters")
        calc_layout = QtWidgets.QFormLayout(calc_group)

        self.pixel_pitch_label = QtWidgets.QLabel("0.00 μm")
        calc_layout.addRow("Pixel Pitch:", self.pixel_pitch_label)

        self.crop_factor_label = QtWidgets.QLabel("0.00x")
        calc_layout.addRow("Crop Factor:", self.crop_factor_label)

        self.fov_h_label = QtWidgets.QLabel("0.0°")
        calc_layout.addRow("FOV Horizontal:", self.fov_h_label)

        self.fov_v_label = QtWidgets.QLabel("0.0°")
        calc_layout.addRow("FOV Vertical:", self.fov_v_label)

        layout.addWidget(calc_group)

        # Connect signals for real-time calculation
        self.sensor_width_spin.valueChanged.connect(self._update_calculated_params)
        self.sensor_height_spin.valueChanged.connect(self._update_calculated_params)
        self.image_width_spin.valueChanged.connect(self._update_calculated_params)
        self.image_height_spin.valueChanged.connect(self._update_calculated_params)
        self.focal_length_spin.valueChanged.connect(self._update_calculated_params)

        # Initial calculation
        self._update_calculated_params()

        # Dialog buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_calculated_params(self):
        """Update calculated parameters in real-time."""
        try:
            spec = self.get_camera_spec()

            # Pixel pitch
            self.pixel_pitch_label.setText(f"{spec.pixel_pitch_um:.2f} μm")

            # Crop factor
            self.crop_factor_label.setText(f"{spec.crop_factor:.2f}x")

            # FOV
            focal_length = self.focal_length_spin.value()
            fov_h, fov_v = spec.calculate_fov(focal_length)
            self.fov_h_label.setText(f"{fov_h:.1f}°")
            self.fov_v_label.setText(f"{fov_v:.1f}°")

        except Exception as e:
            pass  # Ignore calculation errors during input

    def _populate_from_spec(self, spec: CameraSpec):
        """Populate fields from existing CameraSpec."""
        self.name_edit.setText(spec.name)
        self.sensor_width_spin.setValue(spec.sensor_width_mm)
        self.sensor_height_spin.setValue(spec.sensor_height_mm)
        self.image_width_spin.setValue(spec.image_width_px)
        self.image_height_spin.setValue(spec.image_height_px)
        if spec.focal_length_mm:
            self.focal_length_spin.setValue(spec.focal_length_mm)

    def get_camera_spec(self) -> CameraSpec:
        """Get the CameraSpec from dialog inputs."""
        return CameraSpec(
            name=self.name_edit.text() or "Custom Camera",
            sensor_width_mm=self.sensor_width_spin.value(),
            sensor_height_mm=self.sensor_height_spin.value(),
            image_width_px=self.image_width_spin.value(),
            image_height_px=self.image_height_spin.value(),
            focal_length_mm=self.focal_length_spin.value()
        )

    def get_flange_distance(self) -> float:
        """Get the flange distance value."""
        return self.flange_distance_spin.value()

    @staticmethod
    def get_custom_camera(parent=None, initial_spec: Optional[CameraSpec] = None) -> Optional[Dict]:
        """
        Show dialog and return custom camera specification.

        Returns:
            Dictionary with CameraSpec and flange_distance, or None if cancelled
        """
        dialog = CustomCameraDialog(parent, initial_spec)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            return {
                'spec': dialog.get_camera_spec(),
                'flange_distance_mm': dialog.get_flange_distance()
            }

        return None
