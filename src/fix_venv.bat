@echo off
echo ============================================
echo   Fix spaCy version (rebuild venv)
echo ============================================
echo.
echo This will delete the existing venv and
echo recreate it with compatible package versions.
echo.
echo Press any key to continue or Ctrl+C to cancel.
pause >nul

if exist "venv" (
    echo Removing old venv...
    rmdir /s /q venv
)

echo Creating new venv...
python -m venv venv
call venv\Scripts\activate.bat

echo Installing packages with compatible versions...
pip install --upgrade pip
pip install "spacy>=3.7.5,<3.8"
pip install ginza ja-ginza
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Verifying...
python -c "import spacy; print(f'spaCy: {spacy.__version__}')"
python -c "import spacy; nlp=spacy.load('ja_ginza'); print(f'ja_ginza: OK ({nlp.path})')"

echo.
echo ============================================
echo   Done! Now run build.bat to build EXE.
echo ============================================
echo.
pause
