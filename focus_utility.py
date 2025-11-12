#!/usr/bin/env python3
"""
FLIR Boson Focus Peaking Utility - Unified Application
Version 3.0.0

This is the unified entry point for the FLIR Boson Focus Utility.
It provides all features including:
- Multi-algorithm focus detection
- Thermal preprocessing
- Adaptive edge detection
- Smart palette switching
- ROI zoom/inspector
- Multi-algorithm ensemble voting
- Full Boson SDK integration

Usage:
    python focus_utility.py

Legacy compatibility:
    - ROIeditor.py: Full-featured GUI (same as this)
    - main.py: Simplified GUI (deprecated, use this instead)
"""

import sys
from PyQt5 import QtWidgets

# Import the main application class from ROIeditor
from ROIeditor import BosonFocusGUI

def main():
    """Launch the unified FLIR Boson Focus Utility."""
    app = QtWidgets.QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("FLIR Boson Focus Utility")
    app.setApplicationVersion("3.0.0")
    app.setOrganizationName("FLIR Focus Tools")

    # Create and show the main window
    window = BosonFocusGUI()
    window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
