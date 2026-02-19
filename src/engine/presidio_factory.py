from __future__ import annotations

import os
from typing import Optional

import spacy
from spacy.util import get_package_path

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .recognizers import (
    make_email_recognizer,
    make_phone_recognizer,
    make_money_recognizer,
    make_postal_code_recognizer,
    make_id_recognizer,
    make_person_name_recognizer,
    make_age_recognizer,
    make_date_recognizer,
    make_address_recognizer,
    make_company_recognizer,
    make_parties_recognizer,
)

from .dict_recognizer import build_custom_dict_recognizers


def _ensure_v1_compat():
    """Register spaCy v1 architecture aliases for v2.

    ja_ginza 5.2.0 config.cfg references spacy.Tagger.v1 etc.
    but spaCy 3.8+ renamed them to v2. This shim creates aliases.
    """
    try:
        from spacy import registry
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
                registry.architectures.get(v1)
            except Exception:
                try:
                    fn = registry.architectures.get(v2)
                    registry.architectures.register(v1, func=fn)
                except Exception:
                    pass
    except Exception:
        pass


def _resolve_spacy_model(preferred: str = "ja_ginza_electra") -> str:
    """Resolve spaCy model for Japanese NLP.

    Key insight: GiNZA models require `import ginza` BEFORE spacy.load()
    because ginza registers custom pipeline components (tokenizer, etc.)
    that the model's config.cfg references.
    """
    import sys as _sys
    import glob as _glob

    # --- Pre-import ginza to register custom components ---
    try:
        import ginza  # noqa: F401 — side-effect: registers spaCy components
    except ImportError:
        pass

    # --- Register v1→v2 aliases for spaCy 3.8 compatibility ---
    _ensure_v1_compat()

    debug_lines = ["=== spaCy model resolution ==="]

    def _try_load(path_or_name: str, label: str) -> bool:
        try:
            _ = spacy.load(path_or_name)
            debug_lines.append(f"  OK: {label} -> {path_or_name}")
            return True
        except Exception as e:
            debug_lines.append(f"  FAIL: {label} -> {path_or_name} ({e})")
            return False

    def _write_debug():
        """Write debug log to exe directory for troubleshooting."""
        try:
            if getattr(_sys, "frozen", False):
                log_dir = os.path.dirname(_sys.executable)
            else:
                log_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(log_dir, "spacy_debug.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(debug_lines))
        except Exception:
            pass

    # --- 1. SPACY_MODEL_PATH env var (set by main.py for frozen exe) ---
    env_path = os.environ.get("SPACY_MODEL_PATH", "")
    debug_lines.append(f"SPACY_MODEL_PATH={env_path!r}")
    if env_path and os.path.isdir(env_path):
        if _try_load(env_path, "env_path"):
            _write_debug()
            return env_path

    # --- 2. Search _MEIPASS for model directories (frozen exe) ---
    if getattr(_sys, "frozen", False):
        meipass = getattr(_sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(_sys.executable)

        search_dirs = [
            os.path.join(meipass, "spacy_models"),
            os.path.join(exe_dir, "spacy_models"),
            os.path.join(meipass, "ja_ginza"),
            os.path.join(exe_dir, "ja_ginza"),
            meipass,
            exe_dir,
        ]
        debug_lines.append(f"_MEIPASS={meipass!r}")
        debug_lines.append(f"exe_dir={exe_dir!r}")

        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            # Look for meta.json (definitive sign of a spaCy model)
            for root, dirs, files in os.walk(search_dir):
                if "meta.json" in files and "config.cfg" in files:
                    debug_lines.append(f"  Found model dir: {root}")
                    if _try_load(root, f"walk:{root}"):
                        _write_debug()
                        return root

            # Also try direct subdirectories
            for name in os.listdir(search_dir):
                sub = os.path.join(search_dir, name)
                if os.path.isdir(sub):
                    if _try_load(sub, f"subdir:{sub}"):
                        _write_debug()
                        return sub

    # --- 3. Normal Python environment (non-frozen) ---
    candidates = [preferred]
    if preferred != "ja_ginza":
        candidates.append("ja_ginza")

    for model_name in candidates:
        if _try_load(model_name, f"name:{model_name}"):
            _write_debug()
            return model_name
        try:
            path = str(get_package_path(model_name))
            if _try_load(path, f"pkg_path:{model_name}"):
                _write_debug()
                return path
        except Exception:
            pass

    # --- Failed ---
    _write_debug()

    if getattr(_sys, "frozen", False):
        raise RuntimeError(
            "spaCy model not found in EXE.\n\n"
            "Debug log written to: spacy_debug.log\n\n"
            "Rebuild steps:\n"
            "  1. pip install ja-ginza\n"
            "  2. python -c \"import spacy; print(spacy.load('ja_ginza').path)\"\n"
            "  3. pyinstaller legal_masking.spec --noconfirm"
        )

    return "ja_ginza"


def build_analyzer(dict_dir: Optional[str] = None) -> AnalyzerEngine:
    """日本語専用の AnalyzerEngine を構築する。

    ★ 最重要ポイント ★
    RecognizerRegistry() をデフォルト引数で呼ぶと、コンストラクタ内部で
    load_predefined_recognizers() が自動実行され、英語専用の認識器
    （US_SSN, US_PHONE 等）が登録される。これらは supported_language='en'
    を持つため、AnalyzerEngine(supported_languages=["ja"]) と矛盾して
    ValueError になる。

    → recognizers=[] を明示的に渡すことで自動読み込みを抑止する。
    """

    # ── 1) 空のレジストリを作成（英語認識器の自動読み込みを防止）──
    # NOTE:
    #   Presidio のバージョンによっては、RecognizerRegistry(recognizers=[])
    #   としても registry.supported_languages が既定値の ['en'] のまま残り、
    #   AnalyzerEngine(supported_languages=['ja']) 生成時に
    #   ValueError: Misconfigured engine... が発生することがある。
    #   そのため supported_languages=['ja'] を明示して整合させる。
    registry = RecognizerRegistry(recognizers=[], supported_languages=["ja"])

    # ── 2) 日本語カスタム recognizers を登録 ──
    registry.add_recognizer(make_email_recognizer())
    registry.add_recognizer(make_phone_recognizer())
    registry.add_recognizer(make_postal_code_recognizer())
    registry.add_recognizer(make_id_recognizer())
    registry.add_recognizer(make_person_name_recognizer())
    registry.add_recognizer(make_age_recognizer())
    registry.add_recognizer(make_money_recognizer())
    registry.add_recognizer(make_date_recognizer())
    registry.add_recognizer(make_address_recognizer())
    registry.add_recognizer(make_company_recognizer())
    registry.add_recognizer(make_parties_recognizer())

    # ── 3) カスタム辞書 recognizers ──
    if dict_dir:
        for r in build_custom_dict_recognizers(dict_dir):
            registry.add_recognizer(r)

    # ── 4) spaCy / GiNZA NLP エンジン ──
    #   Prefer ja_ginza_electra (higher accuracy) with fallback to ja_ginza
    model_name_or_path = _resolve_spacy_model("ja_ginza_electra")

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "ja", "model_name": model_name_or_path}
            ],
        }
    )
    nlp_engine = provider.create_engine()

    # ── 5) AnalyzerEngine（日本語のみ）──
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["ja"],
    )
