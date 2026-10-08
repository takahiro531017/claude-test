-- 個人情報の自動匿名化バッチ(毎日 03:30 JST = 18:30 UTC)。pg_cron が使える環境でのみ登録。
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    create extension if not exists pg_cron;
    perform cron.schedule('purge-expired-pii', '30 18 * * *', 'select public.purge_expired_pii()');
  else
    raise notice 'pg_cron がないためスケジュール未登録。docs/運用マニュアル.md を参照して手動/外部スケジューラで purge_expired_pii() を実行してください';
  end if;
end $$;
