-- RLS/トリガー/監査の自動テスト(失敗すると例外で停止)
create schema t;
grant usage on schema t to authenticated;
create function t.login(u uuid) returns void language plpgsql as $$
begin perform set_config('request.jwt.claim.sub', u::text, false); execute 'set role authenticated'; end $$;
create function t.logout() returns void language plpgsql as $$
begin execute 'reset role'; perform set_config('request.jwt.claim.sub', '', false); end $$;
create function t.eq(a anyelement, b anyelement, label text) returns void language plpgsql as $$
begin
  if a is distinct from b then raise exception 'FAIL [%]: 期待 % / 実際 %', label, b, a; end if;
  raise notice 'ok  - %', label;
end $$;
-- 失敗すべき SQL(権限エラー等)が本当に失敗することを確認
create function t.fails(q text, label text) returns void language plpgsql as $$
begin
  begin execute q; exception when others then raise notice 'ok  - % (%)', label, left(sqlerrm, 60); return; end;
  raise exception 'FAIL [%]: 失敗するはずが成功した', label;
end $$;
-- 影響行数を返す
create function t.rows(q text) returns int language plpgsql as $$
declare n int; begin execute q; get diagnostics n = row_count; return n; end $$;

-- ユーザー
insert into auth.users(id, email) values
 ('00000000-0000-0000-0000-0000000000a1','admin@example.test'),
 ('00000000-0000-0000-0000-0000000000b1','hq@example.test'),
 ('00000000-0000-0000-0000-0000000000c1','staff-spr@example.test'),
 ('00000000-0000-0000-0000-0000000000c2','staff-fuk@example.test'),
 ('00000000-0000-0000-0000-0000000000d1','viewer-spr@example.test'),
 ('00000000-0000-0000-0000-0000000000e1','inactive@example.test');
insert into public.profiles(user_id, display_name, role, branch_id, active) values
 ('00000000-0000-0000-0000-0000000000a1','管理者','admin',null,true),
 ('00000000-0000-0000-0000-0000000000b1','本社閲覧','hq_viewer',null,true),
 ('00000000-0000-0000-0000-0000000000c1','札幌担当','branch_staff',(select id from branches where code='SPR'),true),
 ('00000000-0000-0000-0000-0000000000c2','福岡担当','branch_staff',(select id from branches where code='FUK'),true),
 ('00000000-0000-0000-0000-0000000000d1','札幌閲覧','branch_viewer',(select id from branches where code='SPR'),true),
 ('00000000-0000-0000-0000-0000000000e1','退職者','branch_staff',(select id from branches where code='SPR'),false);

do $$
declare
  admin_ constant uuid := '00000000-0000-0000-0000-0000000000a1';
  hq constant uuid := '00000000-0000-0000-0000-0000000000b1';
  spr constant uuid := '00000000-0000-0000-0000-0000000000c1';
  fuk constant uuid := '00000000-0000-0000-0000-0000000000c2';
  vw  constant uuid := '00000000-0000-0000-0000-0000000000d1';
  gone constant uuid := '00000000-0000-0000-0000-0000000000e1';
  b_spr smallint := (select id from branches where code='SPR');
  b_fuk smallint := (select id from branches where code='FUK');
  mk int := (select id from manufacturers limit 1);
  r1 uuid; r2 uuid; r3 uuid; v int; n int; m1 text; m2 text; today text := to_char((now() at time zone 'Asia/Tokyo')::date,'YYYYMMDD');
begin
  -- 1. 採番 -----------------------------------------------------------
  perform t.login(spr);
  insert into repairs(branch_id, dealer_name, manufacturer_id, product_name, symptom, serial_no)
    values (b_spr,'テスト販売店',mk,'冷蔵庫','電源が入らない','SN-001') returning id, mgmt_no into r1, m1;
  insert into repairs(branch_id, dealer_name, manufacturer_id, product_name, symptom, mgmt_no)
    values (b_spr,'テスト販売店',mk,'洗濯機','異音','HACK-0') returning id, mgmt_no into r2, m2;
  perform t.eq(m1, 'SPR-'||today||'-001', '管理番号の自動採番(1件目)');
  perform t.eq(m2, 'SPR-'||today||'-002', '管理番号は連番・クライアント指定は無視');
  perform t.fails(format($q$insert into repairs(branch_id,dealer_name,manufacturer_id,product_name,symptom) values (%s,'x',%s,'y','z')$q$, b_fuk, mk), '他拠点への登録は拒否');
  perform t.logout();

  -- 2. 閲覧範囲 -------------------------------------------------------
  perform t.login(fuk);
  insert into repairs(branch_id, dealer_name, manufacturer_id, product_name, symptom)
    values (b_fuk,'福岡販売店',mk,'エアコン','冷えない') returning id into r3;
  perform t.eq((select count(*)::int from repairs), 1, '福岡担当は自拠点のみ閲覧');
  perform t.logout();
  perform t.login(spr);  perform t.eq((select count(*)::int from repairs), 2, '札幌担当は自拠点のみ閲覧'); perform t.logout();
  perform t.login(vw);   perform t.eq((select count(*)::int from repairs), 2, '札幌閲覧者は自拠点のみ閲覧'); perform t.logout();
  perform t.login(hq);   perform t.eq((select count(*)::int from repairs), 3, '本社閲覧者は全拠点閲覧'); perform t.logout();
  perform t.login(admin_); perform t.eq((select count(*)::int from repairs), 3, 'adminは全拠点閲覧'); perform t.logout();
  perform t.login(gone); perform t.eq((select count(*)::int from repairs), 0, '無効化ユーザーは何も見えない'); perform t.logout();

  -- 3. 書込権限 -------------------------------------------------------
  perform t.login(vw);
  perform t.fails(format($q$insert into repairs(branch_id,dealer_name,manufacturer_id,product_name,symptom) values (%s,'x',%s,'y','z')$q$, b_spr, mk), 'branch_viewerは登録不可');
  perform t.eq(t.rows(format($q$update repairs set note='x' where id='%s'$q$, r1)), 0, 'branch_viewerは更新不可');
  perform t.logout();
  perform t.login(hq);
  perform t.fails(format($q$insert into repairs(branch_id,dealer_name,manufacturer_id,product_name,symptom) values (%s,'x',%s,'y','z')$q$, b_spr, mk), 'hq_viewerは登録不可');
  perform t.eq(t.rows(format($q$update repairs set note='x' where id='%s'$q$, r1)), 0, 'hq_viewerは更新不可');
  perform t.logout();
  perform t.login(fuk);
  perform t.eq(t.rows(format($q$update repairs set note='x' where id='%s'$q$, r1)), 0, '他拠点案件は更新不可');
  perform t.logout();

  -- 4. 楽観ロック -----------------------------------------------------
  perform t.login(spr);
  perform t.eq(t.rows(format($q$update repairs set note='A更新' where id='%s' and version=1$q$, r1)), 1, '楽観ロック: 最新版の更新は成功');
  perform t.eq(t.rows(format($q$update repairs set note='B更新' where id='%s' and version=1$q$, r1)), 0, '楽観ロック: 古い版の更新は0件');
  select version into v from repairs where id = r1;
  perform t.eq(v, 2, 'versionが加算される');
  perform t.eq((select updated_by from repairs where id=r1), spr, '最終更新者が記録される');
  perform t.eq(t.rows(format($q$update repairs set version=99 where id='%s'$q$, r1)), 1, 'version直接指定は実行されるが');
  perform t.eq((select version from repairs where id=r1), 3, '値はトリガーが上書き(改ざん不可)');
  perform t.fails(format($q$update repairs set mgmt_no='X-1' where id='%s'$q$, r1), '管理番号は変更不可');
  perform t.fails(format($q$update repairs set branch_id=%s where id='%s'$q$, b_fuk, r1), '拠点の付け替えは不可');
  perform t.fails(format($q$update repairs set deleted_at=now() where id='%s'$q$, r1), 'deleted_atの直接更新は不可');
  perform t.fails(format($q$update repairs set enduser_name_mask='山田 ○○', has_pii=true where id='%s'$q$, r1), 'マスク値/個人情報フラグの直接更新は不可');

  -- 5. ステータス遷移 -------------------------------------------------
  perform t.fails(format($q$update repairs set status='in_repair' where id='%s'$q$, r1), '工程の飛ばし(受付→修理中)は不可');
  select version into v from repairs where id = r1;
  perform change_status(r1, v, 'sent_to_maker', '集荷済み');
  perform t.eq((select status from repairs where id=r1), 'sent_to_maker', 'ステータス前進');
  perform t.eq((select maker_sent_on is not null from repairs where id=r1), true, 'メーカー発送日の自動補完');
  perform t.fails(format($q$select change_status('%s', 1, 'in_repair')$q$, r1), '古いversionでのステータス変更は拒否');
  select version into v from repairs where id = r1;
  perform change_status(r1, v, 'sent_to_maker'::text, null);  -- 同一ステータスは許容
  select version into v from repairs where id = r1;
  perform change_status(r1, v, 'received', '差し戻し');
  perform t.eq((select status from repairs where id=r1), 'received', '1段の差し戻しは可');
  select version into v from repairs where id = r1;
  perform change_status(r1, v, 'on_hold');
  select version into v from repairs where id = r1;
  perform change_status(r1, v, 'received');
  perform t.eq((select count(*)::int from status_history where repair_id=r1), 5, '変更履歴が全て記録される');
  perform t.eq((select comment from status_history where repair_id=r1 and to_status='sent_to_maker' and from_status='received'), '集荷済み', '履歴コメント');
  perform t.logout();

  -- 完了の取消は admin のみ
  perform t.login(spr);
  select version into v from repairs where id = r2;
  perform change_status(r2, v, 'sent_to_maker'); select version into v from repairs where id = r2;
  perform change_status(r2, v, 'in_repair');     select version into v from repairs where id = r2;
  perform change_status(r2, v, 'returned_from_maker'); select version into v from repairs where id = r2;
  perform change_status(r2, v, 'returned_to_dealer');  select version into v from repairs where id = r2;
  perform change_status(r2, v, 'completed');     select version into v from repairs where id = r2;
  perform t.eq((select completed_on is not null from repairs where id=r2), true, '完了日の自動補完');
  perform t.fails(format($q$select change_status('%s', %s, 'returned_to_dealer')$q$, r2, v), '完了の取消はstaff不可');
  perform t.logout();
  perform t.login(admin_);
  perform change_status(r2, v, 'returned_to_dealer');
  perform t.eq((select status from repairs where id=r2), 'returned_to_dealer', '完了の取消はadmin可');
  perform t.logout();

  -- 6. 論理削除/物理削除 ---------------------------------------------
  perform t.login(fuk);
  perform t.fails(format($q$select soft_delete_repair('%s', 1)$q$, r1), '他拠点案件の論理削除は不可');
  perform t.logout();
  perform t.login(vw);
  perform t.fails(format($q$select soft_delete_repair('%s', %s)$q$, r1, (select version from repairs where id=r1)), 'viewerは論理削除不可');
  perform t.logout();
  perform t.login(spr);
  select version into v from repairs where id = r1;
  perform t.fails(format($q$select soft_delete_repair('%s', %s)$q$, r1, v+5), '論理削除も楽観ロック');
  perform soft_delete_repair(r1, v);
  perform t.eq((select count(*)::int from repairs where id=r1), 0, '論理削除後は担当者から見えない');
  perform t.eq(t.rows(format($q$delete from repairs where id='%s'$q$, r2)), 0, 'staffは物理削除不可');
  perform t.logout();
  perform t.login(hq);  perform t.eq((select count(*)::int from repairs where id=r1), 0, '論理削除後は本社閲覧者にも見えない'); perform t.logout();
  perform t.login(admin_);
  perform t.eq((select count(*)::int from repairs where id=r1), 1, 'adminは削除済みも閲覧可');
  select version into v from repairs where id = r1;
  perform soft_delete_repair(r1, v, true);
  perform t.eq((select deleted_at is null from repairs where id=r1), true, 'adminは復元可');
  perform t.eq(t.rows(format($q$delete from repairs where id='%s'$q$, r3)), 1, 'adminのみ物理削除可');
  perform t.logout();

  -- 7. 個人情報・カウンタ・監査ログへのアクセス ------------------------
  insert into repair_pii(repair_id, name_enc) values (r1, 'v1:xx:yy');
  perform t.login(admin_);
  perform t.fails('select * from repair_pii', 'adminでもDBクライアントから暗号文テーブルは読めない');
  perform t.logout();
  perform t.login(spr);
  perform t.fails('select * from repair_pii', 'staffは暗号文テーブルを読めない');
  perform t.fails('select * from repair_counters', 'カウンタは操作不可');
  perform t.eq((select count(*)::int from audit_log), 0, 'staffは監査ログを見られない');
  perform t.fails($q$insert into audit_log(action, hash) values ('fake','x')$q$, '監査ログの直接追記は不可');
  perform t.fails($q$select write_audit('fake', null)$q$, 'write_auditはクライアントから実行不可');
  perform t.fails($q$select purge_expired_pii()$q$, '匿名化バッチはクライアントから実行不可');
  perform log_event('login');
  perform t.fails($q$select log_event('delete_everything')$q$, '許可外イベントは記録不可');
  perform t.logout();
  perform t.login(hq);
  perform t.eq((select count(*)::int from audit_log), 0, 'hq_viewerは監査ログを見られない');
  perform t.logout();
  perform t.login(admin_);
  perform t.eq((select count(*)::int from audit_log) > 0, true, 'adminは監査ログを閲覧可');
  perform t.eq(verify_audit_chain(), null::bigint, '監査ログのハッシュ連鎖が正常');
  perform t.logout();

  -- 8. 監査ログの改ざん防止 -------------------------------------------
  perform t.fails($q$update audit_log set action='x'$q$, '監査ログのUPDATE禁止(superuserでも)');
  perform t.fails($q$delete from audit_log$q$, '監査ログのDELETE禁止(superuserでも)');
  perform t.fails($q$truncate audit_log$q$, '監査ログのTRUNCATE禁止');
  perform t.eq((select count(*)::int from audit_log where action='status_change') >= 5, true, 'ステータス変更が監査される');
  perform t.eq((select count(*)::int from audit_log where action='create') >= 3, true, '作成が監査される');
  -- 改ざん(トリガー無効化して行を書き換え)を検出できるか
  alter table audit_log disable trigger audit_log_no_update;
  update audit_log set meta = '{"tampered":true}' where id = (select min(id) from audit_log);
  alter table audit_log enable trigger audit_log_no_update;
  perform t.eq(verify_audit_chain() is not null, true, '改ざんをハッシュ連鎖で検出');

  -- 9. プロファイル(権限昇格の防止) ------------------------------------
  perform t.login(spr);
  perform t.eq(t.rows(format($q$update profiles set role='admin' where user_id='%s'$q$, spr)), 0, '自分の権限は変更できない');
  perform t.fails(format($q$insert into profiles(user_id,display_name,role) values (gen_random_uuid(),'x','admin')$q$), '自己昇格のINSERT不可');
  perform t.logout();

  -- 10. シリアル重複警告 ----------------------------------------------
  perform t.login(fuk);
  perform t.eq(serial_exists_elsewhere('SN-001'), true, '他拠点の同一シリアルを警告(詳細は返さない)');
  perform t.eq(serial_exists_elsewhere('NOPE'), false, '未登録シリアルは警告なし');
  perform t.logout();

  -- 11. 個人情報の匿名化バッチ ----------------------------------------
  update repairs set completed_on = current_date - interval '4 years', status = 'completed',
         enduser_name_mask='山田 ○○', has_pii = true where id = r2;
  insert into repair_pii(repair_id, name_enc) values (r2, 'v1:aa:bb');
  perform t.eq(purge_expired_pii(), 1, '保持期間超過案件を匿名化');
  perform t.eq((select count(*)::int from repair_pii where repair_id=r2), 0, '暗号文が削除される');
  perform t.eq((select enduser_name_mask is null and not has_pii from repairs where id=r2), true, 'マスク値も消える');
  perform t.eq((select count(*)::int from repair_pii where repair_id=r1), 1, '期間内の案件は対象外');
  perform t.eq((select count(*)::int from audit_log where action='pii_purge'), 1, '匿名化が監査される');
end $$;
