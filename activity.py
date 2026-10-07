"""行動ログ（ログイン・クーポン使用・予約ページを開いた）の記録。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from db import table
from models import ACTIVITY_KINDS, User


def log(user: User, kind: str, menu_id: Optional[str] = None, plan_id: Optional[str] = None) -> None:
    """1件記録する。kind は ACTIVITY_KINDS のキー。失敗しても画面は止めない。"""
    # ① 種別を確認する
    if kind not in ACTIVITY_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    # ② 記録する行を組み立てる
    row = {
        "tenant_id": user.tenant_id,
        "user_id": user.id,
        "menu_id": menu_id,
        "plan_id": plan_id,
        "kind": kind,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    # ③ 保存する。失敗しても利用者の操作は止めない
    try:
        table("activity_logs").insert(row).execute()
    except Exception:
        # 記録の失敗で利用者の操作を止めない
        pass
