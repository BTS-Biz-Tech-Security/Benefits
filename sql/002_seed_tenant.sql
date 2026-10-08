-- 初期テナント（1社）と共通エリア。CSV投入（seed/load.py）の前に実行する
insert into bts_app.tenants (name, code) values ('サンプル株式会社', 'sample')
on conflict (code) do nothing;

insert into bts_app.areas (tenant_id, code, name, region, sort)
select * from (values
  (null::uuid, 'furano', '富良野・旭川', '北海道', 1),
  (null::uuid, 'sapporo', '札幌', '北海道', 2),
  (null::uuid, 'noboribetsu', '登別', '北海道', 3),
  (null::uuid, 'hakodate', '函館', '北海道', 4),
  (null::uuid, 'aomori', '青森・奥入瀬', '東北', 5),
  (null::uuid, 'sendai', '仙台', '東北', 6),
  (null::uuid, 'zao', '蔵王', '東北', 7),
  (null::uuid, 'aizu', '会津・磐梯', '東北', 8),
  (null::uuid, 'nasu', '那須', '関東', 9),
  (null::uuid, 'nikko', '日光', '関東', 10),
  (null::uuid, 'kusatsu', '草津', '関東', 11),
  (null::uuid, 'tokyo', '東京', '関東', 12),
  (null::uuid, 'yokohama', '横浜', '関東', 13),
  (null::uuid, 'hakone', '箱根', '関東', 14),
  (null::uuid, 'atami', '熱海', '関東', 15),
  (null::uuid, 'izu', '伊豆', '関東', 16),
  (null::uuid, 'karuizawa', '軽井沢', '中部', 17),
  (null::uuid, 'fujigoko', '富士五湖', '中部', 18),
  (null::uuid, 'kanazawa', '金沢', '中部', 19),
  (null::uuid, 'takayama', '飛騨高山', '中部', 20),
  (null::uuid, 'gero', '下呂', '中部', 21),
  (null::uuid, 'nagoya', '名古屋', '中部', 22),
  (null::uuid, 'kinosaki', '城崎', '関西', 23),
  (null::uuid, 'kyoto', '京都', '関西', 24),
  (null::uuid, 'kobe', '神戸・有馬', '関西', 25),
  (null::uuid, 'osaka', '大阪', '関西', 26),
  (null::uuid, 'nara', '奈良', '関西', 27),
  (null::uuid, 'ise', '伊勢志摩', '関西', 28),
  (null::uuid, 'shirahama', '南紀白浜', '関西', 29),
  (null::uuid, 'matsue', '松江・出雲', '中国・四国', 30),
  (null::uuid, 'hiroshima', '広島・宮島', '中国・四国', 31),
  (null::uuid, 'dogo', '松山・道後', '中国・四国', 32),
  (null::uuid, 'beppu', '別府', '九州・沖縄', 33),
  (null::uuid, 'nagasaki', '長崎・佐世保', '九州・沖縄', 34),
  (null::uuid, 'okinawa', '沖縄', '九州・沖縄', 35),
  (null::uuid, 'ishigaki', '石垣島', '九州・沖縄', 36)
) as v(tenant_id, code, name, region, sort)
where not exists (select 1 from bts_app.areas a where a.code = v.code and a.tenant_id is null);
