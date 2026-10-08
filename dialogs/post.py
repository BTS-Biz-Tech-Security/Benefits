"""口コミを書くダイアログ。総合の星・お得感・項目ごとの星（任意）・利用した日・コメント・写真を入力して保存する。"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from models import SUB_RATINGS, SUB_RATINGS_BY_CATEGORY, Menu, Plan, User
from posts import COMMENT_MAX, create, upload_photo, validate_photo


def _stars_input(label: str, key: str) -> Optional[int]:
    """星を選ぶ欄。選んだ星（1〜5）、選んでいなければ None。st.feedback は 0〜4 を返すので 1 を足す。"""
    st.markdown(label)
    value = st.feedback("stars", key=key)
    return None if value is None else int(value) + 1


@st.dialog("口コミを書く")
def open_post_dialog(user: User, menu: Menu, plan: Optional[Plan]) -> None:
    """口コミを書くダイアログ。入力を確かめて保存する。口コミタブとクーポンのカードから呼ばれる。"""
    st.write(f"**{menu.name}**" + (f"（{plan.name}）" if plan else ""))
    # ① 総合の星とお得感（総合は必須、お得感は任意）
    rating = _stars_input("総合の評価（必須）", f"post-rating-{menu.id}")
    deal_rating = _stars_input("お得感（福利厚生の価格で、お得だと感じたか）", f"post-deal-{menu.id}")
    # ② 項目ごとの星（任意）。施設のカテゴリに合う項目だけを出す
    sub_ratings: dict[str, int] = {}
    with st.expander("項目ごとの評価（任意）"):
        for key in SUB_RATINGS_BY_CATEGORY.get(menu.category, []):
            value = _stars_input(SUB_RATINGS[key], f"post-{key}-{menu.id}")
            if value is not None:
                sub_ratings[key] = value
    # ③ 利用した日・コメント・写真
    used_at = st.date_input("利用した日（任意）", value=None, format="YYYY/MM/DD")
    comment = st.text_area(f"コメント（任意・{COMMENT_MAX}文字まで）", max_chars=COMMENT_MAX)
    photo = st.file_uploader("写真（任意・JPEG／PNG・5MBまで）", type=["jpg", "jpeg", "png"])
    st.caption("個人が特定される内容や、契約の詳細は書かないでください。人の顔が写った写真は避けてください。")

    if not st.button("投稿する", type="primary", icon=":material/send:"):
        return
    # ④ 総合の星を確かめる
    if rating is None:
        st.error("総合の評価の星を選んでください")
        return
    # ⑤ 写真があれば先に保存してURLを得る。保存できなかったときは、写真なしで投稿する
    photo_url = None
    if photo is not None:
        err = validate_photo(photo.type, photo.size)
        if err:
            st.error(err)
            return
        try:
            photo_url = upload_photo(user, photo.getvalue(), photo.type)
        except Exception:
            st.warning("写真を保存できなかったため、写真なしで投稿します。")
    # ⑥ 保存する
    err = create(user, menu.id, rating, comment, plan.id if plan else None, photo_url,
                 deal_rating=deal_rating, sub_ratings=sub_ratings, used_at=used_at.isoformat() if used_at else None)
    if err:
        st.error(err)
        return
    st.toast("口コミを投稿しました。ありがとうございます。", icon=":material/check_circle:")
    st.rerun()
