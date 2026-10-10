from datetime import date

from prices import update
from models import Plan
from prices.rakuten import Credentials, Fetched


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


def test_fetch_with_retry_uses_plan_conditions(monkeypatch):
    calls = []

    def fake(hotel_ref, checkin, nights, adults, creds, reference=None, meal=None):
        calls.append((hotel_ref, nights, adults, reference, meal))
        return Fetched(26000, "dummy", None)
    monkeypatch.setattr(update, "fetch_price", fake)
    plan = Plan(id="p", menu_id="m", name="2食付", list_price=30000, benefit_price=18000, nights=2, adults=3, meal="2食付き")
    fetched, error = update.fetch_with_retry("12345", plan, date(2026, 10, 17), Credentials())
    assert fetched.price == 26000 and error is None
    assert calls == [("12345", 2, 3, 30000, "2食付き")]
