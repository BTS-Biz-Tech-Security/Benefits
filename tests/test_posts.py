from datetime import datetime

from models import Post
from posts import validate, summary


def test_validate():
    assert validate(0, "") is not None
    assert validate(3, "x" * 201) is not None
    assert validate(5, "良かった") is None


def test_summary():
    ps = [Post("1", "m", "u", 4, None, datetime.now()), Post("2", "m", "u", 5, None, datetime.now())]
    s = summary(ps)
    assert s.count == 2 and s.average == 4.5
    assert summary([]).count == 0


def test_validate_photo():
    from posts import validate_photo
    assert validate_photo("image/jpeg", 1000) is None
    assert validate_photo("image/gif", 1000) is not None
    assert validate_photo("image/png", 6 * 1024 * 1024) is not None


def test_validate_deal_and_sub_ratings():
    assert validate(4, "", deal_rating=6) is not None
    assert validate(4, "", sub_ratings={"rating_room": 0}) is not None
    assert validate(4, "", sub_ratings={"rating_unknown": 3}) is not None
    assert validate(4, "", deal_rating=5, sub_ratings={"rating_room": 4, "rating_meal": 5}) is None


def test_summarize_deal_satisfaction():
    from posts import summarize
    s = summarize([5, 4, 3, 4], [5, 2, None, 4])
    assert s.count == 4 and s.average == 4.0
    assert s.deal_count == 3 and s.deal_satisfaction == 0.67
    assert summarize([4], [None]).deal_satisfaction is None


def test_post_from_row_reads_new_fields():
    p = Post.from_row({"id": "1", "menu_id": "m", "user_id": "u", "rating": 4, "comment": "良い",
                       "created_at": "2026-10-01T12:00:00+09:00", "deal_rating": 5, "rating_room": 4,
                       "rating_bath": None, "used_at": "2026-09-20", "users": {"name": "木下 亮", "family": "夫婦"}})
    assert p.deal_rating == 5 and p.sub_ratings == {"rating_room": 4}
    assert p.user_name == "木下 亮" and p.user_family == "夫婦" and p.used_at == "2026-09-20"


def test_summarize_sub_averages_use_answered_only():
    from posts import summarize
    s = summarize([4, 5, 3], [None, None, None], [{"rating_bath": 5, "rating_meal": 3}, {"rating_bath": 4}, {}])
    assert s.sub_averages == {"rating_bath": 4.5, "rating_meal": 3.0}
