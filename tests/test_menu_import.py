from menu_import import COMBINED_COLUMNS, missing_columns, read_csv_bytes, split_rows, template_csv


def _row(key, name="宿A", plan_name="", **kw):
    row = {c: "" for c in COMBINED_COLUMNS}
    row.update(key=key, area_code="hakone", name=name, category="stay", plan_name=plan_name, **kw)
    return row


def test_split_groups_plans_by_facility():
    rows = [_row("H1", plan_name="素泊まり", plan_list_price="10000", plan_benefit_price="8000"),
            _row("H1", plan_name="2食付き", plan_list_price="20000", plan_benefit_price="15000"),
            _row("H2", name="宿B")]
    menus, plans, problems = split_rows(rows)
    assert [m["key"] for m in menus] == ["H1", "H2"]
    assert [(p["menu_key"], p["name"]) for p in plans] == [("H1", "素泊まり"), ("H1", "2食付き")]
    assert problems == []


def test_split_reports_conflicting_facility_columns_and_blank_key():
    rows = [_row("H1"), _row("H1", name="別の名前"), _row("")]
    menus, _, problems = split_rows(rows)
    assert menus[0]["name"] == "宿A"
    assert len(problems) == 2


def test_missing_columns():
    assert missing_columns([{"key": "x", "name": "y"}]) == ["area_code", "category"]


def test_template_round_trip():
    rows = read_csv_bytes(template_csv())
    menus, plans, problems = split_rows(rows)
    assert len(menus) == 20 and len(plans) == 44 and problems == []
