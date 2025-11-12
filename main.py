#!/usr/bin/env python3
"""
FLIR Boson Focus Utility - Compatibility Redirect

This file redirects to the unified application launcher for backwards compatibility.
All functionality has been consolidated into the full-featured application.

RECOMMENDED: Use `python focus_utility.py` or `python ROIeditor.py` directly.
"""

import sys
import warnings

# Show deprecation warning
warnings.warn(
    "\n\n"
    "=" * 70 + "\n"
    "DEPRECATION NOTICE:\n"
    "main.py is deprecated and redirects to the unified application.\n"
    "\n"
    "Please use instead:\n"
    "  python focus_utility.py    (recommended unified launcher)\n"
    "  python ROIeditor.py         (direct full-featured GUI)\n"
    "=" * 70 + "\n",
    DeprecationWarning,
    stacklevel=2
)

# Import and launch the unified application
try:
    from focus_utility import main

    if __name__ == "__main__":
        print("\n[INFO] Launching unified FLIR Boson Focus Utility...")
        print("[INFO] All features available: Phase 1-6 complete + enhancements\n")
        main()

except ImportError as e:
    print(f"\n[ERROR] Failed to import unified application: {e}")
    print("[INFO] Please ensure focus_utility.py and ROIeditor.py are present.")
    sys.exit(1)
