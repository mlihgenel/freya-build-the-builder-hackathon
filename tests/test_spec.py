"""Spec şeması, openapi okuyucu ve spec → RT derlemesi."""
import json

import pytest
from pydantic import ValidationError

from conftest import KIT, ROOT, RT_A
from fbb.ingest.openapi import load_catalog
from fbb.spec import PolicySpec, cross_check, to_runtime

FIX = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(KIT / "tools" / "openapi.json")


def load(name):
    return PolicySpec.model_validate(json.loads((FIX / name).read_text()))


def test_catalog(cat):
    assert set(cat.tools) == {"verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
                              "transfer_to_agent", "close_call"}
    assert cat.url("close_call").endswith("/v1/close_call")
    assert cat.enum("verify_identity", "field") == ["date_of_birth", "phone_last4"]
    assert "car_loan" in cat.enum("get_account", "products[].type")
    assert cat.tools["create_promise"].fields["amount"].type == "number"


@pytest.mark.parametrize("name", ["spec_a.json", "spec_ab.json"])
def test_fixtures_valid_and_consistent(cat, name):
    spec = load(name)
    assert cross_check(spec, cat) == []


def test_cross_check_catches_bad_enum(cat):
    spec = load("spec_a.json")
    spec.transfers[0].queue = "nope"
    assert any("nope" in e for e in cross_check(spec, cat))


def test_overlapping_bands_rejected():
    data = json.loads((FIX / "spec_a.json").read_text())
    data["bands"][1]["min"] = 5
    with pytest.raises(ValidationError):
        PolicySpec.model_validate(data)


def test_runtime_matches_hand_rt():
    rt = to_runtime(load("spec_a.json"))
    for key in ("cal", "bands", "floor_field", "product_wording", "attempts", "callback", "status_reasons"):
        assert rt[key] == RT_A[key], key
    assert rt["closing"]["transfer_reasons"] == RT_A["closing"]["transfer_reasons"]
