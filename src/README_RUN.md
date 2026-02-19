# Legal Masking Tool v1.0

**開発・提供: Legal GPT編集部 / Legal-gpt.com**

法務実務者向けの個人情報マスキングツールです。  
Word / PDF / テキストファイルの個人情報を自動検出し、マスキング済みファイルを出力します。

---

## 動作要件

- Windows 10/11 (64bit)
- Python 3.10〜3.12（開発環境での実行時）
- EXE配布版はPython不要

---

## クイックスタート（開発環境）

```bat
REM 1. 仮想環境の作成
python -m venv venv
venv\Scripts\activate

REM 2. 依存パッケージのインストール
pip install -r requirements.txt

REM 3. 起動
python main.py
```

### 高精度モデル（オプション）

デフォルトの `ja_ginza` より高精度な `ja_ginza_electra` を使用するには：

```bat
pip install ja-ginza-electra
```

インストール済みであれば自動的に検出・使用されます。

---

## EXE化（配布用ビルド）

### 方法1: ビルドスクリプト（推奨）

```bat
build.bat
```

ダブルクリックで自動的にビルドされます。

### 方法2: 手動ビルド

```bat
venv\Scripts\activate
pip install pyinstaller
pyinstaller legal_masking.spec --noconfirm
```

### ビルド結果

```
dist/LegalMasking/
├── LegalMasking.exe    ← ダブルクリックで起動
├── resources/          ← 設定ファイル・辞書
├── spacy_models/       ← NLPモデル（自動同梱）
└── (各種DLL)
```

`dist/LegalMasking/` フォルダを丸ごとZIPで配布できます。

---

## 使い方（3ステップ）

### Step 1: 解析

「▶ 解析」ボタンでファイルを選択 → 自動的に個人情報を検出

### Step 2: 編集

| 操作 | 方法 |
|------|------|
| マスク解除 | 検出リストの「残す」ボタン |
| 手動追加 | 原文を選択 → 右クリック → 種類を選択 |
| 再解析 | 「🔄 再解析」ボタン |

### Step 3: 確定保存

「💾 確定保存」→ 保存先ダイアログ → マスキング済みファイル + HTMLレポート + CSVを出力

---

## ツールバーボタン一覧

| ボタン | 機能 |
|--------|------|
| ▶ 解析 | ファイル読み込み → NER解析 → GUI表示 |
| 🔄 再解析 | GUI上の編集を反映してプレビュー更新 |
| 💾 確定保存 | 保存先を選んで最終ファイル出力 |
| 🧾 レポート | HTMLレポートをブラウザで表示 |
| ⚖ 免責 | 免責事項の表示 |
| 🏷 / ⬛ | ラベルモード / 黒塗りモード切替 |

---

## 検出アクションボタン

各検出項目に4つのアクションボタンがあります：

| ボタン | 効果 | 永続性 |
|--------|------|--------|
| 残す | 今回だけマスクしない | 今回のみ |
| 消す | 今回だけ強制マスク | 今回のみ |
| 永続残す | allowlist に追加 | YAML保存 |
| 永続消す | 辞書に追加（法人名として） | 辞書保存 |

---

## 対応ファイル形式

| 形式 | 入力 | 出力 |
|------|------|------|
| .txt | ✅ | マスキング済みテキスト |
| .docx | ✅ | 書式保持マスキング済みWord |
| .pdf (テキストPDF) | ✅ | 物理黒塗り済みPDF |

---

## 設定ファイル

### masking_policy.yaml

メイン設定ファイル。初回起動時に自動生成されます。

```yaml
# 主要な設定項目
global:
  allowlist:
    terms: ["甲", "乙", "自社名"]  # マスクしない語句

output:
  mode: LABEL    # LABEL or BLACK
  black_min_len: 3

performance:
  nlp_chunk_size: 15000    # NLPチャンクサイズ
  fast_threshold_chars: 400000  # regex-onlyフォールバック閾値
```

### dict/ フォルダ

| ファイル | 用途 |
|----------|------|
| custom_companies.txt | カスタム法人名辞書 |
| prefectures.txt | 都道府県名 |
| municipalities.txt | 市区町村名 |

---

## 出力ファイル

| ファイル | 内容 |
|----------|------|
| masked_*.docx/pdf/txt | マスキング済みファイル |
| report_*.html | Side-by-side レポート |
| hits_*.csv | 検出一覧CSV |
| audit_log.jsonl | 監査ログ |
| output/backup/ | 原本バックアップ |

---

## トラブルシューティング

### `Input is too long` エラー

`masking_policy.yaml` の `nlp_chunk_size` を確認：
```yaml
performance:
  nlp_chunk_size: 15000  # 40000だとエラーになります
```

### GiNZA が見つからない

```bat
pip install ja-ginza
```

### EXEが起動しない

`dist/LegalMasking/` 内に `resources/` フォルダがあるか確認。  
なければプロジェクトの `resources/` をコピーしてください。

---

## ライセンス・免責

本ソフトウェアは、文書中の情報抽出およびマスキング作業を支援するツールです。  
抽出・判定・置換の結果は完全性・正確性を保証しません。  
提出・開示等の最終判断は利用者の責任において行い、必ず目視で最終確認してください。

**開発・提供: Legal GPT編集部 / Legal-gpt.com**
