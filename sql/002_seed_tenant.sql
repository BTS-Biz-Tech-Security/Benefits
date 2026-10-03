-- 初期テナント（1社）と共通エリア。CSV投入（seed/load.py）の前に実行する
insert into bts_app.tenants (name, code) values ('サンプル株式会社', 'sample')
on conflict (code) do nothing;

insert into bts_app.areas (tenant_id, code, name, region, sort)
select * from (values
  (null::uuid, 'hakone',    '箱根',   '関東', 1),
  (null::uuid, 'atami',     '熱海',   '関東', 2),
  (null::uuid, 'karuizawa', '軽井沢', '中部', 3),
  (null::uuid, 'kyoto',     '京都',   '関西', 4),
  (null::uuid, 'okinawa',   '沖縄',   '九州・沖縄', 5)
) as v(tenant_id, code, name, region, sort)
where not exists (select 1 from bts_app.areas a where a.code = v.code and a.tenant_id is null);
