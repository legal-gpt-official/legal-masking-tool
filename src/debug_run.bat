@echo off
echo ============================================
echo   Debug Launcher (console output visible)
echo ============================================
echo.
cd /d "%~dp0"
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo Running with Python (errors shown below)...
    echo.
    python main.py
) else (
    echo No venv found. Run build.bat first.
)
echo.
echo === Done (exit code: %errorlevel%) ===
pause
