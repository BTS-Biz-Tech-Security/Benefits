"""検索画面。2つのタブを持つ。

- 「1日プラン提案」（_text_tab）: 休日プランの文章から条件を読み取って検索し、エリアごとの1日プランを提案する
- 「施設を検索」（_condition_tab）: エリア・カテゴリ・人数・予算で検索し、施設の一覧だけを出す（1日プランは組まない）

読み取りは nl_search.py、施設の検索は search.py、1日プランの組み立ては day_plan.py に任せ、ここは入力と表示だけを持つ。
"""
from __future__ import annotations

import datetime
import json
from typing import Any

import streamlit as st

from day_plan import DayPlan, make_day_plans
from models import CATEGORIES, Menu
from nl_search import SEARCH_FOCUS_OPTIONS, ai_available, parse_plan
from search import list_areas, min_benefit_price, search_menus
from session import require_login
from ui.day_plan import render_day_plan

WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
ALL = "すべて"


@st.cache_data(ttl=600)
def _areas(tenant_id: str) -> dict[str, str]:
    """{表示名: code}。エリアはめったに変わらないので10分キャッシュする。"""
    return {a.name: a.code for a in list_areas(tenant_id)}


def format_conditions(conditions: dict[str, Any]) -> str:
    """「宿泊日：指定なし ・ 人数：4人 ・ 予算：指定なし」の形の文字列にする。"""
    date_text = people_text = budget_text = "指定なし"
    stay_date = conditions["stay_date"]
    if stay_date:
        date_text = f"{stay_date:%Y/%m/%d}（{WEEKDAY_NAMES[stay_date.weekday()]}）"
    if conditions["people"]:
        people_text = f"{conditions['people']}人"
    if conditions["budget"]:
        budget_text = f"{conditions['budget']:,}円（1泊・全員分）"
    return f"宿泊日：{date_text} ・ 人数：{people_text} ・ 予算：{budget_text}"


def _category_label(key: str) -> str:
    """カテゴリの選択肢の表示名（"stay" → "宿泊"）。「すべて」はそのまま。"""
    return CATEGORIES.get(key, key)


NOT_FOUND = "条件に合う施設が見つかりませんでした。条件を減らして探してください。"


def _render_menu_list(menus: list[Menu]) -> None:
    """施設の一覧をカードで並べる。両方のタブで使う。

    TODO(results_page.py): この一覧は仮のもの。一覧の表示と並び替えは ui/results_page.py（じゅんぺいさん担当）の役割なので、
    results_page.py ができたら、この関数の中身をその表示（render_results）の呼び出しに置き換える。
    """
    for menu in menus:
        price = min_benefit_price(menu)
        price_text = f"福利厚生価格 {price:,}円〜" if price is not None else "価格未登録"
        with st.container(border=True):
            st.markdown(f"**{menu.name}**　:gray[{_category_label(menu.category)}・{price_text}]")
            if menu.description:
                st.caption(menu.description)


def _render_plans_and_list(menus: list[Menu], plans: list[DayPlan]) -> None:
    """「1日プラン提案」タブの結果。1日プランを並べ、その下に施設一覧を折りたたんで置く。"""
    if not menus:
        st.info(NOT_FOUND)
        return
    # エリアごとのプランを、検索結果で上位のエリアから縦に並べる
    for plan in plans:
        render_day_plan(plan)
    with st.expander(f"検索結果の施設一覧（{len(menus)}件）"):
        _render_menu_list(menus)


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

                    # ② 検索し、1日プランを組む。キーワードにエリア名があれば、そのエリアのプランを先に、ほかは代替案として並べる
                    menus = search_menus(tenant_id, people=conditions["people"], budget=conditions["budget"], keywords=words)
                    plans = make_day_plans(tenant_id, menus, plan_text, budget=conditions["budget"], requested_area_names=words)

                    # ③ 画面が再実行されても結果が消えず、AIを呼び直さないよう保存しておく
                    st.session_state["search_text_result"] = {"parsed": parsed, "menus": menus, "plans": plans}

    if "search_text_result" in st.session_state:
        result = st.session_state["search_text_result"]
        parsed = result["parsed"]
        st.divider()
        st.caption("こう読み取りました。違うときは「条件で探す」から検索してください。")
        if parsed.get("summary"):
            st.write(parsed["summary"])
        st.markdown(format_conditions(parsed["conditions"]))
        _render_plans_and_list(result["menus"], result["plans"])
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
        budget = col_budget.number_input("予算（1泊・全員分の円。0なら上限なし）", min_value=0, value=0, step=1000)

        if st.form_submit_button("検索", type="primary", icon=":material/search:"):
            # ① 「すべて」と「0円」は、条件なし（None）にする
            area_code = areas.get(area)
            category_key = None if category == ALL else category
            budget_value = int(budget) if budget > 0 else None
            with st.spinner("福利厚生メニューから探しています..."):
                # ② 検索する（このタブでは1日プランは組まない）
                menus = search_menus(tenant_id, area_code=area_code, category=category_key,
                                     people=int(people), budget=budget_value)
                # ③ 画面が再実行されても結果が消えないよう保存しておく
                st.session_state["search_condition_result"] = {"menus": menus}

    # ④ 検索結果の施設一覧だけを、折りたたまずに表示する
    if "search_condition_result" in st.session_state:
        menus = st.session_state["search_condition_result"]["menus"]
        if not menus:
            st.info(NOT_FOUND)
        else:
            st.markdown(f"**見つかった施設：{len(menus)}件**")
            _render_menu_list(menus)


def render() -> None:
    user = require_login()
    with st.container(border=True):
        st.subheader(":material/search: 検索")
        tab_text, tab_condition = st.tabs([":material/chat: 1日プラン提案", ":material/tune: 施設を検索"])
        with tab_text:
            _text_tab(user.tenant_id)
        with tab_condition:
            _condition_tab(user.tenant_id)
