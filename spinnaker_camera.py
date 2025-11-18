"""
Spinnaker Camera Backend - FLIR Firefly Support

Provides PySpin integration for FLIR machine vision cameras (Firefly, BlackFly, etc.)
"""

import numpy as np
from typing import Optional, Tuple, List, Dict
import logging

try:
    import PySpin
    PYSPIN_AVAILABLE = True
except ImportError:
    PYSPIN_AVAILABLE = False
    PySpin = None


class SpinnakerCamera:
    """
    Spinnaker SDK camera interface for FLIR machine vision cameras.

    Supports:
    - FLIR Firefly
    - FLIR BlackFly
    - FLIR Oryx
    - Other Spinnaker-compatible cameras
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.system = None
        self.camera = None
        self.is_connected = False
        self.camera_info = {}

        if not PYSPIN_AVAILABLE:
            self.logger.warning("PySpin not available. Install with: pip install spinnaker-python")

    def detect_cameras(self) -> List[Dict]:
        """
        Detect all Spinnaker cameras on the system.

        Returns:
            List of camera info dictionaries
        """
        if not PYSPIN_AVAILABLE:
            return []

        cameras_found = []

        try:
            self.system = PySpin.System.GetInstance()
            cam_list = self.system.GetCameras()

            for i, cam in enumerate(cam_list):
                try:
                    # Get camera info without initializing
                    nodemap_tldevice = cam.GetTLDeviceNodeMap()

                    device_model = self._get_node_value(nodemap_tldevice, 'DeviceModelName')
                    device_serial = self._get_node_value(nodemap_tldevice, 'DeviceSerialNumber')
                    device_vendor = self._get_node_value(nodemap_tldevice, 'DeviceVendorName')

                    camera_info = {
                        'index': i,
                        'backend': 'Spinnaker',
                        'model': device_model or 'Unknown',
                        'serial': device_serial or 'Unknown',
                        'vendor': device_vendor or 'FLIR',
                        'name': f"{device_vendor} {device_model} ({device_serial})"
                    }

                    cameras_found.append(camera_info)

                except Exception as e:
                    self.logger.error(f"Error reading camera {i}: {e}")

            cam_list.Clear()

        except Exception as e:
            self.logger.error(f"Failed to detect Spinnaker cameras: {e}")

        return cameras_found

    def connect(self, camera_index: int = 0) -> bool:
        """
        Connect to a Spinnaker camera.

        Args:
            camera_index: Index of camera to connect to

        Returns:
            True if successful, False otherwise
        """
        if not PYSPIN_AVAILABLE:
            self.logger.error("PySpin not available")
            return False

        try:
            if self.system is None:
                self.system = PySpin.System.GetInstance()

            cam_list = self.system.GetCameras()

            if camera_index >= cam_list.GetSize():
                self.logger.error(f"Camera index {camera_index} out of range")
                cam_list.Clear()
                return False

            self.camera = cam_list[camera_index]
            self.camera.Init()

            # Get camera node maps
            nodemap_tldevice = self.camera.GetTLDeviceNodeMap()
            nodemap = self.camera.GetNodeMap()

            # Get camera information
            self.camera_info = {
                'model': self._get_node_value(nodemap_tldevice, 'DeviceModelName'),
                'serial': self._get_node_value(nodemap_tldevice, 'DeviceSerialNumber'),
                'vendor': self._get_node_value(nodemap_tldevice, 'DeviceVendorName'),
                'width': self._get_node_value(nodemap, 'Width'),
                'height': self._get_node_value(nodemap, 'Height'),
                'pixel_format': self._get_node_value(nodemap, 'PixelFormat'),
                'backend': 'Spinnaker'
            }

            # Configure camera for continuous acquisition
            self._configure_camera()

            # Start acquisition
            self.camera.BeginAcquisition()
            self.is_connected = True

            self.logger.info(f"Connected to {self.camera_info['vendor']} {self.camera_info['model']}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Spinnaker camera: {e}")
            return False

    def _configure_camera(self):
        """Configure camera for optimal performance."""
        try:
            nodemap = self.camera.GetNodeMap()

            # Set acquisition mode to continuous
            node_acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionMode'))
            if PySpin.IsAvailable(node_acquisition_mode) and PySpin.IsWritable(node_acquisition_mode):
                node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
                acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()
                node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

            # Set pixel format to Mono8 or RGB8 (preferred for processing)
            node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
            if PySpin.IsAvailable(node_pixel_format) and PySpin.IsWritable(node_pixel_format):
                # Try RGB8 first, fall back to Mono8
                for fmt in ['RGB8', 'Mono8', 'BayerRG8']:
                    try:
                        entry = node_pixel_format.GetEntryByName(fmt)
                        if PySpin.IsAvailable(entry) and PySpin.IsReadable(entry):
                            node_pixel_format.SetIntValue(entry.GetValue())
                            self.logger.info(f"Set pixel format to {fmt}")
                            break
                    except:
                        continue

        except Exception as e:
            self.logger.warning(f"Failed to configure camera settings: {e}")

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from the camera.

        Returns:
            (success, frame): Success flag and frame as numpy array (BGR format)
        """
        if not self.is_connected or self.camera is None:
            return False, None

        try:
            # Retrieve next received image with timeout
            image_result = self.camera.GetNextImage(1000)  # 1 second timeout

            if image_result.IsIncomplete():
                self.logger.warning(f"Image incomplete: {image_result.GetImageStatus()}")
                image_result.Release()
                return False, None

            # Convert to numpy array
            width = image_result.GetWidth()
            height = image_result.GetHeight()
            image_data = image_result.GetNDArray()

            # Handle different pixel formats
            pixel_format = image_result.GetPixelFormatName()

            if 'Mono' in pixel_format or 'Bayer' in pixel_format:
                # Grayscale or Bayer pattern - convert to BGR
                if len(image_data.shape) == 2:
                    # Grayscale
                    frame = np.stack([image_data] * 3, axis=-1)
                else:
                    # Bayer - convert to RGB then to BGR
                    frame = image_data
                    if frame.shape[2] == 1:
                        frame = np.stack([frame[:,:,0]] * 3, axis=-1)
            elif 'RGB' in pixel_format:
                # RGB - convert to BGR
                frame = image_data[:, :, ::-1].copy()
            else:
                # Unknown format - try to handle gracefully
                frame = image_data
                if len(frame.shape) == 2:
                    frame = np.stack([frame] * 3, axis=-1)

            image_result.Release()

            return True, frame

        except Exception as e:
            self.logger.error(f"Failed to read frame: {e}")
            return False, None

    def disconnect(self):
        """Disconnect from camera and release resources."""
        try:
            if self.camera is not None:
                if self.is_connected:
                    self.camera.EndAcquisition()
                self.camera.DeInit()
                del self.camera
                self.camera = None

            if self.system is not None:
                self.system.ReleaseInstance()
                self.system = None

            self.is_connected = False
            self.logger.info("Disconnected from Spinnaker camera")

        except Exception as e:
            self.logger.error(f"Error disconnecting: {e}")

    def get_camera_info(self) -> Dict:
        """Get camera information."""
        return self.camera_info.copy()

    def _get_node_value(self, nodemap, node_name: str):
        """Safely get node value from nodemap."""
        try:
            node = nodemap.GetNode(node_name)
            if PySpin.IsAvailable(node) and PySpin.IsReadable(node):
                if PySpin.IsInteger(node):
                    return PySpin.CIntegerPtr(node).GetValue()
                elif PySpin.IsString(node):
                    return PySpin.CStringPtr(node).GetValue()
                elif PySpin.IsEnum(node):
                    return PySpin.CEnumerationPtr(node).ToString()
            return None
        except:
            return None

    def set_exposure(self, exposure_us: float) -> bool:
        """
        Set camera exposure time.

        Args:
            exposure_us: Exposure time in microseconds

        Returns:
            True if successful
        """
        if not self.is_connected:
            return False

        try:
            nodemap = self.camera.GetNodeMap()

            # Disable auto exposure
            node_exposure_auto = PySpin.CEnumerationPtr(nodemap.GetNode('ExposureAuto'))
            if PySpin.IsAvailable(node_exposure_auto) and PySpin.IsWritable(node_exposure_auto):
                entry = node_exposure_auto.GetEntryByName('Off')
                node_exposure_auto.SetIntValue(entry.GetValue())

            # Set exposure time
            node_exposure = PySpin.CFloatPtr(nodemap.GetNode('ExposureTime'))
            if PySpin.IsAvailable(node_exposure) and PySpin.IsWritable(node_exposure):
                exposure_to_set = min(exposure_us, node_exposure.GetMax())
                exposure_to_set = max(exposure_to_set, node_exposure.GetMin())
                node_exposure.SetValue(exposure_to_set)
                return True

        except Exception as e:
            self.logger.error(f"Failed to set exposure: {e}")

        return False

    def set_gain(self, gain_db: float) -> bool:
        """
        Set camera gain.

        Args:
            gain_db: Gain in dB

        Returns:
            True if successful
        """
        if not self.is_connected:
            return False

        try:
            nodemap = self.camera.GetNodeMap()

            # Disable auto gain
            node_gain_auto = PySpin.CEnumerationPtr(nodemap.GetNode('GainAuto'))
            if PySpin.IsAvailable(node_gain_auto) and PySpin.IsWritable(node_gain_auto):
                entry = node_gain_auto.GetEntryByName('Off')
                node_gain_auto.SetIntValue(entry.GetValue())

            # Set gain
            node_gain = PySpin.CFloatPtr(nodemap.GetNode('Gain'))
            if PySpin.IsAvailable(node_gain) and PySpin.IsWritable(node_gain):
                gain_to_set = min(gain_db, node_gain.GetMax())
                gain_to_set = max(gain_to_set, node_gain.GetMin())
                node_gain.SetValue(gain_to_set)
                return True

        except Exception as e:
            self.logger.error(f"Failed to set gain: {e}")

        return False
