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
