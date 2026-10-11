"""specdiff: iki spec arasındaki puan, metin ve bilgi farkları."""
import json

from conftest import ROOT
from fbb.specdiff import diff, load

FIX = ROOT / "tests" / "fixtures"


def _spec(name):
    return load(FIX / name)


def test_same_spec_has_no_difference():
    d = diff(_spec("spec_a.json"), _spec("spec_a.json"))
    assert d == {"PUAN": [], "METİN": [], "BİLGİ": []}


def test_order_and_names_do_not_count():
    a, b = _spec("spec_a.json"), _spec("spec_a.json")
    b["bands"] = list(reversed(b["bands"]))
    b["calendar"]["holidays"] = list(reversed(b["calendar"]["holidays"]))
    b["statuses"] = list(reversed(b["statuses"]))
    b["confirmation"]["confirm_question"] = b["confirmation"]["confirm_question"].upper() + "  "
    assert diff(a, b)["PUAN"] == [] and diff(a, b)["METİN"] == []


def test_score_and_text_differences_are_found():
    a, b = _spec("spec_a.json"), _spec("spec_a.json")
    b["bands"][0]["deadline_bd"] += 1
    b["calendar"]["holidays"] = b["calendar"]["holidays"][1:]
    b["disclosure"]["floor_rule"] = {"credit_card": "percent:10"}
    b["negotiation"]["floor_note"] = ""
    b["closing"]["goodbye_sentence"] = "Bye."
    d = diff(a, b)
    paths = [p for p, _, _ in d["PUAN"]]
    assert "bands.0.deadline_bd" in paths and "calendar.holidays" in paths and "floor.credit_card" in paths
    assert [p for p, _, _ in d["METİN"]] == ["negotiation.floor_note"]
    assert any(p == "closing.goodbye_sentence" for p, _, _ in d["BİLGİ"])


def test_ab_differs_from_a_only_where_expected():
    d = diff(_spec("spec_ab.json"), _spec("spec_a.json"))
    paths = {p.split(".")[0] for p, _, _ in d["PUAN"]}
    assert "multi_product" in paths
    assert json.dumps(d["PUAN"]).count("calendar") == 0


def test_identity_status_mapping_and_override_note_are_not_score_diffs():
    """C ikili çıkarımı (11 Eki): status_to_reason'da {'refused': 'refused'} ile boş eşleme aynıdır (closing.py
    .get(r, r)); override'ın açıklama notu puanı etkilemez."""
    import json

    from conftest import ROOT
    from fbb.specdiff import diff

    a = json.loads((ROOT / "tests" / "fixtures" / "variants" / "spec_c_expected.json").read_text())
    b = json.loads(json.dumps(a))
    b["closing"]["status_to_reason"] = {}
    b["overrides"][0]["note"] = "another wording"
    assert diff(a, b)["PUAN"] == []
    b["closing"]["status_to_reason"] = {"disputed": "dispute"}
    assert [d[0] for d in diff(a, b)["PUAN"]] == ["closing.status_to_reason.disputed"]
