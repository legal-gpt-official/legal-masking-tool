from __future__ import annotations
from presidio_analyzer import PatternRecognizer, Pattern

# All recognizers MUST specify supported_language="ja"
# to match AnalyzerEngine(supported_languages=["ja"]).


def make_email_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="EMAIL",
        supported_language="ja",
        patterns=[
            Pattern(
                name="email_regex",
                regex=r"(?<![\w\-\.])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w\-\.])",
                score=0.99,
            )
        ],
    )


def make_phone_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="PHONE",
        supported_language="ja",
        patterns=[
            Pattern(
                name="phone_regex",
                regex=r"(?<!\d)(0\d{1,4}[-\u30FC]?\d{1,4}[-\u30FC]?\d{3,4})(?!\d)",
                score=0.85,
            )
        ],
    )


def make_money_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="MONEY",
        supported_language="ja",
        patterns=[
            Pattern(
                # NOTE:
                #   旧実装は「数字」だけを MONEY として拾うため、郵便番号/電話/ID/日付/年齢
                #   などの数字列が大量に MONEY 扱いになり、
                #   MaskingEngine 側の "keep:money_no_context" で素通しになっていた。
                #   → 通貨の記号/単位を含む「金額」だけを MONEY として認識する。
                name="money_amount",
                regex=(
                    r"(?:"
                    r"(?:[¥￥]\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
                    r"|"
                    r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:円|万円|千円|百万円))"
                    r")"
                ),
                score=0.85,
            )
        ],
    )


def make_postal_code_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="ID",
        supported_language="ja",
        patterns=[
            Pattern(
                name="jp_postal",
                regex=r"(?<!\d)(\d{3}[-\u30FC]?\d{4})(?!\d)",
                score=0.95,
            )
        ],
    )


def make_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="ID",
        supported_language="ja",
        patterns=[
            # S001, A12, AB1234 など（顧客ID/社員IDのようなもの）
            Pattern(
                name="compact_id",
                regex=r"(?<![A-Za-z0-9])([A-Z]{1,3}\d{2,6})(?![A-Za-z0-9])",
                score=0.80,
            ),
            # PRIV-2025-Q3-102 など（管理番号っぽいハイフン区切り）
            Pattern(
                name="hyphenated_id",
                regex=r"(?<![A-Za-z0-9])([A-Z]{2,10}-\d{2,4}(?:-[A-Z0-9]{1,6}){1,6})(?![A-Za-z0-9])",
                score=0.85,
            ),
        ],
    )


def make_person_name_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="PERSON",
        supported_language="ja",
        patterns=[
            # NOTE:
            #   Python の lookbehind は「固定長」しか許容されないため、
            #   \r?\n や可変空白を含むラベル行の直後だけを狙う表現は壊れやすい。
            #   → 帳票の実データで頻出する「姓<space>名 の1行」を安定的に拾う。
            #   （独身/既婚/男/女 などの2文字属性を誤検出しないため、
            #    “必ず空白区切り” を要件にする。）
            Pattern(
                name="jp_name_line_with_space",
                # 行頭の空白/タブを許容しつつ「姓<space>名」だけの行を拾う
                # ※行全体にマッチさせることで、改行コード差（\n / \r\n）の影響を受けにくい
                regex=r"(?m)^[\t \u3000]*[一-龥]{1,4}[\t \u0020\u3000]+[一-龥]{1,4}[\t \u3000]*$",
                score=0.86,
            ),
            # 担当:田中 / （担当:田中） のような“単独姓”にも対応
            Pattern(
                name="tanto_single_surname",
                regex=r"(?<=担当[:：])[一-龥]{2,4}",
                score=0.82,
            ),
            Pattern(
                name="tanto_single_surname_paren",
                regex=r"(?<=\(担当[:：])[一-龥]{2,4}(?=\))",
                score=0.80,
            ),
            Pattern(
                name="tanto_single_surname_fwparen",
                regex=r"(?<=（担当[:：])[一-龥]{2,4}(?=）)",
                score=0.80,
            ),
        ],
    )


def make_age_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="ID",
        supported_language="ja",
        patterns=[
            Pattern(
                name="age_after_colon",
                regex=r"(?<=年齢[:：])\d{1,3}",
                score=0.75,
            ),
            # 帳票の値行だけが抜粋されるケース（例："鈴木 一郎\n42\n男\n"）
            # → 「次の行が 男/女」である 1〜3桁の数値を“年齢”として拾う
            Pattern(
                name="age_standalone_line_before_gender",
                regex=r"(?m)(?<=\n)\d{1,3}(?=\n(?:男|女)\n)",
                score=0.78,
            ),
        ],
    )


def make_date_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="DATE",
        supported_language="ja",
        patterns=[
            Pattern(
                "ymd",
                r"\d{4}[\/\.\-\u5E74]\s*\d{1,2}[\/\.\-\u6708]\s*\d{1,2}\s*(\u65E5)?",
                0.80,
            ),
            Pattern(
                "wareki",
                r"(\u4EE4\u548C|\u5E73\u6210|\u662D\u548C|R|H|S)\s*(\d{1,2}|\u5143)\s*\u5E74",
                0.75,
            ),
        ],
    )


def make_address_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="ADDRESS",
        supported_language="ja",
        patterns=[
            Pattern(
                "addr_hint",
                r"(..??[\u90FD\u9053\u5E9C\u770C].{1,30}?[\u5E02\u533A\u753A\u6751].{0,40})",
                0.55,
            )
        ],
    )


def make_company_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="COMPANY",
        supported_language="ja",
        patterns=[
            Pattern(
                "kabushiki_1",
                r"(\u682A\u5F0F\u4F1A\u793E|\u6709\u9650\u4F1A\u793E|\u5408\u540C\u4F1A\u793E)\s*\S{1,30}",
                0.70,
            ),
            Pattern(
                "kabushiki_2",
                r"\S{1,30}\s*(\u682A\u5F0F\u4F1A\u793E|\u6709\u9650\u4F1A\u793E|\u5408\u540C\u4F1A\u793E)",
                0.70,
            ),
            Pattern(
                "abbr",
                r"(\uFF08\u682A\uFF09|\(\u682A\))\s*\S{1,30}",
                0.65,
            ),
        ],
    )


def make_parties_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="PARTIES",
        supported_language="ja",
        patterns=[
            Pattern(
                "parties",
                r"(?<!\w)(\u7532|\u4E59|\u4E19|\u4E01)(?!\w)",
                0.99,
            )
        ],
    )
