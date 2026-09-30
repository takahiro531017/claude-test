# 開発者向けメモ

Vite + TypeScript の静的サイトです。バックエンドはなく、データはすべてブラウザ内（IndexedDB / localStorage）で処理します。
グラフは Chart.js、ヒートマップは依存なしのHTML表です。

## コマンド

```bash
npm install
npm run dev         # 開発サーバー
npm test            # Vitest（CSV解析・列名の揺れ・重複統合・集計・気づき）
npm run typecheck
npm run build       # dist/ に出力（相対パスなので、どの公開先・サブパスでも動く）
npx vite-node scripts/make-sample-csv.ts   # public/sample/sample-posts.csv を再生成
```

## 公開（どれでも可）

- **Vercel / Netlify**: ルートを `venusis-insights/`、ビルド `npm run build`、出力 `dist`。
- **GitHub Pages**: `dist/` の中身を公開ブランチまたは `gh-pages` に配置（`base: './'` のため、サブパスでもそのまま動く）。
- 検索に載せない設定（`noindex`）を `index.html` に入れています。不要なら外してください。

## ディレクトリ

```
src/
  config/columnMap.ts   CSV列名の候補リスト、投稿タイプの判定語、時間帯の区分 ← 実CSVに合わせて直すのはここ
  config/labels.ts      指標の説明、チェックリスト、書き出し手順の文言
  data/                 csv / decode(UTF-8,Shift_JIS) / normalize / merge / storage / sample
  analytics/            metrics(期間・比較) / groupings(月別・タイプ別・ヒートマップ) / insights(気づき文章)
  ui/                   各セクションの描画
  styles/main.css       デザイントークン（ライト/ダーク）とレイアウト
tests/                  Vitest
scripts/                サンプルCSV生成
```

## 実際のCSVの列名に合わせる

`src/config/columnMap.ts` の `COLUMN_CANDIDATES` に候補を足します。照合は、全角半角・大文字小文字・空白・記号（`！` `?` など）を無視した完全一致 → 部分一致の順です。
見つからない必須列（日付・リーチ）がある場合、画面に「列を手動で選ぶ」フォームが出ます。投稿タイプの値の判定は `TYPE_PATTERNS`、時間帯の区分は `TIME_BANDS` で変更できます。

## データモデルと集計の定義

- `Post`: `id`（日付＋キャプションのハッシュ＝重複判定キー）, `publishedAt`（ローカル時刻）, `timeKnown`, `caption`, `type`, `reach`, `likes`, `comments`, `shares`, `saves`, `source`
- エンゲージメント率・保存率は **投稿ごとの率の平均**（`reach = 0` の投稿は除外）。
- 期間の基準日は「データ内で最新の投稿の日」。前の期間は同じ日数だけ前。全期間は比較なし。
- 月別グラフは選択期間に関係なく全データ、投稿タイプ別・ヒートマップ・ランキング・気づきは選択期間。
- ヒートマップは、ストーリーズと時刻不明（日付のみ）の投稿を除く。
- サンプルデータは保存せず、起動時に生成（`mode=sample`）。実データを取り込むとサンプルは破棄される。

## デザイン・アクセシビリティ

- グラフ色は Okabe-Ito 系。ライト（`#0072B2 / #C77F00 / #009E73`）とダーク（`#3D9FD6 / #C48500 / #1FA882`）をそれぞれ検証済み（明度帯・CVD分離・コントラスト）。
- 色だけに頼らない表現: ▲▼―と符号、値の直接ラベル、軸ラベルと件数、ヒートマップのセル内数値、「数値を表で見る」。
- ボタンの高さは44px以上。スマホでは入力欄を16px（iOSのズーム防止）、ランキング表はカード表示。

## 動作確認の観点

空データ／1件／6か月分（`public/sample/sample-posts.csv`、Shift_JIS版も）で、幅400pxの横スクロールが無いこと、ライト/ダークの表示、CSV読み込み→統合→集計→表示を、ヘッドレスChromiumで確認済み。
