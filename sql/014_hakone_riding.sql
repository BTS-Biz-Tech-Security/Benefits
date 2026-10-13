-- 箱根エリアに乗馬の施設を1件追加する（デモの入力例「箱根・乗馬・温泉」で、1日プランに乗馬が入るようにするため）
-- 001〜012 のあとに実行する。何度実行しても同じ結果になる（同じテナントに同じ名前の施設・プランがあれば入れない）
-- 施設は 2026-10-13 にWebで調べた実在の乗馬クラブ。所在地は御殿場市（箱根町の西隣）だが、エリアは箱根にする
-- 定価は体験乗馬の事前予約料金4,200円＋ヘルメット・保険1,250円。福利厚生価格は定価の約2割引のテスト用の値
-- 体験できるのは小学4年生以上（掲載サイトの記載）。年齢の条件は紹介文に書く
-- 実行後に sql/012 を実行し直すと、この施設にも見本の口コミが入る

begin;

-- ① 施設
insert into bts_app.menus (tenant_id, area_id, name, category, address, description, usage_limit, family_scope, cancel_policy, matched, content_updated_at, tags)
select t.id, a.id, v.name, v.category, v.address, v.description, v.usage_limit, v.family_scope, '前日まで', false, '2026-10-13', v.tags
from (values
  ('hakone', '乗馬クラブ ニューシーズン', 'leisure', '静岡県御殿場市新橋1213',
   '箱根の西隣、御殿場の乗馬クラブ。インストラクターの指導で初めてでも体験乗馬ができる（小学4年生以上・事前予約制）。',
   '年3回まで', '本人と2親等まで', array['乗馬', '体験', '子ども', '家族向け', '自然'])
) as v(area_code, name, category, address, description, usage_limit, family_scope, tags)
join bts_app.tenants t on t.code = 'sample'
join bts_app.areas a on a.code = v.area_code and a.tenant_id is null
where not exists (select 1 from bts_app.menus m where m.tenant_id = t.id and m.name = v.name and m.deleted_at is null);

-- ② 料金プラン（1名）
insert into bts_app.plans (menu_id, name, adults, children, nights, list_price, benefit_price, coupon_code, member_url)
select m.id, v.plan_name, 1, 0, 1, v.list_price, v.benefit_price, v.coupon_code, v.member_url
from (values
  ('乗馬クラブ ニューシーズン', '体験乗馬（1名・ヘルメット・保険込み）', 5450, 4400, 'L-HAKONE-RIDING', 'https://example.com/member/l-hakone-riding')
) as v(menu_name, plan_name, list_price, benefit_price, coupon_code, member_url)
join bts_app.tenants t on t.code = 'sample'
join bts_app.menus m on m.tenant_id = t.id and m.name = v.menu_name and m.deleted_at is null
where not exists (select 1 from bts_app.plans p where p.menu_id = m.id and p.name = v.plan_name and p.deleted_at is null);

commit;

-- ③ 確認用: 箱根エリアのレジャー施設（乗馬クラブ ニューシーズンが出れば成功）
-- select m.name, m.tags from bts_app.menus m join bts_app.areas a on a.id = m.area_id
-- where a.code = 'hakone' and m.category = 'leisure' and m.deleted_at is null order by m.name;
