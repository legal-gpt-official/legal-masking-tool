"""Bootstrap: ensure required directories and config files exist on first run.

Called from main.py before GUI launch.  If a file already exists it is never
overwritten -- only missing items are created from embedded templates.
"""
from __future__ import annotations

import os
from typing import Dict

# ---------------------------------------------------------------------------
# Template contents
# ---------------------------------------------------------------------------

POLICY_YAML = """\
version: 1

global:
  allowlist:
    terms:
      - "甲"
      - "乙"
      - "丙"
      - "丁"

output:
  mode: "LABEL"
  black_min_len: 3
  label_format:
    PERSON: "[PERSON_{n:02d}]"
    COMPANY: "[COMPANY_{n:02d}]"
    ADDRESS: "[ADDRESS]"
    EMAIL: "[EMAIL]"
    PHONE: "[PHONE]"
    MONEY: "[MONEY]"
    DATE: "[DATE]"
    ID: "[ID]"
    PARTIES: ""

review:
  threshold: 0.80

address:
  granularity: "UNTIL_CITY"

pdf:
  japanese_ratio_threshold: 0.20
  max_rects_per_term: 50
  min_term_length: 2

entities:
  - name: "EMAIL"
    enabled: true
    tier: 1
    priority: 100
  - name: "PHONE"
    enabled: true
    tier: 1
    priority: 100
  - name: "ID"
    enabled: true
    tier: 1
    priority: 100
  - name: "PERSON"
    enabled: true
    tier: 1
    priority: 90
  - name: "ADDRESS"
    enabled: true
    tier: 1
    priority: 90
  - name: "COMPANY"
    enabled: true
    tier: 2
    priority: 80
  - name: "MONEY"
    enabled: true
    tier: 2
    priority: 70
  - name: "DATE"
    enabled: true
    tier: 2
    priority: 70
  - name: "KEYWORD"
    enabled: true
    tier: 3
    priority: 60
  - name: "PARTIES"
    enabled: true
    tier: 0
    priority: 10

performance:
  force_fast: false
  fast_threshold_chars: 400000
  nlp_chunk_size: 15000
  nlp_chunk_overlap: 300
"""

PREFECTURES_TXT = """\
# 都道府県一覧（長い順にソート）
神奈川県
和歌山県
鹿児島県
北海道
青森県
岩手県
宮城県
秋田県
山形県
福島県
茨城県
栃木県
群馬県
埼玉県
千葉県
東京都
新潟県
富山県
石川県
福井県
山梨県
長野県
岐阜県
静岡県
愛知県
三重県
滋賀県
京都府
大阪府
兵庫県
奈良県
島根県
岡山県
広島県
山口県
徳島県
香川県
愛媛県
高知県
福岡県
佐賀県
長崎県
熊本県
大分県
宮崎県
沖縄県
鳥取県
"""

MUNICIPALITIES_TXT = """\
# 主要市区町村（サンプル）
東京都千代田区
東京都中央区
東京都港区
東京都新宿区
東京都文京区
東京都台東区
東京都墨田区
東京都江東区
東京都品川区
東京都目黒区
東京都大田区
東京都世田谷区
東京都渋谷区
東京都中野区
東京都杉並区
東京都豊島区
東京都北区
東京都荒川区
東京都板橋区
東京都練馬区
東京都足立区
東京都葛飾区
東京都江戸川区
大阪府大阪市
大阪府堺市
愛知県名古屋市
北海道札幌市
福岡県福岡市
神奈川県横浜市
神奈川県川崎市
京都府京都市
兵庫県神戸市
"""

CUSTOM_COMPANIES_TXT = """\
# ユーザー登録の社名辞書（1行1社名）
"""

CUSTOM_KEYWORDS_TXT = """\
# カスタムキーワード辞書（1行1語）
"""


# ---------------------------------------------------------------------------
# Bootstrap logic
# ---------------------------------------------------------------------------

def ensure_bootstrap(base_dir: str) -> Dict[str, bool]:
    """Create missing directories and template files.

    Returns dict of {path: created} for logging/debugging.
    """
    results: Dict[str, bool] = {}

    # Directories
    dirs = [
        os.path.join(base_dir, "output"),
        os.path.join(base_dir, "output", "backup"),
        os.path.join(base_dir, "resources"),
        os.path.join(base_dir, "resources", "dict"),
    ]
    for d in dirs:
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            results[d] = True
        else:
            results[d] = False

    # Template files
    files = {
        os.path.join(base_dir, "resources", "masking_policy.yaml"): POLICY_YAML,
        os.path.join(base_dir, "resources", "dict", "prefectures.txt"): PREFECTURES_TXT,
        os.path.join(base_dir, "resources", "dict", "municipalities.txt"): MUNICIPALITIES_TXT,
        os.path.join(base_dir, "resources", "dict", "custom_companies.txt"): CUSTOM_COMPANIES_TXT,
        os.path.join(base_dir, "resources", "dict", "custom_keywords.txt"): CUSTOM_KEYWORDS_TXT,
    }
    for path, content in files.items():
        if not os.path.isfile(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            results[path] = True
        else:
            results[path] = False

    # audit_log.jsonl (touch only)
    audit_path = os.path.join(base_dir, "audit_log.jsonl")
    if not os.path.isfile(audit_path):
        with open(audit_path, "w", encoding="utf-8") as f:
            pass
        results[audit_path] = True
    else:
        results[audit_path] = False

    return results
