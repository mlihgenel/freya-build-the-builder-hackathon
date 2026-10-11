"""Freya içinde çalışacak runtime kodunun testleri. Beklenen değerler brief metninden ve PUB vakalarından."""
import datetime
import json

import pytest

from fbb.runtime.emit import build_snippet, run_snippet

D = datetime.date


def test_parse_now_variants(ns):
    assert ns["parse_now"]("2026-10-14T11:00") == (D(2026, 10, 14), 660)
    assert ns["parse_now"]("2026-10-14 11:00:30Z") == (D(2026, 10, 14), 660)
    assert ns["parse_now"]("2026-10-14") == (D(2026, 10, 14), 0)


def test_deadlines_brief_a(ns, rt_a):
    today = D(2026, 10, 14)
    cal = rt_a["cal"]
    assert ns["add_business_days"](today, 7, cal) == D(2026, 10, 23)  # PUB-04 late band
    assert ns["add_business_days"](today, 12, cal) == D(2026, 11, 2)  # early band, 26 Eki tatil


def test_end_of_week_and_weekday_rules(ns, rt_a):
    cal = rt_a["cal"]
    assert ns["end_of_week_offer"](D(2026, 10, 14), cal) == D(2026, 10, 16)  # PUB-06 Cuma 16 Eki
    assert ns["end_of_week_offer"](D(2026, 10, 16), cal) == D(2026, 10, 23)  # bugün Cuma → gelecek Cuma
    assert ns["this_weekday"](D(2026, 10, 16), 4) == D(2026, 10, 16)
    assert ns["next_weekday"](D(2026, 10, 16), 4) == D(2026, 10, 23)  # Cuma günü "next Friday"
    assert ns["next_business_day"](D(2026, 10, 26), cal) == D(2026, 10, 27)  # PUB-07


def test_band_for(ns, rt_a):
    assert ns["band_for"](3, rt_a["bands"])["name"] == "early"
    assert ns["band_for"](8, rt_a["bands"])["name"] == "late"
    assert ns["band_for"](99, rt_a["bands"]) is None


@pytest.mark.parametrize("text,iso", [
    ("14 March 1988", "1988-03-14"),
    ("the fourteenth of March nineteen eighty-eight", "1988-03-14"),
    ("March 14th, 1988", "1988-03-14"),
    ("14/03/1988", "1988-03-14"),
    ("1988-03-14", "1988-03-14"),
    ("third of June nineteen eighty seven", "1987-06-03"),
    ("twenty-first of July 1990", "1990-07-21"),
    ("July twenty first nineteen ninety", "1990-07-21"),
    ("12 July 1991", "1991-07-12"),
])
def test_parse_spoken_date(ns, text, iso):
    assert ns["parse_spoken_date"](text, "DMY") == iso


def test_digits_and_amounts(ns):
    assert ns["digits_from_speech"]("four four seven one") == "4471"
    assert ns["digits_from_speech"]("forty-four seventy-one") == "4471"
    assert ns["digits_from_speech"]("44 71") == "4471"
    assert ns["normalize_answer"]("digits:4", "four four")[1] == "partial"
    assert ns["normalize_answer"]("digits:4", "2288") == ("2288", "ok")
    assert ns["normalize_amount"]("six hundred thirty-seven point five zero") == 637.5
    assert ns["normalize_amount"]("455") == 455


def _plans(ns, rt, case, now="2026-10-14T11:00"):
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(case["products"])]
    vars = {"now": now, "products": products}
    ns["prep_account"](vars, rt)
    return vars, json.loads(vars["plans_json"])


def test_prep_account_pub13(ns, rt_a, public_cases):
    vars, plans = _plans(ns, rt_a, public_cases["PUB-13"])
    by = {p["product_id"]: p for p in plans}
    late = [p for p in plans if p["band"] == "late"][0]
    early = [p for p in plans if p["band"] == "early"][0]
    assert late["deadline"] == "2026-10-23"  # "loan recorded on its own deadline, 23 October"
    assert early["deadline"] == "2026-11-02"
    assert "2026-10-26 Monday" in vars["day_table"] and "HOLIDAY" in vars["day_table"]
    assert len(by) == 2


def test_prep_account_pub06_floor_attempts(ns, rt_a, public_cases):
    vars, plans = _plans(ns, rt_a, public_cases["PUB-06"])
    p = plans[0]
    assert p["floor"] > 0
    assert p["attempts"][0]["date"] == "2026-10-16"
    assert "Can you make this payment today?" == vars["first_ask"]
    assert p["sentence"].endswith("days late.")


def test_validate_results(ns, rt_a, public_cases):
    vars, plans = _plans(ns, rt_a, public_cases["PUB-11"])
    state, msg, _ = ns["validate_results"](vars, "p1:220:2026-10-16; p2:640:2026-10-16; p3:75:2026-10-16", rt_a)
    assert state == "confirm", msg
    assert len(json.loads(vars["rec_queue"])) == 3
    assert vars["readback_say"].endswith("Do you confirm?") and "Friday 16 October" in vars["readback_say"]
    vars2, _ = _plans(ns, rt_a, public_cases["PUB-11"])
    state, msg, _ = ns["validate_results"](vars2, "p1:220:2026-10-17", rt_a)  # eksik ürünler: modelin hatası
    assert state == "invalid" and "missing" in msg
    state, msg, say = ns["validate_results"](vars2, "p1:10:2026-10-16; p2:refused; p3:refused", rt_a)
    assert state == "invalid_say" and "cannot accept less than" in say
    state, msg, _ = ns["validate_results"](vars2, "p1:66:2026-10-16; p2:refused; p3:dispute", rt_a)
    assert state == "confirm", msg


def test_validate_moves_weekend_and_deadline(ns, rt_a, public_cases):
    """B kural 6 / A kural 20: kod düzeltir ve read-back'te söyler (PUB-13: ortak tarih kredinin deadline'ını aşıyor)."""
    vars, plans = _plans(ns, rt_a, public_cases["PUB-13"])
    late = [p for p in plans if p["band"] == "late"][0]
    early = [p for p in plans if p["band"] == "early"][0]
    text = "; ".join(f"{p['product_id']}:{p['past_due']}:2026-10-30" for p in plans)
    state, msg, _ = ns["validate_results"](vars, text, rt_a)
    assert state == "confirm", msg
    queue = {p["product_id"]: p["date"] for p in json.loads(vars["rec_queue"])}
    assert queue[late["product_id"]] == "2026-10-23" and queue[early["product_id"]] == "2026-10-30"
    assert "latest date I can record" in vars["readback_say"] and "Friday 23 October" in vars["readback_say"]
    vars, plans = _plans(ns, rt_a, public_cases["PUB-07"])
    state, msg, _ = ns["validate_results"](vars, f"p1:{plans[0]['past_due']}:2026-10-26", rt_a)
    assert json.loads(vars["rec_queue"])[0]["date"] == "2026-10-27"
    assert "is not a business day" in vars["readback_say"]
    state, msg, say = ns["validate_results"](vars, f"p1:{plans[0]['past_due']}:2026-10-01", rt_a)
    assert state == "invalid_say" and "already passed" in say


def test_identity_pieces_are_joined(ns, rt_a):
    q4 = {"field": "phone", "ask": "x", "answer_type": "digits:4"}
    qd = {"field": "dob", "ask": "y", "answer_type": "date"}
    rt = dict(rt_a, identity={"questions": [qd, q4], "numeric_date_order": "DMY", "max_wrong_total": 3})
    v = {}
    ns["id_take_answer"](v, rt, "fourteenth of March", 0, "ask_q0")
    assert v["id_go"] == "partial" and v["id_partial"]
    ns["id_take_answer"](v, rt, "nineteen eighty-eight", 0, "ask_q0")
    assert v["id_answer"] == "1988-03-14" and v["id_go"] == "ask_q0:0"
    ns["id_take_answer"](v, rt, "four four", 1, "ask_q1")
    assert v["id_go"] == "partial"
    ns["id_take_answer"](v, rt, "seven one", 1, "ask_q1")
    assert v["id_answer"] == "4471" and v["id_go"] == "ask_q1:1"
    ns["id_take_answer"](v, rt, "double four seven one", 1, "reask")
    assert v["id_answer"] == "4471" and v["id_go"] == "reask:1"


def test_identity_answer_and_question_in_one_message(ns):
    assert ns["normalize_answer"]("date", "twenty one July nineteen ninety. how much do I owe?") == ("1990-07-21", "ok")


def test_swap_hint_month_only_answer(ns, rt_a):
    qd = {"field": "dob", "ask": "y", "answer_type": "date"}
    rt = dict(rt_a, identity={"questions": [qd], "numeric_date_order": "DMY", "max_wrong_total": 3})
    v = {}
    ns["id_take_answer"](v, rt, "04/03/1988", 0, "ask_q0")
    assert v["id_answer"] == "1988-03-04"
    ns["id_take_answer"](v, rt, "April", 0, "reask", True)
    assert v["id_answer"] == "1988-04-03"


@pytest.mark.parametrize("text,example,want", [
    ("S W one A one A A", "SW1A 1AA", "SW1A 1AA"),
    ("sierra whiskey one alpha one alpha alpha", "SW1A 1AA", "SW1A 1AA"),
    ("my postcode is sw1a 1aa", "SW1A 1AA", "SW1A 1AA"),
])
def test_postcode(ns, text, example, want):
    assert ns["normalize_answer"]("postcode", text, "DMY", example) == (want, "ok")


def test_alnum_and_partial(ns):
    assert ns["normalize_answer"]("alnum", "S C one two three four five six", "DMY", "SC123456") == ("SC123456", "ok")
    assert ns["normalize_answer"]("postcode", "S W one A", "DMY", "SW1A 1AA")[1] == "partial"


def test_floor_and_amount_rules(ns):
    rt = {"floor_rule": {"*": "percent:10", "card": "fixed:50"}}
    assert ns["floor_amount"]({}, "loan", 400.0, rt) == 40.0
    assert ns["floor_amount"]({}, "card", 400.0, rt) == 50.0
    assert ns["attempt_amount"]("percent:50", 40.0, 400.0) == 200.0
    assert ns["attempt_amount"]("floor", 0.0, 400.0) == 400.0


def test_floor_max_min_rules(ns):
    rt = {"floor_rule": {"od": "max:percent:25,field:min_due", "car": "min:fixed:100,field:inst"}}
    assert ns["floor_amount"]({"min_due": 50.0}, "od", 400.0, rt) == 100.0     # %25 büyük
    assert ns["floor_amount"]({"min_due": 150.0}, "od", 400.0, rt) == 150.0    # alan büyük
    assert ns["floor_amount"]({"inst": 80.0}, "car", 400.0, rt) == 80.0
    assert ns["floor_amount"]({}, "car", 400.0, rt) == 0.0                     # eksik alan 0 sayılır


def test_deadline_rules(ns, rt_a):
    cal = rt_a["cal"]
    today = D(2026, 10, 14)
    assert ns["deadline_for"]({"deadline_rule": "calendar_days:10", "deadline_bd": 0}, today, cal) == D(2026, 10, 23)
    assert ns["deadline_for"]({"deadline_rule": "end_of_month", "deadline_bd": 0}, today, cal) == D(2026, 10, 30)
    assert ns["deadline_for"]({"deadline_rule": "", "deadline_bd": 7}, today, cal) == D(2026, 10, 23)


def test_overrides_by_date(ns, rt_a):
    rt = dict(rt_a, overrides=[{"effective_from": "2026-11-01", "holidays_add": ["2026-11-02"],
                                "bands": [{"name": "all", "min": 1, "max": 99, "deadline_bd": 3, "attempts": 1}]}])
    assert ns["effective_rt"](rt, D(2026, 10, 14))["bands"] == rt_a["bands"]
    later = ns["effective_rt"](rt, D(2026, 11, 3))
    assert later["bands"][0]["name"] == "all" and "2026-11-02" in later["cal"]["holidays"]


def test_callback_today_only_on_business_day(ns, rt_a):
    v = {"now": "2026-10-17T11:00"}  # Cumartesi
    ns["prep_callback"](v, rt_a)
    assert v["cb_days"] == "2026-10-19"


def test_callback_window(ns, rt_a):
    vars = {"now": "2026-10-14T11:00"}
    ns["prep_callback"](vars, rt_a)
    assert vars["cb_days"] == "2026-10-14,2026-10-15"
    assert ns["check_callback"](vars, "2026-10-15", "11:00", rt_a)[0]  # PUB-02
    assert ns["check_callback"](vars, "2026-10-15", "19:00", rt_a)[0]
    assert not ns["check_callback"](vars, "2026-10-15", "19:30", rt_a)[0]
    assert not ns["check_callback"](vars, "2026-10-14", "10:30", rt_a)[0]  # şimdiden önce
    assert not ns["check_callback"](vars, "2026-10-16", "11:00", rt_a)[0]


@pytest.mark.parametrize("state,expected", [
    ({"promises_ok": "1"}, ("promise", "")),
    ({"promises_ok": "1", "transfer_queue": "restructuring"}, ("transferred", "restructuring")),
    ({"transfer_queue": "general"}, ("transferred", "human")),
    ({"close_fixed_outcome": "not_reached", "close_fixed_reason": "callback"}, ("not_reached", "callback")),
    ({"transfer_ok_support": "true"}, ("transferred", "support")),
    ({"statuses_json": json.dumps([{"product_id": "p1", "reason": "paid"}])}, ("paid", "")),
    ({"statuses_json": json.dumps([{"product_id": "p1", "reason": "paid"},
                                   {"product_id": "p2", "reason": "dispute"}])}, ("no_promise", "dispute")),
    ({"id_state": "verified"}, ("no_promise", "refused")),
    ({}, ("not_verified", "declined")),
])
def test_decide_close(ns, rt_a, state, expected):
    assert ns["decide_close"](state, rt_a) == expected


def test_close_body_drops_reason_for_promise(ns, rt_a):
    body = ns["apply_close_body"]({"promises_ok": "2"}, {"outcome": "x", "reason": "{{reason}}"}, rt_a)
    assert body == {"outcome": "promise"}


def test_snippet_is_self_contained_and_safe(rt_a, public_cases):
    code = build_snippet("prep_account(vars, RT)", rt_a,
                         fallback="vars['account_state'] = 'error'")
    assert "{{" not in code and "}}" not in code
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(public_cases["PUB-11"]["products"])]
    vars = {"now": "2026-10-14T11:00", "products": products}
    run_snippet(code, vars=vars)
    assert vars["account_state"] == "ready" and vars["product_count"] == "3"
    bad = {"now": "garbage"}
    run_snippet(code, vars=bad)  # hata fırlatmaz
    assert bad["account_state"] == "error" and "runtime_error" in bad


def test_products_from_flattened_keys(ns):
    vars = {"get_account_response.data.products.0.product_id": "p1",
            "get_account_response.data.products.0.past_due": "100",
            "get_account_response.data.products.1.product_id": "p2"}
    assert [p["product_id"] for p in ns["read_products"](vars)] == ["p1", "p2"]


def test_differential_deadlines(ns, rt_a):
    """Bağımsız, kaba kuvvet bir hesapla 120 günlük karşılaştırma."""
    cal = rt_a["cal"]
    hol = set(cal["holidays"])

    def brute(start, n):
        d, k = start, 0
        while k < n:
            d += datetime.timedelta(days=1)
            if d.weekday() < 5 and d.isoformat() not in hol:
                k += 1
        return d

    start = D(2026, 10, 10)
    for i in range(120):
        day = start + datetime.timedelta(days=i)
        for n in (1, 7, 12):
            assert ns["add_business_days"](day, n, cal) == brute(day, n)


def test_lone_number_is_partial_date(ns):
    """asks_back PUB-03: 'It is 1…' doğrulamaya gitmesin, sistem kalanını sorsun."""
    assert ns["normalize_answer"]("date", "It is 1")[1] == "partial"
    assert ns["normalize_answer"]("date", "I don't know")[1] == "unreadable"
    assert ns["combine_answer"]({"answer_type": "date"}, "12 July 1991", "1") == ("1991-07-12", "ok")
