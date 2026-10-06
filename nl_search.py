"""文章（理想の休日プラン）から、検索キーワードと宿泊日・人数・予算を読み取る。

AIは secrets.toml の [llm] に api_key があるときだけ使う。なければ簡易なルールで読み取る。
画面は持たない（画面は ui/search_page.py）。
"""
from __future__ import annotations

import datetime
import json
import re
from typing import Any, Optional

import streamlit as st

MODEL = "gpt-4o-mini"

# どの観点のキーワードを重視するかの選択肢（福利厚生メニューの施設情報はエリア・施設タイプ・設備で絞り込む）
SEARCH_FOCUS_OPTIONS = [
    "バランスよく",
    "エリア（地域名・温泉地名など）を重視",
    "施設タイプ（旅館・ホテル・コテージなど）を重視",
    "設備・サービス（露天風呂・キッズ対応など）を重視",
]

# AIがないときに文章から拾う語（seed/menus.csv の地名・タグに出てくる語）
RULE_KEYWORDS = {
    "エリア": ["箱根", "熱海", "軽井沢", "京都", "沖縄"],
    "施設タイプ": ["旅館", "ホテル", "コテージ", "グランピング"],
    "設備・サービス": ["温泉", "露天風呂", "貸切風呂", "部屋食", "個室", "キッズ", "子ども", "家族向け", "ペット", "プール", "駅近"],
}


def _api_key() -> Optional[str]:
    """secrets.toml の [llm] api_key。なければ None。"""
    try:
        return st.secrets.get("llm", {}).get("api_key")
    except FileNotFoundError:
        return None


def ai_available() -> bool:
    return bool(_api_key())


def normalize_conditions(raw: Any, today: Optional[datetime.date] = None) -> dict[str, Any]:
    """読み取った宿泊日・人数・予算を整える。読めない値は「指定なし」（None）にする。"""
    raw = raw if isinstance(raw, dict) else {}
    today = today or datetime.date.today()

    # 月日（MM-DD）だけを使い、年はプログラムで決める（今日以降で最も近い日付）
    # 年付き（YYYY-MM-DD）で返った場合も、年は古いことがあるため無視して月日だけを使う
    stay_date = None
    match = re.fullmatch(r"(?:\d{4}-)?(\d{1,2})-(\d{1,2})", str(raw.get("stay_date")))
    if match:
        try:
            stay_date = datetime.date(today.year, int(match.group(1)), int(match.group(2)))
            if stay_date < today:
                stay_date = stay_date.replace(year=today.year + 1)
        except ValueError:
            stay_date = None

    def to_positive_int(value: Any) -> Optional[int]:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    return {"stay_date": stay_date, "people": to_positive_int(raw.get("people")), "budget": to_positive_int(raw.get("budget"))}


def _drop_numeric_keywords(keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """「予算10万円」「4人」のような数字入りの語は施設検索でヒットしにくいため除く（半角・全角の数字）。"""
    return [item for item in keywords if not re.search(r"[0-9０-９]", item.get("keyword", ""))]


def _build_prompt(plan_text: str, focus: str) -> str:
    return (
        "あなたは企業の福利厚生サービス（会員制の宿泊・レジャー優待メニュー）に詳しい旅行アドバイザーです。"
        "以下の「理想の休日プラン」に合う宿泊施設・食事施設・レジャー施設を、福利厚生サービスの施設検索（キーワード検索）で見つけるための検索キーワードを提案してください。\n"
        "- キーワードの個数は固定せず、プランの条件を過不足なくカバーできる最適な数（目安3〜12個）を自分で判断すること。条件が少なければ少なく、多ければ多くてよい。重複・言い換えだけのキーワードで数を水増ししないこと\n"
        "- 福利厚生メニューの施設名・所在地・施設紹介文・設備欄に実際に書かれていそうな語を選ぶこと（例：「箱根」「草津温泉」「旅館」「コテージ」「露天風呂」「貸切風呂」「キッズルーム」「ペット可」「オールインクルーシブ」）\n"
        "- 「癒し」「最高」「おしゃれ」のような抽象的・主観的な語や、「旅行」「宿」のように広すぎる語は避けること\n"
        "- 1つのキーワードは必ず1単語のみとし、スペースや記号で複数の語を組み合わせないこと\n"
        "- 各キーワードを「エリア」「施設タイプ」「設備・サービス」「アクティビティ」のいずれかに分類すること\n"
        "- プランに地域の指定がない場合は、出発地・日数・目的から現実的に行けるエリアを推測して提案すること\n"
        "- キーワードの観点は「" + focus + "」の方針で配分すること\n"
        "- プランから宿泊日（利用日）・人数・予算を読み取り、conditionsに入れること。"
        "プランに書かれていない項目や、「夏休み」「週末」「安めで」のように1つの値に決められないあいまいな書き方の項目はnullとし、推測で埋めないこと\n"
        "- 宿泊日は「12月26日」のように月日が書かれている場合だけ、月日をMM-DD形式（例：03-03）で入れること。年は入れないこと。「来週の土曜日」のように曜日だけで書かれている場合はnullとすること\n"
        "- 人数と予算（円）は整数で入れること。予算は全体の金額とし、1人あたりで書かれている場合は人数を掛けた合計にすること（泊数は掛けないこと）\n"
        "- 出力は次のJSON形式のみとすること: "
        '{"summary": "施設選びの条件の要約（1文）", '
        '"conditions": {"stay_date": "MM-DD または null", "people": 人数 または null, "budget": 予算の金額 または null}, '
        '"keywords": [{"keyword": "検索キーワード", "category": "分類", "reason": "このキーワードでどんな施設が見つかるか（1文）"}]}\n\n'
        "理想の休日プラン: " + plan_text
    )


def _parse_with_ai(plan_text: str, focus: str, api_key: str) -> dict[str, Any]:
    from openai import OpenAI

    response = OpenAI(api_key=api_key).chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": _build_prompt(plan_text, focus)}],
        response_format={"type": "json_object"},
        # JSONモードでまれに起きる出力の暴走で、長時間待たされないよう上限を設ける
        max_tokens=1500,
    )
    # 読めない場合は json.JSONDecodeError をそのまま呼び出し側へ返す
    return json.loads(response.choices[0].message.content.strip())


def parse_with_rules(plan_text: str) -> dict[str, Any]:
    """AIを使わずに読み取る。決まった語の完全一致と、「4人」「10万円」「12月26日」の形だけを拾う。"""
    keywords = [
        {"keyword": word, "category": category, "reason": "文章に含まれていた語"}
        for category, words in RULE_KEYWORDS.items() for word in words if word in plan_text
    ]

    text = plan_text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    raw: dict[str, Any] = {}
    if m := re.search(r"(\d{1,2})月(\d{1,2})日", text):
        raw["stay_date"] = f"{m.group(1)}-{m.group(2)}"
    if m := re.search(r"(\d+)\s*人", text):
        raw["people"] = m.group(1)
    if m := re.search(r"(\d+(?:\.\d+)?)\s*万円", text):
        raw["budget"] = int(float(m.group(1)) * 10000)
    elif m := re.search(r"([\d,]+)\s*円", text):
        raw["budget"] = m.group(1).replace(",", "")

    return {"summary": "", "conditions": raw, "keywords": keywords}


def parse_plan(plan_text: str, focus: str = SEARCH_FOCUS_OPTIONS[0], today: Optional[datetime.date] = None) -> dict[str, Any]:
    """休日プランの文章から {summary, conditions, keywords, used_ai} を返す。

    conditions は {stay_date: date|None, people: int|None, budget: int|None}。
    keywords は [{keyword, category, reason}]。AIの返答が JSON として読めないときは json.JSONDecodeError を送出する。
    """
    api_key = _api_key()
    result = _parse_with_ai(plan_text, focus, api_key) if api_key else parse_with_rules(plan_text)
    result["keywords"] = _drop_numeric_keywords(result.get("keywords", []))
    result["conditions"] = normalize_conditions(result.get("conditions"), today)
    result["used_ai"] = bool(api_key)
    return result
