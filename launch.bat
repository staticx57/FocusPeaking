@echo off
REM FLIR Boson Focus Utility Launcher
REM Version 2.0.0

echo ===============================================
echo   FLIR Boson Focus Utility
echo   Version 2.0.0
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

REM Display menu
echo Choose interface:
echo   1. Simple Interface (main.py)
echo   2. Advanced Interface with ROI Editor (ROIeditor.py)
echo   3. Exit
echo.
set /p choice="Enter choice (1-3): "

if "%choice%"=="1" (
    echo.
    echo Launching Simple Interface...
    echo.
    python main.py
) else if "%choice%"=="2" (
    echo.
    echo Launching Advanced Interface...
    echo.
    python ROIeditor.py
) else if "%choice%"=="3" (
    echo.
    echo Exiting...
    exit /b 0
) else (
    echo.
    echo Invalid choice. Launching Simple Interface by default...
    echo.
    python main.py
)

echo.
echo Application closed.
pause
