-- 【任意】全8拠点を登録する場合に実行(将来の拡大用。福岡のみの運用では実行しない)。
-- DBの権限テスト(複数拠点間の分離の検証)でも使用する。
insert into public.branches(code, name) values
  ('SPR','札幌支店'),('SDI','仙台支店'),('HQ','本社'),('OTA','太田物流'),
  ('NGT','新潟支店'),('NGY','名古屋支店'),('KSI','関西支社'),('FUK','福岡支店')
on conflict (code) do nothing;
