-- 市場価格（market_prices）に、テスト用の仮の価格を入れる
-- 001〜007 のあとに実行する。何度実行しても同じ結果になる（前回の仮の価格を消してから入れ直す）
-- 楽天から取った本物の価格（source が dummy 以外）がある宿には入れない

-- ① 前回入れた仮の価格を消す
delete from bts_app.market_prices where source = 'dummy';

-- ② 宿ごとに、2名1泊の定価のうち一番安いものを元に、仮の価格を作る
--    価格 ＝ 定価 × 宿ごとに決まった割合（80〜98%）× 1.2（土曜料金）を100円単位に丸めたもの
--    比べる日は、実行した日から見て次の土曜。2名1泊
with stay as (
  select m.id as menu_id, m.hotel_ref,
         min(p.list_price / greatest(p.nights, 1)) filter (where p.adults = 2) as ref_price
  from bts_app.menus m
  join bts_app.tenants t on t.id = m.tenant_id and t.code = 'sample'
  join bts_app.plans p on p.menu_id = m.id and p.deleted_at is null
  where m.category = 'stay' and m.hotel_ref is not null and m.deleted_at is null
  group by m.id, m.hotel_ref
),
priced as (
  select s.menu_id, s.hotel_ref,
         0.80 + (('x' || lpad(substr(md5(s.hotel_ref), 1, 8), 16, '0'))::bit(64)::bigint % 1000) / 999.0 * 0.18 as rate,
         s.ref_price
  from stay s
  where s.ref_price is not null
)
insert into bts_app.market_prices (menu_id, hotel_ref, checkin, nights, adults, children, meal, price, source, source_url, fetched_at, is_representative)
select p.menu_id, p.hotel_ref,
       current_date + (case when (6 - extract(isodow from current_date)::int + 7) % 7 = 0 then 7
                            else (6 - extract(isodow from current_date)::int + 7) % 7 end),
       1, 2, 0, null,
       (round(p.ref_price * p.rate * 1.2 / 100) * 100)::int,
       'dummy', null, now(), true
from priced p
where not exists (
  select 1 from bts_app.market_prices mp
  where mp.menu_id = p.menu_id and mp.is_representative and mp.source <> 'dummy'
);

-- ③ 確認用: 宿の数と、仮の価格の入った数が同じなら成功
-- select count(*) from bts_app.menus where category = 'stay' and hotel_ref is not null and deleted_at is null;
-- select count(*) from bts_app.market_prices where source = 'dummy';
