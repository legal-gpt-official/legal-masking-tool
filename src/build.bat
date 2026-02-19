@echo off
echo ============================================
echo   Legal Masking Tool - EXE Build
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

if not exist "venv" (
    echo [1/6] Creating venv...
    python -m venv venv
)
call venv\Scripts\activate.bat

echo [2/6] Installing packages...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
pip install pyinstaller

echo [3/6] Checking spaCy version compatibility...
python -c "import spacy; v=spacy.__version__; print(f'spaCy {v}'); exit(0 if v.startswith('3.7') else 1)" 2>nul
if errorlevel 1 (
    echo Fixing spaCy version for ja_ginza compatibility...
    pip install "spacy>=3.7.5,<3.8" --force-reinstall
    pip install ja-ginza --force-reinstall
)

echo [4/6] Pre-build check...
python check_build.py
if errorlevel 1 (
    echo [ERROR] Pre-build check failed.
    pause
    exit /b 1
)

echo [5/6] Building EXE...
pyinstaller legal_masking.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [6/6] Verifying...
if not exist "dist\LegalMasking\resources" (
    xcopy /E /I /Y resources dist\LegalMasking\resources
)

echo.
echo ============================================
echo   BUILD COMPLETE
echo   Output: dist\LegalMasking\LegalMasking.exe
echo ============================================
echo.
pause
