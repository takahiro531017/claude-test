-- 本番でも使うマスタ初期データ(個人情報なし)
insert into public.branches(code, name) values
  ('SPR','札幌支店'),('SDI','仙台支店'),('HQ','本社'),('OTA','太田物流'),
  ('NGT','新潟支店'),('NGY','名古屋支店'),('KSI','関西支社'),('FUK','福岡支店')
on conflict (code) do nothing;

insert into public.manufacturers(name) values
  ('パナソニック'),('シャープ'),('日立グローバルライフソリューションズ'),('三菱電機'),
  ('東芝ライフスタイル'),('ソニー'),('ダイキン工業'),('アイリスオーヤマ')
on conflict (name) do nothing;
