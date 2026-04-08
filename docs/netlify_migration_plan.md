# Netlify移行計画書

## 概要

利益計算アプリ（Flask製）をNetlifyにデプロイし、SPAベースで運用する。
データ収集（Playwright）は引き続きローカルPCで実行し、外部DBに書き込む構成とする。

---

## アーキテクチャ

```
┌─────────────────────┐     ┌──────────────────┐
│  ローカルPC          │     │  Netlify          │
│                     │     │                  │
│  Playwright         │     │  静的SPA          │
│  データ収集スクリプト  │────▶│  (HTML/JS/CSS)    │
│                     │     │                  │
│                     │     │  Netlify Functions │
│                     │     │  (計算API※)       │
└────────┬────────────┘     └────────┬─────────┘
         │                           │
         │     ┌─────────────────┐   │
         └────▶│  Supabase       │◀──┘
               │  (PostgreSQL)   │
               │  無料枠で十分   │
               └─────────────────┘
```

---

## スプレッドシート運用を不採用とした理由

| 問題 | 詳細 |
|------|------|
| 計算ロジックが複雑すぎる | FBA手数料算出・国際送料・関税・ACOS含む利益計算をシート関数で再現するのは非現実的 |
| データ構造が多層 | ベストセラーキャッシュ、商品詳細、バリエーション、利益計算結果…リレーションが多い |
| UIが既にSPAとして完成 | 機会スコアのスライダー、カテゴリ3階層ナビ、TOP100モーダル等をシートで再現不可 |
| API制限 | Google Sheets APIは読み書き60req/minで、複数人同時利用に弱い |

---

## DB: Supabase（PostgreSQL）

- PostgreSQL互換、REST API自動生成
- 無料枠: 500MB / 50K月間リクエスト（仲間内運用なら十分）
- Pythonクライアントあり → Playwrightスクリプトからそのまま書き込み可
- Row Level Securityで認証も簡単

---

## フロントエンド: 静的SPA → Netlify配信

- 現在の `templates/index.html` + `static/js/app.js` + CSS をそのまま静的配信
- API呼び出し先を Flask → Supabase REST API / Netlify Functions に差し替え

---

## 計算ロジックの配置

| 方式 | メリット | デメリット |
|------|---------|-----------|
| **A. クライアントサイド（JS）★推奨** | サーバー不要、即応答 | Python→JS移植が必要 |
| B. Netlify Functions | Pythonロジック流用しやすい | コールドスタート遅延、10秒制限 |

利益計算ロジック（`services/profit_calculator.py`）は外部APIを叩かない純粋関数のため、JSに移植してクライアントサイドで動かすのが最もシンプル。

---

## Playwrightデータ収集

- 今まで通りローカルPCで実行
- 保存先を SQLite → Supabase に変更（`supabase-py` で INSERT）
- 収集スクリプトは既存コードの保存部分のみ書き換え

---

## 移行で変わるもの / 変わらないもの

| 項目 | 変更内容 |
|------|---------|
| フロントUI | ほぼそのまま（API呼び出し先の差し替えのみ） |
| 利益計算 | Python → JSに移植（純粋関数なので容易） |
| DB | SQLite → Supabase PostgreSQL |
| Playwrightスクレイピング | ローカル継続、保存先をSupabaseに変更 |
| 為替レート取得 | Netlify Functionsか、クライアントから直接fetch |
| Claude API呼び出し | Netlify Functions経由（APIキーをサーバー側に隠すため） |

---

## Netlify Functions が必要なエンドポイント

APIキーや秘匿情報を扱うものだけサーバーサイドに置く:

1. **Claude API呼び出し**（OEM提案・キーワード抽出） → APIキー秘匿のため
2. **為替レート取得** → 外部API呼び出し（CORSの都合でサーバー経由が安全）
3. **画像プロキシ** → Amazon画像のCORS回避

それ以外（利益計算・FBA手数料算出・送料計算等）はすべてクライアントサイドJSで処理。

---

## Supabase テーブル設計（移行対象）

現在のSQLiteモデルをベースに以下のテーブルを作成:

- `bestseller_products` — ベストセラーキャッシュ（カテゴリ・ランク・価格・レビュー等）
- `product_details` — 単品調査の結果
- `profit_calculations` — 保存済み利益計算結果（出品済み管理タブ用）
- `categories` — カテゴリマスタ（3階層ナビ用）

---

## 移行ステップ

### Phase 1: 基盤準備
1. Supabaseプロジェクト作成・テーブル定義
2. 既存SQLiteデータをSupabaseに移行
3. GitリポジトリをNetlifyに接続

### Phase 2: フロントエンド移行
4. `index.html` を静的SPA化（Flaskテンプレート変数の除去）
5. 利益計算ロジックをJSに移植
6. FBA手数料・送料計算をJSに移植
7. API呼び出しをSupabase REST API + Netlify Functionsに差し替え

### Phase 3: バックエンド移行
8. Netlify Functions作成（Claude API / 為替レート / 画像プロキシ）
9. Playwrightスクリプトの保存先をSupabaseに変更

### Phase 4: デプロイ・検証
10. Netlifyにデプロイ・動作確認
11. 各タブの機能テスト
12. ローカルPlaywright → Supabase → Netlify SPAのデータフロー確認
