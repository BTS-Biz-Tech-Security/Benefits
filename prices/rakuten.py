"""一般サイトの価格の取得。楽天トラベルの空室検索APIで、宿の最安料金を取る。

- 楽天のアプリID・アクセスキーがない、または hotel_ref が楽天のホテル番号（数字）でない宿は、仮の価格（ダミー）を返す
- 取得に失敗したときは例外を投げる。再試行と停止は呼び出し側（update.py）が決める
- 2026年の楽天ウェブサービスの新しい仕様に合わせている（新しいドメイン、アプリIDとアクセスキーの両方が必要）
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

import requests

API_URL = "https://openapi.rakuten.co.jp/engine/api/Travel/VacantHotelSearch/20170426"
TIMEOUT = 10
SATURDAY_RATE = 1.2  # 仮の価格: 土曜は2割高くする
DUMMY_RATE_MIN = 0.80  # 仮の価格: 定価のこの割合〜DUMMY_RATE_MAX の間にする（宿ごとに決まった値）
DUMMY_RATE_MAX = 0.98


@dataclass
class Credentials:
    """楽天ウェブサービスの接続情報。secrets.toml の [rakuten] か、環境変数から読む。"""
    application_id: str = ""
    access_key: str = ""
    referer: str = ""  # アプリに登録した「許可Webサイト」。登録してある場合だけ送る

    def ready(self) -> bool:
        """APIを呼べるだけの情報がそろっているか。"""
        return bool(self.application_id and self.access_key)


@dataclass
class Fetched:
    price: int  # 大人 adults 人・nights 泊の合計
    source: str  # 'rakuten_api' / 'dummy'
    source_url: Optional[str]


def is_rakuten_ref(hotel_ref: Optional[str]) -> bool:
    """hotel_ref が楽天のホテル番号（数字）かどうか。"""
    return bool(hotel_ref) and hotel_ref.isdigit()


def fetch_price(hotel_ref: str, checkin: date, nights: int, adults: int, creds: Optional[Credentials] = None,
                reference_price: Optional[int] = None) -> Fetched:
    """宿・日程・人数で、一般サイトの最安の合計料金を返す。APIを使えない宿は仮の価格。

    reference_price は仮の価格の元にする定価（同じ人数・1泊）。update.py が料金プランから渡す。
    """
    # ① 接続情報がない、または楽天のホテル番号でなければ仮の価格
    if creds is None or not creds.ready() or not is_rakuten_ref(hotel_ref):
        return dummy_price(hotel_ref, checkin, nights, adults, reference_price)

    # ② 空室検索APIを呼ぶ。アクセスキーはヘッダーで送る（URLに残さないため）
    params = {
        "applicationId": creds.application_id,
        "format": "json",
        "hotelNo": hotel_ref,
        "checkinDate": checkin.isoformat(),
        "checkoutDate": (checkin + timedelta(days=nights)).isoformat(),
        "adultNum": adults,
        "responseType": "small",
    }
    headers = {"accessKey": creds.access_key}
    if creds.referer:
        headers["Referer"] = creds.referer
        headers["Origin"] = creds.referer.rstrip("/")
    r = requests.get(API_URL, params=params, headers=headers, timeout=TIMEOUT)
    if r.status_code == 404:  # 空室がないときは 404 が返る
        raise ValueError("空室がありません")
    r.raise_for_status()
    data = r.json()

    # ③ 部屋ごとの料金から最安を取る。料金は1泊目のものなので、泊数をかけて合計にする
    totals = room_totals(data)
    if not totals:
        raise ValueError("料金が見つかりません")
    return Fetched(min(totals) * nights, "rakuten_api", hotel_url(data))


def _hotel_parts(data: dict[str, Any]) -> list[dict[str, Any]]:
    """応答の hotels から、宿ごとの部品（hotelBasicInfo や roomInfo を持つ dict）を平らに並べる。"""
    parts: list[dict[str, Any]] = []
    for item in data.get("hotels", []):
        hotel = item.get("hotel", item) if isinstance(item, dict) else item
        if isinstance(hotel, dict):
            parts.append(hotel)
        elif isinstance(hotel, list):
            parts.extend(p for p in hotel if isinstance(p, dict))
    return parts


def room_totals(data: dict[str, Any]) -> list[int]:
    """応答に含まれる部屋ごとの料金（dailyCharge の total）を集める。"""
    totals: list[int] = []
    for part in _hotel_parts(data):
        rooms = part.get("roomInfo") or []
        for room in rooms if isinstance(rooms, list) else [rooms]:
            # roomInfo は [{"roomBasicInfo": {...}}, {"dailyCharge": {...}}] のように部品が分かれて入っている
            charge = room.get("dailyCharge") if isinstance(room, dict) else None
            if isinstance(charge, dict) and charge.get("total"):
                totals.append(int(charge["total"]))
    return totals


def hotel_url(data: dict[str, Any]) -> Optional[str]:
    """宿の楽天トラベルのページ。比較の根拠として画面に出す。"""
    for part in _hotel_parts(data):
        info = part.get("hotelBasicInfo")
        if isinstance(info, dict) and info.get("hotelInformationUrl"):
            return info["hotelInformationUrl"]
    return None


def dummy_price(hotel_ref: Optional[str], checkin: date, nights: int, adults: int,
                reference_price: Optional[int] = None) -> Fetched:
    """仮の価格。同じ入力なら同じ値になる。土曜は2割高い。

    定価（reference_price）があれば、その 80〜98% の間で宿ごとに決まった割合にする（福利厚生価格との差が現実に近くなるように）。
    定価がなければ、2名1泊 16,000〜41,000円の間で宿ごとに決まった値にする。
    """
    # ① 宿IDから、宿ごとに決まった数を作る
    seed = int(hashlib.md5(f"{hotel_ref}".encode()).hexdigest(), 16)
    # ② 1人1泊の基準の価格
    if reference_price:
        rate = DUMMY_RATE_MIN + (seed % 1000) / 999 * (DUMMY_RATE_MAX - DUMMY_RATE_MIN)
        per_adult = reference_price * rate / max(adults, 1)
    else:
        per_adult = (16000 + (seed % 26) * 1000) / 2
    # ③ 人数と泊数をかけ、土曜は高くする。100円単位に丸める
    price = per_adult * adults * nights
    if checkin.weekday() == 5:
        price *= SATURDAY_RATE
    return Fetched(int(round(price / 100) * 100), "dummy", None)
