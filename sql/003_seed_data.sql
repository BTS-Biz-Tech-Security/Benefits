-- 見本データ（施設・プラン・利用者・支出額・周辺情報）。seed/ のCSVと同じ内容
-- 001_schema.sql・002_seed_tenant.sql・004_search.sql のあとに実行する。何度実行しても同じ行は増えない

-- 施設（menus）
insert into bts_app.menus (tenant_id, area_id, name, category, address, description, usage_limit, family_scope, cancel_policy, hotel_ref, matched, content_updated_at, tags)
select t.id, a.id, v.name, v.category, v.address, v.description, v.usage_limit, v.family_scope, v.cancel_policy, v.hotel_ref, v.hotel_ref is not null, v.content_updated_at::date, v.tags
from (values
  ('hakone', '箱根湯本温泉 天成園', 'stay', '神奈川県足柄下郡箱根町湯本682', '庭園露天風呂と天然温泉。箱根湯本駅から徒歩12分', '年2回まで', '本人と2親等まで', '3日前まで無料', 'H-TENSEI', '2026-09-01', array['温泉', '露天風呂', '庭園', '駅近']),
  ('hakone', '箱根ホテル小涌園', 'stay', '神奈川県足柄下郡箱根町二ノ平1297', '箱根小涌園ユネッサンに隣接。家族向け', '年2回まで', '本人と2親等まで', '3日前まで無料', 'H-KOWAKIEN', '2026-09-02', array['温泉', '家族向け', '子ども', 'プール', 'テーマパーク']),
  ('hakone', '箱根 芦ノ湖 はなをり', 'stay', '神奈川県足柄下郡箱根町元箱根桃源台160', '芦ノ湖を望む足湯テラスと大浴場', '年2回まで', '本人と2親等まで', '7日前まで無料', 'H-HANAORI', '2026-09-03', array['温泉', '足湯', '湖', '絶景', '大浴場']),
  ('atami', '熱海 ニューフジヤホテル', 'stay', '静岡県熱海市銀座町1-16', '熱海駅から徒歩約12分。大浴場と展望風呂', '年2回まで', '本人と2親等まで', '3日前まで無料', 'H-NEWFUJIYA', '2026-09-04', array['温泉', '大浴場', '展望風呂', '駅近']),
  ('atami', '熱海後楽園ホテル', 'stay', '静岡県熱海市和田浜南町10-1', '相模湾を望むオーシャンビューの温泉リゾート', '年2回まで', '本人と2親等まで', '7日前まで無料', 'H-KORAKUEN', '2026-09-05', array['温泉', '海', 'オーシャンビュー', 'リゾート']),
  ('karuizawa', '軽井沢プリンスホテル ウエスト', 'stay', '長野県北佐久郡軽井沢町軽井沢', '軽井沢駅南口。ショッピングプラザに隣接', '年1回まで', '本人と2親等まで', '7日前まで無料', 'H-KPRINCE', '2026-09-06', array['買い物', 'アウトレット', '駅近', '高原']),
  ('karuizawa', 'ホテルブレストンコート', 'stay', '長野県北佐久郡軽井沢町星野', '星野エリアの森の中のホテル', '年1回まで', '本人と配偶者', '14日前まで無料', 'H-BLESTON', '2026-09-07', array['森', '自然', '高原', '静か']),
  ('kyoto', '京都タワーホテル', 'stay', '京都府京都市下京区烏丸通七条下ル東塩小路町721-1', '京都駅烏丸口すぐ', '年2回まで', '本人と2親等まで', '3日前まで無料', 'H-KTOWER', '2026-09-08', array['駅近', '観光', '街歩き']),
  ('kyoto', 'ホテルグランヴィア京都', 'stay', '京都府京都市下京区烏丸通塩小路下る', '京都駅ビル内。改札から直結', '年2回まで', '本人と2親等まで', '3日前まで無料', 'H-GRANVIA', '2026-09-09', array['駅直結', '観光', '街歩き']),
  ('okinawa', 'ANAインターコンチネンタル万座ビーチリゾート', 'stay', '沖縄県国頭郡恩納村瀬良垣2260', '万座ビーチに面したリゾート', '年1回まで', '本人と2親等まで', '14日前まで無料', 'H-MANZA', '2026-09-10', array['海', 'ビーチ', 'リゾート', 'マリンスポーツ', '子ども']),
  ('okinawa', 'ルネッサンス リゾート オキナワ', 'stay', '沖縄県国頭郡恩納村山田3425-2', 'マリンアクティビティが充実', '年1回まで', '本人と2親等まで', '14日前まで無料', 'H-RENAISSANCE', '2026-09-01', array['海', 'ビーチ', 'マリンスポーツ', '子ども', 'プール']),
  ('okinawa', 'ホテル日航アリビラ', 'stay', '沖縄県中頭郡読谷村儀間600', '読谷村のビーチリゾート', '年1回まで', '本人と2親等まで', '14日前まで無料', 'H-ALIVILA', '2026-09-02', array['海', 'ビーチ', 'リゾート', '静か']),
  ('hakone', '箱根小涌園ユネッサン', 'leisure', '神奈川県足柄下郡箱根町二ノ平1297', '水着で入る温泉テーマパーク', '年3回まで', '本人と2親等まで', '当日可', null, '2026-09-03', array['温泉', 'プール', '水着', 'テーマパーク', '子ども', '雨の日']),
  ('hakone', '箱根園水族館', 'leisure', '神奈川県足柄下郡箱根町元箱根139', '芦ノ湖畔の水族館', '年3回まで', '本人と2親等まで', '当日可', null, '2026-09-04', array['水族館', '湖', '子ども', '雨の日']),
  ('atami', '熱海城', 'leisure', '静岡県熱海市熱海1993', '熱海市街と相模湾を一望', '年3回まで', '本人と2親等まで', '当日可', null, '2026-09-05', array['絶景', '観光', '海']),
  ('kyoto', '京都水族館', 'leisure', '京都府京都市下京区観喜寺町35-1', '梅小路公園内の水族館', '年3回まで', '本人と2親等まで', '当日可', null, '2026-09-06', array['水族館', '公園', '子ども', '雨の日']),
  ('okinawa', '沖縄美ら海水族館', 'leisure', '沖縄県国頭郡本部町石川424', '海洋博公園内の水族館', '年3回まで', '本人と2親等まで', '当日可', null, '2026-09-07', array['水族館', '海', '子ども', '絶景']),
  ('hakone', '箱根 自然薯の森 山薬', 'meal', '神奈川県足柄下郡箱根町宮ノ下224', '自然薯料理の店', '制限なし', '本人と同行者', '当日可', null, '2026-09-08', array['和食', '郷土料理', 'ランチ']),
  ('atami', '熱海 まぐろや', 'meal', '静岡県熱海市田原本町7-2', '駅前のまぐろ料理店', '制限なし', '本人と同行者', '当日可', null, '2026-09-09', array['和食', '海鮮', 'ランチ', '駅近']),
  ('kyoto', '京都 ぎをん徳屋', 'meal', '京都府京都市東山区祇園町南側570-127', 'わらび餅の甘味処', '制限なし', '本人と同行者', '当日可', null, '2026-09-10', array['甘味', '和菓子', 'カフェ'])
) as v(area_code, name, category, address, description, usage_limit, family_scope, cancel_policy, hotel_ref, content_updated_at, tags)
join bts_app.tenants t on t.code = 'sample'
left join bts_app.areas a on a.code = v.area_code and a.tenant_id is null
where not exists (select 1 from bts_app.menus m where m.tenant_id = t.id and m.name = v.name);

-- プラン（plans）。施設は名前で探す
insert into bts_app.plans (menu_id, name, room_type, meal, grade, adults, children, nights, list_price, benefit_price, coupon_code, member_url)
select m.id, v.name, v.room_type, v.meal, v.grade, v.adults, v.children, v.nights, v.list_price, v.benefit_price, v.coupon_code, v.member_url
from (values
  ('箱根湯本温泉 天成園', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 26000, 15600, 'H-TENSEI-1', 'https://example.com/member/h-tensei'),
  ('箱根湯本温泉 天成園', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 38000, 28500, 'H-TENSEI-2', 'https://example.com/member/h-tensei'),
  ('箱根湯本温泉 天成園', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 18000, 10800, 'H-TENSEI-3', 'https://example.com/member/h-tensei'),
  ('箱根ホテル小涌園', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 18000, 9900, 'H-KOWAKIEN-1', 'https://example.com/member/h-kowakien'),
  ('箱根ホテル小涌園', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 30000, 21000, 'H-KOWAKIEN-2', 'https://example.com/member/h-kowakien'),
  ('箱根ホテル小涌園', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 10000, 6000, 'H-KOWAKIEN-3', 'https://example.com/member/h-kowakien'),
  ('箱根 芦ノ湖 はなをり', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 36000, 21600, 'H-HANAORI-1', 'https://example.com/member/h-hanaori'),
  ('箱根 芦ノ湖 はなをり', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 48000, 28800, 'H-HANAORI-2', 'https://example.com/member/h-hanaori'),
  ('箱根 芦ノ湖 はなをり', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 28000, 16800, 'H-HANAORI-3', 'https://example.com/member/h-hanaori'),
  ('熱海 ニューフジヤホテル', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 30000, 21000, 'H-NEWFUJIYA-1', 'https://example.com/member/h-newfujiya'),
  ('熱海 ニューフジヤホテル', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 42000, 25200, 'H-NEWFUJIYA-2', 'https://example.com/member/h-newfujiya'),
  ('熱海 ニューフジヤホテル', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 22000, 15400, 'H-NEWFUJIYA-3', 'https://example.com/member/h-newfujiya'),
  ('熱海後楽園ホテル', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 18000, 12600, 'H-KORAKUEN-1', 'https://example.com/member/h-korakuen'),
  ('熱海後楽園ホテル', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 30000, 18000, 'H-KORAKUEN-2', 'https://example.com/member/h-korakuen'),
  ('熱海後楽園ホテル', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 10000, 6000, 'H-KORAKUEN-3', 'https://example.com/member/h-korakuen'),
  ('軽井沢プリンスホテル ウエスト', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 22000, 12100, 'H-KPRINCE-1', 'https://example.com/member/h-kprince'),
  ('軽井沢プリンスホテル ウエスト', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 34000, 25500, 'H-KPRINCE-2', 'https://example.com/member/h-kprince'),
  ('軽井沢プリンスホテル ウエスト', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 14000, 8400, 'H-KPRINCE-3', 'https://example.com/member/h-kprince'),
  ('ホテルブレストンコート', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 22000, 12100, 'H-BLESTON-1', 'https://example.com/member/h-bleston'),
  ('ホテルブレストンコート', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 34000, 22100, 'H-BLESTON-2', 'https://example.com/member/h-bleston'),
  ('ホテルブレストンコート', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 14000, 11200, 'H-BLESTON-3', 'https://example.com/member/h-bleston'),
  ('京都タワーホテル', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 30000, 18000, 'H-KTOWER-1', 'https://example.com/member/h-ktower'),
  ('京都タワーホテル', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 42000, 25200, 'H-KTOWER-2', 'https://example.com/member/h-ktower'),
  ('京都タワーホテル', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 22000, 17600, 'H-KTOWER-3', 'https://example.com/member/h-ktower'),
  ('ホテルグランヴィア京都', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 36000, 21600, 'H-GRANVIA-1', 'https://example.com/member/h-granvia'),
  ('ホテルグランヴィア京都', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 48000, 28800, 'H-GRANVIA-2', 'https://example.com/member/h-granvia'),
  ('ホテルグランヴィア京都', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 28000, 19600, 'H-GRANVIA-3', 'https://example.com/member/h-granvia'),
  ('ANAインターコンチネンタル万座ビーチリゾート', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 26000, 14300, 'H-MANZA-1', 'https://example.com/member/h-manza'),
  ('ANAインターコンチネンタル万座ビーチリゾート', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 38000, 22800, 'H-MANZA-2', 'https://example.com/member/h-manza'),
  ('ANAインターコンチネンタル万座ビーチリゾート', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 18000, 10800, 'H-MANZA-3', 'https://example.com/member/h-manza'),
  ('ルネッサンス リゾート オキナワ', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 36000, 21600, 'H-RENAISSANCE-1', 'https://example.com/member/h-renaissance'),
  ('ルネッサンス リゾート オキナワ', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 48000, 36000, 'H-RENAISSANCE-2', 'https://example.com/member/h-renaissance'),
  ('ルネッサンス リゾート オキナワ', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 28000, 25200, 'H-RENAISSANCE-3', 'https://example.com/member/h-renaissance'),
  ('ホテル日航アリビラ', 'スタンダード（2食付）', '洋室', '2食付き', 'standard', 2, 0, 1, 26000, 18200, 'H-ALIVILA-1', 'https://example.com/member/h-alivila'),
  ('ホテル日航アリビラ', 'デラックス（2食付）', '和洋室', '2食付き', 'deluxe', 2, 0, 1, 38000, 28500, 'H-ALIVILA-2', 'https://example.com/member/h-alivila'),
  ('ホテル日航アリビラ', '素泊まり', '洋室', 'なし', 'standard', 2, 0, 1, 18000, 14400, 'H-ALIVILA-3', 'https://example.com/member/h-alivila'),
  ('箱根小涌園ユネッサン', '入場（大人1名）', null, null, null, 1, 0, 1, 3500, 2400, 'L-YUNESSUN-1', 'https://example.com/member/l-yunessun'),
  ('箱根園水族館', '入場（大人1名）', null, null, null, 1, 0, 1, 2500, 1800, 'L-HAKONEEN-1', 'https://example.com/member/l-hakoneen'),
  ('熱海城', '入場（大人1名）', null, null, null, 1, 0, 1, 2500, 1800, 'L-ATAMIJO-1', 'https://example.com/member/l-atamijo'),
  ('京都水族館', '入場（大人1名）', null, null, null, 1, 0, 1, 5000, 3500, 'L-KYOTOAQ-1', 'https://example.com/member/l-kyotoaq'),
  ('沖縄美ら海水族館', '入場（大人1名）', null, null, null, 1, 0, 1, 2500, 1800, 'L-CHURAUMI-1', 'https://example.com/member/l-churaumi'),
  ('箱根 自然薯の森 山薬', 'コース（1名）', null, null, null, 1, 0, 1, 3000, 2400, 'M-YAMAGUSURI-1', 'https://example.com/member/m-yamagusuri'),
  ('熱海 まぐろや', 'コース（1名）', null, null, null, 1, 0, 1, 6000, 4800, 'M-MAGUROYA-1', 'https://example.com/member/m-maguroya'),
  ('京都 ぎをん徳屋', 'コース（1名）', null, null, null, 1, 0, 1, 4500, 3600, 'M-TOKUYA-1', 'https://example.com/member/m-tokuya')
) as v(menu_name, name, room_type, meal, grade, adults, children, nights, list_price, benefit_price, coupon_code, member_url)
join bts_app.tenants t on t.code = 'sample'
join bts_app.menus m on m.tenant_id = t.id and m.name = v.menu_name
where not exists (select 1 from bts_app.plans p where p.menu_id = m.id and p.name = v.name);

-- 利用者（users）。auth_id（ログイン用アカウントとの紐づけ）はあとで Table Editor で入れる
insert into bts_app.users (tenant_id, email, name, role, department, family)
select t.id, v.email, v.name, v.role, v.department, v.family
from (values
  ('kinoshita@example.com', '木下 亮', 'employee', '法務', '夫婦'),
  ('tanaka@example.com', '田中 健太', 'employee', '営業', '子あり（小学生）'),
  ('oyama@example.com', '大山 亮太', 'employee', '営業企画', '子あり（未就学）'),
  ('sasaki@example.com', '佐々木 玲奈', 'employee', 'カスタマーサポート', '単身'),
  ('yamamoto@example.com', '山本 直子', 'hr', '人事総務', null),
  ('nakamura@example.com', '中村 誠', 'executive', '経営企画', null)
) as v(email, name, role, department, family)
join bts_app.tenants t on t.code = 'sample'
where not exists (select 1 from bts_app.users x where x.tenant_id = t.id and x.email = v.email);

-- 支出額（spend）
insert into bts_app.spend (tenant_id, period_start, period_end, amount, headcount)
select t.id, v.period_start::date, v.period_end::date, v.amount, v.headcount
from (values
  ('2025-04-01', '2026-03-31', 24000000, 1000),
  ('2026-04-01', '2027-03-31', 24000000, 1020)
) as v(period_start, period_end, amount, headcount)
join bts_app.tenants t on t.code = 'sample'
on conflict (tenant_id, period_start, period_end) do nothing;

-- 周辺情報（spots）。全社共通（tenant_id なし）
insert into bts_app.spots (area_id, kind, name, description, url, source)
select a.id, v.kind, v.name, v.description, v.url, 'seed'
from (values
  ('hakone', 'meal', '箱根 田むら銀かつ亭', '豆腐かつ煮が名物の老舗', 'https://example.com/hakone/ginkatsu'),
  ('hakone', 'meal', '箱根 甘酒茶屋', '江戸時代から続く茶屋。甘酒と力餅', 'https://example.com/hakone/amazake'),
  ('hakone', 'leisure', '箱根彫刻の森美術館', '屋外彫刻と体験型の作品', 'https://example.com/hakone/chokoku'),
  ('hakone', 'leisure', '箱根ロープウェイ', '大涌谷と芦ノ湖を結ぶ', 'https://example.com/hakone/ropeway'),
  ('atami', 'meal', '熱海 囲炉茶屋', '干物と地魚の定食', 'https://example.com/atami/irori'),
  ('atami', 'leisure', '熱海サンビーチ', '市街地に近い砂浜。夜はライトアップ', 'https://example.com/atami/sunbeach'),
  ('atami', 'leisure', 'MOA美術館', '海を見下ろす高台の美術館', 'https://example.com/atami/moa'),
  ('karuizawa', 'meal', '軽井沢 川上庵', 'そばと一品料理', 'https://example.com/karuizawa/kawakamian'),
  ('karuizawa', 'leisure', '旧軽井沢銀座', '土産物と食べ歩きの通り', 'https://example.com/karuizawa/ginza'),
  ('karuizawa', 'leisure', '白糸の滝', '幅70mの滝。夏は涼しい', 'https://example.com/karuizawa/shiraito'),
  ('kyoto', 'meal', '京都 おめん 銀閣寺本店', 'うどんと野菜の薬味', 'https://example.com/kyoto/omen'),
  ('kyoto', 'leisure', '清水寺', '舞台からの眺め。夜間拝観あり', 'https://example.com/kyoto/kiyomizu'),
  ('kyoto', 'leisure', '嵐山 竹林の小径', '早朝が静か', 'https://example.com/kyoto/arashiyama'),
  ('okinawa', 'meal', '沖縄 首里そば', '手打ちの沖縄そば', 'https://example.com/okinawa/shurisoba'),
  ('okinawa', 'leisure', '古宇利大橋', '全長約2kmの橋。ドライブに', 'https://example.com/okinawa/kouri'),
  ('okinawa', 'leisure', '万座毛', '象の鼻の形の断崖', 'https://example.com/okinawa/manzamo')
) as v(area_code, kind, name, description, url)
join bts_app.areas a on a.code = v.area_code and a.tenant_id is null
where not exists (select 1 from bts_app.spots s where s.area_id = a.id and s.name = v.name);
