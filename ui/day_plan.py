"""1日プランの表示部品。組み立ては day_plan.py に任せ、ここは表示だけを持つ。

「いくら得か」が一目で分かるよう、見出しの横に合計のお得額、各施設にお得額と割合を緑で出す。
宿代の予算を超える宿には超える額を、利用者が挙げたエリア以外のプランには代替案であることを、バッジで示す。
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from day_plan import COMPARED_TO_LIST, COMPARED_TO_MARKET, KIND_LABELS, DayPlan, PlanItem
from ui.detail_page import open_detail


def price_text(price: Optional[int], compared_price: Optional[int] = None, saving: Optional[int] = None,
               saving_rate: Optional[int] = None, compared_to: str = COMPARED_TO_LIST, over_budget: Optional[int] = None,
               plan_price: Optional[int] = None, plan_people: Optional[int] = None) -> str:
    """「定価 15,000円 → 10,500円　4,500円お得（30%）（2名で21,000円）」の形。お得額がなければ福利厚生価格だけ。

    お得額と割合は計算せず、plan_saving（day_plan.py）で計算済みの値を受け取って出すだけ。
    compared_to が「市場価格」なら「市場価格 〇〇円 →」と出し、市場価格の方が安ければそう添える。
    金額は1人あたり。料金プランが2名分などのときは、料金プランに書かれた金額を（2名で〇〇円）と添える。
    1日プランと、検索画面の施設一覧・詳細画面で使う（同じ見た目にそろえるため）。
    """
    if price is None:
        return ""
    if saving and saving > 0 and compared_price is not None:
        old_price = f":gray[~~{compared_to} {compared_price:,}円~~ →]"  # ~~ ~~ は取り消し線
        new_price = f"**{price:,}円**"
        text = f"{old_price} {new_price}　:green[**{saving:,}円お得**（{saving_rate}%）]"
    elif saving and saving < 0 and compared_to == COMPARED_TO_MARKET:
        text = f"福利厚生 {price:,}円　:gray[市場価格の方が{-saving:,}円安い]"
    else:
        text = f"福利厚生 {price:,}円"
    if plan_people and plan_people > 1 and plan_price is not None:
        text = ":gray[1人あたり] " + text + f"　:gray[（{plan_people}名で{plan_price:,}円）]"
    if over_budget:
        text += f"　:orange-badge[予算＋{over_budget:,}円]"
    return text


def item_price_text(item: PlanItem) -> str:
    """プランの1枠（PlanItem）の金額を price_text の形にする。1日プランと検索画面の施設一覧で使う。"""
    return price_text(item.price, item.compared_price, item.saving, item.saving_rate, item.compared_to or COMPARED_TO_LIST,
                      item.over_budget, item.plan_price, item.plan_people)


def render_day_plan(plan: DayPlan) -> None:
    """1つのプランを枠で囲んで表示する。検索画面から呼ばれる。"""
    with st.container(border=True):
        # ① 見出し（代替案ならバッジ付き）と、右側に合計のお得額
        col_title, col_total = st.columns([3, 2], vertical_alignment="center")
        title = f"#### :material/event: 1日プラン（{plan.area_name}）"
        if plan.alternative:
            title += "　:blue-badge[ご希望以外のエリアからの代替案]"
        col_title.markdown(title)
        if plan.total_saving > 0:
            col_total.metric("合計のお得額（1人あたり）", f"{plan.total_saving:,}円お得")

        # ② 枠ごとに「時間帯 ｜ 場所 ｜ 金額 ｜ 詳細を見る」の4列で並べる
        for item in plan.items:
            col_slot, col_name, col_price, col_button = st.columns([1, 4, 5, 2], vertical_alignment="center")
            col_slot.markdown(item.slot)  # 時間帯は普通の文字
            name = item.name
            if item.url:
                name = f"[{item.name}]({item.url})"  # 周辺スポットにリンクがあれば、名前をリンクにする
            if item.kind == "benefit":
                col_name.markdown(f"**{item.name}**")  # 福利厚生の施設名は太字
                col_name.caption(item.plan_name or "")
                col_price.markdown(item_price_text(item))
                # 福利厚生の施設は、「詳細を見る」ボタンで詳細画面に移れる
                if item.menu_id:
                    col_button.button("詳細を見る", key=f"day-plan-{plan.area_id}-{item.slot}-{item.menu_id}",
                                      icon=":material/arrow_forward:", on_click=open_detail, args=(item.menu_id,))
            elif item.kind == "spot":
                col_name.markdown(name)
                col_price.markdown(f":gray[{KIND_LABELS[item.kind]}]")
            else:
                col_name.markdown(name)  # 自由時間

        # ③ 補足（日帰り・価格の合計）と説明文
        if plan.day_trip:
            st.caption("宿泊の施設が見つからなかったため、日帰りのプランです。")
        if plan.total_price is not None:
            st.caption(f"福利厚生価格の合計：{plan.total_price:,}円（1人あたり）")
        if plan.explanation:
            st.markdown(plan.explanation)
