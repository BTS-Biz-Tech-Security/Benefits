from datetime import date

from prices import update
from prices.rakuten import Credentials


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "ROOT", tmp_path)  # secrets.toml がない場所
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    monkeypatch.setenv("RAKUTEN_APPLICATION_ID", "app")
    monkeypatch.delenv("RAKUTEN_ACCESS_KEY", raising=False)
    monkeypatch.delenv("RAKUTEN_REFERER", raising=False)
    cfg = update.load_config()
    assert cfg == {"url": "https://x.supabase.co", "key": "k", "creds": Credentials("app", "", "")}


def test_load_config_from_file(tmp_path, monkeypatch):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text(
        '[supabase]\nurl = "u"\nanon_key = "a"\n[rakuten]\napplication_id = "r"\naccess_key = "s"\n', encoding="utf-8")
    monkeypatch.setattr(update, "ROOT", tmp_path)
    assert update.load_config() == {"url": "u", "key": "a", "creds": Credentials("r", "s", "")}


def test_next_saturday():
    assert update.next_saturday(date(2026, 10, 8)) == date(2026, 10, 10)  # 木曜 → その週の土曜
    assert update.next_saturday(date(2026, 10, 10)) == date(2026, 10, 17)  # 土曜 → 翌週の土曜


def test_reference_prices():
    plans = [
        {"menu_id": "a", "list_price": 26000, "adults": 2, "nights": 1},
        {"menu_id": "a", "list_price": 38000, "adults": 2, "nights": 1},
        {"menu_id": "b", "list_price": 30000, "adults": 3, "nights": 1},  # 2名のプランがない → 2名分に割り戻す
        {"menu_id": "c", "list_price": 60000, "adults": 2, "nights": 2},  # 2泊 → 1泊あたり
    ]
    assert update.reference_prices(plans, 2) == {"a": 26000, "b": 20000, "c": 30000}
