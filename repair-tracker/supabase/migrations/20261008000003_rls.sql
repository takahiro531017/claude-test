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
