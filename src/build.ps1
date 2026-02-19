# build.ps1
$ErrorActionPreference = "Stop"

Write-Host "== LegalMasking build start =="

# 1) venv
if (Test-Path ".\.venv") {
  Write-Host "[1/6] Remove old venv"
  Remove-Item -Recurse -Force ".\.venv"
}

Write-Host "[2/6] Create venv"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

Write-Host "[3/6] Upgrade pip"
python -m pip install -U pip

Write-Host "[4/6] Install requirements"
pip install -r requirements.txt

Write-Host "[5/6] Precheck (must pass)"
python .\check_build.py

Write-Host "[6/6] PyInstaller build"
pyinstaller .\legal_masking.spec --noconfirm

Write-Host "== Build done =="
Write-Host "dist\LegalMasking\LegalMasking.exe を確認してください"
