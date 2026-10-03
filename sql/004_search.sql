-- 検索の強化（第8回MTGのハイブリッド検索）。タグと、意味の近さで引くためのベクトルを施設に持たせる
-- 001・002 のあとに実行する（003 より先）。003 を先に実行済みのDBでも、⑤で見本データにタグが付く。何度実行しても同じ結果になる

-- ① タグ（検索ワードの照合先）。施設ごとに文字列の配列で持つ
alter table bts_app.menus add column if not exists tags text[] not null default '{}';

-- ② ベクトル検索の拡張機能（pgvector）。Supabase の推奨どおり extensions スキーマに入れる
create extension if not exists vector with schema extensions;

-- ③ 施設の説明文・タグをベクトルにしたもの。seed/embed_menus.py が入れる
--    次元数は埋め込みモデル text-embedding-3-small に合わせる
alter table bts_app.menus add column if not exists embedding extensions.vector(1536);

-- ④ 検索文のベクトルに近い施設を、近い順に返す。similarity は 1 に近いほど意味が近い
create or replace function bts_app.match_menus(query_embedding extensions.vector(1536), p_tenant_id uuid, match_count int default 50)
returns table (menu_id uuid, similarity float)
language sql stable
set search_path = bts_app, extensions, public
as $$
  select m.id, 1 - (m.embedding <=> query_embedding)
  from bts_app.menus m
  where m.tenant_id = p_tenant_id and m.deleted_at is null and m.embedding is not null
  order by m.embedding <=> query_embedding
  limit match_count
$$;

grant execute on function bts_app.match_menus(extensions.vector, uuid, int) to anon, authenticated;

-- ⑤ 見本データの施設にタグを付ける（seed/menus.csv の tags 列と同じ内容）
update bts_app.menus m set tags = v.tags
from (values
  ('箱根湯本温泉 天成園', array['温泉', '露天風呂', '庭園', '駅近']),
  ('箱根ホテル小涌園', array['温泉', '家族向け', '子ども', 'プール', 'テーマパーク']),
  ('箱根 芦ノ湖 はなをり', array['温泉', '足湯', '湖', '絶景', '大浴場']),
  ('熱海 ニューフジヤホテル', array['温泉', '大浴場', '展望風呂', '駅近']),
  ('熱海後楽園ホテル', array['温泉', '海', 'オーシャンビュー', 'リゾート']),
  ('軽井沢プリンスホテル ウエスト', array['買い物', 'アウトレット', '駅近', '高原']),
  ('ホテルブレストンコート', array['森', '自然', '高原', '静か']),
  ('京都タワーホテル', array['駅近', '観光', '街歩き']),
  ('ホテルグランヴィア京都', array['駅直結', '観光', '街歩き']),
  ('ANAインターコンチネンタル万座ビーチリゾート', array['海', 'ビーチ', 'リゾート', 'マリンスポーツ', '子ども']),
  ('ルネッサンス リゾート オキナワ', array['海', 'ビーチ', 'マリンスポーツ', '子ども', 'プール']),
  ('ホテル日航アリビラ', array['海', 'ビーチ', 'リゾート', '静か']),
  ('箱根小涌園ユネッサン', array['温泉', 'プール', '水着', 'テーマパーク', '子ども', '雨の日']),
  ('箱根園水族館', array['水族館', '湖', '子ども', '雨の日']),
  ('熱海城', array['絶景', '観光', '海']),
  ('京都水族館', array['水族館', '公園', '子ども', '雨の日']),
  ('沖縄美ら海水族館', array['水族館', '海', '子ども', '絶景']),
  ('箱根 自然薯の森 山薬', array['和食', '郷土料理', 'ランチ']),
  ('熱海 まぐろや', array['和食', '海鮮', 'ランチ', '駅近']),
  ('京都 ぎをん徳屋', array['甘味', '和菓子', 'カフェ'])
) as v(name, tags)
join bts_app.tenants t on t.code = 'sample'
where m.tenant_id = t.id and m.name = v.name;
