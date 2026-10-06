"""1日プランの表示部品。組み立ては day_plan.py に任せ、ここは表示だけを持つ。

「いくら得か」が一目で分かるよう、見出しの横に合計のお得額、各施設にお得額と割合を緑で出す。
"""
from __future__ import annotations

import streamlit as st

from day_plan import KIND_LABELS, DayPlan, PlanItem


def _price_text(item: PlanItem) -> str:
    """「定価 30,000円 → 21,000円　9,000円お得（30%）」の形。お得額がなければ福利厚生価格だけ。"""
    if item.price is None:
        return ""
    if not item.saving or item.list_price is None:
        return f"福利厚生 {item.price:,}円"
    return f":gray[~~定価 {item.list_price:,}円~~ →] **{item.price:,}円**　:green[**{item.saving:,}円お得**（{item.saving_rate}%）]"


def render_day_plan(plan: DayPlan) -> None:
    with st.container(border=True):
        col_title, col_total = st.columns([3, 2], vertical_alignment="center")
        col_title.markdown(f"#### :material/event: 1日プラン（{plan.area_name}）")
        if plan.total_saving > 0:
            col_total.metric("合計のお得額", f"{plan.total_saving:,}円お得")
        for item in plan.items:
            name = f"[{item.name}]({item.url})" if item.url else item.name
            col_slot, col_name, col_price = st.columns([1, 4, 5], vertical_alignment="center")
            col_slot.markdown(f"**{item.slot}**")
            if item.kind == "benefit":
                col_name.markdown(f"{name}　:gray[{item.plan_name or ''}]")
                col_price.markdown(_price_text(item))
            else:
                col_name.markdown(name)
                if item.kind == "spot":
                    col_price.markdown(f":gray[{KIND_LABELS[item.kind]}]")
        if plan.day_trip:
            st.caption("宿泊の施設が見つからなかったため、日帰りのプランです。")
        if plan.total_price is not None:
            st.caption(f"福利厚生価格の合計：{plan.total_price:,}円")
        if plan.explanation:
            st.markdown(plan.explanation)
