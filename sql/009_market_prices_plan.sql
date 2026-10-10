-- 市場価格（market_prices）を料金プラン（plans）にひも付ける（plan_id を足す）
-- 001〜008 のあとに実行する。何度実行しても同じ結果になる
-- 宿ごとに1件だった市場価格を、料金プランごとに1件にする（人数・泊数・食事の条件をプランに合わせて比べるため）

begin;

-- ① plans の (id, menu_id) を一意にする。market_prices から「同じ宿のプラン」を組で参照するため
--   （2回目以降の実行のため、先に参照している制約を外す）
alter table bts_app.market_prices drop constraint if exists market_prices_plan_menu_fkey;
alter table bts_app.plans drop constraint if exists plans_id_menu_id_key;
alter table bts_app.plans add constraint plans_id_menu_id_key unique (id, menu_id);

-- ② どの料金プランの価格か。宿ごとの古い行のために null を許す
alter table bts_app.market_prices add column if not exists plan_id uuid;

-- ③ plan_id と menu_id の組で plans を参照する（別の宿のプランへのひも付けを弾く）
alter table bts_app.market_prices add constraint market_prices_plan_menu_fkey
  foreign key (plan_id, menu_id) references bts_app.plans (id, menu_id);

-- ④ 同じプラン・同じ条件・同じ取得元の価格は1行だけ。取り直しは上書き（upsert）する
--   supabase-py: upsert(row, on_conflict="plan_id,checkin,nights,adults,children,source")
create unique index if not exists uq_market_prices_plan_condition
  on bts_app.market_prices (plan_id, checkin, nights, adults, children, source);

-- ⑤ 比べる日の価格（is_representative）はプランごとに1つだけ
create unique index if not exists uq_market_prices_plan_representative
  on bts_app.market_prices (plan_id) where is_representative;

-- ⑥ 宿ごとの古い仮の価格（plan_id が空）を、比べる日の価格から外す。行は残す
update bts_app.market_prices
   set is_representative = false, updated_at = now()
 where plan_id is null and source = 'dummy';

-- ⑦ 料金プランごとの仮の価格。価格はそのプランの定価の 0.70〜1.10 倍（プランごとに決まった値、100円単位）
--   福利厚生価格より安くなるプランも一部できる（「市場価格の方が安い」の表示を確かめるため）
--   人数・泊数・食事の条件はプランと同じ。比べる日は実行日の次の土曜
--   7件に1件は作らない（市場価格が取れなかったプラン → 定価と比べる動きを確かめるため）
--   楽天から取った本物の価格（source が dummy 以外）が入っているプランには入れない
delete from bts_app.market_prices where plan_id is not null and source = 'dummy';

insert into bts_app.market_prices
  (menu_id, plan_id, hotel_ref, checkin, nights, adults, children, meal, price, source, fetched_at, is_representative)
select p.menu_id, p.id, m.hotel_ref,
       current_date + ((6 - extract(dow from current_date)::int + 7) % 7 + case when extract(dow from current_date) = 6 then 7 else 0 end),
       p.nights, coalesce(p.adults, 2), coalesce(p.children, 0), p.meal,
       (round(p.list_price * (0.70 + ((hashtext(p.id::text) & 2147483647) % 41) / 100.0), -2))::int,
       'dummy', now(), true
  from bts_app.plans p
  join bts_app.menus m on m.id = p.menu_id
 where m.category = 'stay' and m.hotel_ref is not null
   and p.deleted_at is null and m.deleted_at is null
   and (hashtext(p.id::text) & 2147483647) % 7 <> 0
   and not exists (select 1 from bts_app.market_prices x where x.plan_id = p.id and x.source <> 'dummy');

commit;

-- 確認: プランごとの仮の価格の件数
-- select count(*) from bts_app.market_prices where plan_id is not null and is_representative;
