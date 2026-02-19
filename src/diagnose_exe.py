"""Post-build diagnostic: run INSIDE the dist folder to check model.

Usage (after build):
    Copy this file to dist/LegalMasking/
    Then run the EXE normally, or:
    python diagnose_exe.py (from dev environment for comparison)
"""
import os
import sys
import traceback

print("=" * 60)
print("  Legal Masking - Model Diagnostic")
print("=" * 60)
print()

frozen = getattr(sys, "frozen", False)
print(f"Frozen (EXE): {frozen}")

if frozen:
    meipass = getattr(sys, "_MEIPASS", "???")
    exe_dir = os.path.dirname(sys.executable)
    print(f"_MEIPASS: {meipass}")
    print(f"EXE dir:  {exe_dir}")
else:
    meipass = os.path.dirname(os.path.abspath(__file__))
    exe_dir = meipass
    print(f"Script dir: {meipass}")

print()

# Search for model files
print("--- Searching for meta.json (spaCy model indicator) ---")
found_models = []
for base_label, base in [("_MEIPASS", meipass), ("EXE_DIR", exe_dir)]:
    if not os.path.isdir(base):
        continue
    for root, dirs, files in os.walk(base):
        # Skip very deep paths
        depth = root[len(base):].count(os.sep)
        if depth > 6:
            continue
        if "meta.json" in files:
            has_cfg = "config.cfg" in files
            found_models.append(root)
            print(f"  FOUND: {root}")
            print(f"         config.cfg: {'YES' if has_cfg else 'NO'}")

if not found_models:
    print("  NO MODELS FOUND!")
    print()
    print("--- Listing top-level dirs ---")
    for name in sorted(os.listdir(meipass))[:30]:
        p = os.path.join(meipass, name)
        marker = "[DIR]" if os.path.isdir(p) else "[FILE]"
        print(f"  {marker} {name}")

    if os.path.isdir(os.path.join(meipass, "spacy_models")):
        print()
        print("--- spacy_models/ contents ---")
        sm = os.path.join(meipass, "spacy_models")
        for root, dirs, files in os.walk(sm):
            depth = root[len(sm):].count(os.sep)
            indent = "  " * (depth + 1)
            print(f"{indent}{os.path.basename(root)}/")
            for f in files[:10]:
                print(f"{indent}  {f}")

print()

# Try loading
print("--- Trying spacy.load ---")
env_path = os.environ.get("SPACY_MODEL_PATH", "")
print(f"SPACY_MODEL_PATH env: {env_path!r}")

try:
    import ginza
    print("ginza import: OK")
except Exception as e:
    print(f"ginza import: FAILED ({e})")

try:
    import spacy
    print(f"spacy version: {spacy.__version__}")
except Exception as e:
    print(f"spacy import: FAILED ({e})")
    input("Press Enter to exit...")
    sys.exit(1)

# Check and apply v1→v2 compat shim
print()
print("--- Checking v1/v2 architecture compatibility ---")
try:
    from spacy import registry
    v1_test = "spacy.Tagger.v1"
    try:
        registry.architectures.get(v1_test)
        print(f"  {v1_test}: EXISTS (native)")
    except Exception:
        print(f"  {v1_test}: MISSING - applying v1->v2 shim...")
        aliases = [
            ("spacy.Tagger.v1", "spacy.Tagger.v2"),
            ("spacy.Morphologizer.v1", "spacy.Morphologizer.v2"),
            ("spacy.Tok2Vec.v1", "spacy.Tok2Vec.v2"),
            ("spacy.HashEmbedCNN.v1", "spacy.HashEmbedCNN.v2"),
            ("spacy.MaxoutWindowEncoder.v1", "spacy.MaxoutWindowEncoder.v2"),
            ("spacy.MishWindowEncoder.v1", "spacy.MishWindowEncoder.v2"),
            ("spacy.MultiHashEmbed.v1", "spacy.MultiHashEmbed.v2"),
            ("spacy.CharacterEmbed.v1", "spacy.CharacterEmbed.v2"),
            ("spacy.TransitionBasedParser.v1", "spacy.TransitionBasedParser.v2"),
        ]
        for v1, v2 in aliases:
            try:
                fn = registry.architectures.get(v2)
                registry.architectures.register(v1, func=fn)
                print(f"    Registered: {v1} -> {v2}")
            except Exception as e2:
                print(f"    FAILED: {v1} -> {v2}: {e2}")
        # Verify
        try:
            registry.architectures.get(v1_test)
            print(f"  {v1_test}: NOW EXISTS (shimmed)")
        except Exception:
            print(f"  {v1_test}: STILL MISSING after shim")
except Exception as e:
    print(f"  Registry check failed: {e}")
print()

# Try each model path
for label, path in [("env_path", env_path)] + [(f"found_{i}", p) for i, p in enumerate(found_models)]:
    if not path or not os.path.isdir(path):
        continue
    try:
        nlp = spacy.load(path)
        print(f"spacy.load({label}): OK -> {nlp.meta.get('name', '?')}")
    except Exception as e:
        print(f"spacy.load({label}): FAILED")
        print(f"  Path: {path}")
        print(f"  Error: {e}")
        # Try to show config.cfg for debugging
        cfg = os.path.join(path, "config.cfg")
        if os.path.exists(cfg):
            with open(cfg, "r") as f:
                lines = f.readlines()[:5]
            print(f"  config.cfg (first 5 lines):")
            for line in lines:
                print(f"    {line.rstrip()}")

for name in ["ja_ginza_electra", "ja_ginza"]:
    try:
        nlp = spacy.load(name)
        print(f"spacy.load('{name}'): OK")
    except Exception as e:
        print(f"spacy.load('{name}'): FAILED ({type(e).__name__}: {e})")

print()
print("--- Done ---")
input("Press Enter to exit...")
