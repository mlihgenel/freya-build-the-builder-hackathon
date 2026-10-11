"""Farklı `now` günleri (docs/13 Faz 4.1): elle yazılmış beklentiler (tests/fixtures/days.json) ile builder'ın
runtime kodu aynı tarihleri üretiyor mu. Beklentiler builder'dan türetilmez; aşağıdaki bağımsız takvim de
builder kodunu kullanmaz."""
import datetime
import json

import pytest

from conftest import ROOT
from fbb.days import cases_for

D = datetime.date
DAYS = json.loads((ROOT / "tests" / "fixtures" / "days.json").read_text())["days"]
HOL = {"2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"}  # Brief A


def _bd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL


def _add(d, n):
    k = 0
    while k < n:
        d += datetime.timedelta(days=1)
        k += _bd(d)
    return d


def _band_deadline(days_late, today):
    return _add(today, 12 if days_late <= 7 else 7)


@pytest.mark.parametrize("now", sorted(DAYS))
def test_fixture_promises_are_valid_dates(now, public_cases):
    """Her beklenen promise: iş günü, bugün ya da sonrası, ürünün deadline'ını aşmıyor (A kural 19)."""
    today = D.fromisoformat(now[:10])
    for cid, over in DAYS[now].items():
        exp = over.get("expected", public_cases[cid]["expected"])
        products = public_cases[cid]["products"]
        for p in exp["promises"]:
            when = D.fromisoformat(p["date"])
            idx = int(p["product_id"][1:]) - 1
            assert _bd(when) and when >= today, (now, cid, p)
            assert when <= _band_deadline(products[idx]["days_late"], today), (now, cid, p)
        for cb in exp["callbacks"]:
            assert _bd(D.fromisoformat(cb["date"])), (now, cid, cb)


def test_cases_for_overrides(public_cases):
    cases = {c["id"]: c for c in cases_for("2026-10-23T11:00")}
    assert cases["PUB-02"]["variables"]["now"] == "2026-10-23T11:00"
    assert "Tuesday at eleven" in cases["PUB-02"]["script"]
    assert cases["PUB-03"]["script"] == public_cases["PUB-03"]["script"]
    assert [c["id"] for c in cases_for("2026-10-23T11:00", brief="B")] == ["PUB-11", "PUB-12", "PUB-13"]


def _plans(ns, rt, case, now):
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(case["products"])]
    v = {"now": now, "products": products}
    ns["prep_account"](v, rt)
    return v, json.loads(v["plans_json"])


@pytest.mark.parametrize("now,cid,deadlines,first_offer", [
    ("2026-10-16T11:00", "PUB-06", ["2026-10-28"], "2026-10-23"),   # Cuma → gelecek Cuma
    ("2026-10-23T11:00", "PUB-06", ["2026-11-04"], "2026-10-30"),   # 26 Eki tatil sayılmaz
    ("2026-12-23T11:00", "PUB-06", ["2027-01-05"], "2026-12-24"),   # Cuma 25 tatil → Perşembe
    ("2026-10-16T11:00", "PUB-13", ["2026-11-04", "2026-10-28"], None),
    ("2026-10-23T11:00", "PUB-13", ["2026-11-12", "2026-11-04"], None),
    ("2026-12-23T11:00", "PUB-13", ["2027-01-12", "2027-01-05"], None),
])
def test_runtime_deadlines_and_first_offer(ns, rt_a, public_cases, now, cid, deadlines, first_offer):
    _, plans = _plans(ns, rt_a, public_cases[cid], now)
    assert [p["deadline"] for p in plans] == deadlines
    if first_offer:
        assert plans[0]["attempts"][0]["date"] == first_offer


@pytest.mark.parametrize("now,cid,text,expect", [
    ("2026-10-16T11:00", "PUB-07", "p1:540:2026-10-26", ["2026-10-27"]),
    ("2026-10-23T11:00", "PUB-07", "p1:540:2026-11-11", ["2026-11-12"]),
    ("2026-12-23T11:00", "PUB-07", "p1:540:2027-01-01", ["2027-01-04"]),
    ("2026-10-16T11:00", "PUB-12", "p1:510:2026-10-17; p2:refused; p3:refused", ["2026-10-19"]),   # yarın Cumartesi
    ("2026-10-23T11:00", "PUB-12", "p1:510:2026-10-24; p2:refused; p3:refused", ["2026-10-27"]),   # Pzt tatil
    ("2026-12-23T11:00", "PUB-11", "p1:220:2026-12-25; p2:640:2026-12-25; p3:75:2026-12-25",
     ["2026-12-28", "2026-12-28", "2026-12-28"]),
    ("2026-10-16T11:00", "PUB-13", "p1:300:2026-10-30; p2:900:2026-10-30", ["2026-10-30", "2026-10-28"]),
    ("2026-10-23T11:00", "PUB-13", "p1:300:2026-11-06; p2:900:2026-11-06", ["2026-11-06", "2026-11-04"]),
    ("2026-12-23T11:00", "PUB-13", "p1:300:2027-01-08; p2:900:2027-01-08", ["2027-01-08", "2027-01-05"]),
])
def test_runtime_moves_dates_like_the_fixture(ns, rt_a, public_cases, now, cid, text, expect):
    """Müşterinin söylediği gün kodun düzeltmesinden sonra days.json'daki beklentiyle aynı."""
    v, _ = _plans(ns, rt_a, public_cases[cid], now)
    state, msg, _ = ns["validate_results"](v, text, rt_a)
    assert state == "confirm", msg
    got = [p["date"] for p in json.loads(v["rec_queue"])]
    assert got == expect
    exp = DAYS[now][cid].get("expected", public_cases[cid]["expected"])
    assert got == [p["date"] for p in exp["promises"]]


@pytest.mark.parametrize("now,days,ok,bad", [
    ("2026-10-16T11:00", "2026-10-16,2026-10-19", ("2026-10-19", "11:00"), ("2026-10-17", "11:00")),
    ("2026-10-23T11:00", "2026-10-23,2026-10-27", ("2026-10-27", "11:00"), ("2026-10-26", "11:00")),
    ("2026-12-23T11:00", "2026-12-23,2026-12-24", ("2026-12-24", "11:00"), ("2026-12-25", "11:00")),
])
def test_callback_window_on_days(ns, rt_a, now, days, ok, bad):
    v = {"now": now}
    ns["prep_callback"](v, rt_a)
    assert v["cb_days"] == days
    assert ns["check_callback"](v, *ok, rt_a)[0]
    assert not ns["check_callback"](v, *bad, rt_a)[0]


@pytest.mark.parametrize("now,row,tags", [
    ("2026-10-16T11:00", "2026-10-17", ["tomorrow", "this Saturday", "weekend"]),
    ("2026-10-16T11:00", "2026-10-23", ["next Friday", "business day"]),
    ("2026-10-23T11:00", "2026-10-26", ["next Monday", "HOLIDAY"]),
    ("2026-12-23T11:00", "2026-12-25", ["this Friday", "HOLIDAY"]),
])
def test_day_table_labels(ns, rt_a, public_cases, now, row, tags):
    v, _ = _plans(ns, rt_a, public_cases["PUB-01"], now)
    line = [x for x in v["day_table"].splitlines() if x.startswith(row)][0]
    for t in tags:
        assert t in line, (line, t)
