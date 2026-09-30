# メルカリ せどり支援ツール(半自動)

相場より安い商品を見つけて**通知するだけ**のローカルツールです。購入は必ず人間が最終確認して行います。
**自動ログイン・自動購入・自動コメントは実装していません(今後も追加しないでください)。**

## 機能
| 機能 | モジュール |
|---|---|
| 収集(手動CSV / Playwright) | `src/sedori/collector/` |
| 相場算出(直近30日・外れ値除外・信頼度) | `src/sedori/pricing/` |
| 利益判定・除外ルール | `src/sedori/profit/` |
| Discord通知(重複防止) | `src/sedori/notifier/` |
| 出品文生成(Claude API)・値下げ戦略 | `src/sedori/listing/` |
| 在庫・損益・確定申告CSV | `src/sedori/inventory/` |
| Streamlitダッシュボード | `src/sedori/dashboard/` |

## セットアップ
```bash
cd mercari-sedori
python -m venv .venv && source .venv/bin/activate    # Python 3.11+
pip install -e . -r requirements.txt
playwright install chromium                          # Playwright版を使う場合のみ
cp config.yaml.example config.yaml
cp .env.example .env                                 # DISCORD_WEBHOOK_URL / ANTHROPIC_API_KEY を記入
pytest                                               # テスト
```
`.env` は `.gitignore` 済みです。キーやWebhook URLはコード・ログに出力しません。

## 使い方
```bash
# 1) CSV版(動作確認。sample は 2026-06 のデータなので --as-of で基準日を指定)
python -m sedori run --csv data/sample_items.csv --dry-run --as-of 2026-06-30

# 2) Playwright版(公開検索ページを閲覧のみ・レート制限つき)
python -m sedori run --playwright

# 3) 定期実行(config の interval_minutes ごと、quiet_hours は停止)
python -m sedori schedule --playwright      # cron で `run` を叩く運用でも可

# 4) 在庫・損益
python -m sedori inventory add "Switch HAC-001 青" 9000
python -m sedori inventory listed 1 15000
python -m sedori inventory sold 1 15000 --shipping 850 --packing 100
python -m sedori inventory report
python -m sedori inventory export data/2026.csv --year 2026
streamlit run src/sedori/dashboard/app.py

# 5) 出品文生成(要 ANTHROPIC_API_KEY)
python -m sedori listing 1 --condition "目立った傷なし。箱なし。動作確認済み"
```

### CSV形式(手動取り込み)
`item_id,title,price,condition,shipping_payer,listed_at,url,image_url,status,sold_at[,category,description]`
`status` は `販売中` / `売り切れ`。売り切れ行が相場の元データになります(`sold_at` は `YYYY-MM-DD`)。
`shipping_payer` が `着払い` の場合は仕入れ時の送料も利益から差し引きます。

## 設定(config.yaml)
すべての判定条件は `config.yaml.example` にコメント付きで記載しています。主なもの:
- `search.price_max`: 仕入れ上限(デフォルト10,000円)
- `market.min_samples`: これ未満の件数は「信頼度低」(デフォルト通知対象外)
- `profit.*`: 手数料率・梱包費・最低利益・最低利益率・送料テーブル・サイズ区分
- `exclude.*`: ジャンク/偽物/ブランド/禁止カテゴリ/NGワード
- `schedule.quiet_hours`: 夜間停止
- 利益率の分母は `profit.margin_basis`(`sale`=想定売価 / `cost`=仕入れ価格)

**送料のサイズ区分**は商品情報から判別できないため、`size_class_by_keyword` でキーワード別に指定します。未指定は `default_size_class`(安全側)です。

## ⚠ 利用上の注意
### 規約・サーバー負荷
- メルカリの[利用規約](https://help.jp.mercari.com/guide/articles/1224/)および `https://jp.mercari.com/robots.txt` を**必ず自分で確認**してください。自動アクセス(スクレイピング)を規約が制限・禁止している場合、Playwright版は使わず手動CSV取り込みだけにしてください。使用の可否と責任は利用者にあります。
- Playwright版は起動時に robots.txt を確認し、禁止パスや取得失敗時は取得しません。リクエスト間隔は最低5秒(+ランダム待機、既定8〜14秒)、1時間の検索回数は `max_searches_per_hour`(既定30)で制限され、履歴はDBに保存されるためプロセスを跨いでも有効です。この制限を緩めないでください。
- セレクタは実サイトで検証していません。DOM変更で0件になる場合は警告ログが出ます(`logs/sedori.log`)。売り切れ検索結果には売却日が出ないため、Playwright版では**取得日を売却日として代用**します(相場の日付精度に注意)。
- ログイン・購入・コメント操作は行いません。

### 古物商許可
中古品を**利益目的で反復継続して仕入れ・販売**する場合、古物営業法上の**古物商許可(公安委員会)**が必要になる可能性があります(新品を小売店から買って売る場合などは対象外のことがあります)。管轄の警察署(生活安全課)や専門家に確認してください。本ツールは法的助言を提供しません。

### その他
- 偽物・転売禁止品(チケット、食品、化粧品、医薬品等)を避けるための除外ルールは補助であり、最終確認は人間が行ってください。
- 出品文は事実ベースで生成し、誇大表現を検出すると警告しますが、内容は必ず自分で確認・修正してから出品してください。
- 売上・利益は確定申告の対象になります。`inventory export` のCSVを税理士等への相談に利用できます。
