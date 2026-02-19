# -*- mode: python ; coding: utf-8 -*-
"""Console-mode diagnostic EXE - same bundling as main, with visible output.

Usage:
    pyinstaller diagnose.spec --noconfirm
"""
import os
import sys

block_cipher = None

import spacy
try:
    import ginza
except:
    pass

model_path = None
model_name = None
for candidate in ["ja_ginza_electra", "ja_ginza"]:
    try:
        nlp = spacy.load(candidate)
        model_path = str(nlp.path)
        model_name = os.path.basename(model_path)
        break
    except:
        continue

if not model_path:
    raise RuntimeError("No GiNZA model. pip install ja-ginza")

ginza_path = os.path.dirname(ginza.__file__)
spacy_path = os.path.dirname(spacy.__file__)

import importlib
ja_mod_name = candidate.replace("-", "_")
try:
    ja_mod = importlib.import_module(ja_mod_name)
    ja_pkg_path = os.path.dirname(ja_mod.__file__)
except:
    ja_pkg_path = os.path.dirname(model_path)

datas = [
    ("resources", "resources"),
    (model_path, os.path.join("spacy_models", model_name)),
    (ginza_path, "ginza"),
    (ja_pkg_path, ja_mod_name),
    (os.path.join(spacy_path, "lang"), os.path.join("spacy", "lang")),
]

hidden_imports = [
    "ginza", ja_mod_name, "spacy", "spacy.lang.ja",
    "thinc", "thinc.backends", "cymem", "preshed", "blis",
    "srsly", "catalogue", "wasabi", "confection",
]

a = Analysis(
    ["diagnose_exe.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hidden_imports,
    runtime_hooks=["runtime_hook.py"],
    excludes=["matplotlib", "notebook", "jupyter", "scipy", "pandas"],
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DiagnoseLM",
    debug=False,
    strip=False,
    upx=True,
    console=True,  # <-- CONSOLE MODE for visible output
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="DiagnoseLM")
