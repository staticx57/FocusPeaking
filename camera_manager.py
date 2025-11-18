"""
Camera management module for FLIR Boson Focus Peaking.

Handles camera initialization, device detection, error recovery,
and reconnection logic.
"""

import cv2
import numpy as np
import logging
import platform
from typing import Optional, List, Tuple, Dict
from pathlib import Path

from config import (
    FRAME_WIDTH,
    FRAME_HEIGHT,
    CAMERA_RETRY_INTERVAL_MS,
    MAX_CAMERA_RETRY_ATTEMPTS,
    ENABLE_MOCK_CAMERA,
)

# Import Spinnaker camera support
try:
    from spinnaker_camera import SpinnakerCamera, PYSPIN_AVAILABLE
except ImportError:
    PYSPIN_AVAILABLE = False
    SpinnakerCamera = None

logger = logging.getLogger(__name__)


class CameraDevice:
    """Represents a camera device with its properties."""

    def __init__(self, index: int, name: str = None, backend: str = None,
                 camera_type: str = "opencv", serial: str = None):
        """
        Initialize camera device information.

        Args:
            index: Camera device index
            name: Human-readable device name
            backend: OpenCV backend name (e.g., 'V4L2', 'DSHOW') or 'Spinnaker'
            camera_type: Type of camera ('opencv' or 'spinnaker')
            serial: Camera serial number (for Spinnaker cameras)
        """
        self.index = index
        self.name = name or f"Camera {index}"
        self.backend = backend or "Unknown"
        self.camera_type = camera_type
        self.serial = serial

    def __str__(self) -> str:
        if self.backend == "Spinnaker" and self.serial:
            return f"{self.name} [Spinnaker]"
        return f"{self.name} (Device {self.index})"

    def __repr__(self) -> str:
        return f"CameraDevice(index={self.index}, name='{self.name}', backend='{self.backend}', type='{self.camera_type}')"


class CameraManager:
    """
    Manages camera connection, device enumeration, and error recovery.
    """

    def __init__(self):
        """Initialize the camera manager."""
        self.cap: Optional[cv2.VideoCapture] = None
        self.spinnaker_cam: Optional[SpinnakerCamera] = None
        self.current_device: Optional[CameraDevice] = None
        self.is_connected = False
        self.retry_count = 0
        self.frame_width = FRAME_WIDTH
        self.frame_height = FRAME_HEIGHT
        self._blank_frame = self._create_blank_frame()
        self.camera_type = "opencv"  # "opencv" or "spinnaker"

    def _create_blank_frame(self) -> np.ndarray:
        """Create a blank frame for when camera is unavailable."""
        frame = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
        # Add "No Camera" text
        text = "No Camera Connected"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1, 2)[0]
        text_x = (self.frame_width - text_size[0]) // 2
        text_y = (self.frame_height + text_size[1]) // 2
        cv2.putText(frame, text, (text_x, text_y), font, 1, (128, 128, 128), 2)
        return frame

    @staticmethod
    def detect_cameras(max_cameras: int = 10) -> List[CameraDevice]:
        """
        Detect available camera devices (OpenCV + Spinnaker).

        Args:
            max_cameras: Maximum number of camera indices to check

        Returns:
            List of detected camera devices
        """
        logger.info("Detecting available cameras...")
        available_cameras = []

        system = platform.system()
        logger.debug(f"Operating system: {system}")

        # First, detect Spinnaker cameras (FLIR Firefly, BlackFly, etc.)
        if PYSPIN_AVAILABLE and SpinnakerCamera is not None:
            try:
                spinner_cam = SpinnakerCamera()
                spinnaker_cameras = spinner_cam.detect_cameras()

                for cam_info in spinnaker_cameras:
                    device = CameraDevice(
                        index=cam_info['index'],
                        name=cam_info['name'],
                        backend="Spinnaker",
                        camera_type="spinnaker",
                        serial=cam_info.get('serial')
                    )
                    available_cameras.append(device)
                    logger.info(f"Found Spinnaker camera: {device}")

            except Exception as e:
                logger.warning(f"Error detecting Spinnaker cameras: {e}")

        # Then detect OpenCV cameras
        opencv_base_index = len(available_cameras)  # Offset to avoid conflicts

        for i in range(max_cameras):
            try:
                # Try to open camera
                cap = cv2.VideoCapture(i)

                if cap.isOpened():
                    # Try to read a frame to verify camera works
                    ret, _ = cap.read()

                    if ret:
                        # Get camera backend name
                        backend = cap.getBackendName()

                        # Try to get camera name (not always available)
                        name = f"Camera {i}"

                        # On Windows with DirectShow, we might get device name
                        if system == "Windows":
                            name = f"Camera {i} ({backend})"
                        elif system == "Linux":
                            # On Linux, cameras are typically /dev/videoX
                            name = f"/dev/video{i}"

                        device = CameraDevice(
                            index=i,
                            name=name,
                            backend=backend,
                            camera_type="opencv"
                        )
                        available_cameras.append(device)
                        logger.info(f"Found OpenCV camera: {device}")

                    cap.release()

            except Exception as e:
                logger.debug(f"Error checking camera {i}: {e}")
                continue

        logger.info(f"Detected {len(available_cameras)} camera(s) total")
        return available_cameras

    def connect(self, device: CameraDevice = None, device_index: int = 0) -> bool:
        """
        Connect to a camera device.

        Args:
            device: CameraDevice object (preferred) or None
            device_index: Camera device index (fallback if device is None)

        Returns:
            True if connection successful, False otherwise
        """
        # Release existing connection if any
        self.disconnect()

        # Handle legacy device_index parameter
        if device is None:
            device = CameraDevice(index=device_index, camera_type="opencv")

        logger.info(f"Attempting to connect to {device}...")

        try:
            if device.camera_type == "spinnaker":
                # Connect to Spinnaker camera
                if not PYSPIN_AVAILABLE:
                    logger.error("PySpin not available for Spinnaker camera")
                    return False

                self.spinnaker_cam = SpinnakerCamera()
                success = self.spinnaker_cam.connect(device.index)

                if success:
                    self.current_device = device
                    self.is_connected = True
                    self.camera_type = "spinnaker"
                    self.retry_count = 0
                    logger.info(f"Connected to Spinnaker camera: {device}")
                    return True
                else:
                    self.spinnaker_cam = None
                    return False

            else:
                # Connect to OpenCV camera
                self.cap = cv2.VideoCapture(device.index)

                if not self.cap.isOpened():
                    logger.error(f"Failed to open OpenCV camera {device.index}")
                    self.cap = None
                    return False

                # Set camera properties
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)

                # Try to read a test frame
                ret, frame = self.cap.read()
                if not ret:
                    logger.error(f"Camera {device.index} opened but cannot read frames")
                    self.cap.release()
                    self.cap = None
                    return False

                # Success!
                self.current_device = device
                self.is_connected = True
                self.camera_type = "opencv"
                self.retry_count = 0

                # Get actual frame dimensions
                actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                logger.info(
                    f"Successfully connected to camera {device} "
                    f"({actual_width}x{actual_height})"
                )

                return True

        except Exception as e:
            logger.error(f"Exception while connecting to camera {device}: {e}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """Disconnect from current camera."""
        # Disconnect Spinnaker camera
        if self.spinnaker_cam is not None:
            try:
                self.spinnaker_cam.disconnect()
                logger.info(f"Disconnected from Spinnaker camera {self.current_device}")
            except Exception as e:
                logger.error(f"Error releasing Spinnaker camera: {e}")
            finally:
                self.spinnaker_cam = None

        # Disconnect OpenCV camera
        if self.cap is not None:
            try:
                self.cap.release()
                logger.info(f"Disconnected from OpenCV camera {self.current_device}")
            except Exception as e:
                logger.error(f"Error releasing OpenCV camera: {e}")
            finally:
                self.cap = None

        self.current_device = None
        self.is_connected = False
        self.camera_type = "opencv"

    def read_frame(self) -> Tuple[bool, np.ndarray]:
        """
        Read a frame from the camera.

        Returns:
            Tuple of (success, frame)
            If camera not connected or read fails, returns (False, blank_frame)
        """
        if not self.is_connected:
            return False, self._blank_frame.copy()

        try:
            # Read from Spinnaker camera
            if self.camera_type == "spinnaker" and self.spinnaker_cam is not None:
                ret, frame = self.spinnaker_cam.read_frame()

                if not ret or frame is None:
                    logger.warning("Failed to read frame from Spinnaker camera")
                    self.is_connected = False
                    return False, self._blank_frame.copy()

            # Read from OpenCV camera
            elif self.camera_type == "opencv" and self.cap is not None:
                ret, frame = self.cap.read()

                if not ret:
                    logger.warning("Failed to read frame from OpenCV camera")
                    self.is_connected = False
                    return False, self._blank_frame.copy()

            else:
                return False, self._blank_frame.copy()

            # Resize frame to target dimensions if needed (optional)
            # Disabled for now to preserve original resolution
            # if frame.shape[:2] != (self.frame_height, self.frame_width):
            #     frame = cv2.resize(frame, (self.frame_width, self.frame_height))

            return True, frame

        except Exception as e:
            logger.error(f"Exception while reading frame: {e}")
            self.is_connected = False
            return False, self._blank_frame.copy()

    def attempt_reconnect(self) -> bool:
        """
        Attempt to reconnect to the last known camera device.

        Returns:
            True if reconnection successful, False otherwise
        """
        if self.retry_count >= MAX_CAMERA_RETRY_ATTEMPTS:
            logger.error(
                f"Max reconnection attempts ({MAX_CAMERA_RETRY_ATTEMPTS}) reached"
            )
            return False

        self.retry_count += 1
        logger.info(
            f"Reconnection attempt {self.retry_count}/{MAX_CAMERA_RETRY_ATTEMPTS}"
        )

        if self.current_device is not None:
            return self.connect(self.current_device)
        else:
            # Try to connect to first available camera
            cameras = self.detect_cameras()
            if cameras:
                return self.connect(cameras[0].index)
            return False

    def get_camera_info(self) -> Dict[str, any]:
        """
        Get information about the current camera.

        Returns:
            Dictionary with camera properties
        """
        if not self.is_connected or self.cap is None:
            return {
                "connected": False,
                "device": None,
                "width": 0,
                "height": 0,
                "fps": 0,
                "backend": None,
            }

        return {
            "connected": True,
            "device": self.current_device,
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": int(self.cap.get(cv2.CAP_PROP_FPS)),
            "backend": self.cap.getBackendName(),
            "fourcc": int(self.cap.get(cv2.CAP_PROP_FOURCC)),
        }

    def set_resolution(self, width: int, height: int) -> bool:
        """
        Set camera resolution.

        Args:
            width: Desired frame width
            height: Desired frame height

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected or self.cap is None:
            logger.warning("Cannot set resolution: camera not connected")
            return False

        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            # Verify the change
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if actual_width == width and actual_height == height:
                self.frame_width = width
                self.frame_height = height
                self._blank_frame = self._create_blank_frame()
                logger.info(f"Resolution set to {width}x{height}")
                return True
            else:
                logger.warning(
                    f"Requested {width}x{height}, got {actual_width}x{actual_height}"
                )
                return False

        except Exception as e:
            logger.error(f"Error setting resolution: {e}")
            return False

    def __del__(self):
        """Cleanup when manager is destroyed."""
        self.disconnect()


class MockCamera:
    """
    Mock camera for testing without physical hardware.
    Generates synthetic thermal-like imagery.
    """

    def __init__(self, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT):
        """
        Initialize mock camera.

        Args:
            width: Frame width
            height: Frame height
        """
        self.width = width
        self.height = height
        self.frame_count = 0
        logger.info("Mock camera initialized")

    def read(self) -> Tuple[bool, np.ndarray]:
        """
        Generate a synthetic frame.

        Returns:
            Tuple of (True, synthetic_frame)
        """
        # Create a frame with some synthetic thermal-like patterns
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Add some gradient background
        for y in range(self.height):
            intensity = int(40 + 20 * np.sin(y / 50 + self.frame_count / 50))
            frame[y, :] = intensity

        # Add some moving "hot spots"
        center_x = self.width // 2 + int(100 * np.sin(self.frame_count / 30))
        center_y = self.height // 2 + int(50 * np.cos(self.frame_count / 40))

        cv2.circle(frame, (center_x, center_y), 50, (150, 150, 150), -1)
        cv2.circle(frame, (center_x, center_y), 25, (200, 200, 200), -1)

        # Add some edges for focus peaking testing
        cv2.rectangle(frame, (50, 50), (200, 200), (180, 180, 180), 2)
        cv2.rectangle(frame, (400, 300), (550, 450), (180, 180, 180), 2)

        # Add "MOCK CAMERA" watermark
        cv2.putText(
            frame,
            "MOCK CAMERA",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (100, 100, 100),
            2,
        )

        self.frame_count += 1
        return True, frame

    def release(self):
        """Mock release (no-op)."""
        logger.info("Mock camera released")

    def isOpened(self) -> bool:
        """Mock is always 'open'."""
        return True

    def get(self, prop_id: int) -> float:
        """Mock property getter."""
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.height)
        elif prop_id == cv2.CAP_PROP_FPS:
            return 30.0
        return 0.0

    def set(self, prop_id: int, value: float) -> bool:
        """Mock property setter."""
        return True

    def getBackendName(self) -> str:
        """Return mock backend name."""
        return "MockCamera"
