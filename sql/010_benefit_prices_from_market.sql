-- 福利厚生価格（plans.benefit_price）と定価（plans.list_price）を、楽天の市場価格をもとにテスト用の値に直す
-- prices.update で楽天の価格（source='rakuten_api'）を保存したあとに実行する。何度実行しても同じ結果になる
-- 楽天の価格が取れていない料金プランは変えない
--
-- 割引の区分は宿ごとに決める（宿ID から毎回同じ値を作る）
--   よくお得（約6割の宿）  : スタンダード・素泊まりは市場価格の 65〜80%、デラックスはそれより10ポイント高い
--   少しお得（約3割の宿）  : スタンダード・素泊まりは 88〜93%、デラックスはそれより5ポイント高い
--   お得ではない（約1割） : スタンダード・素泊まりは 105〜110%、デラックスはそれより5ポイント高い
-- 楽天の価格は部屋のグレードを区別しない（同じ宿・同じ食事なら同じ価格）ため、デラックスがスタンダードより安くならないよう割合を上げる
-- 定価は市場価格の 115〜130%（料金プランごと）。福利厚生価格を下回らないようにする（CSV取り込みの検証と合わせる）
-- 金額は100円単位に丸める

-- ① 確認用: 直したあとの値を表示する（書き込みはしない）。先にこれを実行して中身を確かめる
with market as (
  select mp.plan_id, mp.price as market_price
  from bts_app.market_prices mp
  where mp.is_representative and mp.source = 'rakuten_api' and mp.plan_id is not null
),
hotel as (
  select m.id as menu_id, m.name,
         ('x' || lpad(substr(md5(m.id::text), 1, 8), 16, '0'))::bit(64)::bigint % 10 as bucket,
         (('x' || lpad(substr(md5(m.id::text), 9, 8), 16, '0'))::bit(64)::bigint % 1000) / 999.0 as u
  from bts_app.menus m
  where m.category = 'stay' and m.deleted_at is null
),
rate as (
  select h.menu_id, h.name,
         case when h.bucket <= 5 then '1 よくお得' when h.bucket <= 8 then '2 少しお得' else '3 お得ではない' end as kind,
         case when h.bucket <= 5 then 0.65 + h.u * 0.15
              when h.bucket <= 8 then 0.88 + h.u * 0.05
              else 1.05 + h.u * 0.05 end as base_rate,
         case when h.bucket <= 5 then 0.10 else 0.05 end as deluxe_step
  from hotel h
),
calc as (
  select p.id, r.name as hotel, p.name as plan, r.kind, k.market_price, p.benefit_price as old_benefit, p.list_price as old_list,
         (round(k.market_price * (r.base_rate + case when p.grade = 'deluxe' then r.deluxe_step else 0 end) / 100) * 100)::int as new_benefit,
         (round(k.market_price * (1.15 + (('x' || lpad(substr(md5(p.id::text), 1, 8), 16, '0'))::bit(64)::bigint % 1000) / 999.0 * 0.15) / 100) * 100)::int as new_list
  from bts_app.plans p
  join market k on k.plan_id = p.id
  join rate r on r.menu_id = p.menu_id
  where p.deleted_at is null
)
select hotel, plan, kind, market_price, old_benefit, new_benefit, greatest(new_list, new_benefit) as new_list,
       round((1 - new_benefit::numeric / market_price) * 100) as discount_pct
from calc
order by kind, hotel, plan;

-- ② 書き込み: ①の結果に問題がなければ、ここから下を実行する
begin;

with market as (
  select mp.plan_id, mp.price as market_price
  from bts_app.market_prices mp
  where mp.is_representative and mp.source = 'rakuten_api' and mp.plan_id is not null
),
hotel as (
  select m.id as menu_id,
         ('x' || lpad(substr(md5(m.id::text), 1, 8), 16, '0'))::bit(64)::bigint % 10 as bucket,
         (('x' || lpad(substr(md5(m.id::text), 9, 8), 16, '0'))::bit(64)::bigint % 1000) / 999.0 as u
  from bts_app.menus m
  where m.category = 'stay' and m.deleted_at is null
),
rate as (
  select h.menu_id,
         case when h.bucket <= 5 then 0.65 + h.u * 0.15
              when h.bucket <= 8 then 0.88 + h.u * 0.05
              else 1.05 + h.u * 0.05 end as base_rate,
         case when h.bucket <= 5 then 0.10 else 0.05 end as deluxe_step
  from hotel h
),
calc as (
  select p.id,
         (round(k.market_price * (r.base_rate + case when p.grade = 'deluxe' then r.deluxe_step else 0 end) / 100) * 100)::int as new_benefit,
         (round(k.market_price * (1.15 + (('x' || lpad(substr(md5(p.id::text), 1, 8), 16, '0'))::bit(64)::bigint % 1000) / 999.0 * 0.15) / 100) * 100)::int as new_list
  from bts_app.plans p
  join market k on k.plan_id = p.id
  join rate r on r.menu_id = p.menu_id
  where p.deleted_at is null
)
update bts_app.plans p
set benefit_price = c.new_benefit,
    list_price = greatest(c.new_list, c.new_benefit),
    updated_at = now()
from calc c
where p.id = c.id;

commit;

-- ③ 確認用: 区分ごとの料金プランの数
-- select case when p.benefit_price < mp.price * 0.85 then 'よくお得' when p.benefit_price <= mp.price then '少しお得' else 'お得ではない' end as kind, count(*)
-- from bts_app.plans p join bts_app.market_prices mp on mp.plan_id = p.id and mp.is_representative and mp.source = 'rakuten_api'
-- group by 1 order by 1;
