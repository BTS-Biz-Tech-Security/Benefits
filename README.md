# Benefits
Step2-2 Webアプリ
なかりん（班長）、JP、のむりん

福利厚生検索アプリ（チームBTS）。Streamlit ＋ Supabase（スキーマ bts_app）で作る、福利厚生の施設を一般サイトの価格と比べて探せる社内アプリ。

## はじめに
- 手順・担当・各ファイルの説明は、チームLPの「実装ガイド」を参照
- 接続情報は `.streamlit/secrets.toml` に書く（各自のPCにだけ作る。GitHub には上げない）
- サイドバーの「開発用: 利用者を選ぶ」で見本の利用者を選ぶと、ログインした状態で画面を確かめられる（人事の画面は山本さんを選ぶ）。パスワードを確かめない開発用の仕組みなので、本番運用では app.py から外す
- AIを使う機能（文章からの条件読み取り・意味の近さで探す・1日プランの説明）は、secrets.toml の `[llm]` に `api_key` があるときだけ動く。なければ簡易なルールと完全一致で動く
- 意味の近さで探すには、`sql/004_search.sql` を実行し、`python -m seed.embed_menus` で施設のベクトルを入れておく

## 担当
| 担当 | ファイル |
|---|---|
| のむりん（自然言語検索・絞り込み・ログイン） | search.py, nl_search.py, embedding.py, seed/embed_menus.py, day_plan.py, auth.py, ui/login_form.py, ui/search_page.py, ui/day_plan.py, ui/admin_page.py, ui/detail_page.py |
| じゅんぺい（差額計算・ランキング表示） | pricing.py, ranking.py, placeholder.py, prices/rakuten.py, prices/update.py, .github/workflows/update_prices.yml, ui/home.py, ui/results_page.py, ui/price_tab.py |
| なかりん（従業員投稿入力・保存） | posts.py, coupon.py, activity.py, spots.py, prices/crawl_spots.py, prices/crawl_targets.csv, dialogs/post.py, ui/review_tab.py, ui/coupon_card.py, ui/spots_tab.py, ui/mypage.py |
| 共通 | app.py, db.py, models.py, session.py, seed/（embed_menus.py を除く）, sql/, assets/, requirements.txt, .gitignore, .gitattributes, .streamlit/config.toml, README.md |

## 画面を足すとき
- 自分のブランチで画面のファイル（例: `ui/search_page.py`）を作り、同じプルリクエストで `app.py` につなぐ。`PAGES` に `"search": ":material/search: 検索"` のように1行、⑤の呼び分けに `elif page == "search":` と `from ui.search_page import render` / `render()` を足す
- ログインフォームとログアウトは、ログイン機能（auth.py・ui/login_form.py）のプルリクエストで `app.py` につなぐ
- ほかの担当の関数がまだないときは、自分のブランチでダミーの関数を置くか、テストで仮の値を渡して作る。main には、相手の本物が入ってからマージする
- main はいつでも起動できる状態に保つ。プルリクエストを出す前に、自分のPCで `streamlit run app.py` と `python -m pytest` が通ることを確かめる

テスト（tests/）は答え合わせ用: `python -m pytest tests`
