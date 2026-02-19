# runtime_hook.py
# - PyInstaller(onefile/onedir) 実行時のパス/ログ整備
# - spaCy/GiNZAロード時の情報をログに出す（ユーザー環境切り分け用）

import os
import sys
import traceback
from pathlib import Path

def _write_runtime_log(msg: str) -> None:
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        log_dir = base / "LegalMasking" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "runtime_hook.log").write_text(msg, encoding="utf-8")
    except Exception:
        pass

try:
    frozen = getattr(sys, "frozen", False)
    meipass = getattr(sys, "_MEIPASS", None)

    # どこから起動しても、内部リソースの基準点を揃える
    if frozen and meipass:
        os.environ["LEGAL_MASKING_BUNDLE_DIR"] = str(meipass)
    else:
        os.environ["LEGAL_MASKING_BUNDLE_DIR"] = str(Path(__file__).resolve().parent)

    # 文字化け対策（Windowsコンソール向け・GUIでも害はない）
    os.environ.setdefault("PYTHONUTF8", "1")

    # デバッグ用：バージョンとパスを記録
    info = []
    info.append(f"frozen={frozen}")
    info.append(f"_MEIPASS={meipass}")
    info.append(f"cwd={os.getcwd()}")
    info.append(f"bundle_dir={os.environ.get('LEGAL_MASKING_BUNDLE_DIR')}")

    try:
        import spacy
        info.append(f"spacy={spacy.__version__}")
    except Exception as e:
        info.append(f"spacy_import_error={e}")

    try:
        import ginza
        info.append(f"ginza={getattr(ginza, '__version__', 'unknown')}")
    except Exception as e:
        info.append(f"ginza_import_error={e}")

    _write_runtime_log("\n".join(info))

except Exception:
    _write_runtime_log("runtime_hook failed:\n" + traceback.format_exc())
