-- ============================================================================
-- 開発・検証専用ダミーデータ(本番では絶対に実行しないこと)
--  - 氏名・電話・住所はすべて架空。実在の個人情報は含まない。
--  - テストユーザーのパスワードは開発専用の固定値。本番には存在させない。
--  - 事前に seed_master.sql を実行しておくこと。福岡支店(FUK)のみのデータを作成する。
-- ============================================================================
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

-- テストユーザー(各ロール)。ローカルの Supabase でログインできる形式(開発専用パスワード)で作成する。
--   パスワード: DevOnly-Passw0rd!   ※本番に存在させない。ログイン後、TOTP(MFA)の登録が必要。
--   ※ Supabase の内部テーブル構造はバージョンで変わる。失敗する場合は、ダッシュボード/`supabase start` の
--     Studio からユーザーを作成し、下の profiles の user_id だけ合わせればよい。
insert into auth.users(id, instance_id, aud, role, email, encrypted_password, email_confirmed_at,
                       raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                       confirmation_token, recovery_token, email_change_token_new, email_change)
select u.id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', u.email,
       extensions.crypt('DevOnly-Passw0rd!', extensions.gen_salt('bf')), now(),
       '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb, now(), now(), '', '', '', ''
  from (values
    ('10000000-0000-0000-0000-000000000001'::uuid,'admin@example.test'),
    ('10000000-0000-0000-0000-000000000004'::uuid,'staff-fuk@example.test'),
    ('10000000-0000-0000-0000-000000000005'::uuid,'viewer-fuk@example.test')) as u(id, email)
on conflict (id) do nothing;

do $$ begin
  if to_regclass('auth.identities') is not null then
    insert into auth.identities(id, provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
    select gen_random_uuid(), u.id::text, u.id, jsonb_build_object('sub', u.id::text, 'email', u.email), 'email', now(), now(), now()
      from auth.users u where u.email like '%@example.test'
       and not exists (select 1 from auth.identities i where i.user_id = u.id);
  end if;
end $$;

insert into public.profiles(user_id, display_name, role, branch_id) values
  ('10000000-0000-0000-0000-000000000001','管理者(テスト)','admin',null),
  ('10000000-0000-0000-0000-000000000004','福岡担当(テスト)','branch_staff',(select id from branches where code='FUK')),
  ('10000000-0000-0000-0000-000000000005','福岡閲覧(テスト)','branch_viewer',(select id from branches where code='FUK'))
on conflict (user_id) do nothing;

insert into public.dealers(code, name) values
  ('D001','サンプル電機 北店'),('D002','テスト家電センター'),('D003','ダミー電化ストア'),
  ('D004','架空ホームプラザ'),('D005','見本でんきの店')
on conflict (code) do nothing;

-- 30件(福岡支店。ステータス・日付を散らし、滞留アラートも発生させる)
do $$
declare
  i int; r_id uuid; b smallint; m int; d int; st text; days_ago int;
    mk_n int := (select count(*) from manufacturers);
  statuses text[] := array['received','sent_to_maker','in_repair','returned_from_maker','returned_to_dealer','completed','on_hold','quote_pending','unrepairable','cancelled'];
  products text[] := array['ドラム式洗濯機','冷蔵庫','電子レンジ','炊飯器','エアコン','掃除機','液晶テレビ','ドライヤー'];
  surnames text[] := array['架空','見本','試験','仮名','例示'];
  staff uuid[] := array['10000000-0000-0000-0000-000000000004','10000000-0000-0000-0000-000000000001']::uuid[];
begin
  for i in 1..30 loop
    b := (select id from branches where code = 'FUK');
    m := (select id from manufacturers order by id offset ((i - 1) % mk_n) limit 1);
    d := (select id from dealers order by id offset ((i - 1) % 5) limit 1);
    st := statuses[1 + ((i - 1) % 10)];
    days_ago := 3 + (i * 2) % 40;
    insert into repairs(branch_id, received_on, priority, dealer_id, dealer_name, dealer_code, dealer_contact_name, dealer_contact,
                        manufacturer_id, product_name, model_no, serial_no, purchased_on, has_warranty_card, in_warranty,
                        accessories, symptom, appearance_note, created_by, enduser_name_mask, enduser_phone_mask, has_pii)
    select b, current_date - days_ago, case when i % 7 = 0 then 'urgent' else 'normal' end, d, dl.name, dl.code,
           '担当 ' || surnames[1 + (i % 5)], '000-0000-' || lpad(i::text, 4, '0'),
           m, products[1 + (i % 8)], 'MODEL-' || lpad(i::text, 3, '0'), 'DUMMY-SN-' || lpad(i::text, 5, '0'),
           current_date - days_ago - 300, i % 3 <> 0, i % 2 = 0,
           '["電源コード","取扱説明書"]'::jsonb, '電源が入らない(ダミー症状 ' || i || ')', '目立つ傷なし(ダミー)',
           staff[1 + (i % 2)],
           case when i % 3 = 0 then surnames[1 + (i % 5)] || ' ○○' end,
           case when i % 3 = 0 then '000-****-' || lpad(i::text, 4, '0') end,
           (i % 3 = 0)
      from dealers dl where dl.id = d
    returning id into r_id;

    -- ステータスと工程日付(サービス権限=auth.uid() null のため遷移検証はスキップされる)
    update repairs set status = st,
      maker_sent_on        = case when st in ('sent_to_maker','in_repair','returned_from_maker','returned_to_dealer','completed') then current_date - greatest(days_ago - 2, 1) end,
      maker_returned_on    = case when st in ('returned_from_maker','returned_to_dealer','completed') then current_date - greatest(days_ago - 5, 0) end,
      dealer_returned_on   = case when st in ('returned_to_dealer','completed') then current_date - greatest(days_ago - 6, 0) end,
      completed_on         = case when st = 'completed' then current_date - greatest(days_ago - 7, 0) end,
      maker_receipt_no     = case when st <> 'received' then 'MK-' || lpad(i::text, 6, '0') end,
      outbound_tracking_no = case when st <> 'received' then '9999-0000-' || lpad(i::text, 4, '0') end
     where id = r_id;
  end loop;
end $$;

-- 滞留アラートの確認用に、確実に超過している案件を2件作る
update repairs set status = 'in_repair', maker_sent_on = current_date - 30 where mgmt_no = (select mgmt_no from repairs order by mgmt_no limit 1);
update repairs set status = 'returned_from_maker', maker_returned_on = current_date - 12 where mgmt_no = (select mgmt_no from repairs order by mgmt_no offset 1 limit 1);
