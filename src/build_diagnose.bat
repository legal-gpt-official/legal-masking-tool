@echo off
echo ============================================
echo   Diagnostic EXE Build (console output)
echo ============================================
echo.

if not exist "venv" (
    echo Run build.bat first to set up venv.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

echo Building diagnostic EXE...
pyinstaller diagnose.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Diagnostic EXE built.
echo   Run: dist\DiagnoseLM\DiagnoseLM.exe
echo   It will show model detection details.
echo ============================================
echo.
echo Please run it and share the output.
echo.
pause
