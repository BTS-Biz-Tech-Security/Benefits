# Benefits
Step2-2 Webアプリ
なかりん（班長）、JP、のむりん

福利厚生検索アプリ（チームBTS）。Streamlit ＋ Supabase（スキーマ bts_app）で作る、福利厚生の施設を市場価格と比べて探せる社内アプリ。

## はじめに
- 手順・担当・各ファイルの説明は、チームLPの「実装ガイド」を参照
- 接続情報は `.streamlit/secrets.toml` に書く（各自のPCにだけ作る。GitHub には上げない）
- サイドバーの「開発用: 利用者を選ぶ」で見本の利用者を選ぶと、ログインした状態で画面を確かめられる（人事の画面は山本さんを選ぶ）。パスワードを確かめない開発用の仕組みなので、本番運用では app.py から外す
- AIを使う機能（文章からの条件読み取り・意味の近さで探す・1日プランの説明）は、secrets.toml の `[llm]` に `api_key` があるときだけ動く。なければ簡易なルールと完全一致で動く
- 市場価格（楽天トラベルの価格）は market_prices に料金プランごとに入れる（人数・泊数・食事の条件をプランに合わせる。sql/009）。検索のたびに、取得してから6時間以上たったプランを最大5件まで楽天から取り直し、DBの値と違えば上書きする（prices/refresh.py）。secrets.toml の `[rakuten]` に `application_id` と `access_key`（許可Webサイトを登録した場合は `referer` も）がなければ取り直さず、DBの値をそのまま使う。楽天のキーはチャットに貼らない
- 宿を楽天の施設と照合するときは `python -m prices.match_hotels`（結果の表示だけ。`--apply` を付けると、住所と名前が合う候補が1件だけの宿の hotel_ref を楽天のホテル番号に書き換える）。照合のあとに下の `prices.update` を動かすと、本物の市場価格が入る。楽天のキーが必要
- まとめて入れるときは `python -m prices.update`（`--dry-run` を付けると表示だけ）。楽天のキーがなければ仮の価格（source が dummy）を入れる
- 意味の近さで探すには、`sql/004_search.sql` を実行し、`python -m seed.embed_menus` で施設のベクトルを入れておく

## 担当
| 担当 | ファイル |
|---|---|
| のむりん（自然言語検索・絞り込み・ログイン） | search.py, nl_search.py, embedding.py, seed/embed_menus.py, day_plan.py, auth.py, ui/login_form.py, ui/search_page.py, ui/day_plan.py, ui/admin_page.py, ui/detail_page.py |
| じゅんぺい（差額計算・ランキング表示） | pricing.py, ranking.py, placeholder.py, ui/home.py, ui/results_page.py, ui/price_tab.py |
| なかりん（従業員投稿入力・保存） | posts.py, coupon.py, activity.py, spots.py, menu_import.py, prices/rakuten.py, prices/update.py, prices/refresh.py, prices/match_hotels.py, prices/crawl_spots.py, prices/crawl_targets.csv, dialogs/post.py, ui/review_tab.py, ui/coupon_card.py, ui/spots_tab.py, ui/mypage.py |
| 共通 | app.py, db.py, models.py, session.py, seed/（embed_menus.py を除く）, sql/, assets/, requirements.txt, .gitignore, .gitattributes, .streamlit/config.toml, README.md |

## データの取り出し方（Supabase）
画面を作る前に、欲しいデータが取れるかをターミナルで試せる。アプリと同じ `db.py` の `table()` を使うので、試して取れた書き方をそのまま自分のファイルに貼れば動く。

1. リポジトリのフォルダで仮想環境を有効にし、`python` と打って対話モードに入る（接続先は `.streamlit/secrets.toml` から読む）
2. 次のように打つ。`.execute().data` で、行の一覧（辞書のリスト）が返る

```python
from db import table

# 宿泊の施設を名前順に3件
table("menus").select("name,category").eq("category", "stay").order("name").limit(3).execute().data

# 箱根の施設（エリアのIDで絞る）
area = table("areas").select("id").eq("code", "hakone").execute().data[0]["id"]
table("menus").select("name").eq("area_id", area).execute().data

# 名前に「水族館」を含む施設
table("menus").select("name").ilike("name", "%水族館%").execute().data
```

| 書き方 | 意味 |
|---|---|
| `.select("列,列")` | 取り出す列（`"*"` で全部） |
| `.eq("列", 値)` | 等しい |
| `.in_("列", [値, 値])` | どれかに等しい |
| `.ilike("列", "%語%")` | 語を含む |
| `.gte("列", 値)` / `.lte("列", 値)` | 以上 / 以下 |
| `.is_("列", "null")` | 空（削除されていない行は `.is_("deleted_at", "null")`） |
| `.order("列")` / `.limit(件数)` | 並び替え / 件数 |

- 主なテーブル: menus（施設）、plans（プラン）、areas（エリア）、users（利用者）、posts（口コミ）、market_prices（市場価格）、spots（周辺情報）。列名は `sql/001_schema.sql` か、チームLPのER図で確かめる
- データの中身を表で見たいときは Supabase の Table Editor、SQLで試したいときは SQL Editor も使える
- 試すときは取り出し（select）だけにする。insert・update・delete は共有の見本データを書き換えるため

## 画面を足すとき
- 自分のブランチで画面のファイル（例: `ui/search_page.py`）を作り、同じプルリクエストで `app.py` につなぐ。`PAGES` に `"search": ":material/search: 検索"` のように1行、⑤の呼び分けに `elif page == "search":` と `from ui.search_page import render` / `render()` を足す
- ログインフォームとログアウトは、ログイン機能（auth.py・ui/login_form.py）のプルリクエストで `app.py` につなぐ
- ほかの担当の関数がまだないときは、自分のブランチでダミーの関数を置くか、テストで仮の値を渡して作る。main には、相手の本物が入ってからマージする
- main はいつでも起動できる状態に保つ。プルリクエストを出す前に、自分のPCで `streamlit run app.py` と `python -m pytest` が通ることを確かめる

テスト（tests/）は答え合わせ用: `python -m pytest tests`
