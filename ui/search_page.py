"""検索画面。「文章で探す」と「条件で探す」の2つのタブ。

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
    stay_date, people, budget = conditions["stay_date"], conditions["people"], conditions["budget"]
    date_text = f"{stay_date:%Y/%m/%d}（{WEEKDAY_NAMES[stay_date.weekday()]}）" if stay_date else "指定なし"
    people_text = f"{people}人" if people else "指定なし"
    budget_text = f"{budget:,}円" if budget else "指定なし"
    return f"宿泊日：{date_text} ・ 人数：{people_text} ・ 予算：{budget_text}"


def _render_results(menus: list[Menu], plans: list[DayPlan]) -> None:
    if not menus:
        st.info("条件に合う施設が見つかりませんでした。条件を減らして探してください。")
        return
    # エリアごとのプランを、検索結果で上位のエリアから縦に並べる
    for plan in plans:
        render_day_plan(plan)
    # TODO(results_page.py): ここから下の施設一覧は仮のもの。一覧の表示と並び替えは ui/results_page.py（じゅんぺいさん担当）の役割なので、
    # results_page.py ができたら、この折りたたみをその表示（render_results）の呼び出しに置き換える。
    with st.expander(f"検索結果の施設一覧（{len(menus)}件）"):
        for m in menus:
            price = min_benefit_price(m)
            price_text = f"福利厚生価格 {price:,}円〜" if price is not None else "価格未登録"
            with st.container(border=True):
                st.markdown(f"**{m.name}**　:gray[{CATEGORIES.get(m.category, m.category)}・{price_text}]")
                if m.description:
                    st.caption(m.description)


def _text_tab(tenant_id: str) -> None:
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
                try:
                    parsed = parse_plan(plan_text, focus)
                except json.JSONDecodeError:
                    st.error("AIの返答をうまく読み取れませんでした。もう一度「探す」を押してください。")
                else:
                    c = parsed["conditions"]
                    menus = search_menus(tenant_id, people=c["people"], budget=c["budget"],
                                         keywords=[k.get("keyword", "") for k in parsed["keywords"]])
                    # キーワードにエリア名があれば、そのエリアのプランを先に、ほかは代替案として並べる
                    plans = make_day_plans(tenant_id, menus, plan_text, budget=c["budget"],
                                           requested_area_names=[k.get("keyword", "") for k in parsed["keywords"]])
                    # 画面が再実行されても結果が消えず、AIを呼び直さないよう保存しておく
                    st.session_state["search_text_result"] = {"parsed": parsed, "menus": menus, "plans": plans}

    if "search_text_result" in st.session_state:
        result = st.session_state["search_text_result"]
        parsed = result["parsed"]
        st.divider()
        st.caption("こう読み取りました。違うときは「条件で探す」から検索してください。")
        if parsed.get("summary"):
            st.write(parsed["summary"])
        st.markdown(format_conditions(parsed["conditions"]))
        _render_results(result["menus"], result["plans"])
        with st.expander(f"使用した検索キーワード（{len(parsed.get('keywords', []))}個）"):
            for item in parsed.get("keywords", []):
                st.markdown(f"**{item.get('keyword', '')}**（{item.get('category', '')}）　:gray[{item.get('reason', '')}]")


def _condition_tab(tenant_id: str) -> None:
    areas = _areas(tenant_id)
    with st.form("search_condition_form"):
        col_area, col_category = st.columns(2)
        area = col_area.selectbox("エリア", options=[ALL, *areas])
        category = col_category.selectbox("カテゴリ", options=[ALL, *CATEGORIES], format_func=lambda k: CATEGORIES.get(k) or k)

        col_date, col_people, col_budget = st.columns(3)
        col_date.date_input("宿泊日", value=datetime.date.today() + datetime.timedelta(days=14), format="YYYY/MM/DD")
        people = col_people.number_input("人数", min_value=1, value=2, step=1)
        budget = col_budget.number_input("予算（円・0なら上限なし）", min_value=0, value=0, step=1000)

        if st.form_submit_button("検索", type="primary", icon=":material/search:"):
            with st.spinner("福利厚生メニューから探して、1日プランを組み立てています..."):
                menus = search_menus(
                    tenant_id,
                    area_code=areas.get(area),
                    category=None if category == ALL else category,
                    people=int(people),
                    budget=int(budget) or None,
                )
                budget_text = f"{int(budget):,}円" if budget else "上限なし"
                request_text = f"エリア：{area}・カテゴリ：{CATEGORIES.get(category) or category}・人数：{int(people)}人・予算：{budget_text}"
                # 画面が再実行されても結果が消えず、AIを呼び直さないよう保存しておく
                st.session_state["search_condition_result"] = {"menus": menus, "plans": make_day_plans(tenant_id, menus, request_text, budget=int(budget) or None)}

    if "search_condition_result" in st.session_state:
        result = st.session_state["search_condition_result"]
        _render_results(result["menus"], result["plans"])


def render() -> None:
    user = require_login()
    with st.container(border=True):
        st.subheader(":material/search: 検索")
        tab_text, tab_condition = st.tabs([":material/chat: 文章で探す", ":material/tune: 条件で探す"])
        with tab_text:
            _text_tab(user.tenant_id)
        with tab_condition:
            _condition_tab(user.tenant_id)
