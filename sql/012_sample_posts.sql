-- 見本の口コミ（is_sample = true）を、全施設（宿・レジャー・食事）について作り直す
-- 001〜011 と prices.update・sql/010 のあとに実行する。何度実行しても同じ結果になる（見本の口コミは消して入れ直す）
-- sql/005 で入れた見本の口コミ（68件）も消して作り直す。利用者が画面から書いた口コミ（is_sample = false）は消さない
--
-- 作り方（乱数は使わず、施設IDと番号から毎回同じ値を作る）
-- - 件数: 施設ごとに 0件（約1割）・2〜6件（約8割）・10〜12件（約1割。社員の口コミの比重が最大になる件数）
-- - 投稿者: 見本の利用者（sql/003 の6人）から選ぶ。家族構成をコメントの書き出しに使う
-- - 総合の星: 宿は楽天の★、レジャー・食事は4.2を基準に、前後に散らす
-- - お得感: 施設のいちばんお得な料金プランの割引率（市場価格があればそれと、なければ定価と比べる）で決める
--     15%以上 → 主に4〜5／0〜15% → 主に3〜4／市場価格より高い → 1〜3（満足の割合が5割を下回り、ランキングで減点される）
-- - 項目別の星: 宿はすべて、レジャーはサービス・立地・設備、食事はサービス・立地・食事（sql/005 と同じ）
-- - コメント: カテゴリ・星・お得感に合った文を組み合わせる

begin;

-- ① 施設ID と番号から、0〜999 の決まった数を作る
create or replace function pg_temp.h(t text) returns int language sql immutable as $$
  select (('x' || lpad(substr(md5(t), 1, 8), 16, '0'))::bit(64)::bigint % 1000)::int
$$;

-- ② 見本の口コミを消す
delete from bts_app.posts where is_sample;

-- ③ 施設ごとの割引率（いちばんお得な料金プラン）と件数
with tenant as (
  select id from bts_app.tenants where code = 'sample'
),
plan_rate as (
  select p.menu_id, mp.price is not null as has_market,
         1 - p.benefit_price::numeric / nullif(coalesce(mp.price, p.list_price), 0) as rate
  from bts_app.plans p
  left join bts_app.market_prices mp on mp.plan_id = p.id and mp.is_representative
  where p.deleted_at is null
),
facility as (
  -- 市場価格のある料金プランがあれば、その中でいちばんお得なもの。なければ定価と比べたもの（画面のお得額と同じ考え方）
  select m.id, m.category, coalesce(m.external_rating, 4.2) as base,
         coalesce(max(pr.rate) filter (where pr.has_market), max(pr.rate)) as rate,
         case when pg_temp.h(m.id::text || 'n') < 100 then 0
              when pg_temp.h(m.id::text || 'n') < 900 then 2 + pg_temp.h(m.id::text || 'k') % 5
              else 10 + pg_temp.h(m.id::text || 'k') % 3 end as n
  from bts_app.menus m
  join tenant t on t.id = m.tenant_id
  left join plan_rate pr on pr.menu_id = m.id
  where m.deleted_at is null
  group by m.id, m.category, m.external_rating
),
sample_users as (
  select u.id, u.family, row_number() over (order by u.email) - 1 as idx, count(*) over () as cnt
  from bts_app.users u join tenant t on t.id = u.tenant_id
  where u.deleted_at is null and u.email like '%@example.com'
),
-- ④ 1件ずつの値を決める
draft as (
  select f.id as menu_id, f.category, f.rate, i,
         pg_temp.h(f.id::text || i) as r1, pg_temp.h(f.id::text || i || 'b') as r2, pg_temp.h(f.id::text || i || 'c') as r3,
         greatest(1, least(5, round(f.base + (pg_temp.h(f.id::text || i || 'r') % 3 - 1) * 0.8)))::int as rating
  from facility f, generate_series(1, f.n) as i
),
post as (
  select d.*, u.id as user_id, u.family,
         case when d.rate is null then 4
              when d.rate >= 0.15 then case when d.r2 < 100 then 3 when d.r2 < 550 then 4 else 5 end
              when d.rate > 0 then case when d.r2 < 150 then 2 when d.r2 < 600 then 3 else 4 end
              else 1 + d.r2 % 3 end as deal,
         date '2026-04-01' + (d.r1 % 170) as used_at
  from draft d
  join sample_users u on u.idx = d.r3 % u.cnt
)
insert into bts_app.posts (tenant_id, user_id, menu_id, used_at, rating,
  rating_service, rating_location, rating_room, rating_equipment, rating_bath, rating_meal,
  deal_rating, comment, is_sample, created_at)
select (select id from tenant), p.user_id, p.menu_id, p.used_at, p.rating,
  -- 項目別の星: 総合の星の前後（カテゴリに合わない項目は空）
  greatest(1, least(5, p.rating + (p.r1 / 7) % 3 - 1)),
  greatest(1, least(5, p.rating + (p.r2 / 7) % 3 - 1)),
  case when p.category = 'stay' then greatest(1, least(5, p.rating + (p.r3 / 7) % 3 - 1)) end,
  case when p.category in ('stay', 'leisure') then greatest(1, least(5, p.rating + (p.r1 / 11) % 3 - 1)) end,
  case when p.category = 'stay' then greatest(1, least(5, p.rating + (p.r2 / 11) % 3 - 1)) end,
  case when p.category in ('stay', 'meal') then greatest(1, least(5, p.rating + (p.r3 / 11) % 3 - 1)) end,
  p.deal,
  -- コメント: 家族構成 ＋ 感想 ＋ お得感
  (case when p.family like '子あり%' then '子ども連れで利用しました。'
        when p.family = '夫婦' then '夫婦で利用しました。'
        when p.family = '単身' then '一人で利用しました。'
        else '家族で利用しました。' end)
  || (case
        when p.rating <= 2 then (array['混雑していて、ゆっくり過ごせませんでした。', '期待していたほどではありませんでした。',
                                       '設備が少し古く感じました。'])[1 + p.r1 % 3]
        when p.category = 'stay' then (array['お風呂が広く、ゆっくりできました。', '食事の量が多く満足です。',
                                             'スタッフの対応が丁寧で、過ごしやすかったです。', '部屋からの眺めが良く、また来たいと思いました。',
                                             '部屋が清潔で快適でした。', '駅から近く、移動が楽でした。'])[1 + p.r1 % 6]
        when p.category = 'leisure' then (array['見どころが多く、時間が足りないくらいでした。', '雨の日でも楽しめて助かりました。',
                                                'スタッフの案内が分かりやすかったです。', '景色が良く、写真をたくさん撮りました。',
                                                '思っていたより空いていて、ゆっくり回れました。'])[1 + p.r1 % 5]
        else (array['名物の料理がおいしく、量も十分でした。', 'お昼どきは少し並びましたが、待つ価値がありました。',
                    '地元の味を楽しめました。', 'お店の方の対応が気持ちよかったです。'])[1 + p.r1 % 4]
      end)
  || (case
        when p.deal >= 4 and p.category = 'stay' then (array['一般の予約サイトより安く泊まれて満足です。',
                                                             '福利厚生の料金でこの内容なら十分です。'])[1 + p.r2 % 2]
        when p.deal >= 4 then '福利厚生の割引で、かなりお得に利用できました。'
        when p.deal = 3 then 'お得感はそこそこでした。'
        when p.category = 'stay' then '時期によっては一般の予約サイトの方が安く、お得感は少なめでした。'
        else '割引はありましたが、お得感は少なめでした。'
      end),
  true,
  ((p.used_at + 1 + p.r3 % 10)::timestamp + time '12:00') at time zone 'Asia/Tokyo'
from post p;

commit;

-- ⑤ 確認用: カテゴリごとの件数と、お得感の満足（4以上）の割合
-- select m.category, count(*) as posts, round(avg((p.deal_rating >= 4)::int) * 100) as deal_satisfied_pct
-- from bts_app.posts p join bts_app.menus m on m.id = p.menu_id where p.is_sample group by m.category;
