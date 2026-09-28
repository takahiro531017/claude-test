# 在庫管理システム

入出庫を登録すると在庫数が自動計算される、ブラウザで使う在庫管理アプリです。
Node.js (Express) + libSQL(SQLite互換) で動作し、ビルド不要でそのまま起動できます。

## ローカルでのセットアップ

```bash
npm install
npm start
```

起動後、ブラウザで http://localhost:3000 を開いてください。

初回起動時に `data/seed_data.json` から拠点・商品マスタが自動投入されます
（既存の在庫管理表から抽出した拠点25件・商品638件）。

ローカル実行時はデータを `data/inventory.db`（SQLiteファイル、Git管理対象外）に保存します。

## インターネット上に公開する（Turso + Render、どちらも無料枠あり）

ローカルにNode.jsを入れず、ブラウザだけでアクセスできるようにする手順です。
DBをクラウド（[Turso](https://turso.tech)）に置くことで、Renderの無料プランでも
サーバー再起動でデータが消えません。

### 1. Turso（データベース）を用意する

1. https://turso.tech で無料アカウントを作成
2. [Turso CLI](https://docs.turso.tech/cli/installation) をインストールしてログイン
3. データベースを作成し、接続情報を取得
   ```bash
   turso db create inventory-app
   turso db show inventory-app --url        # → TURSO_DATABASE_URL
   turso db tokens create inventory-app      # → TURSO_AUTH_TOKEN
   ```

### 2. Render（ホスティング）にデプロイする

1. https://render.com で無料アカウントを作成し、GitHubリポジトリ（このリポジトリ）を接続
2. "New +" → "Blueprint" を選び、このリポジトリの `render.yaml` を検出させる
   （Blueprintを使わない場合は "New +" → "Web Service" から手動設定してもOK。
   Build Command: `npm install` / Start Command: `npm start`）
3. 環境変数に、手順1で取得した値を設定
   - `TURSO_DATABASE_URL`
   - `TURSO_AUTH_TOKEN`
4. デプロイが完了すると、Renderが発行するURL（`https://xxxxx.onrender.com`）でアクセスできます

`TURSO_DATABASE_URL` が設定されていない場合は自動的にローカルファイルにフォールバックするため、
開発中はこれまで通り `npm start` だけで動作します。

## 画面構成

- **ダッシュボード**: 商品ごとの現在庫を一覧表示。在庫僅少・欠品を検索/フィルタ可能
- **入庫登録**: 品番・拠点・数量を入力すると在庫に加算
- **出荷登録**: 出荷数量・箱破損数量を入力すると在庫から減算
- **履歴一覧**: 入出庫履歴を品番・拠点・区分・期間で絞り込み、誤登録の削除も可能
- **商品マスタ**: 品番・商品名・寸法・重量・在庫僅少の閾値を管理
- **拠点マスタ**: 入出庫の拠点（引取り業者・倉庫など）を管理
