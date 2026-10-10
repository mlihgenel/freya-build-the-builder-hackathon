"""Altın spec → workflow: statik kontroller, determinizm, snippet'lerin yerel çalışması."""
import json

import pytest

from conftest import KIT, ROOT
from fbb.ingest.openapi import load_catalog
from fbb.runtime.emit import run_snippet
from fbb.spec import PolicySpec
from fbb.workflow.graph import build_workflow, workflow_hash
from fbb.workflow.lint import lint

FIX = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(KIT / "tools" / "openapi.json")


def spec(name):
    return PolicySpec.model_validate(json.loads((FIX / name).read_text()))


@pytest.mark.parametrize("name", ["spec_a.json", "spec_ab.json"])
def test_workflow_lints_clean(cat, name):
    s = spec(name)
    wf = build_workflow(s, cat)
    assert lint(wf, cat, call_vars=s.call_variables.all, forbidden_pre_verify=s.opening.forbidden_before_verification) == []


def test_deterministic(cat):
    assert workflow_hash(build_workflow(spec("spec_a.json"), cat)) == workflow_hash(build_workflow(spec("spec_a.json"), cat))


def test_system_prompt_has_no_purpose_words(cat):
    s = spec("spec_a.json")
    wf = build_workflow(s, cat)
    sp = wf["system_prompt"].lower()
    for w in ("collections", "debt", "past due", "loan"):
        assert w not in sp


def _code_of(node):
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def _tool_code(node, tool):
    t = [x for x in node["tools"] if x["function"]["name"] == tool][0]
    return t["function"]["parameters"]["properties"]["code"]["default"]


def test_identity_loop_locally(cat, public_cases):
    """PUB-01 kimlik akışı: engine'in vereceği cevapları taklit ederek code node'larını sırayla çalıştır."""
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    v = {"now": "2026-10-14T11:00", "customer_id": "c1"}
    run_snippet(_code_of(n["identity_check"]), vars=v)
    assert "date of birth" in v["id_say"]
    v["submit_answer_args.answer"] = "fourteenth of March nineteen eighty-eight"
    run_snippet(_tool_code(n["ask_identity"], "submit_answer"), vars=v)
    assert v["id_ready"] == "yes" and v["id_answer"] == "1988-03-14" and v["id_field"] == "date_of_birth"
    v.update({"id_r_ok": "true", "id_r_verified": "true", "id_r_all": "false", "id_r_left": "3"})
    run_snippet(_code_of(n["id_result"]), vars=v)
    assert v["id_state"] == "asking" and "four digits" in v["id_say"]
    v["submit_answer_args.answer"] = "four four"
    run_snippet(_tool_code(n["ask_identity"], "submit_answer"), vars=v)
    assert v["id_ready"] == ""  # yarım cevap gönderilmez
    v["submit_answer_args.answer"] = "four four seven one"
    run_snippet(_tool_code(n["ask_identity"], "submit_answer"), vars=v)
    assert v["id_answer"] == "4471" and v["id_field"] == "phone_last4"
    v.update({"id_r_ok": "true", "id_r_verified": "true", "id_r_all": "true"})
    run_snippet(_code_of(n["id_result"]), vars=v)
    assert v["id_state"] == "verified"


def test_three_wrong_answers_fail(cat):
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(n["identity_check"]), vars=v)
    v.update({"id_r_ok": "true", "id_r_verified": "false", "id_r_all": "false", "id_r_left": "0"})
    run_snippet(_code_of(n["id_result"]), vars=v)
    assert v["id_state"] == "failed"


def _commit(n, v, results):
    v["submit_results_args.results"] = results
    run_snippet(_tool_code(n["negotiate"], "submit_results"), vars=v)


def test_record_loop_with_failure(cat, public_cases):
    """PUB-10: ilk create_promise başarısız, ikincisi başarılı → tek promise, outcome promise."""
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(public_cases["PUB-10"]["products"])]
    v = {"now": "2026-10-14T11:00", "products": products}
    run_snippet(_code_of(n["prep_account"]), vars=v)
    plan = json.loads(v["plans_json"])[0]
    _commit(n, v, f"p1:{plan['past_due']}:2026-10-16")
    assert v["commit"] == "ready" and v["next_step"] == "record", v.get("commit_msg")
    v["rec_r_ok"] = ""  # 500: mapping boş kalır
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "record"  # bir kez daha denenir
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "end_nr" and v["promises_ok"] == "1"
    assert v["close_outcome"] == "promise" and v["close_kind"] == "noreason"
    assert "text message" in v["closing_speech"] and "recorded" in v["closing_speech"]
    # promise: close_call gövdesinde reason alanı hiç yok (score.py None bekliyor)
    body = n["send_close_nr"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert set(body) == {"customer_id", "outcome"}
    assert n["send_close_nr"]["on_enter"] == {"type": "tts", "text": "{{closing_speech}}"}


def test_record_fails_twice_service_error(cat, public_cases):
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(public_cases["PUB-10"]["products"])]
    v = {"now": "2026-10-14T11:00", "products": products}
    run_snippet(_code_of(n["prep_account"]), vars=v)
    plan = json.loads(v["plans_json"])[0]
    _commit(n, v, f"p1:{plan['past_due']}:2026-10-16")
    for _ in range(2):
        v["rec_r_ok"] = ""
        run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "end_r"
    assert (v["close_outcome"], v["close_reason"]) == ("no_promise", "service_error")
    assert "could not record" in v["closing_speech"]


def test_multi_product_notes(cat, public_cases):
    """PUB-12: bir promise, iki 'refused' notu."""
    wf = build_workflow(spec("spec_ab.json"), cat)
    n = wf["nodes"]
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(public_cases["PUB-12"]["products"])]
    v = {"now": "2026-10-14T11:00", "products": products}
    run_snippet(_code_of(n["prep_account"]), vars=v)
    plans = json.loads(v["plans_json"])
    _commit(n, v, f"p1:{plans[0]['past_due']}:2026-10-15; p2:refused; p3:refused")
    assert v["next_step"] == "record", v.get("commit_msg")
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    notes = []
    while v["next_step"] == "note":
        notes.append((v["note_pid"], v["note_reason"]))
        v["note_r_ok"] = "true"
        run_snippet(_code_of(n["note_step"]), vars=v)
    assert notes == [("p2", "refused"), ("p3", "refused")]
    assert v["next_step"] == "end_nr" and v["close_outcome"] == "promise"


def test_transfer_prepares_close(cat):
    wf = build_workflow(spec("spec_ab.json"), cat)
    v = {"title": "Mr", "last_name": "X"}
    run_snippet(_code_of(wf["nodes"]["transfer_restructuring"]), vars=v)
    assert (v["close_outcome"], v["close_reason"]) == ("transferred", "restructuring")
    assert wf["nodes"]["do_transfer"]["transitions"][-1]["target_node"] == "send_close"
    assert wf["tools"] == []  # close_call artık lifecycle değil, hook'suz bir adım


def test_closing_speech_fills_call_variables(cat):
    wf = build_workflow(spec("spec_a.json"), cat)
    v = {"title": "Ms", "last_name": "Almeida", "close_outcome": ""}
    run_snippet(_code_of(wf["nodes"]["close_id_failed"]), vars=v)
    assert v["closing_speech"].endswith("Ms Almeida. Goodbye.") and "{" not in v["closing_speech"]
    assert v["close_outcome"] == "not_verified" and v["close_reason"] == "failed"


def test_every_code_node_has_failure_guard(cat):
    """Kod servisi çalışmazsa değişkenler güncellenmez; koruma olmazsa döngü sonsuza kadar döner (10 Ekim)."""
    wf = build_workflow(spec("spec_ab.json"), cat)
    for name, node in wf["nodes"].items():
        if node["node_type"] == "code":
            first = node["transitions"][0]
            assert first["target_node"] == "end_fallback", name
            assert first["condition"]["conditions"][0]["variable"] == f"{name}_failure_count", name
    assert "{{" not in wf["nodes"]["end_fallback"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"].replace("{{title}}", "").replace("{{last_name}}", "")


def test_third_party_goodbye_has_no_customer_name(cat):
    """PUB-02: telefonu açan eşe müşterinin adıyla veda edilmemeli."""
    wf = build_workflow(spec("spec_a.json"), cat)
    v = {"now": "2026-10-14T11:00", "title": "Ms", "last_name": "Costa"}
    run_snippet(_code_of(wf["nodes"]["close_callback"]), vars=v)
    assert "Costa" not in v["closing_speech"] and v["closing_speech"].endswith("Goodbye.")
    assert (v["close_outcome"], v["close_reason"]) == ("not_reached", "callback")


def test_transfer_close_does_not_repeat_the_transfer_sentence(cat):
    """PUB-09: model transfer cümlesini zaten söylüyor; kapanış tekrar etmemeli."""
    s = spec("spec_a.json")
    wf = build_workflow(s, cat)
    v = {"title": "Mr", "last_name": "Ionescu"}
    run_snippet(_code_of(wf["nodes"]["transfer_restructuring"]), vars=v)
    say = [t.say for t in s.transfers if t.id == "restructuring"][0]
    assert say not in v["closing_speech"]


def test_multi_product_prompt_demands_one_joint_confirmation(cat):
    """PUB-11'de agent her ürün için ayrı onay aldı; brief tek ortak onay istiyor."""
    task = build_workflow(spec("spec_ab.json"), cat)["nodes"]["negotiate"]["task_message"]
    assert "ONE message" in task and "ONCE" in task
    assert "ONE message" not in build_workflow(spec("spec_a.json"), cat)["nodes"]["negotiate"]["task_message"]


def test_close_nodes_route_by_reason(cat):
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    v = {"title": "Mr", "last_name": "Park"}
    run_snippet(_code_of(n["close_id_failed"]), vars=v)
    assert v["close_kind"] == "reason"
    targets = [t["target_node"] for t in n["close_id_failed"]["transitions"]]
    assert targets == ["end_fallback", "send_close_nr", "send_close"]
    assert n["end_main"]["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"] == "none"


def test_day_table_gives_per_product_verdicts(ns, rt_a, public_cases):
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(public_cases["PUB-07"]["products"])]
    v = {"now": "2026-10-14T11:00", "products": products}
    ns["prep_account"](v, rt_a)
    row = [x for x in v["day_table"].splitlines() if x.startswith("2026-10-26")][0]
    assert "HOLIDAY" in row and "offer the next business day 2026-10-27 Tuesday" in row
    late = [x for x in v["day_table"].splitlines() if x.startswith("2026-11-03")][0]
    assert "after its deadline" in late
