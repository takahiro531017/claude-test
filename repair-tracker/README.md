# 全社統一 修理品管理システム

家電問屋向けの「メーカー持込修理品」管理Webシステムです。販売店から預かった修理品を、
**預かり → メーカー発送 → 修理中 → 返却受領 → 販売店へ返送 → 完了** まで全8拠点で同じフォーム・同じ番号ルールで管理します。

- 画面は日本語。PC・タブレット・スマホ対応(倉庫での撮影・入力を想定した大きなボタン)
- 誰かが更新すると、同じ画面を開いている他のユーザーに**リロードなしで反映**(Supabase Realtime)
- 同時編集は**楽観ロック**(version)で保護。「最終更新者・更新日時」を常時表示
- エンドユーザーの個人情報は**暗号化(AES-256-GCM)**。一覧はマスク表示、表示操作は**監査ログ**に記録
- **システム実行時に Claude / Anthropic / その他のAI APIは一切使いません**。Claude Code は開発ツールとして使っただけで、契約終了後も運用・保守できます

> 重要: この README の手順は、**一般的なWeb開発者が Claude なしで**本番構築できるように書いてあります。
> 先に [`docs/引継ぎ書.md`](docs/引継ぎ書.md) と [`docs/セキュリティ設計書.md`](docs/セキュリティ設計書.md) に目を通してください。

## 構成図

```
 [ブラウザ(PC/タブレット/スマホ)]  React + TypeScript + Vite  (静的ファイル)
          │ HTTPS (HSTS/CSP)          ← Vercel / Cloudflare Pages / 自社nginx のどれでも可
          ▼
 ┌────────────── Supabase (東京 ap-northeast-1) ───────────────┐
 │ Auth      メール+パスワード(12文字以上)+TOTP(MFA必須)、招待制   │
 │ Postgres  RLSで権限を強制 / トリガーで採番・楽観ロック・履歴・監査 │
 │ Realtime  repairs の変更を購読者へ配信(RLSが効く)               │
 │ Storage   写真・添付(非公開バケット、署名付きURL、種類/サイズ制限)│
 │ Edge Fn   pii-write / pii-reveal / csv-export / admin-users    │
 │           (暗号鍵はここのシークレットにだけ置く。DBには置かない)  │
 └────────────────────────────────────────────────────────────┘
 バックアップ: scripts/backup.sh (pg_dump → age暗号化)  / CI: GitHub Actions
```

セルフホスト代替案: Docker Compose で PostgreSQL + PostgREST + GoTrue 等を自前運用すれば同じ SQL・同じコードで動きますが、
MFA・Realtime・バックアップ・脆弱性対応をすべて自社で保守することになります。まず Supabase で始め、必要になれば
`pg_dump` と環境変数の切替で移行できる構成にしてあります(Supabase 自体もOSSのセルフホスト版あり)。

## リポジトリ構成

| パス | 内容 |
|---|---|
| `src/` | フロントエンド(React)。`pages/` 画面、`lib/` API・ステータス規則、`auth/` 認証 |
| `supabase/migrations/` | DBスキーマ・トリガー・RLS・監査ログ(番号順に適用) |
| `supabase/functions/` | Edge Functions(個人情報の暗号化/復号、CSV、ユーザー招待)と共有ライブラリ |
| `supabase/seed/` | `seed_master.sql`(拠点・メーカー。本番でも使用) / `seed_dummy.sql`(開発専用ダミー) |
| `supabase/tests/` | DBのRLS・監査・ストレージ権限テスト(SQL) |
| `tests/`, `e2e/` | 単体テスト(Vitest) / 主要フローのE2E(Playwright) |
| `scripts/` | バックアップ/復元、鍵ローテーション、DBテスト実行 |
| `deploy/`, `vercel.json`, `public/_headers` | セキュリティヘッダー設定(配信先ごと) |
| `docs/` | 運用マニュアル、ユーザー操作マニュアル、セキュリティ設計書、引継ぎ書、点検結果 |
| `../.github/workflows/` | CI(テスト・脆弱性・シークレット検査)と日次バックアップ |

## ゼロから本番構築するまで

前提: Node.js 22 以上、[Supabase CLI](https://supabase.com/docs/guides/cli)、`openssl`。
**サービスのアカウントはすべて「会社名義」(会社の共用メールアドレス+複数管理者)で作成**してください。個人名義にしないこと(`docs/引継ぎ書.md`)。

### 1. Supabase プロジェクトを作る
1. 会社名義の Supabase 組織を作成し、新規プロジェクトを作る。**Region は Northeast Asia (Tokyo)**。DBパスワードは長い乱数にして会社の金庫(パスワード管理)に保管。
2. 本番運用は **Pro プラン以上**を推奨(日次バックアップ、PITR、セッションの無操作タイムアウトが使える)。
3. CLI でログインして紐付け:
   ```bash
   cd repair-tracker
   supabase login
   supabase link --project-ref <プロジェクトREF>
   ```

### 2. DB・認証設定を反映する
```bash
supabase db push                 # supabase/migrations/ を順に適用(スキーマ・RLS・監査・バケット)
psql "$DATABASE_URL" -f supabase/seed/seed_master.sql   # 8拠点・メーカーの初期マスタ(ダミーデータは入れない)
```
- `supabase/config.toml` の `site_url`(= 本番URL)と `additional_redirect_urls` を本番ドメインに書き換えてから `supabase config push`(または同じ値をダッシュボードの Authentication 設定へ)。
- ダッシュボード Authentication で確認: **Sign ups = 無効**、最小パスワード長 12、MFA(TOTP)有効。
- pg_cron(Database → Extensions で有効化)が使えるなら、`20261008000005_retention_cron.sql` が個人情報の自動匿名化を毎日登録します。

### 3. 暗号鍵とシークレットを設定する(あなたが直接行う。コード・チャット・Gitに貼らない)
```bash
# 32バイトの乱数をbase64にして鍵番号1として登録(画面に表示される値を会社の金庫にも必ず保管)
KEY=$(openssl rand -base64 32)
supabase secrets set PII_KEYS="{\"1\":\"$KEY\"}" PII_KEY_CURRENT=1 \
  ALLOWED_ORIGIN=https://repair.example.co.jp SITE_URL=https://repair.example.co.jp
unset KEY
```
⚠ **この鍵を失うと個人情報は二度と復号できません。** 金庫に2か所以上(別の人・別の場所)で保管してください。

### 4. Edge Functions をデプロイ
```bash
supabase functions deploy pii-write pii-reveal csv-export admin-users
```

### 5. 最初の管理者を作る(自己登録は禁止のため、ここだけ手作業)
1. Supabase ダッシュボード → Authentication → Users → **Add user → Send invitation**(管理者のメールアドレス)。
2. SQL Editor で、そのユーザーのID(`auth.users.id`)を使ってプロファイルを作成:
   ```sql
   insert into public.profiles(user_id, display_name, role)
   values ('<上で作成したユーザーのUUID>', '情報システム 管理者', 'admin');
   ```
3. 招待メールのリンクからパスワードを設定 → 認証アプリでMFAを登録 → ログイン。以降のユーザーは画面の「管理 → ユーザー → 招待」から追加します。

### 6. フロントエンドをビルド・公開
```bash
cp .env.example .env.local       # VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY(ダッシュボード → Project Settings → API)を記入
npm ci
npm run build                    # dist/ に静的ファイルが出力される
```
`dist/` を次のいずれかで公開します(いずれも環境変数だけで切替可能。コード変更不要)。
- **Vercel**: リポジトリを接続し、Root Directory=`repair-tracker`、環境変数 `VITE_SUPABASE_URL` `VITE_SUPABASE_ANON_KEY` を設定。ヘッダーは `vercel.json` が適用されます。
- **Cloudflare Pages**: Build command=`npm run build`、出力=`dist`。ヘッダーは `public/_headers`、SPA用の転送は `public/_redirects`。
- **自社サーバー**: `deploy/nginx.conf.example` を参照(HTTPSリダイレクト、HSTS、CSP込み)。

CSP の `connect-src` は `https://*.supabase.co` を許可しています。独自ドメインやセルフホストにした場合は、ヘッダー設定内のドメインを合わせて変更してください。

### 7. 公開後の確認(必ず実施)
- [ ] 管理者でログイン → MFA登録 → 招待したテストユーザー(各ロール)で権限が仕様どおりか
- [ ] 拠点担当で新規受付 → 管理番号 `拠点コード-YYYYMMDD-連番` が採番される
- [ ] 2つのブラウザで同じ一覧を開き、片方の更新がもう片方に即時反映される
- [ ] 個人情報を入力 → 一覧はマスク → 「表示」で平文 → 管理画面の監査ログに記録される
- [ ] `https://` 以外でアクセスできない / [securityheaders.com](https://securityheaders.com) 等でヘッダー確認
- [ ] `scripts/backup.sh` を1回実行し、`scripts/restore.sh` で検証用DBに復元できる

## 開発・テスト

```bash
npm ci
npm run dev           # 開発サーバー(.env.local が必要)
npm run lint && npm run typecheck && npm test      # 静的検査・単体テスト
npm run test:db       # DBのRLS/監査/ストレージ権限テスト(PostgreSQL 16 が必要。PGHOST等は環境変数)
npm run test:e2e      # E2E(Playwright。バックエンドはモック)
```
ローカルに本物の Supabase を立てる場合(Docker 必須): `supabase start` → `supabase db reset`(マイグレーション+`supabase/seed/` を適用)。
`seed_dummy.sql` は**開発専用**(架空データ。テストユーザー含む)で、本番では実行しません。

## 注意事項(必読)

- 本番のキー・パスワード・実データを、このリポジトリ・チャット・ログに書かないでください(`.gitignore` と CI の gitleaks で混入を検知)。
- 画面側の制御だけに頼らず、権限は DB の RLS で強制しています。画面を変更する場合も DB のポリシーを緩めないでください(`supabase/tests/` のテストが守っています)。
- 開発時点で**実際の Supabase 環境(Auth/Realtime/Storage/Edge Functions)での通し検証は未実施**です。本番公開前に上記「公開後の確認」を実環境で必ず実施してください(詳細は `docs/要件充足チェック表.md` の「未検証事項」)。
