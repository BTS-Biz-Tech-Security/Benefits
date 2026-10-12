-- 代表的なレジャー（ゴルフ・スキー・マリンスポーツ・デイキャンプ・遊覧船・ものづくり体験）を3件ずつ追加する（2026-10-12 にWebで調べた実在の施設）
-- 011 のあとに実行する。何度実行しても同じ結果になる（同じテナントに同じ名前の施設があれば入れない）
-- 料金プランは大人1名分。定価は公式サイト・観光協会・予約サイトで調べた料金（ゴルフは予約サイトの土日の最安値、スキーはシーズン中の1日券）。
-- 福利厚生価格は定価の10〜30%引き（施設ごとに決まった割合）のテスト用の値
-- スキー場は冬季のみ、ゴルフ場・キャンプ場には冬季休業のところがある（施設の説明文には書いていない）

begin;

-- ① 施設
insert into bts_app.menus (tenant_id, area_id, name, category, address, description, usage_limit, family_scope, cancel_policy, matched, content_updated_at, tags)
select t.id, a.id, v.name, 'leisure', v.address, v.description, '年3回まで', '本人と2親等まで', '当日可', false, '2026-10-12', v.tags
from (values
  ('hakone', '箱根園ゴルフ場', '神奈川県足柄下郡箱根町元箱根138', '芦ノ湖と富士山を望む18ホールの山岳コース。全組セルフプレーで乗用カートを利用できる。', array['ゴルフ', 'スポーツ', '絶景', '湖']),
  ('karuizawa', '晴山ゴルフ場', '長野県北佐久郡軽井沢町軽井沢', '軽井沢の林間に広がるプリンス系の18ホール。1961年開場で、冬期はクローズする。', array['ゴルフ', 'スポーツ', '自然']),
  ('nasu', '那須カントリークラブ', '栃木県那須郡那須町寺子乙677-28', '那須高原に広がるフラットな18ホールのリゾートコース。セルフプレーのプランがある。', array['ゴルフ', 'スポーツ', '自然']),
  ('zao', '蔵王温泉スキー場', '山形県山形市蔵王温泉708-1', '蔵王連峰に広がる大規模スキー場。ロープウェイとリフトで多彩なコースを滑れ、樹氷でも知られる。', array['スキー', 'スポーツ', '絶景', '自然']),
  ('furano', '富良野スキー場', '北海道富良野市中御料', '富良野盆地を見下ろすパウダースノーのスキー場。北の峰と富良野の2ゾーンで構成される。', array['スキー', 'スポーツ', '絶景', '自然']),
  ('kusatsu', '草津温泉スキー場', '群馬県吾妻郡草津町大字草津字白根国有林158林班', '草津白根山麓にある温泉街から近いスキー場。初心者向けから上級者向けまでコースがそろう。', array['スキー', 'スポーツ', '自然', '家族向け']),
  ('fujigoko', '浩庵キャンプ場', '山梨県南巨摩郡身延町中之倉2926', '本栖湖の湖畔にあるキャンプ場。富士山を望みながら日帰りのデイキャンプができる。', array['キャンプ', '自然', '湖', '絶景']),
  ('nasu', '那須高原アカルパ', '栃木県那須郡那須町高久丙2993-1', '那須高原の林間にあるオートキャンプ場。食材や道具を持ち込んで日帰りのデイキャンプができる。', array['キャンプ', '自然', '家族向け', '子ども']),
  ('karuizawa', 'ライジング・フィールド軽井沢', '長野県北佐久郡軽井沢町長倉山国有林2129', '軽井沢の国有林内にあるキャンプ場。BBQコーナーや森のアスレチックを日帰りで利用できる。', array['キャンプ', '自然', '家族向け', '体験']),
  ('okinawa', 'マリンクラブUMI', '沖縄県国頭郡恩納村山田2668-1', '恩納村にあるマリンショップ。ボートで向かう青の洞窟の体験ダイビングやシュノーケルを実施。', array['マリンスポーツ', '体験', '海', '自然']),
  ('ishigaki', '石垣島 ADVENTURE PiPi', '沖縄県石垣市美崎町1（石垣港離島ターミナル集合）', '石垣島の青の洞窟でのシュノーケリングと川平湾観光を組み合わせたツアーを催行する事業者。', array['マリンスポーツ', '体験', '海', '絶景']),
  ('izu', '伊豆海洋公園ダイビングセンター', '静岡県伊東市富戸841-1', '伊東市城ヶ崎海岸にあるダイビング施設。ビーチダイビングやスノーケリングツアーを実施。', array['マリンスポーツ', '体験', '海', '自然']),
  ('hakone', '箱根海賊船', '神奈川県足柄下郡箱根町元箱根164（桃源台港）', '芦ノ湖の桃源台港・元箱根港・箱根町港を結ぶ海賊船型の遊覧船。湖上から富士山を望める。', array['遊覧船', '湖', '絶景', '観光', '家族向け']),
  ('sendai', '松島島巡り観光船', '宮城県宮城郡松島町松島字町内85', '松島海岸の中央観光桟橋から松島湾の島々を約50分で巡る遊覧船（仁王丸コース）。', array['遊覧船', '海', '絶景', '観光']),
  ('yokohama', 'シーバス', '神奈川県横浜市神奈川区金港町1-10 横浜ベイクォーター2F（横浜駅東口乗り場）', '横浜駅東口からみなとみらい・赤レンガ倉庫・山下公園を結ぶ水上バス。港の景色を楽しめる。', array['遊覧船', '海', '観光', '絶景']),
  ('kanazawa', '金箔屋さくだ 本店', '石川県金沢市東山1-3-27', 'ひがし茶屋街近くの金箔店。箸や小皿などに金箔を貼る体験ができる工房を併設。', array['ものづくり', '体験', '雨の日', '歴史', '観光']),
  ('kyoto', '京友禅体験工房 丸益西村屋', '京都府京都市中京区小川通御池南入ル壺屋町446', '京町家で型紙を使った京友禅の染色を体験できる工房。ハンカチなどを染められる。', array['ものづくり', '体験', '雨の日', '歴史']),
  ('takayama', '飛騨高山思い出体験館 飛騨の里店', '岐阜県高山市上岡本町1-436', '飛騨の里近くの体験施設。さるぼぼ作りや手焼きせんべい、マイ箸作りができる。', array['ものづくり', '体験', '雨の日', '子ども', '家族向け'])
) as v(area_code, name, address, description, tags)
join bts_app.tenants t on t.code = 'sample'
join bts_app.areas a on a.code = v.area_code and a.tenant_id is null
where not exists (select 1 from bts_app.menus m where m.tenant_id = t.id and m.name = v.name and m.deleted_at is null);

-- ② 料金プラン（大人1名）。同じ施設に同じ名前のプランがあれば入れない
insert into bts_app.plans (menu_id, name, adults, children, nights, list_price, benefit_price, coupon_code, member_url)
select m.id, v.plan_name, 1, 0, 1, v.list_price, v.benefit_price, v.coupon_code, v.member_url
from (values
  ('箱根園ゴルフ場', 'プレー（大人1名・土日・セルフ乗用カート）', 12910, 10270, 'L-HAKONE-X01', 'https://example.com/member/l-hakone-x01'),
  ('晴山ゴルフ場', 'プレー（大人1名・土日）', 29878, 24600, 'L-KARUIZAWA-X02', 'https://example.com/member/l-karuizawa-x02'),
  ('那須カントリークラブ', 'プレー（大人1名・土日・セルフ）', 9400, 7760, 'L-NASU-X03', 'https://example.com/member/l-nasu-x03'),
  ('蔵王温泉スキー場', '1日リフト券（大人1名）', 8000, 6430, 'L-ZAO-X04', 'https://example.com/member/l-zao-x04'),
  ('富良野スキー場', '1日リフト券（大人1名）', 9000, 6730, 'L-FURANO-X05', 'https://example.com/member/l-furano-x05'),
  ('草津温泉スキー場', '1日リフト券（大人1名）', 6000, 4330, 'L-KUSATSU-X06', 'https://example.com/member/l-kusatsu-x06'),
  ('浩庵キャンプ場', 'デイキャンプ（大人1名）', 500, 380, 'L-FUJIGOKO-X07', 'https://example.com/member/l-fujigoko-x07'),
  ('那須高原アカルパ', 'デイキャンプ（大人1名）', 500, 430, 'L-NASU-X08', 'https://example.com/member/l-nasu-x08'),
  ('ライジング・フィールド軽井沢', 'BBQ（大人1名・2時間）', 1000, 830, 'L-KARUIZAWA-X09', 'https://example.com/member/l-karuizawa-x09'),
  ('マリンクラブUMI', '青の洞窟 体験ダイビング（大人1名）', 9500, 7120, 'L-OKINAWA-X10', 'https://example.com/member/l-okinawa-x10'),
  ('石垣島 ADVENTURE PiPi', '青の洞窟シュノーケリング＆川平湾 1日ツアー（大人1名）', 9800, 8310, 'L-ISHIGAKI-X11', 'https://example.com/member/l-ishigaki-x11'),
  ('伊豆海洋公園ダイビングセンター', 'スノーケリングツアー（大人1名）', 8250, 6190, 'L-IZU-X12', 'https://example.com/member/l-izu-x12'),
  ('箱根海賊船', '乗船 桃源台港〜箱根町港 片道（大人1名・普通船室）', 1700, 1480, 'L-HAKONE-X13', 'https://example.com/member/l-hakone-x13'),
  ('松島島巡り観光船', '仁王丸コース 乗船（大人1名）', 1500, 1270, 'L-SENDAI-X14', 'https://example.com/member/l-sendai-x14'),
  ('シーバス', '乗船 横浜駅東口〜山下公園 片道（大人1名）', 1000, 830, 'L-YOKOHAMA-X15', 'https://example.com/member/l-yokohama-x15'),
  ('金箔屋さくだ 本店', '金箔貼り体験（大人1名）', 1760, 1490, 'L-KANAZAWA-X16', 'https://example.com/member/l-kanazawa-x16'),
  ('京友禅体験工房 丸益西村屋', '友禅染体験 ハンカチ小（大人1名）', 1600, 1280, 'L-KYOTO-X17', 'https://example.com/member/l-kyoto-x17'),
  ('飛騨高山思い出体験館 飛騨の里店', 'さるぼぼづくり体験（1名）', 2900, 2160, 'L-TAKAYAMA-X18', 'https://example.com/member/l-takayama-x18')
) as v(menu_name, plan_name, list_price, benefit_price, coupon_code, member_url)
join bts_app.tenants t on t.code = 'sample'
join bts_app.menus m on m.tenant_id = t.id and m.name = v.menu_name and m.deleted_at is null
where not exists (select 1 from bts_app.plans p where p.menu_id = m.id and p.name = v.plan_name and p.deleted_at is null);

commit;

-- ③ 確認用: 追加した種類ごとの数（各3件なら成功）
-- select t as tag, count(*) from bts_app.menus m, unnest(m.tags) t
-- where t in ('ゴルフ', 'スキー', 'マリンスポーツ', 'キャンプ', '遊覧船', 'ものづくり') and m.deleted_at is null group by t;
