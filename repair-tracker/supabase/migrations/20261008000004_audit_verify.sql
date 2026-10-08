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
