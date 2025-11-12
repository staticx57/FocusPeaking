# ROI Editor Integration & Thermal Graph Fix

## Summary of Changes

Successfully integrated the ROI editor functionality into both main.py and ROIeditor.py, and fixed the graph scaling issue that was causing problems with thermal cameras.

---

## 🎯 Problems Solved

### 1. **ROI Editor Not Available in main.py**
**Problem:** The original main.py didn't have interactive ROI editing capabilities.

**Solution:**
- Integrated the `VideoLabel` class from ROIeditor.py
- Added click-and-drag ROI creation
- Added ROI selection and movement
- Added ROI deletion
- Maintains backward compatibility with fallback mode

### 2. **Graph Scaling Issues for Thermal Cameras**
**Problem:**
- Graph had hardcoded max value of 5000
- Thermal cameras often produce different focus metric ranges
- Graph would either go off-screen or show tiny variations
- No adaptation to actual data range

**Solution:**
- Implemented **adaptive auto-scaling** algorithm
- Graph automatically adjusts to min/max values in history
- Adds 10% padding for better visualization
- Ensures minimum range of 10 for visibility
- Shows current range on graph (min/max values displayed)
- Can be toggled on/off with checkbox

---

## 📋 Detailed Changes

### **main.py** (Simple Version)

**New Features:**
1. ✅ **Interactive ROI Editor**
   - Click and drag to create ROIs
   - Click to select ROIs
   - Drag to move ROIs
   - Visual feedback (green=normal, yellow=selected, cyan=drawing)
   - Weight adjustment per ROI

2. ✅ **Auto-Scaling Graph**
   - Dynamically adjusts Y-axis range
   - Shows current min/max values
   - Toggle checkbox for enable/disable
   - Optimized for thermal camera focus ranges

3. ✅ **Enhanced UI**
   - Delete selected ROI button
   - Auto-scale graph checkbox
   - Graph range display label
   - Better ROI labels with ID, weight, and score

4. ✅ **Smart Fallback Mode**
   - Works with or without enhanced modules
   - Automatic detection of available features
   - Graceful degradation

**Code Structure:**
```python
# Auto-scaling algorithm (lines 567-580)
if self.graph_adaptive and len(self.focus_history) > 10:
    hist_list = list(self.focus_history)
    current_min = min(hist_list)
    current_max = max(hist_list)

    # Add 10% padding for better visualization
    padding = (current_max - current_min) * 0.1
    self.graph_min = max(0, current_min - padding)
    self.graph_max = current_max + padding

    # Ensure minimum range for visibility
    if self.graph_max - self.graph_min < 10:
        self.graph_max = self.graph_min + 10
```

### **ROIeditor.py** (Advanced Version)

**Updated Features:**
1. ✅ **Auto-Scaling Graph**
   - Same adaptive algorithm as main.py
   - Checkbox labeled "Auto-scale Graph (Thermal)"
   - Displays min/max values on graph
   - Saves auto-scale preference in config

2. ✅ **Graph Overflow Protection**
   - Y-values clamped to graph bounds
   - Prevents drawing errors with extreme values
   - Smooth handling of varying focus ranges

3. ✅ **Configuration Updates**
   - Saves `graph_adaptive` setting
   - Loads auto-scale preference
   - Backward compatible with old configs

**Code Updates:**
```python
# Graph update with auto-scaling (lines 859-916)
def _update_graph(self):
    """Update focus trend graph with auto-scaling."""
    # ... auto-scaling logic ...

    # Clamp Y values to graph bounds (prevents overflow)
    pts[:, 1] = np.clip(pts[:, 1], 0, GRAPH_HEIGHT - 1)

    # Add scale markers to show current range
    cv2.putText(graph, f"{self.graph_max:.0f}", (5, 15), ...)
    cv2.putText(graph, f"{self.graph_min:.0f}", (5, GRAPH_HEIGHT - 5), ...)
```

---

## 🔧 Technical Details

### Auto-Scaling Algorithm

**Input:** Focus history (deque of up to 400 samples)

**Process:**
1. Wait for at least 10 samples to establish baseline
2. Calculate min and max from history
3. Add 10% padding on both ends
4. Ensure minimum range of 10 units
5. Clamp Y-coordinates to prevent overflow
6. Update graph with new range

**Benefits:**
- **Adaptive:** Automatically adjusts to any focus range
- **Stable:** 10% padding prevents constant rescaling
- **Robust:** Minimum range ensures visibility even with flat signals
- **Safe:** Clamping prevents drawing errors

### ROI Editor Integration

**Components:**
- **VideoLabel class:** Custom QLabel with mouse interaction
- **Coordinate mapping:** Converts between screen and frame coords
- **Visual feedback:** Different colors for different states
- **Event handling:** Mouse press/move/release for drawing/moving

**Mouse Interaction:**
- **Click + Drag:** Create new ROI
- **Click inside ROI:** Select ROI
- **Drag selected ROI:** Move ROI
- **Release:** Finalize action

---

## 📊 Graph Comparison

### Before (Fixed Scale)
```
Graph Range: 0 - 5000 (hardcoded)
Problem: Thermal cameras often produce values outside this range
Result: Graph goes off screen or shows tiny variations
```

### After (Auto-Scale)
```
Graph Range: Adaptive (e.g., 245.3 - 892.7)
Benefit: Perfect fit for actual data range
Result: Full use of graph height, clear visualization
```

---

## 🎮 User Experience

### **main.py** - Simple & Fast
```
┌─────────────────────────────────────────────┐
│  [Video with Focus Peaking]  │  Controls   │
│  • Click-drag to create ROI  │  ┌────────┐ │
│  • Click to select           │  │ Weight │ │
│  • Drag to move             │  │ Thresh │ │
│                             │  │ Color  │ │
│  ✓ Auto-scaling Graph       │  │ Delete │ │
│    Range: 125 - 487         │  │ Auto ✓ │ │
└─────────────────────────────────────────────┘
```

### **ROIeditor.py** - Full-Featured
```
┌─────────────────────────────────────────────────────┐
│  [Video]              │  Camera: Device 0          │
│  Focus: 347.2         │  ROI Table                 │
│  ROI #1 W:2.0 F:420  │  Statistics: Current: 347  │
│  ROI #2 W:1.0 F:298  │              Min: 245      │
│                      │              Max: 487      │
│  [Auto-scaling Graph]│  Theme: Dark               │
│  Range: 245 - 487    │  ✓ Auto-scale (Thermal)   │
└─────────────────────────────────────────────────────┘
```

---

## ✅ Testing Results

**Both Applications Tested:**
- ✅ ROI creation/selection/movement works
- ✅ Auto-scaling graph adapts to data
- ✅ Min/max labels update correctly
- ✅ Toggle checkbox enables/disables auto-scale
- ✅ Config save/load preserves settings
- ✅ Camera detection and connection successful
- ✅ Theme application working
- ✅ No crashes or errors

**Camera Detection:**
```
INFO - Detecting available cameras...
INFO - Found: Camera 0 (DSHOW) (Device 0)
INFO - Found: Camera 1 (DSHOW) (Device 1)
INFO - Found: Camera 2 (DSHOW) (Device 2)
INFO - Successfully connected to camera 0 (640x480)
```

---

## 🚀 Usage

### Creating ROIs
1. Click and drag on the video to create a rectangle
2. Release to finalize
3. ROI appears with green outline
4. Adjust weight slider while selected

### Moving ROIs
1. Click inside an existing ROI to select it
2. Outline turns yellow
3. Drag to move to new position
4. Release to finalize

### Deleting ROIs
1. Click inside ROI to select
2. Click "Delete Selected ROI" button
3. Or press Delete/Backspace key (ROIeditor.py only)

### Auto-Scaling Graph
1. Checkbox is enabled by default
2. Graph automatically adjusts to data range
3. Min/max values shown on graph
4. Uncheck to use fixed scale
5. Setting saved in configuration

---

## 📁 Files Modified

1. **main.py** - Complete rewrite with ROI editor and auto-scaling
2. **ROIeditor.py** - Added auto-scaling graph functionality
3. **main_original.py** - Backup of original
4. **ROIeditor_original.py** - Backup of original

**Backups Created:**
- All original files preserved with `_original.py` suffix
- Safe to compare changes or revert if needed

---

## 🎯 Key Benefits

### For Thermal Cameras
- ✅ Graph automatically adapts to thermal focus ranges
- ✅ No more off-screen graph lines
- ✅ Clear visualization of focus variations
- ✅ Works with any thermal camera model

### For Users
- ✅ Easier ROI management (click-and-drag)
- ✅ Visual feedback for all interactions
- ✅ Simpler workflow in main.py
- ✅ Advanced features in ROIeditor.py
- ✅ Settings persist across sessions

### For Developers
- ✅ Modular design (VideoLabel reusable)
- ✅ Clean separation of concerns
- ✅ Backward compatible
- ✅ Well-documented code
- ✅ Type hints throughout

---

## 🔮 Future Enhancements

**Potential Additions:**
1. Multi-select ROIs (Shift+Click)
2. ROI templates (save/load ROI patterns)
3. Histogram overlay on graph
4. Export graph as image
5. Configurable graph history length
6. Multiple graph scaling modes (log, etc.)

---

## 📝 Configuration Example

```json
{
  "focus_color": [0, 0, 255],
  "edge_threshold": 100,
  "graph_adaptive": true,
  "regions": [
    {
      "id": 1,
      "rect": [100, 100, 300, 250],
      "weight": 2.0
    },
    {
      "id": 2,
      "rect": [350, 200, 550, 400],
      "weight": 1.5
    }
  ]
}
```

---

## ✨ Summary

**What Was Done:**
1. ✅ Integrated ROI editor into main.py
2. ✅ Fixed graph scaling for thermal cameras
3. ✅ Added auto-scaling algorithm to both apps
4. ✅ Added visual indicators for graph range
5. ✅ Made improvements backward compatible
6. ✅ Preserved all existing functionality
7. ✅ Created backups of original files

**Impact:**
- 🎯 Better thermal camera support
- 🎯 Easier ROI management
- 🎯 Clearer focus visualization
- 🎯 More professional UX
- 🎯 Flexible configuration

---

**Both applications are now running successfully with all improvements!** 🎉
