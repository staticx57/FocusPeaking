"""
FLIR Boson Camera Controls UI Panel

Provides a user-friendly interface for controlling FLIR Boson camera settings
including gain modes, AGC, FFC, color palettes, and more.
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Optional, Dict, Any
import logging

from boson_control import BosonController, GainMode, AGCMode, FFCMode
from config import BOSON_GAIN_MODES, BOSON_AGC_MODES, BOSON_PALETTES

logger = logging.getLogger(__name__)


class BosonControlPanel(QtWidgets.QGroupBox):
    """
    UI panel for FLIR Boson camera controls.

    Provides controls for:
    - Gain Mode (High/Low/Auto)
    - AGC Mode (Manual/Auto/Linear)
    - Color Palettes
    - Flat Field Correction (FFC)
    - Digital Detail Enhancement (DDE)
    - Temperature Linear Mode

    Signals:
        settingsChanged: Emitted when any setting changes
    """

    # Signals
    settingsChanged = QtCore.pyqtSignal(dict)
    ffcTriggered = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        """
        Initialize Boson control panel.

        Args:
            parent: Parent widget
        """
        super().__init__("FLIR Boson Controls", parent)
        self.controller: Optional[BosonController] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self._create_ui()
        self._set_controls_enabled(False)  # Disabled until controller set

    def _create_ui(self):
        """Create the control panel UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # Gain Mode
        gain_layout = QtWidgets.QHBoxLayout()
        gain_label = QtWidgets.QLabel("Gain Mode:")
        gain_label.setMinimumWidth(90)
        gain_layout.addWidget(gain_label)

        self.gain_combo = QtWidgets.QComboBox()
        self.gain_combo.addItems(["High", "Low", "Auto"])
        self.gain_combo.setToolTip("Camera gain setting:\nHigh - More sensitive, noisier\nLow - Less sensitive, cleaner\nAuto - Automatic adjustment")
        self.gain_combo.currentTextChanged.connect(self._on_gain_changed)
        gain_layout.addWidget(self.gain_combo)
        layout.addLayout(gain_layout)

        # AGC Mode
        agc_layout = QtWidgets.QHBoxLayout()
        agc_label = QtWidgets.QLabel("AGC Mode:")
        agc_label.setMinimumWidth(90)
        agc_layout.addWidget(agc_label)

        self.agc_combo = QtWidgets.QComboBox()
        self.agc_combo.addItems(["Manual", "Auto", "Linear"])
        self.agc_combo.setToolTip("Automatic Gain Control:\nManual - Fixed gain\nAuto - Adaptive contrast\nLinear - Temperature-based")
        self.agc_combo.currentTextChanged.connect(self._on_agc_changed)
        agc_layout.addWidget(self.agc_combo)
        layout.addLayout(agc_layout)

        # Color Palette
        palette_layout = QtWidgets.QHBoxLayout()
        palette_label = QtWidgets.QLabel("Color Palette:")
        palette_label.setMinimumWidth(90)
        palette_layout.addWidget(palette_label)

        self.palette_combo = QtWidgets.QComboBox()
        self.palette_combo.addItems(list(BOSON_PALETTES.keys()))
        self.palette_combo.setToolTip("Color mapping for thermal display")
        self.palette_combo.currentTextChanged.connect(self._on_palette_changed)
        palette_layout.addWidget(self.palette_combo)
        layout.addLayout(palette_layout)

        # Divider
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # FFC Button and mode
        ffc_layout = QtWidgets.QHBoxLayout()

        self.ffc_btn = QtWidgets.QPushButton("Trigger FFC")
        self.ffc_btn.setToolTip("Perform Flat Field Correction\n(Removes fixed pattern noise)")
        self.ffc_btn.clicked.connect(self._on_ffc_clicked)
        ffc_layout.addWidget(self.ffc_btn)

        self.ffc_mode_combo = QtWidgets.QComboBox()
        self.ffc_mode_combo.addItems(["Manual", "Auto", "External"])
        self.ffc_mode_combo.setToolTip("FFC trigger mode")
        self.ffc_mode_combo.currentTextChanged.connect(self._on_ffc_mode_changed)
        ffc_layout.addWidget(self.ffc_mode_combo)

        layout.addLayout(ffc_layout)

        # DDE Slider
        dde_label_layout = QtWidgets.QHBoxLayout()
        dde_label = QtWidgets.QLabel("DDE:")
        dde_label.setToolTip("Digital Detail Enhancement\n(Edge sharpening)")
        dde_label_layout.addWidget(dde_label)
        dde_label_layout.addStretch()
        self.dde_value_label = QtWidgets.QLabel("0")
        self.dde_value_label.setMinimumWidth(30)
        self.dde_value_label.setAlignment(QtCore.Qt.AlignRight)
        dde_label_layout.addWidget(self.dde_value_label)
        layout.addLayout(dde_label_layout)

        self.dde_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.dde_slider.setRange(0, 255)
        self.dde_slider.setValue(0)
        self.dde_slider.setToolTip("Adjust edge enhancement (0-255)")
        self.dde_slider.valueChanged.connect(self._on_dde_changed)
        layout.addWidget(self.dde_slider)

        # Temperature Linear checkbox
        self.tlinear_check = QtWidgets.QCheckBox("Temperature Linear Mode")
        self.tlinear_check.setToolTip("Enable temperature-based pixel values\n(For radiometric measurements)")
        self.tlinear_check.stateChanged.connect(self._on_tlinear_changed)
        layout.addWidget(self.tlinear_check)

        # Divider
        line2 = QtWidgets.QFrame()
        line2.setFrameShape(QtWidgets.QFrame.HLine)
        line2.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line2)

        # Status indicator
        self.status_label = QtWidgets.QLabel("● Status: Not connected")
        self.status_label.setStyleSheet("font-size: 8pt; color: #888;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # SDK info label
        self.sdk_label = QtWidgets.QLabel("SDK: Not available")
        self.sdk_label.setStyleSheet("font-size: 8pt; color: #888;")
        layout.addWidget(self.sdk_label)

    # ========================================================================
    # Public Methods
    # ========================================================================

    def set_controller(self, controller: Optional[BosonController]):
        """
        Set the Boson controller instance.

        Args:
            controller: BosonController instance or None
        """
        self.controller = controller
        self._update_status()

        if controller and controller.sdk_available:
            self.logger.info("Boson controller connected")
            self._load_current_settings()
        else:
            self.logger.warning("Boson controller not available or SDK missing")

    def get_settings(self) -> Dict[str, Any]:
        """
        Get current UI settings.

        Returns:
            Dictionary of current settings
        """
        return {
            "gain_mode": self.gain_combo.currentText(),
            "agc_mode": self.agc_combo.currentText(),
            "palette": self.palette_combo.currentText(),
            "ffc_mode": self.ffc_mode_combo.currentText(),
            "dde": self.dde_slider.value(),
            "tlinear": self.tlinear_check.isChecked(),
        }

    def apply_settings(self, settings: Dict[str, Any]):
        """
        Apply settings from dictionary.

        Args:
            settings: Dictionary of settings to apply
        """
        if "gain_mode" in settings and settings["gain_mode"] in ["High", "Low", "Auto"]:
            self.gain_combo.setCurrentText(settings["gain_mode"])

        if "agc_mode" in settings and settings["agc_mode"] in ["Manual", "Auto", "Linear"]:
            self.agc_combo.setCurrentText(settings["agc_mode"])

        if "palette" in settings and settings["palette"] in BOSON_PALETTES:
            self.palette_combo.setCurrentText(settings["palette"])

        if "ffc_mode" in settings and settings["ffc_mode"] in ["Manual", "Auto", "External"]:
            self.ffc_mode_combo.setCurrentText(settings["ffc_mode"])

        if "dde" in settings and isinstance(settings["dde"], int):
            self.dde_slider.setValue(max(0, min(255, settings["dde"])))

        if "tlinear" in settings and isinstance(settings["tlinear"], bool):
            self.tlinear_check.setChecked(settings["tlinear"])

        self.logger.info("Settings applied to Boson control panel")

    # ========================================================================
    # Event Handlers
    # ========================================================================

    def _on_gain_changed(self, mode_str: str):
        """Handle gain mode change."""
        if not self.controller:
            return

        try:
            mode_map = {
                "High": GainMode.HIGH,
                "Low": GainMode.LOW,
                "Auto": GainMode.AUTO
            }

            if self.controller.set_gain_mode(mode_map[mode_str]):
                self.logger.info(f"Gain mode set to {mode_str}")
                self._emit_settings()
            else:
                self.logger.error(f"Failed to set gain mode to {mode_str}")

        except Exception as e:
            self.logger.error(f"Error setting gain mode: {e}")

    def _on_agc_changed(self, mode_str: str):
        """Handle AGC mode change."""
        if not self.controller:
            return

        try:
            mode_map = {
                "Manual": AGCMode.MANUAL,
                "Auto": AGCMode.AUTO,
                "Linear": AGCMode.LINEAR
            }

            if self.controller.set_agc_mode(mode_map[mode_str]):
                self.logger.info(f"AGC mode set to {mode_str}")
                self._emit_settings()
            else:
                self.logger.error(f"Failed to set AGC mode to {mode_str}")

        except Exception as e:
            self.logger.error(f"Error setting AGC mode: {e}")

    def _on_palette_changed(self, palette_name: str):
        """Handle color palette change."""
        if not self.controller:
            return

        try:
            if self.controller.set_palette(palette_name):
                self.logger.info(f"Palette set to {palette_name}")
                self._emit_settings()
            else:
                self.logger.error(f"Failed to set palette to {palette_name}")

        except Exception as e:
            self.logger.error(f"Error setting palette: {e}")

    def _on_ffc_clicked(self):
        """Handle FFC button click."""
        if not self.controller:
            QtWidgets.QMessageBox.warning(
                self,
                "FFC Error",
                "No Boson controller available"
            )
            return

        try:
            # Disable button during FFC
            self.ffc_btn.setEnabled(False)
            self.ffc_btn.setText("Performing FFC...")
            QtWidgets.QApplication.processEvents()

            if self.controller.perform_ffc():
                self.logger.info("FFC triggered successfully")
                self.ffcTriggered.emit()
                QtWidgets.QMessageBox.information(
                    self,
                    "FFC Complete",
                    "Flat Field Correction completed successfully"
                )
            else:
                self.logger.error("FFC failed")
                QtWidgets.QMessageBox.warning(
                    self,
                    "FFC Failed",
                    "Flat Field Correction failed.\nCheck SDK connection and camera status."
                )

        except Exception as e:
            self.logger.error(f"Error performing FFC: {e}")
            QtWidgets.QMessageBox.warning(
                self,
                "FFC Error",
                f"Error performing FFC:\n{str(e)}"
            )

        finally:
            self.ffc_btn.setEnabled(True)
            self.ffc_btn.setText("Trigger FFC")

    def _on_ffc_mode_changed(self, mode_str: str):
        """Handle FFC mode change."""
        if not self.controller:
            return

        try:
            mode_map = {
                "Manual": FFCMode.MANUAL,
                "Auto": FFCMode.AUTO,
                "External": FFCMode.EXTERNAL
            }

            if self.controller.set_ffc_mode(mode_map[mode_str]):
                self.logger.info(f"FFC mode set to {mode_str}")
                self._emit_settings()
            else:
                self.logger.error(f"Failed to set FFC mode to {mode_str}")

        except Exception as e:
            self.logger.error(f"Error setting FFC mode: {e}")

    def _on_dde_changed(self, value: int):
        """Handle DDE slider change."""
        self.dde_value_label.setText(str(value))

        if not self.controller:
            return

        try:
            if self.controller.set_dde(value):
                # Don't log every slider movement, only on release
                self._emit_settings()
            else:
                self.logger.error(f"Failed to set DDE to {value}")

        except Exception as e:
            self.logger.error(f"Error setting DDE: {e}")

    def _on_tlinear_changed(self, state: int):
        """Handle Temperature Linear checkbox change."""
        if not self.controller:
            return

        try:
            enabled = (state == QtCore.Qt.Checked)

            if self.controller.enable_tlinear(enabled):
                self.logger.info(f"Temperature Linear mode {'enabled' if enabled else 'disabled'}")
                self._emit_settings()
            else:
                self.logger.error(f"Failed to set TLinear mode")

        except Exception as e:
            self.logger.error(f"Error setting TLinear: {e}")

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _update_status(self):
        """Update status display based on controller state."""
        if not self.controller:
            self.status_label.setText("○ Status: No controller")
            self.status_label.setStyleSheet("font-size: 8pt; color: #888;")
            self.sdk_label.setText("SDK: Not initialized")
            self._set_controls_enabled(False)
            return

        if not self.controller.sdk_available:
            self.status_label.setText("○ Status: SDK Not Available")
            self.status_label.setStyleSheet("font-size: 8pt; color: #ff6b6b;")
            self.sdk_label.setText("SDK: Install from flir.com/support/products/boson/")
            self.sdk_label.setWordWrap(True)
            self._set_controls_enabled(False)
            return

        if self.controller.is_connected:
            self.status_label.setText("● Status: Connected")
            self.status_label.setStyleSheet("font-size: 8pt; color: #51cf66;")
            self.sdk_label.setText("SDK: Available ✓")
            self._set_controls_enabled(True)
        else:
            self.status_label.setText("○ Status: Disconnected")
            self.status_label.setStyleSheet("font-size: 8pt; color: #ffa94d;")
            self.sdk_label.setText("SDK: Available (not connected)")
            self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        """
        Enable or disable all controls.

        Args:
            enabled: True to enable, False to disable
        """
        self.gain_combo.setEnabled(enabled)
        self.agc_combo.setEnabled(enabled)
        self.palette_combo.setEnabled(enabled)
        self.ffc_btn.setEnabled(enabled)
        self.ffc_mode_combo.setEnabled(enabled)
        self.dde_slider.setEnabled(enabled)
        self.tlinear_check.setEnabled(enabled)

        # Update tooltip when disabled
        if not enabled:
            disabled_tip = "Boson SDK required - Install from flir.com"
            self.gain_combo.setToolTip(disabled_tip)
            self.agc_combo.setToolTip(disabled_tip)
            self.palette_combo.setToolTip(disabled_tip)

    def _load_current_settings(self):
        """
        Load current settings from controller.

        Note: This requires SDK support for querying current state.
        Not all Boson SDK versions support this.
        """
        if not self.controller or not self.controller.is_connected:
            return

        try:
            # Get current modes if SDK supports it
            gain_mode = self.controller.get_gain_mode()
            if gain_mode is not None:
                mode_names = {GainMode.HIGH: "High", GainMode.LOW: "Low", GainMode.AUTO: "Auto"}
                if gain_mode in mode_names:
                    self.gain_combo.setCurrentText(mode_names[gain_mode])

            agc_mode = self.controller.get_agc_mode()
            if agc_mode is not None:
                mode_names = {AGCMode.MANUAL: "Manual", AGCMode.AUTO: "Auto", AGCMode.LINEAR: "Linear"}
                if agc_mode in mode_names:
                    self.agc_combo.setCurrentText(mode_names[agc_mode])

            self.logger.info("Loaded current settings from Boson camera")

        except Exception as e:
            self.logger.warning(f"Could not load current settings: {e}")

    def _emit_settings(self):
        """Emit current settings as signal."""
        settings = self.get_settings()
        self.settingsChanged.emit(settings)
