"""1日プランの表示部品。組み立ては day_plan.py に任せ、ここは表示だけを持つ。"""
from __future__ import annotations

import streamlit as st

from day_plan import KIND_LABELS, DayPlan


def render_day_plan(plan: DayPlan) -> None:
    with st.container(border=True):
        st.markdown(f"**:material/event: 1日プラン（{plan.area_name}）**")
        for item in plan.items:
            name = f"[{item.name}]({item.url})" if item.url else item.name
            meta = [KIND_LABELS[item.kind]] if item.kind != "free" else []
            if item.price is not None:
                meta.append(f"{item.price:,}円〜")
            col_slot, col_body = st.columns([1, 6])
            col_slot.markdown(f"**{item.slot}**")
            col_body.markdown(f"{name}　:gray[{'・'.join(meta)}]" if meta else name)
        if plan.day_trip:
            st.caption("宿泊の施設が見つからなかったため、日帰りのプランです。")
        if plan.total_price is not None:
            st.markdown(f"福利厚生価格の合計：**{plan.total_price:,}円〜**")
        if plan.explanation:
            st.markdown(plan.explanation)
