"""クーポンの使用と予約ページを開いたことを記録する。表示は ui/coupon_card.py が行う。"""
from __future__ import annotations

from typing import Optional

from activity import log
from models import Plan, User


def coupon_text(plan: Plan) -> Optional[str]:
    """クーポンがあれば表示用の文言、なければ None。クーポンで予約すると福利厚生価格になる。"""
    # ① クーポンがなければ何も出さない
    if not plan.coupon_code:
        return None
    # ② コードと、福利厚生価格になる旨の文言を作る
    return f"クーポンコード {plan.coupon_code}（予約ページで入力すると {plan.benefit_price:,}円）"


def acquire(user: User, plan: Plan) -> None:
    """クーポンの使用を記録する。"""
    # ① 行動ログに「クーポン使用」を記録する
    log(user, "coupon", menu_id=plan.menu_id, plan_id=plan.id)


def member_link(user: User, plan: Plan) -> Optional[str]:
    """予約ページのURLを返し、開いたことを記録する。URLがなければ None。"""
    # ① URLがなければ None
    if not plan.member_url:
        return None
    # ② 行動ログに「予約ページを開いた」を記録してURLを返す
    log(user, "click", menu_id=plan.menu_id, plan_id=plan.id)
    return plan.member_url
