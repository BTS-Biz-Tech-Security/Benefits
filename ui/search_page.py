"""検索画面。2つのタブを持つ。

- 「1日プラン提案」（_text_tab）: 休日プランの文章から条件を読み取って検索し、エリアごとの1日プランを提案する
- 「施設を検索」（_condition_tab）: エリア・カテゴリ・人数・予算（選んだカテゴリの1人あたり）で検索し、施設の一覧だけを出す（1日プランは組まない）

読み取りは nl_search.py、施設の検索は search.py、並べ替えは ranking.py、1日プランの組み立ては day_plan.py に任せ、ここは入力と表示だけを持つ。
"""
from __future__ import annotations

import datetime
import json
from typing import Any, Optional

import streamlit as st

from day_plan import (BUDGET_ALLOWANCE, DayPlan, activity_keywords, load_market_prices, make_day_plans,
                     requested_area_keywords)
from models import CATEGORIES, Menu
from nl_search import SEARCH_FOCUS_OPTIONS, ai_available, parse_plan
from ranking import facility_scores, plan_weights, rank_menus, rank_plans
from search import list_areas, search_menus
from session import require_login
from ui.day_plan import render_day_plan
from ui.home import render_home
from ui.results_page import render_results

WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
ALL = "すべて"


@st.cache_data(ttl=600)
def _areas(tenant_id: str) -> dict[str, str]:
    """{表示名: code}。エリアはめったに変わらないので10分キャッシュする。"""
    return {a.name: a.code for a in list_areas(tenant_id)}


def format_conditions(conditions: dict[str, Any]) -> str:
    """「宿泊日：指定なし ・ 人数：4人 ・ 宿代の予算：指定なし」の形の文字列にする。
    日帰りなら「利用日：… ・ 人数：… ・ 宿泊：なし（日帰り）」の形にする（宿代の予算はないため）。"""
    date_text = people_text = budget_text = "指定なし"
    stay_date = conditions["stay_date"]
    if stay_date:
        date_text = f"{stay_date:%Y/%m/%d}（{WEEKDAY_NAMES[stay_date.weekday()]}）"
    if conditions["people"]:
        people_text = f"{conditions['people']}人"
    if conditions["budget"]:
        budget_text = f"{conditions['budget']:,}円（1泊・1人あたり）"
    if conditions.get("day_trip"):
        return f"利用日：{date_text} ・ 人数：{people_text} ・ 宿泊：なし（日帰り）"
    return f"宿泊日：{date_text} ・ 人数：{people_text} ・ 宿代の予算：{budget_text}"


def _category_label(key: str) -> str:
    """カテゴリの選択肢の表示名（"stay" → "宿泊"）。「すべて」はそのまま。"""
    return CATEGORIES.get(key, key)


NOT_FOUND = "条件に合う施設が見つかりませんでした。条件を減らして探してください。"


def _render_plans_and_list(menus: list[Menu], plans: list[DayPlan], budget: Optional[int]) -> None:
    """「1日プラン提案」タブの結果。1日プランを並べ、その下に施設一覧を折りたたんで置く。"""
    if not menus:
        st.info(NOT_FOUND)
        return
    # エリアごとのプランを、検索結果で上位のエリアから縦に並べる
    for plan in plans:
        render_day_plan(plan)
    with st.expander(f"検索結果の施設一覧（{len(menus)}件）"):
        render_results(menus, key="plan-tab", budget=budget, budget_allowance=BUDGET_ALLOWANCE)


def _text_tab(tenant_id: str) -> None:
    """「1日プラン提案」タブ。文章から条件を読み取って検索し、1日プランと施設一覧を出す。"""
    if not ai_available():
        st.caption("AIの設定がないため、決まった語と「4人」「10万円」「12月26日」の形だけを読み取ります。")
    plan_text = st.text_area(
        "どんな休日にしたいですか",
        placeholder="例：夏休みに家族4人（子ども小学生2人）で、東京から車で行ける温泉旅館に1泊したい。部屋食か個室の食事で、子どもが遊べる施設があると嬉しい。",
    )
    # 選択を外された場合（None）は「バランスよく」として扱う
    focus = st.pills("重視する観点", options=SEARCH_FOCUS_OPTIONS, default=SEARCH_FOCUS_OPTIONS[0]) or SEARCH_FOCUS_OPTIONS[0]

    if st.button("探す", type="primary", icon=":material/search:", key="search_text_submit"):
        if not plan_text.strip():
            st.warning("休日プランを入力してください。")
        else:
            with st.spinner("福利厚生メニューから探して、1日プランを組み立てています..."):
                # ① 文章から、キーワードと宿泊日・人数・予算を読み取る
                try:
                    parsed = parse_plan(plan_text, focus)
                except json.JSONDecodeError:
                    st.error("AIの返答をうまく読み取れませんでした。もう一度「探す」を押してください。")
                    parsed = None  # 読めなかったときは、前回の結果をそのまま表示する
                if parsed is not None:
                    conditions = parsed["conditions"]
                    words = [item.get("keyword", "") for item in parsed["keywords"]]

                    # ② 検索し、1日プランを組む。利用者が文章に書いた地名があれば、そのエリアのプランを先に、ほかは代替案として並べる
                    # （書いた地名がどのエリアにも当たらなければ、すべて代替案。AI が推測した行き先は希望として扱わない）
                    # 宿は予算の1.5倍（BUDGET_ALLOWANCE）まで残し、超える額はバッジで示す。「施設を検索」タブは予算ちょうどまで
                    menus = search_menus(tenant_id, people=conditions["people"], budget=conditions["budget"], keywords=words,
                                         budget_allowance=BUDGET_ALLOWANCE)
                    # 施設を ranking.py の共通スコア（重みは文章から決める）の高い順に並べる。1日プランはこの順で施設を選ぶ
                    scores = facility_scores(menus, words, plan_weights(plan_text))
                    menus = rank_menus(menus, scores)
                    # お得額は、市場価格が取れた料金プランはそれと、取れなかったプランは定価と比べる
                    markets = load_market_prices(menus)
                    plans = make_day_plans(tenant_id, menus, plan_text, budget=conditions["budget"],
                                           requested_area_names=requested_area_keywords(parsed["keywords"], plan_text),
                                           markets=markets, day_trip=conditions["day_trip"],
                                           activities=activity_keywords(parsed["keywords"]))
                    # 1日プランを点の高い順に並べる（利用者が挙げたエリアのプランが先、代替案が後ろの順は保つ）
                    plans = rank_plans(plans, scores)

                    # ③ 画面が再実行されても結果が消えず、AIを呼び直さないよう保存しておく
                    st.session_state["search_text_result"] = {"parsed": parsed, "menus": menus, "plans": plans}

    if "search_text_result" in st.session_state:
        result = st.session_state["search_text_result"]
        parsed = result["parsed"]
        st.divider()
        st.caption("こう読み取りました。違うときは「施設を検索」タブから検索してください。")
        # 結果を見る前に、まず AI が読み取った内容を読んでもらうため、ロボットのアイコン付きの色枠に、要約（太字）と条件をまとめて出す
        summary = f"**{parsed['summary']}**\n\n" if parsed.get("summary") else ""
        st.info(summary + format_conditions(parsed["conditions"]), icon=":material/smart_toy:")
        _render_plans_and_list(result["menus"], result["plans"], parsed["conditions"]["budget"])
        with st.expander(f"使用した検索キーワード（{len(parsed.get('keywords', []))}個）"):
            for item in parsed.get("keywords", []):
                st.markdown(f"**{item.get('keyword', '')}**（{item.get('category', '')}）　:gray[{item.get('reason', '')}]")


def _condition_tab(tenant_id: str) -> None:
    """「施設を検索」タブ。条件で検索し、施設の一覧だけを出す。"""
    areas = _areas(tenant_id)
    with st.form("search_condition_form"):
        col_area, col_category = st.columns(2)
        area = col_area.selectbox("エリア", options=[ALL, *areas])
        category = col_category.selectbox("カテゴリ", options=[ALL, *CATEGORIES], format_func=_category_label)

        col_date, col_people, col_budget = st.columns(3)
        col_date.date_input("宿泊日", value=datetime.date.today() + datetime.timedelta(days=14), format="YYYY/MM/DD")
        people = col_people.number_input("人数", min_value=1, value=2, step=1)
        budget = col_budget.number_input("予算（1人あたりの円。0なら上限なし）", min_value=0, value=0, step=1000,
                                         help="選んだカテゴリの料金と比べます。宿泊は1泊・1人あたり、食事・レジャーは1人あたりの料金です。"
                                              "「すべて」のときは、どのカテゴリにも当てはめます。")

        if st.form_submit_button("検索", type="primary", icon=":material/search:"):
            # ① 「すべて」と「0円」は、条件なし（None）にする
            area_code = areas.get(area)
            category_key = None if category == ALL else category
            budget_value = int(budget) if budget > 0 else None
            # このタブの予算は、選んだカテゴリの料金と比べる（「すべて」なら全カテゴリ）
            budget_categories = [category_key] if category_key else list(CATEGORIES)
            with st.spinner("福利厚生メニューから探しています..."):
                # ② 検索する（このタブでは1日プランは組まない）
                menus = search_menus(tenant_id, area_code=area_code, category=category_key,
                                     people=int(people), budget=budget_value, budget_categories=budget_categories)
                # 施設を ranking.py の共通スコアの高い順に並べる（このタブは検索ワードがないので、お得度と品質で決まる）
                menus = rank_menus(menus, facility_scores(menus, []))
                # ③ 画面が再実行されても結果が消えないよう保存しておく
                st.session_state["search_condition_result"] = {"menus": menus, "budget": budget_value,
                                                               "budget_categories": budget_categories}

    # ④ 検索結果の施設一覧だけを、折りたたまずに表示する
    if "search_condition_result" in st.session_state:
        menus = st.session_state["search_condition_result"]["menus"]
        budget_value = st.session_state["search_condition_result"].get("budget")
        budget_categories = st.session_state["search_condition_result"].get("budget_categories", ["stay"])
        if not menus:
            st.info(NOT_FOUND)
        else:
            render_results(menus, key="search-tab", budget=budget_value, budget_categories=budget_categories)


def render() -> None:
    user = require_login()
    with st.container(border=True):
        st.subheader(":material/search: 検索")
        tab_text, tab_condition = st.tabs([":material/chat: 1日プラン提案", ":material/tune: 施設を検索"])
        with tab_text:
            _text_tab(user.tenant_id)
        with tab_condition:
            _condition_tab(user.tenant_id)
    # 検索する前は、検索欄の下にお得ランキング・新着・最近の口コミを出す（どちらかのタブで検索したら消える）
    if "search_text_result" not in st.session_state and "search_condition_result" not in st.session_state:
        render_home(user)
