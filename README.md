# FLIR Boson Focus Peaking Utility

A professional focus peaking utility for FLIR Boson thermal cameras with Region of Interest (ROI) management, real-time focus metrics, and advanced visualization.

## Features

### Core Functionality
- **Real-time Focus Peaking**: Visual overlay highlighting in-focus edges
- **ROI Management**: Create, edit, move, and weight multiple regions of interest
- **Focus Metrics**: Laplacian variance-based focus scoring with weighted averaging
- **Live Graph**: Real-time focus trend visualization
- **Configuration Persistence**: Save/load ROI configurations and settings

### Advanced Features
- **Interactive ROI Editor**: Click-and-drag to create ROIs, drag to move them
- **Per-ROI Weighting**: Assign different importance to different regions
- **Configurable Peaking Color**: Choose your preferred edge highlight color
- **Adjustable Threshold**: Fine-tune edge detection sensitivity
- **Focus Statistics**: Real-time min/max/average focus metrics
- **CSV Export**: Export focus data for analysis
- **Keyboard Shortcuts**: Fast workflow with keyboard controls
- **Camera Selection**: Choose from available video devices
- **Robust Error Handling**: Graceful degradation and helpful error messages

## Requirements

- Python 3.8+
- FLIR Boson thermal camera (or any compatible video device)
- Windows, Linux, or macOS

## Installation

1. Clone or download this repository:
```bash
git clone <repository-url>
cd FlirFocusPeaking
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
# Advanced ROI Editor (recommended)
python ROIeditor.py

# Simple version
python main.py
```

## Usage

### Getting Started

1. **Launch the application**: Run `python ROIeditor.py`
2. **Select camera**: Choose your FLIR Boson from the device dropdown
3. **Create ROIs**: Click and drag on the video to create focus regions
4. **Adjust weights**: Select an ROI and adjust its weight slider
5. **Configure peaking**: Adjust edge threshold and color as needed
6. **Save configuration**: Click "Save Config" to preserve your settings

### ROI Management

- **Create ROI**: Click and drag on the video display
- **Select ROI**: Click inside an existing ROI or select from table
- **Move ROI**: Drag a selected ROI to reposition
- **Delete ROI**: Select an ROI and click "Delete ROI"
- **Adjust Weight**: Use the weight slider when an ROI is selected

### Keyboard Shortcuts

- `Delete` / `Backspace`: Delete selected ROI
- `Ctrl+S`: Save configuration
- `Ctrl+O`: Load configuration
- `Ctrl+E`: Export focus data to CSV
- `Space`: Pause/Resume video
- `+` / `-`: Increase/decrease edge threshold
- `1-9`: Quick-select ROI by number

### Focus Metrics

The application calculates focus using Laplacian variance:
- Higher values = better focus
- Per-ROI scores shown in real-time
- Global score is weighted average of all ROIs
- Focus trend graph shows historical data

### Configuration Files

Settings are saved to `focus_config.json` with:
- ROI definitions (position, weight)
- Edge threshold
- Peaking color
- Camera device index

## File Structure

```
FlirFocusPeaking/
├── ROIeditor.py       # Advanced ROI editor (main application)
├── main.py            # Simple focus peaking tool
├── focus_utils.py     # Shared focus metric utilities
├── config.py          # Configuration constants
├── camera_manager.py  # Camera management and device selection
├── requirements.txt   # Python dependencies
├── README.md          # This file
└── focus_config.json  # Configuration file (created on first save)
```

## Technical Details

### Focus Calculation

The application uses Laplacian variance as a focus metric:

```python
focus_score = cv2.Laplacian(gray, cv2.CV_64F).var()
```

For multiple ROIs, the global score is:
```
global_score = Σ(roi_score × roi_weight) / Σ(roi_weight)
```

### Focus Peaking

Edge detection highlights:
1. Convert frame to grayscale
2. Apply Laplacian edge detection
3. Threshold to binary mask
4. Overlay colored highlight on edges

### Performance

- Default: 20 FPS (50ms timer)
- Frame size: 640×480 (configurable)
- Graph history: 400 samples
- Optimized for real-time processing

## Troubleshooting

### Camera Not Found
- Verify camera is connected
- Try different device indices (0, 1, 2, etc.)
- Check camera permissions on Linux: `sudo chmod 666 /dev/video*`

### Low Focus Scores
- Ensure camera is not in fixed focus mode
- Check lens is clean
- Verify ROIs are on high-contrast areas

### Application Crashes
- Check `flir_focus.log` for error details
- Ensure all dependencies are installed
- Verify Python version >= 3.8

### Poor Performance
- Reduce number of ROIs
- Decrease frame size in config
- Increase timer interval (lower FPS)

## Development

### Adding Features

The codebase is modular:
- **focus_utils.py**: Add new focus metrics
- **camera_manager.py**: Enhance camera handling
- **config.py**: Add new configuration options

### Code Style

- Type hints for all functions
- Docstrings for public APIs
- Logging instead of print statements
- Comprehensive error handling

## License

[Your License Here]

## Credits

Developed for FLIR Boson thermal camera focus assistance.

## Support

For issues, feature requests, or questions:
- Check troubleshooting section
- Review log file: `flir_focus.log`
- Open an issue on GitHub

## Version History

### v2.0.0 (Current)
- Complete refactor with modular architecture
- Added camera selection and robust error handling
- CSV export and statistics
- Keyboard shortcuts
- Comprehensive logging
- Type hints throughout

### v1.0.0 (Original)
- Basic focus peaking
- Simple ROI support
- Config save/load
