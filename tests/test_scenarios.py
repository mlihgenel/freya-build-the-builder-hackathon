"""Kendi canlı senaryolarımız (tests/fixtures/scenarios.json, `fbb scenarios`): fixture tutarlılığı ve
`scenarios_for`'un public vakanın hesabını kendi script/beklentimizle birleştirmesi."""
import datetime
import json

import pytest

from conftest import ROOT
from fbb.days import scenarios_for
from test_days import _add, _band_deadline, _bd

SC = json.loads((ROOT / "tests" / "fixtures" / "scenarios.json").read_text())["scenarios"]
LEDGER_KEYS = {"outcome", "reason", "promises", "notes", "callbacks", "transfers"}


@pytest.mark.parametrize("sid", sorted(SC))
def test_scenario_fixture_shape(sid, public_cases):
    sc = SC[sid]
    assert sc["base"] in public_cases
    assert set(sc["expected"]) == LEDGER_KEYS
    assert sc["script"] and sc["checks"] and sc["why"] and sc["slot"]
    base = public_cases[sc["base"]]
    ids = {f"p{i + 1}" for i in range(len(base["products"]))}
    today = datetime.date.fromisoformat(sc.get("now", base["variables"]["now"])[:10])
    for p in sc["expected"]["promises"]:
        assert p["product_id"] in ids
        prod = base["products"][int(p["product_id"][1:]) - 1]
        d = datetime.date.fromisoformat(p["date"])
        assert _bd(d) and today <= d <= _band_deadline(prod["days_late"], today)
    for n in sc["expected"]["notes"]:
        assert n["product_id"] in ids
    for c in sc["expected"]["callbacks"]:
        d = datetime.date.fromisoformat(c["date"])
        assert d in (today, _add(today, 1)) and "10:00" <= c["time"] <= "19:00"


def test_scenarios_for_uses_base_account(public_cases):
    cases = {c["id"]: c for c in scenarios_for()}
    assert set(cases) == set(SC)
    c = cases["SC-01"]
    assert c["base"] == "PUB-11" and c["products"] == public_cases["PUB-11"]["products"]
    assert c["script"] == SC["SC-01"]["script"] and c["expected"] == SC["SC-01"]["expected"]
    assert c["title"] == SC["SC-01"]["title"]
    assert [x["id"] for x in scenarios_for(only="SC-02,SC-03")] == ["SC-02", "SC-03"]
