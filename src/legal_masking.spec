# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Legal Masking Tool

Usage:
    python check_build.py
    pyinstaller legal_masking.spec --noconfirm
"""
import os
import sys
import importlib
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ---------------------------------------------------------------------------
# 1) Detect spaCy/GiNZA model (ja_ginza)
# ---------------------------------------------------------------------------
import spacy
import ginza  # noqa: F401

model_path = None
model_pkg_name = None

for candidate in ["ja_ginza_electra", "ja_ginza"]:
    try:
        nlp = spacy.load(candidate)
        model_path = str(nlp.path)
        model_pkg_name = candidate
        print(f"[spec] Model: {candidate}")
        print(f"[spec] Path : {model_path}")
        break
    except Exception as e:
        print(f"[spec] {candidate}: {e}")
        continue

if not model_path:
    raise RuntimeError(
        "No GiNZA model found!\n"
        "Run: pip install ja-ginza\n"
        "Then: python check_build.py\n"
    )

# ---------------------------------------------------------------------------
# 2) Collect package paths
# ---------------------------------------------------------------------------
ginza_path = os.path.dirname(importlib.import_module("ginza").__file__)
spacy_path = os.path.dirname(importlib.import_module("spacy").__file__)

# ja_ginza Python package
try:
    ja_mod = importlib.import_module(model_pkg_name.replace("-", "_"))
    ja_pkg_path = os.path.dirname(ja_mod.__file__)
    print(f"[spec] {model_pkg_name} package: {ja_pkg_path}")
except Exception:
    ja_pkg_path = os.path.dirname(model_path)
    print(f"[spec] {model_pkg_name} package (fallback): {ja_pkg_path}")

# ---------------------------------------------------------------------------
# 3) Data files
# ---------------------------------------------------------------------------
binaries = []
hidden_collect = []
datas = [
    ("resources", "resources"),
    # model directory (meta.json, config.cfg, etc.)
    (model_path, os.path.join("spacy_models", os.path.basename(model_path))),
    # ginza python package
    (ginza_path, "ginza"),
    # ja_ginza python package
    (ja_pkg_path, model_pkg_name.replace("-", "_")),
    # spacy language data
    (os.path.join(spacy_path, "lang"), os.path.join("spacy", "lang")),
]

# customtkinter assets
try:
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)
    datas.append((ctk_path, "customtkinter"))
except Exception:
    pass

# additional NLP deps (Sudachi, lookups, etc.)
for pkg in [
    "ginza",
    "sudachipy",
    "sudachidict_core",
    "spacy_lookups_data",
    model_pkg_name.replace("-", "_"),
]:
    try:
        _d, _b, _h = collect_all(pkg)
        datas += _d
        binaries += _b
        hidden_collect += _h
        print(f"[spec] collect_all: {pkg} (datas={len(_d)}, bins={len(_b)}, hidden={len(_h)})")
    except Exception as e:
        print(f"[spec] collect_all failed: {pkg} ({e})")

print(f"[spec] Data entries: {len(datas)}")
for src, dst in datas:
    print(f"  {'OK' if os.path.exists(src) else 'MISSING'}: {src} -> {dst}")

# ---------------------------------------------------------------------------
# 4) Hidden imports
# ---------------------------------------------------------------------------
hidden_imports = [
    # spaCy/GiNZA core
    "spacy",
    "spacy.lang.ja",
    "spacy.lang.ja.stop_words",
    "ginza",
    "ginza.bunsetu_recognizer",
    "ginza.inflection",
    "ginza.reading_form",
    model_pkg_name.replace("-", "_"),

    # thinc/backend
    "thinc",
    "thinc.api",
    "thinc.backends",
    "thinc.backends.numpy_ops",
    "thinc.shims",

    # spaCy deps
    "cymem",
    "preshed",
    "blis",
    "srsly",
    "srsly.msgpack",
    "srsly.ujson",
    "catalogue",
    "wasabi",
    "typer",
    "confection",
    "pydantic",

    # Presidio
    "presidio_analyzer",
    "presidio_analyzer.nlp_engine",
    "presidio_analyzer.nlp_engine.spacy_nlp_engine",
    "presidio_analyzer.predefined_recognizers",
    "presidio_anonymizer",

    # GUI / file
    "customtkinter",
    "chardet",
    "yaml",
    "fitz",
    "docx",
    "lxml",
    "lxml.etree",
]

hidden_imports += hidden_collect
hidden_imports += ["docx.opc", "docx.oxml", "docx.parts"]

# ---------------------------------------------------------------------------
# 5) Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["runtime_hook.py"],  # ★このファイルを必ず同階層に置く
    excludes=["matplotlib", "notebook", "jupyter", "scipy", "pandas", "PIL", "tkinter.test", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LegalMasking",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="favicon.ico" if os.path.exists("favicon.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LegalMasking",
)
