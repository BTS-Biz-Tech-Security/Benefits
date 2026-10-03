# Benefits
Step2-2 Webアプリ
なかりん（班長）、JP、のむりん

福利厚生検索アプリ（チームBTS）。Streamlit ＋ Supabase（スキーマ bts_app）で作る、福利厚生の施設を一般サイトの価格と比べて探せる社内アプリ。

## はじめに
- 手順・担当・各ファイルの説明は、チームLPの「実装ガイド」を参照
- 接続情報は `.streamlit/secrets.toml` に書く（各自のPCにだけ作る。GitHub には上げない）
- 開発中は secrets.toml に `login_as = "kinoshita@example.com"`（`[supabase]` より上）を書くと、その利用者としてログインした状態で起動する。本番の設定には書かない
- AIを使う機能（文章からの条件読み取り・意味の近さで探す・1日プランの説明）は、secrets.toml の `[llm]` に `api_key` があるときだけ動く。なければ簡易なルールと完全一致で動く
- 意味の近さで探すには、`sql/004_search.sql` を実行し、`python -m seed.embed_menus` で施設のベクトルを入れておく

## 担当
| 担当 | ファイル |
|---|---|
| のむりん（自然言語検索・絞り込み・ログイン） | search.py, nl_search.py, embedding.py, seed/embed_menus.py, day_plan.py, auth.py, ui/login_form.py, ui/search_page.py, ui/day_plan.py, ui/admin_page.py, ui/detail_page.py |
| じゅんぺい（差額計算・ランキング表示） | pricing.py, ranking.py, placeholder.py, prices/rakuten.py, prices/update.py, .github/workflows/update_prices.yml, ui/home.py, ui/results_page.py, ui/price_tab.py |
| なかりん（従業員投稿入力・保存） | posts.py, coupon.py, activity.py, spots.py, prices/crawl_spots.py, prices/crawl_targets.csv, dialogs/post.py, ui/review_tab.py, ui/coupon_card.py, ui/spots_tab.py, ui/mypage.py |
| 共通 | app.py, db.py, models.py, session.py, seed/（embed_menus.py を除く）, sql/, assets/, requirements.txt, .gitignore, .gitattributes, .streamlit/config.toml, README.md |

テスト（tests/）は答え合わせ用: `python -m pytest tests`
