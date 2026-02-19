"""Legal Masking Tool v1.0
開発・提供: Legal GPT編集部 / Legal-gpt.com
"""
import os
import sys

# =====================================================================
# PyInstaller console=False fix:
# When built with console=False, sys.stdout and sys.stderr are None.
# Libraries like wasabi (used by spaCy) crash with:
#   AttributeError: 'NoneType' object has no attribute 'flush'
# Fix: redirect to devnull BEFORE any other imports.
# =====================================================================
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# PyInstaller frozen exe support
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)

    _meipass = getattr(sys, "_MEIPASS", BASE_DIR)

    # --- spaCy model path resolution ---
    # PyInstaller bundles the model into spacy_models/ inside _MEIPASS
    _spacy_models = os.path.join(_meipass, "spacy_models")
    if os.path.isdir(_spacy_models):
        for name in os.listdir(_spacy_models):
            model_dir = os.path.join(_spacy_models, name)
            if os.path.isdir(model_dir):
                os.environ["SPACY_MODEL_PATH"] = model_dir
                break

    # Also check alongside the exe (for manual deployment)
    _local_models = os.path.join(BASE_DIR, "spacy_models")
    if os.path.isdir(_local_models) and "SPACY_MODEL_PATH" not in os.environ:
        for name in os.listdir(_local_models):
            model_dir = os.path.join(_local_models, name)
            if os.path.isdir(model_dir):
                os.environ["SPACY_MODEL_PATH"] = model_dir
                break

    # Prevent spaCy from attempting downloads in frozen mode
    os.environ["SPACY_WARNING_IGNORE"] = "W095"

# bootstrap: create required files/dirs on first run
from bootstrap import ensure_bootstrap  # noqa: E402
ensure_bootstrap(BASE_DIR)

from gui_app import run_gui  # noqa: E402

if __name__ == "__main__":
    run_gui()
