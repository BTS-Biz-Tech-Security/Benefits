"""文章（理想の休日プラン）から、検索キーワードと宿泊日・人数・予算を読み取る。

AIは secrets.toml の [llm] に api_key があるときだけ使う。なければ簡易なルールで読み取る。
画面は持たない（画面は ui/search_page.py）。
"""
from __future__ import annotations

import datetime
import json
import re
import unicodedata
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
    "エリア": [
        "富良野", "旭川", "札幌", "登別", "函館", "青森", "奥入瀬", "仙台", "蔵王", "会津", "磐梯", "那須", "日光", "草津", "東京", "横浜", "箱根", "熱海", "伊豆", "軽井沢", "富士五湖", "金沢", "高山", "下呂",
        "名古屋", "城崎", "京都", "神戸", "有馬", "大阪", "奈良", "伊勢", "志摩", "白浜", "松江", "出雲", "広島", "宮島", "松山", "道後", "別府", "長崎", "佐世保", "沖縄", "石垣",
    ],  # sql/007_areas.sql のエリア名（「・」で分けたもの）
    "施設タイプ": ["旅館", "ホテル", "コテージ", "グランピング"],
    "設備・サービス": ["温泉", "露天風呂", "貸切風呂", "部屋食", "個室", "キッズ", "子ども", "家族向け", "ペット", "プール", "駅近"],
}


def llm_api_key() -> Optional[str]:
    """secrets.toml の [llm] api_key。なければ None。1日プランの説明文（day_plan.py）でも使う。"""
    try:
        return st.secrets.get("llm", {}).get("api_key")
    except FileNotFoundError:
        return None


def ai_available() -> bool:
    """AI を使える設定になっているか。"""
    return bool(llm_api_key())


def normalize_conditions(raw: Any, today: Optional[datetime.date] = None) -> dict[str, Any]:
    """読み取った宿泊日・人数・予算・日帰りかを整える。読めない値は「指定なし」（None）にする。"""
    conditions: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if today is None:
        today = datetime.date.today()

    # ① 宿泊日: 月日（MM-DD）だけを使い、年はプログラムで決める（今日以降で最も近い日付）
    #    年付き（YYYY-MM-DD）で返った場合も、年は古いことがあるため無視して月日だけを使う
    stay_date = None
    match = re.fullmatch(r"(?:\d{4}-)?(\d{1,2})-(\d{1,2})", str(conditions.get("stay_date")))
    if match:
        try:
            stay_date = datetime.date(today.year, int(match.group(1)), int(match.group(2)))
            if stay_date < today:
                stay_date = stay_date.replace(year=today.year + 1)
        except ValueError:
            stay_date = None

    # ② 人数・予算: 1以上の整数にできるものだけ使う
    people = _to_positive_int(conditions.get("people"))
    budget = _budget_per_person_per_night(conditions, people)

    # ③ 日帰り: true と読み取れたときだけ日帰りにする。日帰りなら宿代はかからないので、予算は「指定なし」にする
    day_trip = conditions.get("day_trip") is True
    if day_trip:
        budget = None
    return {"stay_date": stay_date, "people": people, "budget": budget, "day_trip": day_trip}


def _budget_per_person_per_night(conditions: dict[str, Any], people: Optional[int]) -> Optional[int]:
    """宿代の予算を「1泊・1人あたり」の金額にそろえる。宿泊の料金プランを1人あたりの金額として扱うので、それと比べられる形にする。

    計算は AI に任せず、ここで行う。AI（または簡易な読み取り）からは、金額・1人あたりか・1泊あたりか・泊数を受け取る。
    - 全員分の金額なら、人数で割る（人数が分からなければ決められないので None）
    - 旅行全体の金額なら、泊数で割る（泊数が分からなければ1泊とみなす）
    """
    # ① 金額を取り出す。以前の形（budget に金額だけ）は「1泊・全員分」として扱う
    if "budget_amount" in conditions:
        amount = _to_positive_int(conditions.get("budget_amount"))
        per_person = bool(conditions.get("budget_per_person"))
        per_night = bool(conditions.get("budget_per_night"))
    else:
        amount = _to_positive_int(conditions.get("budget"))
        per_person = False
        per_night = True
    if amount is None:
        return None

    # ② 全員分の金額なら、人数で割る
    if not per_person:
        if people is None:
            return None
        amount = amount // people

    # ③ 旅行全体の金額なら、泊数で割る
    nights = _to_positive_int(conditions.get("nights")) or 1
    if not per_night:
        amount = amount // nights
    return amount


def _to_positive_int(value: Any) -> Optional[int]:
    """1以上の整数にできれば、その数。できなければ None。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _drop_numeric_keywords(keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """「予算10万円」「4人」のような数字入りの語は施設検索でヒットしにくいため除く（半角・全角の数字）。"""
    result = []
    for item in keywords:
        if not re.search(r"[0-9０-９]", item.get("keyword", "")):
            result.append(item)
    return result


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
        "- 宿泊日（日帰りなら利用日）は「12月26日」のように月日が書かれている場合だけ、月日をMM-DD形式（例：03-03）で入れること。年は入れないこと。"
        "「8月に」「年末に」のように月や時期だけで日がない場合（1日などに決めつけない）や、「来週の土曜日」のように曜日だけで書かれている場合はnullとすること。"
        "日帰りでも、月日が書かれていれば必ず stay_date に入れること（例：「1月3日に日帰りで」→ 01-03）\n"
        "- 人数は整数で入れること\n"
        "- 予算は宿代（宿泊費）の予算だけを読み取ること。食事・レジャーの予算（例：「ランチは1人3,000円」）は宿代ではないので、"
        "ほかに宿代の予算が書かれていなければ budget_amount を null とすること\n"
        "- 予算は計算せず（人数や泊数を掛けたり割ったりせず）、書かれている金額（円）をそのまま budget_amount に整数で入れること（「1万円」なら10000）。"
        "その金額が1人あたりなら budget_per_person を true、1泊あたりなら budget_per_night を true にすること"
        "（例：「1人1泊1万円」→ budget_amount 10000、budget_per_person true、budget_per_night true）。"
        "budget_per_night は、金額が1泊分か（true）、複数泊の合計か（false）で決めること。"
        "「1泊2万円」なら true（合計に直さず 20000 のまま）、「2泊の合計で6万円」「全部で6万円」なら false"
        "（例：「3人・2泊の合計で6万円」→ budget_amount 60000、budget_per_person false、budget_per_night false、nights 2）。"
        "泊数が書かれていれば nights に整数で入れること\n"
        "- 「日帰り」「泊まらない」「宿泊なし」のように、泊まらないことがはっきり書かれていれば day_trip を true、それ以外は false にすること。"
        "day_trip が true のときは、宿泊施設のキーワードを出さないこと\n"
        "- 出力は次のJSON形式のみとすること: "
        '{"summary": "施設選びの条件の要約（1文）", '
        '"conditions": {"stay_date": "宿泊日（日帰りなら利用日）のMM-DD または null", "people": 人数 または null, '
        '"budget_amount": 書かれている宿代の予算の金額（食事・レジャーの予算は入れない） または null, "budget_per_person": true/false, "budget_per_night": true/false, '
        '"nights": 泊数 または null, "day_trip": true/false}, '
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
    # 読めない場合（返答が空のときも）は json.JSONDecodeError をそのまま呼び出し側へ返す
    return json.loads((response.choices[0].message.content or "").strip())


def parse_with_rules(plan_text: str) -> dict[str, Any]:
    """AIを使わずに読み取る。決まった語の完全一致と、「4人」「10万円」「12月26日」の形だけを拾う。"""
    # ① キーワード: 決まった語が文章に含まれていれば拾う
    keywords = []
    for category, words in RULE_KEYWORDS.items():
        for word in words:
            if word in plan_text:
                keywords.append({"keyword": word, "category": category, "reason": "文章に含まれていた語"})

    # ② 宿泊日・人数・予算: 全角の数字を半角にしてから、決まった形を探す
    text = plan_text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    raw: dict[str, Any] = {}
    date_match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if date_match:
        raw["stay_date"] = f"{date_match.group(1)}-{date_match.group(2)}"
    people_match = re.search(r"(\d+)\s*人", text)
    if people_match:
        raw["people"] = people_match.group(1)
    nights_match = re.search(r"(\d+)\s*泊", text)
    if nights_match:
        raw["nights"] = nights_match.group(1)
    man_yen_match = re.search(r"(\d+(?:\.\d+)?)\s*万円", text)  # 「10万円」「1.5万円」
    yen_match = re.search(r"([\d,]+)\s*円", text)  # 「30,000円」
    if man_yen_match:
        raw["budget_amount"] = int(float(man_yen_match.group(1)) * 10000)
    elif yen_match:
        raw["budget_amount"] = yen_match.group(1).replace(",", "")
    # 「1人あたり」「ひとり」があれば1人あたりの金額、「1泊」があれば1泊あたりの金額とみなす
    raw["budget_per_person"] = bool(re.search(r"(1人|一人|ひとり)(あたり|当たり|1泊)", text))
    raw["budget_per_night"] = "1泊" in text

    return {"summary": "", "conditions": raw, "keywords": keywords}


def parse_plan(plan_text: str, focus: str = SEARCH_FOCUS_OPTIONS[0], today: Optional[datetime.date] = None) -> dict[str, Any]:
    """休日プランの文章から {summary, conditions, keywords, used_ai} を返す。

    conditions は {stay_date: date|None, people: int|None, budget: int|None, day_trip: bool}。budget は宿代の予算で、「1泊・1人あたり」の金額。
    keywords は [{keyword, category, reason}]。AIの返答が JSON として読めないときは json.JSONDecodeError を送出する。
    """
    # ① AI があれば AI、なければ簡易なルールで読み取る
    api_key = llm_api_key()
    if api_key:
        result = _parse_with_ai(plan_text, focus, api_key)
    else:
        result = parse_with_rules(plan_text)

    # ② 読み取った結果を整える
    result["keywords"] = _drop_numeric_keywords(result.get("keywords", []))
    result["conditions"] = normalize_conditions(result.get("conditions"), today)
    # AI は「12月に」から 12月1日のような日付を作ることがあるので、文章に月日が書かれているときだけ使う
    stay_date = result["conditions"]["stay_date"]
    if stay_date is not None and not date_is_written(plan_text, stay_date):
        result["conditions"]["stay_date"] = None
    result["used_ai"] = bool(api_key)
    return result


def date_is_written(text: str, date: datetime.date) -> bool:
    """文章にその月日が「12月26日」「12/26」の形で書かれているか。全角の数字も同じに扱う。"""
    text = unicodedata.normalize("NFKC", text)  # 全角の数字・記号を半角にする
    written = re.findall(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    written += re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text)
    return any((int(month), int(day)) == (date.month, date.day) for month, day in written)
