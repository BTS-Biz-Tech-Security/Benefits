-- 施設に外部サイト（楽天トラベル）の評価を持たせる（第10回MTGのランキング「品質・信頼」に使う）
-- 001〜003 のあとに実行する。何度実行しても同じ結果になる

-- ① 外部の評価（星の平均 0〜5）と口コミ件数、その取得元。宿ごとに1つの値なので、日付ごとの価格（market_prices）とは分ける
alter table bts_app.menus add column if not exists external_rating numeric(2, 1) check (external_rating between 0 and 5);
alter table bts_app.menus add column if not exists external_review_count int check (external_review_count >= 0);
alter table bts_app.menus add column if not exists external_rating_source text;  -- 'rakuten_api' / 'dummy'

-- ② 楽天から取れるまでの仮の値（宿だけ）。prices/update.py が楽天から取れたら上書きする
update bts_app.menus m set external_rating = v.rating, external_review_count = v.cnt, external_rating_source = 'dummy'
from (values
  ('箱根湯本温泉 天成園', 4.3, 2850),
  ('箱根ホテル小涌園', 4.1, 1920),
  ('箱根 芦ノ湖 はなをり', 4.6, 1340),
  ('熱海 ニューフジヤホテル', 3.8, 2210),
  ('熱海後楽園ホテル', 4.4, 3050),
  ('軽井沢プリンスホテル ウエスト', 4.2, 1680),
  ('ホテルブレストンコート', 4.5, 980),
  ('京都タワーホテル', 4.0, 2470),
  ('ホテルグランヴィア京都', 4.4, 3120),
  ('ANAインターコンチネンタル万座ビーチリゾート', 4.5, 1760),
  ('ルネッサンス リゾート オキナワ', 4.3, 1450),
  ('ホテル日航アリビラ', 4.6, 1210)
) as v(name, rating, cnt)
join bts_app.tenants t on t.code = 'sample'
where m.tenant_id = t.id and m.name = v.name
  and coalesce(m.external_rating_source, 'dummy') = 'dummy';
