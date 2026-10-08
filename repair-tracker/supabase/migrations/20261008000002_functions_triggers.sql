-- ヘルパー関数・トリガー

-- 現在のユーザーのロール/拠点(無効ユーザーは null = 何も見えない)
create function public.app_role() returns public.user_role
language sql stable security definer set search_path = public as $$
  select role from public.profiles where user_id = auth.uid() and active
$$;

create function public.app_branch() returns smallint
language sql stable security definer set search_path = public as $$
  select branch_id from public.profiles where user_id = auth.uid() and active
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
