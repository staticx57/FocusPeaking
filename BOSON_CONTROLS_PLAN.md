# FLIR Boson Controls Integration Plan

## Executive Summary

This document outlines the plan to integrate FLIR Boson camera controls into the focus peaking application, providing users with direct access to camera settings (AGC, gain, FFC, palettes, etc.) without leaving the application.

---

## 📋 Table of Contents

1. [Current State](#current-state)
2. [Goals & Objectives](#goals--objectives)
3. [Architecture Overview](#architecture-overview)
4. [Implementation Plan](#implementation-plan)
5. [UI Design](#ui-design)
6. [Technical Details](#technical-details)
7. [Testing Strategy](#testing-strategy)
8. [Timeline & Milestones](#timeline--milestones)
9. [Risk Assessment](#risk-assessment)
10. [Future Enhancements](#future-enhancements)

---

## 1. Current State

### ✅ What Exists

**boson_control.py Module:**
- Complete `BosonController` class
- Support for all major Boson functions:
  - Gain modes (High/Low/Auto)
  - AGC modes (Manual/Auto/Linear)
  - FFC (Flat Field Correction)
  - Color palettes (WhiteHot, BlackHot, Rainbow, etc.)
  - Temperature Linear mode
  - Digital Detail Enhancement (DDE)
- Graceful SDK fallback
- Comprehensive logging
- Error handling

**Current Limitations:**
- ❌ No UI integration
- ❌ Not accessible to users
- ❌ Controls not connected to camera
- ❌ No visual feedback
- ❌ Settings not persisted

### 🎯 What's Needed

1. UI controls for each camera setting
2. Real-time status display
3. Error handling and user feedback
4. Setting persistence in config
5. Integration with both main.py and ROIeditor.py
6. Documentation and tooltips

---

## 2. Goals & Objectives

### Primary Goals

1. **Accessibility**
   - Make Boson controls easily accessible in the UI
   - Intuitive controls that don't require technical knowledge
   - Clear visual feedback for all settings

2. **Functionality**
   - Support all major Boson camera features
   - Real-time setting updates
   - Persistence of user preferences

3. **Reliability**
   - Graceful handling when SDK not available
   - Clear error messages
   - No crashes due to SDK issues

4. **Integration**
   - Seamless fit into existing UI
   - Works with current theme system
   - Compatible with camera selector

### Success Criteria

- ✅ All Boson settings controllable from UI
- ✅ Settings persist across sessions
- ✅ Clear feedback on current state
- ✅ Works with/without SDK
- ✅ No performance impact on focus peaking
- ✅ Professional appearance

---

## 3. Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Application UI                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Camera       │  │ Boson        │  │ Focus        │  │
│  │ Selector     │  │ Controls     │  │ Peaking      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼──────────────────┼──────────────────┼──────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐
│ CameraManager   │  │ BosonController │  │ FocusUtils  │
│ - detect()      │  │ - set_gain()    │  │ - metric()  │
│ - connect()     │  │ - set_agc()     │  │ - overlay() │
│ - read()        │  │ - set_ffc()     │  │ - compute() │
└─────────────────┘  └────────┬────────┘  └─────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  FLIR Boson SDK │
                     │  (if available) │
                     └─────────────────┘
```

### Data Flow

```
User Action
    ↓
UI Control (ComboBox/Button/Slider)
    ↓
Signal/Slot Connection
    ↓
Handler Method
    ↓
BosonController Method
    ↓
SDK Command (if available)
    ↓
Camera Hardware
    ↓
Status Update/Feedback
    ↓
UI Update
```

---

## 4. Implementation Plan

### Phase 1: UI Framework (Week 1)

**Tasks:**
1. Create `BosonControlPanel` widget class
2. Design layout with grouped controls
3. Add to both main.py and ROIeditor.py
4. Implement enable/disable based on SDK availability

**Deliverables:**
- New `boson_ui.py` module
- UI controls visible in both apps
- Basic layout and styling

### Phase 2: Basic Controls (Week 2)

**Tasks:**
1. Implement Gain Mode selector
2. Implement AGC Mode selector
3. Add FFC trigger button
4. Connect to BosonController
5. Add status indicators

**Deliverables:**
- Working Gain/AGC controls
- FFC button functional
- Status display

### Phase 3: Advanced Controls (Week 3)

**Tasks:**
1. Add Color Palette selector
2. Add DDE slider
3. Add Temperature Linear toggle
4. Implement all remaining controls

**Deliverables:**
- Complete control set
- All features accessible
- Proper validation

### Phase 4: Persistence & Polish (Week 4)

**Tasks:**
1. Save Boson settings to config
2. Load settings on startup
3. Add tooltips and help text
4. Error handling and feedback
5. Testing and bug fixes

**Deliverables:**
- Settings persistence
- Professional UI
- Comprehensive testing
- Documentation

---

## 5. UI Design

### Layout Option 1: Compact Panel

```
┌─────────────────────────────────────┐
│ FLIR Boson Controls                 │
├─────────────────────────────────────┤
│ Gain Mode:    [Auto      ▼]        │
│ AGC Mode:     [Linear    ▼]        │
│ Color Palette:[WhiteHot  ▼]        │
│                                     │
│ [Trigger FFC]  DDE: [====|====] 128│
│                                     │
│ ☐ Temperature Linear Mode           │
│                                     │
│ Status: ● Connected | SDK: ✓       │
└─────────────────────────────────────┘
```

### Layout Option 2: Expandable Sections

```
┌─────────────────────────────────────┐
│ ▼ FLIR Boson Controls               │
├─────────────────────────────────────┤
│ ▼ Image Processing                  │
│   Gain Mode:    [Auto      ▼]      │
│   AGC Mode:     [Linear    ▼]      │
│   DDE Level:    [====|====] 128    │
│                                     │
│ ▼ Color & Display                   │
│   Palette:      [WhiteHot  ▼]      │
│   ☐ Temp Linear Mode                │
│                                     │
│ ▼ Calibration                       │
│   [Trigger FFC Now]                 │
│   FFC Mode:     [Auto      ▼]      │
│   Last FFC: 2 minutes ago          │
│                                     │
│ Status: ● Connected | SDK v2.1.0   │
└─────────────────────────────────────┘
```

### Layout Option 3: Tabbed Interface

```
┌─────────────────────────────────────┐
│ [Image] [Color] [Calibration] [Info]│
├─────────────────────────────────────┤
│ Image Processing Tab:               │
│                                     │
│ Gain Mode:                          │
│ ○ High  ○ Low  ● Auto              │
│                                     │
│ AGC Mode:                           │
│ ○ Manual  ○ Auto  ● Linear         │
│                                     │
│ Digital Detail Enhancement:         │
│ [================|======] 128/255   │
│                                     │
│ Temperature Linear: [Enable]        │
└─────────────────────────────────────┘
```

**Recommendation:** Layout Option 1 (Compact Panel)
- Most space-efficient
- All controls visible at once
- Quick access to common functions
- Matches existing UI style

---

## 6. Technical Details

### 6.1 New Module: boson_ui.py

```python
"""
FLIR Boson camera controls UI panel.
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Optional
import logging

from boson_control import BosonController, GainMode, AGCMode, FFCMode
from config import BOSON_GAIN_MODES, BOSON_AGC_MODES, BOSON_PALETTES

logger = logging.getLogger(__name__)


class BosonControlPanel(QtWidgets.QGroupBox):
    """UI panel for FLIR Boson camera controls."""

    # Signals
    settingsChanged = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__("FLIR Boson Controls", parent)
        self.controller: Optional[BosonController] = None
        self._create_ui()

    def _create_ui(self):
        """Create the control panel UI."""
        layout = QtWidgets.QVBoxLayout(self)

        # Gain Mode
        gain_layout = QtWidgets.QHBoxLayout()
        gain_layout.addWidget(QtWidgets.QLabel("Gain:"))
        self.gain_combo = QtWidgets.QComboBox()
        self.gain_combo.addItems(["High", "Low", "Auto"])
        self.gain_combo.currentTextChanged.connect(self._on_gain_changed)
        gain_layout.addWidget(self.gain_combo)
        layout.addLayout(gain_layout)

        # AGC Mode
        agc_layout = QtWidgets.QHBoxLayout()
        agc_layout.addWidget(QtWidgets.QLabel("AGC:"))
        self.agc_combo = QtWidgets.QComboBox()
        self.agc_combo.addItems(["Manual", "Auto", "Linear"])
        self.agc_combo.currentTextChanged.connect(self._on_agc_changed)
        agc_layout.addWidget(self.agc_combo)
        layout.addLayout(agc_layout)

        # Color Palette
        palette_layout = QtWidgets.QHBoxLayout()
        palette_layout.addWidget(QtWidgets.QLabel("Palette:"))
        self.palette_combo = QtWidgets.QComboBox()
        self.palette_combo.addItems(list(BOSON_PALETTES.keys()))
        self.palette_combo.currentTextChanged.connect(self._on_palette_changed)
        palette_layout.addWidget(self.palette_combo)
        layout.addLayout(palette_layout)

        # FFC Button
        self.ffc_btn = QtWidgets.QPushButton("Trigger FFC")
        self.ffc_btn.clicked.connect(self._on_ffc_clicked)
        layout.addWidget(self.ffc_btn)

        # DDE Slider
        dde_layout = QtWidgets.QVBoxLayout()
        dde_label_layout = QtWidgets.QHBoxLayout()
        dde_label_layout.addWidget(QtWidgets.QLabel("DDE:"))
        self.dde_value_label = QtWidgets.QLabel("0")
        dde_label_layout.addWidget(self.dde_value_label)
        dde_layout.addLayout(dde_label_layout)

        self.dde_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.dde_slider.setRange(0, 255)
        self.dde_slider.valueChanged.connect(self._on_dde_changed)
        dde_layout.addWidget(self.dde_slider)
        layout.addLayout(dde_layout)

        # TLinear checkbox
        self.tlinear_check = QtWidgets.QCheckBox("Temperature Linear")
        self.tlinear_check.stateChanged.connect(self._on_tlinear_changed)
        layout.addWidget(self.tlinear_check)

        # Status
        self.status_label = QtWidgets.QLabel("Status: Not connected")
        self.status_label.setStyleSheet("font-size: 8pt; color: #888;")
        layout.addWidget(self.status_label)

    def set_controller(self, controller: BosonController):
        """Set the Boson controller instance."""
        self.controller = controller
        self._update_status()
        self._load_current_settings()

    def _on_gain_changed(self, mode_str: str):
        """Handle gain mode change."""
        if not self.controller:
            return
        mode_map = {"High": GainMode.HIGH, "Low": GainMode.LOW, "Auto": GainMode.AUTO}
        self.controller.set_gain_mode(mode_map[mode_str])
        self._emit_settings()

    def _on_agc_changed(self, mode_str: str):
        """Handle AGC mode change."""
        if not self.controller:
            return
        mode_map = {"Manual": AGCMode.MANUAL, "Auto": AGCMode.AUTO, "Linear": AGCMode.LINEAR}
        self.controller.set_agc_mode(mode_map[mode_str])
        self._emit_settings()

    def _on_palette_changed(self, palette_name: str):
        """Handle palette change."""
        if not self.controller:
            return
        self.controller.set_palette(palette_name)
        self._emit_settings()

    def _on_ffc_clicked(self):
        """Handle FFC button click."""
        if not self.controller:
            return
        if self.controller.perform_ffc():
            QtWidgets.QMessageBox.information(self, "FFC", "FFC triggered successfully")
        else:
            QtWidgets.QMessageBox.warning(self, "FFC", "FFC failed")

    def _on_dde_changed(self, value: int):
        """Handle DDE slider change."""
        self.dde_value_label.setText(str(value))
        if not self.controller:
            return
        self.controller.set_dde(value)
        self._emit_settings()

    def _on_tlinear_changed(self, state: int):
        """Handle TLinear checkbox change."""
        if not self.controller:
            return
        self.controller.enable_tlinear(state == QtCore.Qt.Checked)
        self._emit_settings()

    def _update_status(self):
        """Update status display."""
        if not self.controller:
            self.status_label.setText("Status: No controller")
            self._set_controls_enabled(False)
            return

        if self.controller.sdk_available and self.controller.is_connected:
            self.status_label.setText("Status: ● Connected | SDK Available")
            self._set_controls_enabled(True)
        elif self.controller.sdk_available:
            self.status_label.setText("Status: ○ Disconnected | SDK Available")
            self._set_controls_enabled(False)
        else:
            self.status_label.setText("Status: SDK Not Available")
            self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        """Enable or disable all controls."""
        self.gain_combo.setEnabled(enabled)
        self.agc_combo.setEnabled(enabled)
        self.palette_combo.setEnabled(enabled)
        self.ffc_btn.setEnabled(enabled)
        self.dde_slider.setEnabled(enabled)
        self.tlinear_check.setEnabled(enabled)

    def _load_current_settings(self):
        """Load current settings from controller."""
        # This would query the camera for current settings
        # Not implemented in basic SDK interface
        pass

    def _emit_settings(self):
        """Emit current settings."""
        settings = {
            "gain_mode": self.gain_combo.currentText(),
            "agc_mode": self.agc_combo.currentText(),
            "palette": self.palette_combo.currentText(),
            "dde": self.dde_slider.value(),
            "tlinear": self.tlinear_check.isChecked(),
        }
        self.settingsChanged.emit(settings)

    def get_settings(self) -> dict:
        """Get current UI settings."""
        return {
            "gain_mode": self.gain_combo.currentText(),
            "agc_mode": self.agc_combo.currentText(),
            "palette": self.palette_combo.currentText(),
            "dde": self.dde_slider.value(),
            "tlinear": self.tlinear_check.isChecked(),
        }

    def apply_settings(self, settings: dict):
        """Apply settings from dict."""
        if "gain_mode" in settings:
            self.gain_combo.setCurrentText(settings["gain_mode"])
        if "agc_mode" in settings:
            self.agc_combo.setCurrentText(settings["agc_mode"])
        if "palette" in settings:
            self.palette_combo.setCurrentText(settings["palette"])
        if "dde" in settings:
            self.dde_slider.setValue(settings["dde"])
        if "tlinear" in settings:
            self.tlinear_check.setChecked(settings["tlinear"])
```

### 6.2 Integration into main.py

```python
# In __init__:
if ENHANCED_MODE:
    from boson_ui import BosonControlPanel
    from boson_control import create_boson_controller

    # Create Boson controller
    self.boson_controller = create_boson_controller()

# In _create_ui:
if ENHANCED_MODE:
    # Add Boson control panel
    self.boson_panel = BosonControlPanel()
    self.boson_panel.set_controller(self.boson_controller)
    self.boson_panel.settingsChanged.connect(self._on_boson_settings_changed)
    control_layout.addWidget(self.boson_panel)

# In _save_config:
if ENHANCED_MODE and self.boson_panel:
    config["boson"] = self.boson_panel.get_settings()

# In _load_config:
if ENHANCED_MODE and self.boson_panel and "boson" in config:
    self.boson_panel.apply_settings(config["boson"])
```

### 6.3 Configuration Schema

```json
{
  "focus_color": [0, 0, 255],
  "edge_threshold": 100,
  "graph_adaptive": true,
  "theme": "Dark",
  "regions": [...],
  "boson": {
    "gain_mode": "Auto",
    "agc_mode": "Linear",
    "palette": "WhiteHot",
    "dde": 128,
    "tlinear": false,
    "ffc_mode": "Auto"
  }
}
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

```python
# test_boson_ui.py

def test_control_panel_creation():
    """Test panel creates without errors."""
    panel = BosonControlPanel()
    assert panel is not None

def test_gain_mode_selection():
    """Test gain mode can be selected."""
    panel = BosonControlPanel()
    panel.gain_combo.setCurrentText("High")
    assert panel.gain_combo.currentText() == "High"

def test_settings_persistence():
    """Test settings can be saved and loaded."""
    panel = BosonControlPanel()
    settings = {"gain_mode": "Low", "agc_mode": "Auto"}
    panel.apply_settings(settings)
    assert panel.get_settings()["gain_mode"] == "Low"
```

### 7.2 Integration Tests

1. **With SDK Available:**
   - Verify all commands reach camera
   - Check status updates
   - Confirm FFC execution

2. **Without SDK:**
   - Verify graceful degradation
   - Check controls disabled
   - Confirm no crashes

3. **With Both Apps:**
   - Test in main.py
   - Test in ROIeditor.py
   - Verify consistent behavior

### 7.3 Manual Testing Checklist

- [ ] Panel appears in UI
- [ ] All controls visible
- [ ] Gain mode changes work
- [ ] AGC mode changes work
- [ ] Palette selection works
- [ ] FFC button triggers
- [ ] DDE slider updates
- [ ] TLinear checkbox works
- [ ] Settings save correctly
- [ ] Settings load correctly
- [ ] Status displays correctly
- [ ] Works without SDK
- [ ] No performance impact
- [ ] Themes apply correctly

---

## 8. Timeline & Milestones

### Week 1: Foundation
- **Day 1-2:** Create boson_ui.py module
- **Day 3-4:** Basic UI layout
- **Day 5:** Integration into main.py

**Milestone 1:** UI visible with placeholder controls

### Week 2: Core Functionality
- **Day 6-7:** Implement Gain/AGC controls
- **Day 8-9:** Add FFC functionality
- **Day 10:** Status display

**Milestone 2:** Basic controls functional

### Week 3: Advanced Features
- **Day 11-12:** Color palette selector
- **Day 13-14:** DDE and TLinear
- **Day 15:** Polish and refinement

**Milestone 3:** All features implemented

### Week 4: Completion
- **Day 16-17:** Settings persistence
- **Day 18-19:** Testing and bug fixes
- **Day 20:** Documentation

**Milestone 4:** Production ready

---

## 9. Risk Assessment

### High Risk Items

1. **SDK Not Available**
   - **Risk:** Users don't have SDK installed
   - **Mitigation:** Graceful fallback, clear messaging
   - **Impact:** Medium - feature won't work but app stable

2. **SDK Version Incompatibility**
   - **Risk:** Different SDK versions behave differently
   - **Mitigation:** Version detection, compatibility layer
   - **Impact:** Medium - some features may not work

3. **Camera Communication Errors**
   - **Risk:** Commands fail or timeout
   - **Mitigation:** Proper error handling, user feedback
   - **Impact:** Low - individual commands fail gracefully

### Medium Risk Items

1. **Performance Impact**
   - **Risk:** SDK calls slow down UI
   - **Mitigation:** Async operations, threading
   - **Impact:** Low - minimal processing required

2. **UI Complexity**
   - **Risk:** Too many controls overwhelm UI
   - **Mitigation:** Collapsible sections, good UX
   - **Impact:** Low - can reorganize if needed

### Low Risk Items

1. **Setting Conflicts**
   - **Risk:** Some settings incompatible
   - **Mitigation:** Validation, smart defaults
   - **Impact:** Very Low - well documented

2. **Theme Compatibility**
   - **Risk:** New controls don't match themes
   - **Mitigation:** Use existing widget types
   - **Impact:** Very Low - Qt handles styling

---

## 10. Future Enhancements

### Phase 2 Features

1. **Advanced Calibration**
   - Custom FFC schedules
   - Temperature-based FFC
   - NUC table management

2. **Presets System**
   - Save/load setting presets
   - Quick switch between configs
   - Import/export presets

3. **Real-time Monitoring**
   - Temperature readouts
   - Sensor status
   - Diagnostic information

4. **Automation**
   - Auto-adjust based on scene
   - Smart AGC profiles
   - Learning algorithms

### Integration with Other Features

1. **Focus Metrics**
   - Correlate Boson settings with focus quality
   - Suggest optimal settings
   - Performance analytics

2. **ROI-based Settings**
   - Different settings per ROI
   - Region-specific optimization
   - Adaptive processing

3. **Export Enhancement**
   - Include Boson settings in exports
   - Metadata embedding
   - Reproducible captures

---

## Appendix A: Boson SDK Reference

### Available Commands

```python
# Gain Control
bosonSetGainMode(mode)  # 0=High, 1=Low, 2=Auto
bosonGetGainMode()

# AGC Control
bosonSetAGCMode(mode)  # 0=Manual, 1=Auto, 2=Linear
bosonGetAGCMode()

# FFC
bosonRunFFC()
bosonSetFFCMode(mode)  # 0=Manual, 1=Auto, 2=External
bosonGetFFCMode()

# Color Palettes
bosonSetColorPalette(id)
bosonGetColorPalette()

# Temperature Linear
bosonSetTLinearEnable(enable)
bosonGetTLinearEnable()

# DDE
bosonSetDDELevel(level)  # 0-255
bosonGetDDELevel()
```

### SDK Installation

```bash
# Download from FLIR
https://www.flir.com/support/products/boson/

# Install Python bindings
pip install flir-boson-sdk

# Or build from source
git clone https://github.com/flir/boson-sdk
cd boson-sdk/python
python setup.py install
```

---

## Appendix B: UI Mockups

[See separate mockup images or ASCII art above]

---

## Appendix C: Configuration Examples

### Minimal Config
```json
{
  "boson": {
    "gain_mode": "Auto",
    "agc_mode": "Linear"
  }
}
```

### Full Config
```json
{
  "boson": {
    "gain_mode": "High",
    "agc_mode": "Manual",
    "palette": "Ironbow",
    "dde": 192,
    "tlinear": true,
    "ffc_mode": "Auto",
    "ffc_period": 300
  }
}
```

---

## Summary

This plan provides a comprehensive roadmap for integrating FLIR Boson camera controls into the focus peaking application. The implementation will:

✅ Provide full camera control from UI
✅ Maintain graceful degradation without SDK
✅ Integrate seamlessly with existing features
✅ Persist user preferences
✅ Follow professional UI/UX standards
✅ Complete in ~4 weeks

**Next Steps:**
1. Review and approve plan
2. Begin Week 1 implementation
3. Create boson_ui.py module
4. Integrate into main.py
5. Test and iterate

**Ready to proceed when approved!** 🚀
