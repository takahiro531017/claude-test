-- ============================================================================
-- 修理品管理システム 初期構築SQL(自動生成: scripts/build-setup-sql.sh)
-- Supabase ダッシュボード → SQL Editor に全文を貼り付けて Run を1回だけ実行する。
-- 内容: スキーマ / トリガー / 権限(RLS) / 監査ログ / 写真バケット / 福岡支店とメーカーの初期マスタ
-- ※ 1つのプロジェクトにつき1回だけ実行すること(2回目はエラーになる)。個人情報は含まない。
-- ============================================================================

-- ---------- 20261008000001_core_schema.sql ----------
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

-- ---------- 20261008000002_functions_triggers.sql ----------
-- ヘルパー関数・トリガー

-- MFA(TOTP)を通過したセッション(aal2)かどうか。DBレベルでMFAを強制する。
create function public.mfa_ok() returns boolean
language sql stable as $$ select coalesce(auth.jwt() ->> 'aal', '') = 'aal2' $$;

-- 現在のユーザーのロール/拠点(無効ユーザー・MFA未通過は null = 何も見えない/できない)
create function public.app_role() returns public.user_role
language sql stable security definer set search_path = public as $$
  select role from public.profiles where user_id = auth.uid() and active and public.mfa_ok()
$$;

create function public.app_branch() returns smallint
language sql stable security definer set search_path = public as $$
  select branch_id from public.profiles where user_id = auth.uid() and active and public.mfa_ok()
$$;

-- ---------- 監査ログ ----------
create function public.write_audit(p_action text, p_repair_id uuid, p_meta jsonb default '{}'::jsonb,
                                   p_actor uuid default null)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_prev text;
  v_actor uuid := coalesce(p_actor, auth.uid());
  v_role text;
  v_at timestamptz := clock_timestamp();
  v_hash text;
begin
  perform pg_advisory_xact_lock(7770001);  -- 連鎖の直列化
  select hash into v_prev from public.audit_log order by id desc limit 1;
  select role::text into v_role from public.profiles where user_id = v_actor;
  v_hash := encode(sha256(convert_to(
      coalesce(v_prev,'') || '|' || extract(epoch from v_at)::text || '|' || coalesce(v_actor::text,'') || '|' ||
      p_action || '|' || coalesce(p_repair_id::text,'') || '|' || p_meta::text, 'UTF8')), 'hex');
  insert into public.audit_log(at, actor, actor_role, action, repair_id, meta, prev_hash, hash)
  values (v_at, v_actor, v_role, p_action, p_repair_id, p_meta, v_prev, v_hash);
end $$;

create function public.audit_block_mutation() returns trigger language plpgsql as $$
begin
  raise exception '監査ログは追記専用です' using errcode = '42501';
end $$;

create trigger audit_log_no_update before update or delete on public.audit_log
  for each row execute function public.audit_block_mutation();
create trigger audit_log_no_truncate before truncate on public.audit_log
  for each statement execute function public.audit_block_mutation();

-- ログイン/ログアウトなど、クライアントから記録してよいイベントのみ許可
create function public.log_event(p_action text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or public.app_role() is null then
    raise exception 'permission denied' using errcode = '42501';
  end if;
  if p_action not in ('login', 'logout') then
    raise exception 'invalid action';
  end if;
  perform public.write_audit(p_action, null, '{}'::jsonb);
end $$;

-- ---------- 管理番号採番 ----------
create function public.next_mgmt_no(p_branch smallint, p_date date) returns text
language plpgsql security definer set search_path = public as $$
declare v_code text; v_seq int;
begin
  select code into v_code from public.branches where id = p_branch;
  insert into public.repair_counters(branch_id, ymd, last_seq) values (p_branch, p_date, 1)
  on conflict (branch_id, ymd) do update set last_seq = repair_counters.last_seq + 1
  returning last_seq into v_seq;
  return v_code || '-' || to_char(p_date, 'YYYYMMDD') || '-' || lpad(v_seq::text, 3, '0');
end $$;

-- ---------- repairs: INSERT 前処理 ----------
create function public.repairs_before_insert() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  NEW.mgmt_no := public.next_mgmt_no(NEW.branch_id, NEW.received_on);  -- クライアント指定は無視
  NEW.version := 1;
  NEW.status := 'received';
  NEW.created_by := coalesce(auth.uid(), NEW.created_by);
  NEW.received_by := coalesce(auth.uid(), NEW.received_by);
  NEW.updated_by := NEW.created_by;
  NEW.created_at := now();
  NEW.updated_at := now();
  NEW.deleted_at := null; NEW.deleted_by := null; NEW.pii_purged_at := null;
  return NEW;
end $$;
create trigger repairs_bi before insert on public.repairs
  for each row execute function public.repairs_before_insert();

-- ---------- ステータス遷移規則 ----------
create function public.status_rank(s text) returns int language sql immutable as $$
  select case s when 'received' then 1 when 'sent_to_maker' then 2 when 'in_repair' then 3
    when 'returned_from_maker' then 4 when 'returned_to_dealer' then 5 when 'completed' then 6 end
$$;

create function public.transition_allowed(p_from text, p_to text, p_role public.user_role) returns boolean
language plpgsql immutable as $$
declare rf int := public.status_rank(p_from); rt int := public.status_rank(p_to);
begin
  if p_from = p_to then return true; end if;
  if p_role = 'admin' then return true; end if;
  if p_from = 'completed' then return false; end if;               -- 完了の取消は admin のみ
  if p_from = 'cancelled' then return false; end if;               -- キャンセルの復活は admin のみ
  if p_from = 'unrepairable' then return p_to in ('returned_to_dealer', 'completed'); end if;
  if rf is not null and rt is not null then return abs(rf - rt) = 1; end if;   -- 1段ずつ前進/差し戻し
  if rt is null then return true; end if;                        -- 補助ステータスへはいつでも
  if rf is null then return rt <= 5; end if;                     -- 補助から本流へ復帰(完了は経由が必要)
  return false;
end $$;

-- ---------- repairs: UPDATE 前処理(楽観ロック・不変項目・遷移・自動日付) ----------
create function public.repairs_before_update() returns trigger
language plpgsql security definer set search_path = public as $$
declare v_role public.user_role := public.app_role();
begin
  -- service_role/管理バッチ(auth.uid() が null)は検証をスキップしない: 不変項目だけは常に守る
  if NEW.id <> OLD.id or NEW.mgmt_no <> OLD.mgmt_no or NEW.branch_id <> OLD.branch_id
     or NEW.created_by is distinct from OLD.created_by or NEW.created_at <> OLD.created_at
     or NEW.received_by is distinct from OLD.received_by then
    raise exception '管理番号・拠点・作成情報は変更できません' using errcode = '42501';
  end if;

  -- 論理削除列は専用関数(app.soft_delete=on)経由のみ
  if (NEW.deleted_at is distinct from OLD.deleted_at or NEW.deleted_by is distinct from OLD.deleted_by)
     and coalesce(current_setting('app.soft_delete', true), '') <> 'on' then
    raise exception '削除/復元は専用機能を使用してください' using errcode = '42501';
  end if;
  -- 匿名化列はバッチ関数経由のみ
  if NEW.pii_purged_at is distinct from OLD.pii_purged_at
     and coalesce(current_setting('app.purge', true), '') <> 'on' then
    raise exception '匿名化列は変更できません' using errcode = '42501';
  end if;
  -- 個人情報マスク値/有無は Edge Function(service_role) のみ変更可
  if (NEW.enduser_name_mask is distinct from OLD.enduser_name_mask
      or NEW.enduser_phone_mask is distinct from OLD.enduser_phone_mask
      or NEW.has_pii is distinct from OLD.has_pii)
     and auth.uid() is not null and coalesce(current_setting('app.purge', true), '') <> 'on' then
    raise exception '個人情報は専用機能から更新してください' using errcode = '42501';
  end if;

  if NEW.status is distinct from OLD.status then
    if auth.uid() is not null and not public.transition_allowed(OLD.status, NEW.status, v_role) then
      raise exception 'このステータス変更は許可されていません (% -> %)', OLD.status, NEW.status
        using errcode = '23514';
    end if;
    -- 工程に応じた日付の自動補完
    if NEW.status = 'sent_to_maker'       and NEW.maker_sent_on is null       then NEW.maker_sent_on := (now() at time zone 'Asia/Tokyo')::date; end if;
    if NEW.status = 'returned_from_maker' and NEW.maker_returned_on is null   then NEW.maker_returned_on := (now() at time zone 'Asia/Tokyo')::date; end if;
    if NEW.status = 'returned_to_dealer'  and NEW.dealer_returned_on is null  then NEW.dealer_returned_on := (now() at time zone 'Asia/Tokyo')::date; end if;
    if NEW.status = 'completed'           and NEW.completed_on is null        then NEW.completed_on := (now() at time zone 'Asia/Tokyo')::date; end if;
  end if;

  NEW.version := OLD.version + 1;           -- クライアント指定は無視
  NEW.updated_at := now();
  NEW.updated_by := coalesce(auth.uid(), NEW.updated_by);
  return NEW;
end $$;
create trigger repairs_bu before update on public.repairs
  for each row execute function public.repairs_before_update();

-- ---------- repairs: 履歴 + 監査(AFTER) ----------
create function public.repairs_after_write() returns trigger
language plpgsql security definer set search_path = public as $$
declare v_comment text := nullif(current_setting('app.status_comment', true), '');
begin
  if TG_OP = 'INSERT' then
    insert into public.status_history(repair_id, from_status, to_status, changed_by)
      values (NEW.id, null, NEW.status, NEW.created_by);
    perform public.write_audit('create', NEW.id, jsonb_build_object('mgmt_no', NEW.mgmt_no), NEW.created_by);
  else
    if NEW.status is distinct from OLD.status then
      insert into public.status_history(repair_id, from_status, to_status, changed_by, comment)
        values (NEW.id, OLD.status, NEW.status, NEW.updated_by, v_comment);
      perform public.write_audit('status_change', NEW.id,
        jsonb_build_object('mgmt_no', NEW.mgmt_no, 'from', OLD.status, 'to', NEW.status), NEW.updated_by);
    elsif NEW.deleted_at is distinct from OLD.deleted_at then
      perform public.write_audit(case when NEW.deleted_at is null then 'restore' else 'soft_delete' end,
        NEW.id, jsonb_build_object('mgmt_no', NEW.mgmt_no), NEW.updated_by);
    elsif NEW.pii_purged_at is distinct from OLD.pii_purged_at then
      perform public.write_audit('pii_purge', NEW.id, jsonb_build_object('mgmt_no', NEW.mgmt_no), null);
    else
      -- 変更された列名のみ記録(値は記録しない=個人情報・機密を監査ログに残さない)
      perform public.write_audit('update', NEW.id, jsonb_build_object('mgmt_no', NEW.mgmt_no,
        'fields', (select coalesce(jsonb_agg(n.key order by n.key), '[]'::jsonb)
                   from jsonb_each(to_jsonb(NEW)) n
                   join jsonb_each(to_jsonb(OLD)) o using (key)
                   where n.value is distinct from o.value
                     and n.key not in ('version','updated_at','updated_by'))), NEW.updated_by);
    end if;
  end if;
  return null;
end $$;
create trigger repairs_ai after insert on public.repairs
  for each row execute function public.repairs_after_write();
create trigger repairs_au after update on public.repairs
  for each row execute function public.repairs_after_write();

-- ---------- 論理削除/復元(専用関数) ----------
create function public.soft_delete_repair(p_id uuid, p_version int, p_restore boolean default false)
returns void language plpgsql security definer set search_path = public as $$
declare v_role public.user_role := public.app_role(); v_branch smallint := public.app_branch();
        v_row public.repairs; n int;
begin
  select * into v_row from public.repairs where id = p_id;
  if v_row.id is null or v_role is null then raise exception 'not found' using errcode = 'P0002'; end if;
  if not (v_role = 'admin' or (v_role = 'branch_staff' and v_row.branch_id = v_branch and not p_restore)) then
    raise exception 'permission denied' using errcode = '42501';
  end if;
  perform set_config('app.soft_delete', 'on', true);
  update public.repairs
     set deleted_at = case when p_restore then null else now() end,
         deleted_by = case when p_restore then null else auth.uid() end
   where id = p_id and version = p_version;
  get diagnostics n = row_count;
  if n = 0 then raise exception '他のユーザーが更新しました。画面を更新してください' using errcode = '40001'; end if;
end $$;

-- ステータス変更(コメント付き・楽観ロック)
create function public.change_status(p_id uuid, p_version int, p_to text, p_comment text default null)
returns public.repairs language plpgsql security invoker set search_path = public as $$
declare v_row public.repairs;
begin
  perform set_config('app.status_comment', coalesce(left(p_comment, 500), ''), true);
  update public.repairs set status = p_to where id = p_id and version = p_version returning * into v_row;
  if v_row.id is null then
    raise exception '他のユーザーが更新したか、権限がありません' using errcode = '40001';
  end if;
  return v_row;
end $$;

-- 同一シリアルの二重登録チェック(他拠点に存在するかは真偽のみ返し、詳細は漏らさない)
create function public.serial_exists_elsewhere(p_serial text) returns boolean
language sql stable security definer set search_path = public as $$
  select public.app_role() is not null and exists (
    select 1 from public.repairs
     where serial_no = p_serial and deleted_at is null
       and (public.app_role() in ('admin','hq_viewer') or branch_id <> public.app_branch()))
$$;

-- ---------- 匿名化バッチ(保持期間経過後) ----------
create function public.purge_expired_pii() returns int
language plpgsql security definer set search_path = public as $$
declare v_years int; v_ids uuid[]; n int := 0;
begin
  select value::int into v_years from public.settings where key = 'retention_years';
  select coalesce(array_agg(id), '{}') into v_ids from public.repairs
   where completed_on is not null and completed_on < (current_date - make_interval(years => v_years))
     and pii_purged_at is null;
  if array_length(v_ids, 1) is null then return 0; end if;
  perform set_config('app.purge', 'on', true);
  delete from public.repair_pii where repair_id = any(v_ids);
  update public.repairs set enduser_name_mask = null, enduser_phone_mask = null, has_pii = false,
         pii_purged_at = now(), dealer_contact_name = null, dealer_contact = null
   where id = any(v_ids);
  get diagnostics n = row_count;
  return n;
end $$;

-- ---------- プロファイル変更の監査 ----------
create function public.profiles_audit() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if TG_OP = 'INSERT' or NEW.role is distinct from OLD.role or NEW.branch_id is distinct from OLD.branch_id
     or NEW.active is distinct from OLD.active then
    perform public.write_audit('permission_change', null, jsonb_build_object(
      'target_user', NEW.user_id, 'role', NEW.role, 'branch_id', NEW.branch_id, 'active', NEW.active));
  end if;
  return null;
end $$;
create trigger profiles_audit_t after insert or update on public.profiles
  for each row execute function public.profiles_audit();

-- ---------- 20261008000003_rls.sql ----------
-- Row Level Security: 権限はDBで強制する(画面制御には依存しない)

-- まず全権限を剥奪し、必要なものだけ付与する
revoke all on all tables in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated, public;
revoke all on all sequences in schema public from anon, authenticated;

alter table public.branches        enable row level security;
alter table public.manufacturers   enable row level security;
alter table public.dealers         enable row level security;
alter table public.settings        enable row level security;
alter table public.profiles        enable row level security;
alter table public.repair_counters enable row level security;
alter table public.repairs         enable row level security;
alter table public.repair_pii      enable row level security;
alter table public.repair_files    enable row level security;
alter table public.status_history  enable row level security;
alter table public.audit_log       enable row level security;

-- ---- マスタ/設定/プロファイル: 有効ユーザーは閲覧、admin のみ変更 ----
grant select on public.branches, public.manufacturers, public.dealers, public.settings, public.profiles to authenticated;
grant insert, update on public.branches, public.manufacturers, public.dealers, public.settings, public.profiles to authenticated;

create policy branches_sel on public.branches for select to authenticated using (public.app_role() is not null);
create policy branches_ins on public.branches for insert to authenticated with check (public.app_role() = 'admin');
create policy branches_upd on public.branches for update to authenticated using (public.app_role() = 'admin') with check (public.app_role() = 'admin');

create policy manufacturers_sel on public.manufacturers for select to authenticated using (public.app_role() is not null);
create policy manufacturers_ins on public.manufacturers for insert to authenticated with check (public.app_role() = 'admin');
create policy manufacturers_upd on public.manufacturers for update to authenticated using (public.app_role() = 'admin') with check (public.app_role() = 'admin');

create policy dealers_sel on public.dealers for select to authenticated using (public.app_role() is not null);
create policy dealers_ins on public.dealers for insert to authenticated with check (public.app_role() = 'admin');
create policy dealers_upd on public.dealers for update to authenticated using (public.app_role() = 'admin') with check (public.app_role() = 'admin');

create policy settings_sel on public.settings for select to authenticated using (public.app_role() is not null);
create policy settings_ins on public.settings for insert to authenticated with check (public.app_role() = 'admin');
create policy settings_upd on public.settings for update to authenticated using (public.app_role() = 'admin') with check (public.app_role() = 'admin');

create policy profiles_sel on public.profiles for select to authenticated using (public.app_role() is not null);
create policy profiles_ins on public.profiles for insert to authenticated with check (public.app_role() = 'admin');
create policy profiles_upd on public.profiles for update to authenticated using (public.app_role() = 'admin') with check (public.app_role() = 'admin');

-- ---- 修理案件 ----
grant select, insert, update, delete on public.repairs to authenticated;

create policy repairs_sel on public.repairs for select to authenticated using (
  case public.app_role()
    when 'admin' then true
    when 'hq_viewer' then deleted_at is null
    when 'branch_staff' then deleted_at is null and branch_id = public.app_branch()
    when 'branch_viewer' then deleted_at is null and branch_id = public.app_branch()
    else false end);

create policy repairs_ins on public.repairs for insert to authenticated with check (
  case public.app_role()
    when 'admin' then true
    when 'branch_staff' then branch_id = public.app_branch()
    else false end);

create policy repairs_upd on public.repairs for update to authenticated
  using (case public.app_role()
    when 'admin' then true
    when 'branch_staff' then deleted_at is null and branch_id = public.app_branch()
    else false end)
  with check (case public.app_role()
    when 'admin' then true
    when 'branch_staff' then deleted_at is null and branch_id = public.app_branch()
    else false end);

create policy repairs_del on public.repairs for delete to authenticated using (public.app_role() = 'admin');

-- ---- 添付/写真: 親案件が見える範囲(=repairs の RLS)に従う ----
grant select, insert, delete on public.repair_files to authenticated;
create policy files_sel on public.repair_files for select to authenticated
  using (exists (select 1 from public.repairs r where r.id = repair_id));
create policy files_ins on public.repair_files for insert to authenticated
  with check (public.app_role() in ('admin','branch_staff') and created_by = auth.uid()
              and exists (select 1 from public.repairs r where r.id = repair_id));
create policy files_del on public.repair_files for delete to authenticated
  using (public.app_role() in ('admin','branch_staff') and exists (select 1 from public.repairs r where r.id = repair_id));

-- ---- 変更履歴: 閲覧のみ(書込はトリガー) ----
grant select on public.status_history to authenticated;
create policy history_sel on public.status_history for select to authenticated
  using (exists (select 1 from public.repairs r where r.id = repair_id));

-- ---- 監査ログ: admin の閲覧のみ ----
grant select on public.audit_log to authenticated;
create policy audit_sel on public.audit_log for select to authenticated using (public.app_role() = 'admin');
revoke insert, update, delete, truncate on public.audit_log from public;

-- ---- 個人情報/カウンタ: authenticated には権限なし(ポリシーなし=全拒否)。service_role のみ ----

-- ---- 関数の実行権限 ----
grant execute on function public.app_role(), public.app_branch(), public.log_event(text),
  public.soft_delete_repair(uuid, int, boolean), public.change_status(uuid, int, text, text),
  public.serial_exists_elsewhere(text) to authenticated;
-- write_audit / purge_expired_pii / next_mgmt_no は service_role・トリガーのみ(authenticated 不可)

-- ---- Storage / Realtime(Supabase 環境でのみ有効) ----
do $$
begin
  if to_regnamespace('storage') is not null then
    insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
    values ('repair-files', 'repair-files', false, 10485760,
            array['image/jpeg','image/png','image/webp','application/pdf'])
    on conflict (id) do update set public = false, file_size_limit = 10485760,
      allowed_mime_types = excluded.allowed_mime_types;

    -- パス規約: <repair_id>/<uuid>.<ext>。親案件が RLS で見える場合のみアクセス可
    execute $p$create policy repair_files_read on storage.objects for select to authenticated
      using (bucket_id = 'repair-files' and exists (
        select 1 from public.repairs r where r.id::text = (storage.foldername(name))[1]))$p$;
    execute $p$create policy repair_files_write on storage.objects for insert to authenticated
      with check (bucket_id = 'repair-files' and public.app_role() in ('admin','branch_staff') and exists (
        select 1 from public.repairs r where r.id::text = (storage.foldername(name))[1]))$p$;
    execute $p$create policy repair_files_delete on storage.objects for delete to authenticated
      using (bucket_id = 'repair-files' and public.app_role() in ('admin','branch_staff') and exists (
        select 1 from public.repairs r where r.id::text = (storage.foldername(name))[1]))$p$;
  end if;
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.repairs, public.status_history;
  end if;
end $$;

-- service_role(Edge Function)専用の実行権限
grant execute on function public.write_audit(text, uuid, jsonb, uuid), public.purge_expired_pii(),
  public.next_mgmt_no(smallint, date) to service_role;

-- ---------- 20261008000004_audit_verify.sql ----------
-- 監査ログのハッシュ連鎖を検証する。改ざんがあれば最初に壊れた行の id を返す(正常なら null)
create function public.verify_audit_chain() returns bigint
language plpgsql stable security definer set search_path = public as $$
declare r record; v_prev text := null; v_calc text;
begin
  if auth.uid() is not null and public.app_role() is distinct from 'admin' then
    raise exception 'permission denied' using errcode = '42501';
  end if;
  for r in select * from public.audit_log order by id loop
    v_calc := encode(sha256(convert_to(
      coalesce(v_prev,'') || '|' || extract(epoch from r.at)::text || '|' || coalesce(r.actor::text,'') || '|' ||
      r.action || '|' || coalesce(r.repair_id::text,'') || '|' || r.meta::text, 'UTF8')), 'hex');
    if r.hash <> v_calc or r.prev_hash is distinct from v_prev then return r.id; end if;
    v_prev := r.hash;
  end loop;
  return null;
end $$;
grant execute on function public.verify_audit_chain() to authenticated;

-- ---------- seed_master.sql ----------
-- 本番でも使うマスタ初期データ(個人情報なし)。現在の運用範囲: 福岡支店のみ。
-- 他拠点を追加する場合は、管理画面「管理 → マスタ → 拠点」から追加できます(プログラム変更は不要)。
insert into public.branches(code, name) values ('FUK','福岡支店')
on conflict (code) do nothing;

insert into public.manufacturers(name) values
  ('パナソニック'),('シャープ'),('日立グローバルライフソリューションズ'),('三菱電機'),
  ('東芝ライフスタイル'),('ソニー'),('ダイキン工業'),('アイリスオーヤマ')
on conflict (name) do nothing;
