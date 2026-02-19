# check_build.py
import sys
import traceback

def main() -> int:
    try:
        import spacy
        import ginza  # noqa: F401
        import ja_ginza  # noqa: F401

        print("[check] Python :", sys.version)
        print("[check] spaCy  :", spacy.__version__)

        # GiNZAロードテスト（ここが通れば勝ち）
        nlp = spacy.load("ja_ginza")
        print("[check] ja_ginza loaded OK")
        print("[check] model path:", nlp.path)
        print("[check] pipe:", nlp.pipe_names)

        # 参考：あなたのエラーは Tagger.v1 が無い(spaCy側が新しすぎ)なので、
        # spacy.__version__ が 3.8.x になっていたらこの時点で警告
        if spacy.__version__.startswith("3.8"):
            print("[WARN] spaCy is 3.8.x. ja_ginza 5.2.0 との互換ズレが出やすいです。spacy==3.7.5 に固定してください。")

        return 0

    except Exception:
        print("[check] FAILED")
        print(traceback.format_exc())
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
