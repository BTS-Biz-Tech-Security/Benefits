"""1日プランの表示部品。組み立ては day_plan.py に任せ、ここは表示だけを持つ。

「いくら得か」が一目で分かるよう、見出しの横に合計のお得額、各施設にお得額と割合を緑で出す。
宿代の予算を超える宿には超える額を、利用者が挙げたエリア以外のプランには代替案であることを、バッジで示す。
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from day_plan import KIND_LABELS, DayPlan
from ui.detail_page import open_detail


def price_text(list_price: Optional[int], price: Optional[int], over_budget: Optional[int] = None) -> str:
    """「定価 30,000円 → 21,000円　9,000円お得（30%）」の形。お得額がなければ福利厚生価格だけ。

    1日プランと、検索画面の施設一覧の両方で使う（同じ見た目にそろえるため）。
    """
    if price is None:
        return ""
    if list_price is None or list_price <= price:
        text = f"福利厚生 {price:,}円"
    else:
        saving = list_price - price
        rate = round(saving * 100 / list_price)
        old_price = f":gray[~~定価 {list_price:,}円~~ →]"  # ~~ ~~ は取り消し線
        new_price = f"**{price:,}円**"
        text = f"{old_price} {new_price}　:green[**{saving:,}円お得**（{rate}%）]"
    if over_budget:
        text += f"　:orange-badge[予算＋{over_budget:,}円]"
    return text


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
            col_slot.markdown(f"**{item.slot}**")
            name = item.name
            if item.url:
                name = f"[{item.name}]({item.url})"  # 周辺スポットにリンクがあれば、名前をリンクにする
            if item.kind == "benefit":
                col_name.markdown(item.name)
                col_name.caption(item.plan_name or "")
                col_price.markdown(price_text(item.list_price, item.price, item.over_budget))
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
