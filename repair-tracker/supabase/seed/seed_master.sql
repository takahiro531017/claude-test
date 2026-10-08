-- 本番でも使うマスタ初期データ(個人情報なし)。現在の運用範囲: 福岡支店のみ。
-- 他拠点を追加する場合は、管理画面「管理 → マスタ → 拠点」から追加できます(プログラム変更は不要)。
insert into public.branches(code, name) values ('FUK','福岡支店')
on conflict (code) do nothing;

insert into public.manufacturers(name) values
  ('パナソニック'),('シャープ'),('日立グローバルライフソリューションズ'),('三菱電機'),
  ('東芝ライフスタイル'),('ソニー'),('ダイキン工業'),('アイリスオーヤマ')
on conflict (name) do nothing;
