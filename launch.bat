@echo off
REM FLIR Boson Focus Utility Launcher
REM Version 3.0.1

echo ===============================================
echo   FLIR Boson Focus Utility
echo   Version 3.0.1 - Unified Application
echo ===============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.7+ or add it to your PATH
    pause
    exit /b 1
)

echo Python found!
echo.
echo Launching FLIR Boson Focus Utility...
echo.
echo All features available:
echo   - 5 Focus Algorithms + Ensemble Voting
echo   - Adaptive Edge Detection
echo   - Thermal Preprocessing
echo   - Smart Palette Switching
echo   - ROI Management
echo   - And more!
echo.

python focus_utility.py

echo.
echo Application closed.
pause
