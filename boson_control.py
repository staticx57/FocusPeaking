"""
FLIR Boson camera control module.

Provides interface to FLIR Boson SDK for controlling camera settings
including AGC, gain modes, FFC, color palettes, and more.

Note: Requires FLIR Boson SDK to be installed. If SDK is not available,
module will operate in compatibility mode with limited functionality.
"""

import sys
import os
import logging
from typing import Optional, Dict, Any, List
from enum import IntEnum
from pathlib import Path

from config import (
    BOSON_GAIN_MODES,
    BOSON_AGC_MODES,
    BOSON_FFC_MODES,
    BOSON_PALETTES,
    BOSON_DEFAULT_INTERFACE,
    BOSON_UART_BAUDRATE,
    BOSON_COMMAND_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Add SDK path to Python path
SDK_PATH = Path(__file__).parent / "3.0 IDD & SDK" / "SDK_USER_PERMISSIONS"
SDK_FOLDER_PATH = SDK_PATH / "SDK_USER_PERMISSIONS"

if SDK_FOLDER_PATH.exists():
    # Add both paths to ensure all imports work
    sys.path.insert(0, str(SDK_PATH))
    sys.path.insert(0, str(SDK_FOLDER_PATH))

# Try to import Boson SDK
SDK_AVAILABLE = False
pyClient = None
CamAPI = None

try:
    # Import from the SDK package (works like: from SDK_USER_PERMISSIONS import *)
    import SDK_USER_PERMISSIONS.ClientFiles_Python.Client_API as Client_API_module
    pyClient = Client_API_module.pyClient

    # Also import the CamAPI alias
    import SDK_USER_PERMISSIONS as SDK
    CamAPI = SDK.CamAPI

    SDK_AVAILABLE = True
    logger.info("FLIR Boson SDK loaded successfully")
except ImportError as e:
    logger.warning(f"FLIR Boson SDK not found: {e}. Camera control will be limited.")
except Exception as e:
    logger.error(f"Error loading FLIR Boson SDK: {e}")


class GainMode(IntEnum):
    """Boson gain mode enumeration."""
    HIGH = 0
    LOW = 1
    AUTO = 2


class AGCMode(IntEnum):
    """Boson AGC mode enumeration."""
    MANUAL = 0
    AUTO = 1
    LINEAR = 2


class FFCMode(IntEnum):
    """Boson FFC mode enumeration."""
    MANUAL = 0
    AUTO = 1
    EXTERNAL = 2


class BosonController:
    """
    Controller for FLIR Boson camera settings.

    Provides high-level interface to camera controls including:
    - Gain control (High/Low/Auto)
    - AGC modes (Manual/Auto/Linear)
    - FFC (Flat Field Correction)
    - Color palettes
    - Temperature linear mode
    - DDE (Digital Detail Enhancement)
    """

    def __init__(self, port: Optional[str] = None):
        """
        Initialize Boson controller.

        Args:
            port: Serial port for UART communication (e.g., 'COM6' or '/dev/ttyUSB0')
                  If None, will attempt auto-detection
        """
        self.port = port
        self.client = None
        self.is_connected = False
        self.sdk_available = SDK_AVAILABLE
        self.current_palette = "WhiteHot"  # Track current palette for software application

        if not SDK_AVAILABLE:
            logger.warning(
                "Boson SDK not available. Install SDK from: "
                "https://www.flir.com/support/products/boson/"
            )
        else:
            # Auto-detect FLIR Control port if not specified
            if not self.port:
                self.port = self._auto_detect_port()
                if self.port:
                    logger.info(f"Auto-detected FLIR Boson on {self.port}")

    def _auto_detect_port(self) -> Optional[str]:
        """
        Auto-detect FLIR Boson COM port.

        Returns:
            COM port string or None if not found
        """
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()

            # Look for FLIR Control port
            for port in ports:
                if 'FLIR' in port.description.upper():
                    logger.info(f"Found FLIR device: {port.device} - {port.description}")
                    return port.device

            # Fallback: check common Boson ports
            for port in ports:
                desc_upper = port.description.upper()
                if any(keyword in desc_upper for keyword in ['BOSON', 'THERMAL', 'USB SERIAL']):
                    logger.info(f"Potential FLIR device: {port.device} - {port.description}")
                    return port.device

        except Exception as e:
            logger.error(f"Error detecting COM ports: {e}")

        return None

    def connect(self) -> bool:
        """
        Connect to Boson camera.

        Returns:
            True if connection successful, False otherwise
        """
        if not self.sdk_available:
            logger.error("Cannot connect: Boson SDK not available")
            return False

        if not self.port:
            logger.error("Cannot connect: No COM port specified")
            return False

        try:
            logger.info(f"Attempting to connect to Boson on {self.port}...")

            # Initialize the Boson SDK client
            self.client = pyClient(
                manualport=self.port,
                manualbaud=BOSON_UART_BAUDRATE,
                useDll=True,  # Use precompiled FSLP DLL
                ex=True  # Enable exception mode
            )

            # Test connection with a simple API call
            try:
                serial_result = self.client.bosonGetCameraSN()
                # Handle both tuple and direct return
                if isinstance(serial_result, tuple):
                    serial_number = serial_result[1] if len(serial_result) > 1 else serial_result[0]
                else:
                    serial_number = serial_result
                logger.info(f"Connected to Boson camera. Serial: {serial_number}")
                self.is_connected = True
                return True
            except Exception as e:
                logger.error(f"Failed to communicate with Boson: {e}")
                self.client = None
                return False

        except Exception as e:
            logger.error(f"Failed to connect to Boson: {e}")
            self.client = None
            return False

    def disconnect(self) -> None:
        """Disconnect from Boson camera."""
        if self.client:
            try:
                self.client.Close()
                logger.info("Disconnected from Boson camera")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self.client = None
                self.is_connected = False

    # ========================================================================
    # Gain Control
    # ========================================================================

    def set_gain_mode(self, mode: GainMode) -> bool:
        """
        Set gain mode.

        Args:
            mode: Gain mode (HIGH, LOW, AUTO)

        Returns:
            True if successful
        """
        if not self._check_connection():
            return False

        try:
            # Map to SDK enum
            from SDK_USER_PERMISSIONS.ClientFiles_Python.EnumTypes import FLR_BOSON_GAINMODE_E
            mode_map = {
                GainMode.HIGH: FLR_BOSON_GAINMODE_E.FLR_BOSON_HIGH_GAIN,
                GainMode.LOW: FLR_BOSON_GAINMODE_E.FLR_BOSON_LOW_GAIN,
                GainMode.AUTO: FLR_BOSON_GAINMODE_E.FLR_BOSON_AUTO_GAIN,
            }

            self.client.bosonSetGainMode(mode_map[mode])
            logger.info(f"Gain mode set to {GainMode(mode).name}")
            return True
        except Exception as e:
            logger.error(f"Failed to set gain mode: {e}")
            return False

    def get_gain_mode(self) -> Optional[GainMode]:
        """
        Get current gain mode.

        Returns:
            Current gain mode or None if error
        """
        if not self._check_connection():
            return None

        try:
            from SDK_USER_PERMISSIONS.ClientFiles_Python.EnumTypes import FLR_BOSON_GAINMODE_E
            mode = self.client.bosonGetGainMode()

            # Map back from SDK enum
            reverse_map = {
                FLR_BOSON_GAINMODE_E.FLR_BOSON_HIGH_GAIN: GainMode.HIGH,
                FLR_BOSON_GAINMODE_E.FLR_BOSON_LOW_GAIN: GainMode.LOW,
                FLR_BOSON_GAINMODE_E.FLR_BOSON_AUTO_GAIN: GainMode.AUTO,
            }

            return reverse_map.get(mode)
        except Exception as e:
            logger.error(f"Failed to get gain mode: {e}")
            return None

    # ========================================================================
    # AGC Control
    # ========================================================================

    def set_agc_mode(self, mode: AGCMode) -> bool:
        """
        Set AGC (Automatic Gain Control) mode.

        Args:
            mode: AGC mode (MANUAL, AUTO, LINEAR)

        Returns:
            True if successful
        """
        if not self._check_connection():
            return False

        try:
            from SDK_USER_PERMISSIONS.ClientFiles_Python.EnumTypes import FLR_AGC_MODE_E

            # Map to SDK enum
            mode_map = {
                AGCMode.MANUAL: FLR_AGC_MODE_E.FLR_AGC_MODE_MANUAL,
                AGCMode.AUTO: FLR_AGC_MODE_E.FLR_AGC_MODE_NORMAL,
                AGCMode.LINEAR: FLR_AGC_MODE_E.FLR_AGC_MODE_AUTO_LINEAR,
            }

            self.client.agcSetMode(mode_map[mode])
            logger.info(f"AGC mode set to {AGCMode(mode).name}")
            return True
        except Exception as e:
            logger.error(f"Failed to set AGC mode: {e}")
            return False

    def get_agc_mode(self) -> Optional[AGCMode]:
        """Get current AGC mode."""
        if not self._check_connection():
            return None

        try:
            from SDK_USER_PERMISSIONS.ClientFiles_Python.EnumTypes import FLR_AGC_MODE_E

            mode = self.client.agcGetMode()

            # Map back from SDK enum
            reverse_map = {
                FLR_AGC_MODE_E.FLR_AGC_MODE_MANUAL: AGCMode.MANUAL,
                FLR_AGC_MODE_E.FLR_AGC_MODE_NORMAL: AGCMode.AUTO,
                FLR_AGC_MODE_E.FLR_AGC_MODE_AUTO_LINEAR: AGCMode.LINEAR,
            }

            result = reverse_map.get(mode)
            if result is None:
                logger.debug(f"Unknown AGC mode value: {mode}, defaulting to AUTO")
                return AGCMode.AUTO
            return result

        except Exception as e:
            # AGC mode query may not be supported in all camera states
            logger.debug(f"Could not query AGC mode (error {e}), defaulting to AUTO")
            return AGCMode.AUTO

    # ========================================================================
    # FFC Control
    # ========================================================================

    def perform_ffc(self) -> bool:
        """
        Manually trigger Flat Field Correction.

        Returns:
            True if successful
        """
        if not self._check_connection():
            return False

        try:
            self.client.bosonRunFFC()
            logger.info("FFC triggered")
            return True
        except Exception as e:
            logger.error(f"Failed to perform FFC: {e}")
            return False

    def set_ffc_mode(self, mode: FFCMode) -> bool:
        """
        Set FFC mode.

        Args:
            mode: FFC mode (MANUAL, AUTO, EXTERNAL)

        Returns:
            True if successful
        """
        if not self._check_connection():
            return False

        try:
            from SDK_USER_PERMISSIONS.ClientFiles_Python.EnumTypes import FLR_BOSON_FFCMODE_E
            mode_map = {
                FFCMode.MANUAL: FLR_BOSON_FFCMODE_E.FLR_BOSON_MANUAL_FFC,
                FFCMode.AUTO: FLR_BOSON_FFCMODE_E.FLR_BOSON_AUTO_FFC,
                FFCMode.EXTERNAL: FLR_BOSON_FFCMODE_E.FLR_BOSON_EXTERNAL_FFC,
            }

            self.client.bosonSetFFCMode(mode_map[mode])
            logger.info(f"FFC mode set to {FFCMode(mode).name}")
            return True
        except Exception as e:
            logger.error(f"Failed to set FFC mode: {e}")
            return False

    # ========================================================================
    # Color Palette Control
    # ========================================================================

    def set_palette(self, palette_name: str) -> bool:
        """
        Set color palette/LUT.

        Args:
            palette_name: Palette name (e.g., 'WhiteHot', 'BlackHot', 'Rainbow')

        Returns:
            True if successful
        """
        if palette_name not in BOSON_PALETTES:
            logger.error(f"Unknown palette: {palette_name}")
            return False

        # Update current palette for software application (works even without SDK connection)
        self.current_palette = palette_name
        logger.info(f"Palette set to {palette_name} (software)")

        # If not connected, software palette is still available
        if not self._check_connection():
            return True

        # Try to set hardware palette (may not be supported on all Boson models)
        try:
            from SDK_USER_PERMISSIONS.ClientFiles_Python.EnumTypes import FLR_COLORLUT_ID_E

            # Map palette names to SDK enum
            palette_map = {
                "WhiteHot": FLR_COLORLUT_ID_E.FLR_COLORLUT_WHITEHOT,
                "BlackHot": FLR_COLORLUT_ID_E.FLR_COLORLUT_BLACKHOT,
                "Rainbow": FLR_COLORLUT_ID_E.FLR_COLORLUT_RAINBOW,
                "RainbowHC": FLR_COLORLUT_ID_E.FLR_COLORLUT_RAINBOW_HC,
                "Ironbow": FLR_COLORLUT_ID_E.FLR_COLORLUT_IRONBOW,
                "Lava": FLR_COLORLUT_ID_E.FLR_COLORLUT_LAVA,
                "Arctic": FLR_COLORLUT_ID_E.FLR_COLORLUT_ARCTIC,
                "Globow": FLR_COLORLUT_ID_E.FLR_COLORLUT_GLOBOW,
                "Gradedfire": FLR_COLORLUT_ID_E.FLR_COLORLUT_GRADEDFIRE,
                "Hottest": FLR_COLORLUT_ID_E.FLR_COLORLUT_HOTTEST,
            }

            if palette_name in palette_map:
                self.client.colorLutSetControl(palette_map[palette_name])
                logger.debug(f"Hardware palette command sent to camera")
        except Exception as e:
            # Hardware palette control may not be supported - software palette will be used
            logger.debug(f"Hardware palette not supported (using software palette): {e}")

        return True

    def get_available_palettes(self) -> List[str]:
        """Get list of available color palettes."""
        return list(BOSON_PALETTES.keys())

    # ========================================================================
    # Temperature and DDE
    # ========================================================================

    def enable_tlinear(self, enable: bool = True) -> bool:
        """
        Enable/disable Temperature Linear mode.

        When enabled, pixel values represent temperature.

        Args:
            enable: True to enable, False to disable

        Returns:
            True if successful
        """
        if not self._check_connection():
            return False

        try:
            state = 1 if enable else 0
            self.client.bosonSetTLinearEnableState(state)
            logger.info(f"TLinear {'enabled' if enable else 'disabled'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set TLinear: {e}")
            return False

    def set_dde(self, level: int) -> bool:
        """
        Set Digital Detail Enhancement level.

        Args:
            level: DDE level (0-255, where 0 is off)

        Returns:
            True if successful
        """
        if not self._check_connection():
            return False

        if not 0 <= level <= 255:
            logger.error(f"DDE level must be 0-255, got {level}")
            return False

        try:
            self.client.dvoSetAnalogVideoState(level)
            logger.info(f"DDE level set to {level}")
            return True
        except Exception as e:
            logger.error(f"Failed to set DDE: {e}")
            return False

    # ========================================================================
    # Camera Information
    # ========================================================================

    def get_camera_info(self) -> Dict[str, Any]:
        """
        Get camera information and current settings.

        Returns:
            Dictionary with camera info
        """
        if not self._check_connection():
            return {"connected": False, "sdk_available": self.sdk_available}

        try:
            info = {
                "connected": True,
                "sdk_available": True,
                "port": self.port,
            }

            # Try to get serial number
            try:
                serial_result = self.client.bosonGetCameraSN()
                if isinstance(serial_result, tuple):
                    info["serial_number"] = serial_result[1] if len(serial_result) > 1 else serial_result[0]
                else:
                    info["serial_number"] = serial_result
            except:
                pass

            # Try to get firmware version
            try:
                fw_result = self.client.bosonGetSoftwareRev()
                if isinstance(fw_result, tuple):
                    if len(fw_result) >= 4:
                        info["firmware_version"] = f"{fw_result[1]}.{fw_result[2]}.{fw_result[3]}"
                    elif len(fw_result) == 3:
                        info["firmware_version"] = f"{fw_result[0]}.{fw_result[1]}.{fw_result[2]}"
                else:
                    info["firmware_version"] = str(fw_result)
            except:
                pass

            # Get current modes
            info["gain_mode"] = self.get_gain_mode()
            info["agc_mode"] = self.get_agc_mode()

            return info

        except Exception as e:
            logger.error(f"Failed to get camera info: {e}")
            return {"connected": False, "error": str(e)}

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _check_connection(self) -> bool:
        """Check if connected to camera."""
        if not self.sdk_available:
            logger.debug("Boson SDK not available")
            return False

        if not self.is_connected:
            logger.warning("Not connected to Boson camera")
            return False

        return True

    def __del__(self):
        """Cleanup on deletion."""
        self.disconnect()


# ============================================================================
# Software Palette Application
# ============================================================================

def apply_palette_software(frame, palette_name: str):
    """
    Apply color palette to grayscale frame in software.

    This is used when the camera outputs grayscale thermal data via USB.

    Args:
        frame: Input frame (grayscale or BGR)
        palette_name: Name of palette to apply

    Returns:
        BGR color frame with palette applied
    """
    import cv2
    import numpy as np

    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame

    # Map Boson palette names to OpenCV colormaps
    # OpenCV has built-in colormaps similar to thermal camera palettes
    colormap_mapping = {
        "WhiteHot": None,  # Keep grayscale (inverted)
        "BlackHot": None,  # Keep grayscale
        "Rainbow": cv2.COLORMAP_RAINBOW,
        "RainbowHC": cv2.COLORMAP_JET,
        "Ironbow": cv2.COLORMAP_HOT,
        "Lava": cv2.COLORMAP_HOT,
        "Arctic": cv2.COLORMAP_WINTER,
        "Globow": cv2.COLORMAP_RAINBOW,
        "Gradedfire": cv2.COLORMAP_AUTUMN,
        "Hottest": cv2.COLORMAP_HOT,
    }

    colormap = colormap_mapping.get(palette_name)

    if colormap is None:
        # For WhiteHot/BlackHot, return grayscale as BGR
        if palette_name == "WhiteHot":
            # White = hot (normal grayscale)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        elif palette_name == "BlackHot":
            # Black = hot (inverted)
            inverted = 255 - gray
            return cv2.cvtColor(inverted, cv2.COLOR_GRAY2BGR)
        else:
            # Unknown palette, return original grayscale
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    else:
        # Apply OpenCV colormap
        return cv2.applyColorMap(gray, colormap)


# ============================================================================
# Standalone Control Functions
# ============================================================================

def create_boson_controller(port: Optional[str] = None) -> BosonController:
    """
    Factory function to create and connect to Boson controller.

    Args:
        port: Optional serial port (e.g., 'COM6'). Auto-detects if None.

    Returns:
        Connected BosonController instance (or unconnected if SDK unavailable)
    """
    controller = BosonController(port)

    if controller.sdk_available:
        if controller.connect():
            logger.info("Successfully connected to Boson camera")
        else:
            logger.warning("Failed to connect to Boson camera")
    else:
        logger.info(
            "Boson SDK not available. Camera control disabled. "
            "To enable, ensure SDK files are in '3.0 IDD & SDK' folder."
        )

    return controller


# ============================================================================
# Smart Palette Switcher (Phase 6)
# ============================================================================

class SmartPaletteSwitcher:
    """
    Automatically switches to optimal palette during focusing.

    This class follows thermal imaging best practices by switching to
    WhiteHot (grayscale) palette when the user is adjusting focus, making
    edges more visible. It automatically detects focus attempts based on
    rapid focus score changes.
    """

    def __init__(self, boson_controller: Optional[BosonController] = None):
        """
        Initialize the smart palette switcher.

        Args:
            boson_controller: Optional BosonController instance
        """
        self.controller = boson_controller
        self.original_palette = None
        self.focus_mode_active = False
        self.auto_switch_enabled = False
        self.focus_mode_palette = "WhiteHot"  # Best for focusing

        # Auto-detection state
        self.detection_enabled = True
        self.focus_stable_count = 0
        self.stable_threshold = 10  # Frames of stability before exit

        logger.debug("SmartPaletteSwitcher initialized")

    def enable_auto_switch(self, enabled: bool) -> None:
        """
        Enable or disable automatic palette switching.

        Args:
            enabled: True to enable auto-switching
        """
        self.auto_switch_enabled = enabled
        logger.info(f"Auto palette switching: {'enabled' if enabled else 'disabled'}")

        # Exit focus mode if auto-switch is disabled
        if not enabled and self.focus_mode_active:
            self.exit_focus_mode()

    def enter_focus_mode(self, manual: bool = False) -> bool:
        """
        Enter focus mode - switch to WhiteHot palette.

        Args:
            manual: If True, this is a manual activation (not auto-detected)

        Returns:
            True if successfully entered focus mode
        """
        if not self.controller or not self.controller.is_connected:
            logger.debug("Cannot enter focus mode: Boson not connected")
            return False

        if self.focus_mode_active:
            logger.debug("Focus mode already active")
            return True

        # Save current palette
        try:
            self.original_palette = self.controller.current_palette or "WhiteHot"
            logger.debug(f"Saved original palette: {self.original_palette}")
        except Exception as e:
            logger.warning(f"Could not save current palette: {e}")
            self.original_palette = "WhiteHot"

        # Switch to focus mode palette
        try:
            if self.original_palette != self.focus_mode_palette:
                # Only switch if not already in focus mode palette
                success = self.controller.set_palette(self.focus_mode_palette)
                if success:
                    self.focus_mode_active = True
                    self.focus_stable_count = 0
                    mode_type = "manually" if manual else "automatically"
                    logger.info(f"Entered focus mode {mode_type}: switched to {self.focus_mode_palette}")
                    return True
                else:
                    logger.warning("Failed to switch to focus mode palette")
                    return False
            else:
                logger.debug(f"Already using {self.focus_mode_palette}, no switch needed")
                self.focus_mode_active = True
                return True

        except Exception as e:
            logger.error(f"Error entering focus mode: {e}")
            return False

    def exit_focus_mode(self, force: bool = False) -> bool:
        """
        Exit focus mode - restore original palette.

        Args:
            force: If True, exit immediately even if auto-detection is active

        Returns:
            True if successfully exited focus mode
        """
        if not self.focus_mode_active:
            return True

        if not self.controller or not self.controller.is_connected:
            self.focus_mode_active = False
            return True

        # Restore original palette
        try:
            if self.original_palette and self.original_palette != self.focus_mode_palette:
                success = self.controller.set_palette(self.original_palette)
                if success:
                    self.focus_mode_active = False
                    logger.info(f"Exited focus mode: restored {self.original_palette} palette")
                    return True
                else:
                    logger.warning("Failed to restore original palette")
                    return False
            else:
                self.focus_mode_active = False
                logger.debug("Exited focus mode (no palette change needed)")
                return True

        except Exception as e:
            logger.error(f"Error exiting focus mode: {e}")
            self.focus_mode_active = False
            return False

    def auto_detect_focus_attempt(self, focus_history: 'deque') -> bool:
        """
        Detect if user is adjusting focus based on rapid changes.

        Args:
            focus_history: Deque of recent focus scores

        Returns:
            True if focus adjustment detected
        """
        if not self.auto_switch_enabled or not self.detection_enabled:
            return False

        if len(focus_history) < 5:
            return False

        # Get recent focus scores
        recent = list(focus_history)[-5:]

        try:
            variance = float(np.var(recent))
            mean = float(np.mean(recent))

            if mean == 0:
                return False

            # Calculate coefficient of variation (normalized variance)
            coefficient_of_variation = (float(np.sqrt(variance)) / mean)

            # High variation suggests focus adjustment
            # 15% variation threshold
            is_adjusting = coefficient_of_variation > 0.15

            if is_adjusting:
                self.focus_stable_count = 0
                return True
            else:
                self.focus_stable_count += 1
                return False

        except Exception as e:
            logger.error(f"Error in focus detection: {e}")
            return False

    def update(self, focus_history: 'deque') -> None:
        """
        Update the palette switcher state based on focus history.

        This should be called on each frame to enable automatic switching.

        Args:
            focus_history: Deque of recent focus scores
        """
        if not self.auto_switch_enabled:
            return

        # Detect if focusing
        is_focusing = self.auto_detect_focus_attempt(focus_history)

        if is_focusing:
            # Enter focus mode if not already in it
            if not self.focus_mode_active:
                self.enter_focus_mode(manual=False)
        else:
            # Exit focus mode if stable for long enough
            if self.focus_mode_active and self.focus_stable_count > self.stable_threshold:
                self.exit_focus_mode(force=False)

    def set_focus_mode_palette(self, palette: str) -> None:
        """
        Set the palette to use in focus mode.

        Args:
            palette: Palette name (default: "WhiteHot")
        """
        self.focus_mode_palette = palette
        logger.info(f"Focus mode palette set to: {palette}")

    def is_active(self) -> bool:
        """Check if focus mode is currently active."""
        return self.focus_mode_active

    def get_status(self) -> Dict[str, any]:
        """
        Get current status of the palette switcher.

        Returns:
            Dictionary with status information
        """
        return {
            'focus_mode_active': self.focus_mode_active,
            'auto_switch_enabled': self.auto_switch_enabled,
            'original_palette': self.original_palette,
            'focus_mode_palette': self.focus_mode_palette,
            'focus_stable_count': self.focus_stable_count,
        }
