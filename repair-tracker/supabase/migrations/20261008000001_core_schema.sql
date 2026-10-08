-- 全社統一 修理品管理システム: コアスキーマ
-- 注意: 個人情報(エンドユーザー氏名/電話/住所)は repairs ではなく repair_pii に暗号文のみ保存する。

create type public.user_role as enum ('admin', 'hq_viewer', 'branch_staff', 'branch_viewer');

-- ---------- マスタ ----------
create table public.branches (
  id smallint generated always as identity primary key,
  code text not null unique check (code ~ '^[A-Z]{2,4}$'),
  name text not null unique,
  active boolean not null default true
);

create table public.manufacturers (
  id int generated always as identity primary key,
  name text not null unique check (char_length(name) between 1 and 100),
  active boolean not null default true
);

create table public.dealers (
  id int generated always as identity primary key,
  code text not null unique check (char_length(code) between 1 and 30),
  name text not null check (char_length(name) between 1 and 100),
  active boolean not null default true
);

create table public.settings (
  key text primary key,
  value text not null,
  description text
);

insert into public.settings(key, value, description) values
  ('stale_sent_days',      '14', 'メーカー発送後、この日数を超えたら滞留アラート'),
  ('stale_return_days',    '7',  'メーカー返却受領後、この日数以内に販売店返送がなければアラート'),
  ('retention_years',      '3',  '完了後この年数が経過した案件の個人情報を匿名化'),
  ('session_timeout_min',  '30', '無操作で自動ログアウトするまでの分数');

-- ---------- ユーザープロファイル ----------
create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 60),
  role public.user_role not null,
  branch_id smallint references public.branches(id),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  -- 拠点ロールは拠点必須
  constraint branch_required check (role in ('admin', 'hq_viewer') or branch_id is not null)
);

-- ---------- 修理案件 ----------
create table public.repair_counters (
  branch_id smallint not null references public.branches(id),
  ymd date not null,
  last_seq int not null default 0,
  primary key (branch_id, ymd)
);

create table public.repairs (
  id uuid primary key default gen_random_uuid(),
  mgmt_no text not null unique,
  branch_id smallint not null references public.branches(id),
  received_on date not null default (now() at time zone 'Asia/Tokyo')::date,
  received_by uuid references auth.users(id),
  status text not null default 'received' check (status in
    ('received','sent_to_maker','in_repair','returned_from_maker','returned_to_dealer','completed',
     'on_hold','quote_pending','unrepairable','cancelled')),
  priority text not null default 'normal' check (priority in ('normal','urgent')),
  due_on date,

  -- 販売店
  dealer_id int references public.dealers(id),
  dealer_name text not null check (char_length(dealer_name) between 1 and 100),
  dealer_code text check (char_length(dealer_code) <= 30),
  dealer_contact_name text check (char_length(dealer_contact_name) <= 60),
  dealer_contact text check (char_length(dealer_contact) <= 100),

  -- 商品
  manufacturer_id int not null references public.manufacturers(id),
  product_name text not null check (char_length(product_name) between 1 and 150),
  model_no text check (char_length(model_no) <= 60),
  serial_no text check (char_length(serial_no) <= 60),
  purchased_on date,
  has_warranty_card boolean not null default false,
  in_warranty boolean,
  accessories jsonb not null default '[]'::jsonb check (jsonb_typeof(accessories) = 'array'),
  symptom text not null check (char_length(symptom) between 1 and 2000),
  appearance_note text check (char_length(appearance_note) <= 2000),

  -- エンドユーザー情報: 一覧用マスク値のみ(平文は持たない)
  enduser_name_mask text check (char_length(enduser_name_mask) <= 60),
  enduser_phone_mask text check (char_length(enduser_phone_mask) <= 30),
  has_pii boolean not null default false,

  -- メーカー対応
  maker_receipt_no text check (char_length(maker_receipt_no) <= 60),
  maker_sent_on date,
  outbound_carrier text check (char_length(outbound_carrier) <= 40),
  outbound_tracking_no text check (char_length(outbound_tracking_no) <= 60),
  quote_amount numeric(12,0) check (quote_amount >= 0),
  quote_approved boolean,
  repair_detail text check (char_length(repair_detail) <= 2000),
  repair_cost numeric(12,0) check (repair_cost >= 0),
  maker_returned_on date,

  -- 返送・完了
  dealer_returned_on date,
  return_carrier text check (char_length(return_carrier) <= 40),
  return_tracking_no text check (char_length(return_tracking_no) <= 60),
  completed_on date,
  note text check (char_length(note) <= 2000),

  -- システム項目
  version int not null default 1,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references auth.users(id),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  deleted_by uuid references auth.users(id),
  pii_purged_at timestamptz
);

create index repairs_branch_status_idx on public.repairs(branch_id, status) where deleted_at is null;
create index repairs_serial_idx on public.repairs(serial_no) where serial_no is not null;
create index repairs_model_idx on public.repairs(model_no);
create index repairs_tracking_out_idx on public.repairs(outbound_tracking_no);
create index repairs_tracking_ret_idx on public.repairs(return_tracking_no);
create index repairs_maker_receipt_idx on public.repairs(maker_receipt_no);
create index repairs_updated_idx on public.repairs(updated_at desc);

-- 個人情報(暗号文)。authenticated には一切権限を与えない(Edge Function が service_role で操作)
create table public.repair_pii (
  repair_id uuid primary key references public.repairs(id) on delete cascade,
  name_enc text,    -- 形式: v<key_version>:<iv b64>:<ciphertext+tag b64>
  phone_enc text,
  addr_enc text,
  key_version smallint not null default 1,
  updated_at timestamptz not null default now()
);

create table public.repair_files (
  id uuid primary key default gen_random_uuid(),
  repair_id uuid not null references public.repairs(id) on delete cascade,
  kind text not null default 'photo' check (kind in ('photo', 'attachment')),
  storage_path text not null unique,
  mime text not null check (mime in ('image/jpeg','image/png','image/webp','application/pdf')),
  size_bytes int not null check (size_bytes between 1 and 10485760),
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);
create index repair_files_repair_idx on public.repair_files(repair_id);

create table public.status_history (
  id bigint generated always as identity primary key,
  repair_id uuid not null references public.repairs(id) on delete cascade,
  from_status text,
  to_status text not null,
  changed_by uuid references auth.users(id),
  changed_at timestamptz not null default now(),
  comment text check (char_length(comment) <= 500)
);
create index status_history_repair_idx on public.status_history(repair_id, changed_at);

-- 監査ログ(追記のみ。ハッシュ連鎖で改ざん検知)
create table public.audit_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor uuid,
  actor_role text,
  action text not null,
  repair_id uuid,
  meta jsonb not null default '{}'::jsonb,
  prev_hash text,
  hash text not null
);
create index audit_log_at_idx on public.audit_log(at desc);
create index audit_log_repair_idx on public.audit_log(repair_id);
