-- 復元後の確認: 件数と監査ログの改ざんチェック
select 'repairs' as t, count(*) from public.repairs
union all select 'repair_pii', count(*) from public.repair_pii
union all select 'audit_log', count(*) from public.audit_log
union all select 'profiles', count(*) from public.profiles;
select public.verify_audit_chain() as first_broken_audit_id;  -- null なら正常
