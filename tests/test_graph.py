"""Altın spec → workflow: statik kontroller, determinizm, snippet'lerin yerel çalışması, route'ların simülasyonu."""
import json

import pytest

from conftest import KIT, ROOT
from fbb.ingest.openapi import load_catalog
from fbb.runtime.emit import run_snippet
from fbb.spec import PolicySpec, cross_check, resolve_response_fields
from fbb.workflow.graph import build_workflow, workflow_hash
from fbb.workflow.lint import lint

FIX = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def cat():
    return load_catalog(KIT / "tools" / "openapi.json")


def spec(name):
    return PolicySpec.model_validate(json.loads((FIX / name).read_text()))


def _lint(wf, s, cat, warnings=None):
    return lint(wf, cat, call_vars=s.call_variables.all,
                forbidden_pre_verify=s.opening.forbidden_before_verification, warnings=warnings)


@pytest.mark.parametrize("name", ["spec_a.json", "spec_ab.json"])
def test_workflow_lints_clean(cat, name):
    s = spec(name)
    wf = build_workflow(s, cat)
    warnings = []
    assert _lint(wf, s, cat, warnings) == []
    assert warnings == []
    assert len(json.dumps(wf)) < 340_000  # her snippet RT'yi gömüyor; boyut F-08'de denenenin yakınında kalmalı


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


def _route(node, v):
    """Platformun deterministik route kararını taklit eder: sıradaki ilk eşleşen koşul (matches_intent hariç)."""
    def check(c):
        if "conditions" in c:
            res = [check(x) for x in c["conditions"]]
            return all(res) if c.get("logic") == "and" else any(res)
        op = c.get("operator")
        val = v.get(c.get("variable"))
        if op == "always":
            return True
        if op == "equals":
            return val is not None and str(val) == str(c["operand"])
        if op == "greater_than":
            try:
                return float(val) > float(c["operand"])
            except (TypeError, ValueError):
                return False
        return False
    for t in node["transitions"]:
        if not t.get("is_tool_call") and t["condition"].get("operator") != "matches_intent" and check(t["condition"]):
            return t["target_node"]
    return None


def _body(node):
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]


def test_identity_happy_path_has_no_code_nodes(cat):
    """PUB-01: soru → submit_answer → verify (api) → sonraki soru: arada code node'u yok (gecikme)."""
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    assert "date of birth" in n["ask_q0"]["on_enter"]["text"]
    v = {"now": "2026-10-14T11:00", "customer_id": "c1"}
    v["submit_answer_args.answer"] = "fourteenth of March nineteen eighty-eight"
    run_snippet(_tool_code(n["ask_q0"], "submit_answer"), vars=v)
    assert v["id_answer"] == "1988-03-14" and _route(n["ask_q0"], v) == "verify_q0"
    assert _body(n["verify_q0"])["field"]["default"] == "date_of_birth"
    assert _body(n["verify_q0"])["answer"]["default"] == "{{id_answer}}"
    v.update({"id_r_ok": "true", "id_r_verified": "true", "id_r_all": "false", "id_r_left": "3", "id_go": "200"})
    assert _route(n["verify_q0"], v) == "ask_q1"
    assert "four digits" in n["ask_q1"]["on_enter"]["text"]
    v["submit_answer_args.answer"] = "four four"
    run_snippet(_tool_code(n["ask_q1"], "submit_answer"), vars=v)
    assert _route(n["ask_q1"], v) == "id_fix"  # yarım cevap gönderilmez; sistem eksik kısmı sorar
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert v["id_say"] == "Thank you. And the rest, please?"
    v["submit_answer_args.answer"] = "seven one"
    run_snippet(_tool_code(n["ask_q1"], "submit_answer"), vars=v)
    assert v["id_answer"] == "4471" and _route(n["ask_q1"], v) == "verify_q1"
    v.update({"id_r_ok": "True", "id_r_verified": "True", "id_r_all": "True"})
    assert _route(n["verify_q1"], v) == "fetch_account"


def test_identity_wrong_swap_and_service_error(cat):
    wf = build_workflow(spec("spec_a.json"), cat)
    n = wf["nodes"]
    v = {"now": "2026-10-14T11:00", "submit_answer_args.answer": "04/03/1988"}
    run_snippet(_tool_code(n["ask_q0"], "submit_answer"), vars=v)
    v.update({"id_r_ok": "true", "id_r_verified": "false", "id_r_left": "3", "id_r_hint": "day_month_swapped"})
    assert _route(n["verify_q0"], v) == "id_fix"
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert "month" in v["id_say"] and v["id_swap"] == "1" and v["id_go"] == ""
    v["submit_answer_args.answer"] = "April"
    run_snippet(_tool_code(n["reask"], "submit_answer"), vars=v)
    assert v["id_answer"] == "1988-04-03" and _route(n["reask"], v) == "verify_q0"
    # yanlış cevap: "That does not match" + aynı soru
    v.update({"id_r_ok": "true", "id_r_verified": "false", "id_r_left": "2", "id_r_hint": ""})
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert v["id_say"].startswith("That does not match") and "date of birth" in v["id_say"]
    # servis hatası (500): mapping boş → 'eşleşmiyor' DENMEZ
    v["submit_answer_args.answer"] = "14 March 1988"
    run_snippet(_tool_code(n["reask"], "submit_answer"), vars=v)
    assert v["id_r_verified"] == ""
    assert _route(n["verify_q0"], v) == "id_fix"
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert "does not match" not in v["id_say"] and "could not check" in v["id_say"]
    assert n["verify_q0"]["pre_actions"][0]["config"]["maxRetries"] == 1


def test_wrong_second_answer_reasks_the_second_question(cat):
    """PUB-12 (10 Eki 20:45, 3/3 düştü): telefon yanlışsa tekrar telefon sorulur, doğum tarihi değil."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {"submit_answer_args.answer": "four four zero one"}
    run_snippet(_tool_code(n["ask_q1"], "submit_answer"), vars=v)
    v.update({"id_r_ok": "true", "id_r_verified": "false", "id_r_left": "2", "id_r_all": "false"})
    assert _route(n["verify_q1"], v) == "id_fix"
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert "four digits" in v["id_say"] and "date of birth" not in v["id_say"]
    v["submit_answer_args.answer"] = "four four one zero"
    run_snippet(_tool_code(n["reask"], "submit_answer"), vars=v)
    assert v["id_answer"] == "4410" and _route(n["reask"], v) == "verify_q1"


@pytest.mark.parametrize("parts,iso", [
    (["The fourteenth of March one nine eight eight"], "1988-03-14"),           # in_words: yıl rakam rakam
    (["8 January", "Nineteen", "Ninety-one"], "1991-01-08"),                    # pieces: yıl iki parça
    (["Nine September", "Nineteen", "Ninety"], "1990-09-09"),
    (["14 March", "19", "88"], "1988-03-14"),                                    # pieces A PUB-01 (2095 oluyordu)
])
def test_partial_dates_from_style_runs(cat, parts, iso):
    """10 Eki stil koşuları: eksik cevapta model bekledi ('one moment' döngüsü). Sistem eksik kısmı sorar."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    node = "ask_q0"
    for i, part in enumerate(parts):
        v["submit_answer_args.answer"] = part
        run_snippet(_tool_code(n[node], "submit_answer"), vars=v)
        if i < len(parts) - 1:
            assert _route(n[node], v) == "id_fix", part
            run_snippet(_code_of(n["id_fix"]), vars=v)
            assert v["id_say"].startswith("Thank you. And") and _route(n["id_fix"], v) == "reask"
            node = "reask"
    assert v["id_answer"] == iso and _route(n[node], v) == "verify_q0"


def test_decline_on_second_question_reasks_second_question(cat):
    """asks_back PUB-12: 2. soruda amaç sorusu → açıklama + yine 2. soru (DOB değil)."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {"id_q": "0"}
    run_snippet(_tool_code(n["ask_q1"], "decline_questions"), vars=v)
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert v["id_say"].startswith("These questions protect") and "date of birth" not in v["id_say"]
    v["submit_answer_args.answer"] = "four four one zero"
    run_snippet(_tool_code(n["reask"], "submit_answer"), vars=v)
    assert v["id_answer"] == "4410" and _route(n["reask"], v) == "verify_q1"  # cevap 2. soruya gider


def test_full_year_after_pieces_wins(cat):
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {"id_partial": "14 March 19", "id_partial_q": "0", "submit_answer_args.answer": "1988"}
    run_snippet(_tool_code(n["reask"], "submit_answer"), vars=v)
    assert v["id_answer"] == "1988-03-14"


def test_three_wrong_answers_fail(cat):
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {"id_r_ok": "true", "id_r_verified": "false", "id_r_all": "false", "id_r_left": "0"}
    assert _route(n["verify_q1"], v) == "close_id_failed"


def test_decline_explains_once_then_closes(cat):
    """PUB-03: ret açıklaması bir kez söylenir (sayaç kodda), ikinci retta kapanır."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    run_snippet(_tool_code(n["ask_q0"], "decline_questions"), vars=v)
    assert _route(n["ask_q0"], v) == "id_fix"
    run_snippet(_code_of(n["id_fix"]), vars=v)
    assert v["id_say"].startswith("These questions protect") and v["id_decl"] == ""
    run_snippet(_tool_code(n["reask"], "decline_questions"), vars=v)
    assert _route(n["reask"], v) == "close_id_declined"


def _account(n, v, case, name):
    products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(case["products"])]
    v.update({"now": "2026-10-14T11:00", "products": products})
    run_snippet(_code_of(n["prep_account"]), vars=v)
    return json.loads(v["plans_json"])


def _propose(n, v, results, node="negotiate"):
    v["propose_results_args.results"] = results
    run_snippet(_tool_code(n[node], "propose_results"), vars=v)
    return _step(n, v, _route(n[node], v))


def _step(n, v, route):
    """Tool'un kaydettiği girdi tek bir code node'unda işlenir (offer_step / propose_step)."""
    while route in ("offer_step", "propose_step"):
        run_snippet(_code_of(n[route]), vars=v)
        route = _route(n[route], v)
    return route


def test_readback_then_record_with_retry(cat, public_cases):
    """PUB-10: read-back kodla üretilir; onaydan sonra kayıt; ilk create_promise başarısız → tekrar → ok."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    plan = _account(n, v, public_cases["PUB-10"], "spec_a")[0]
    assert v["close_outcome"] == "no_promise"  # erken yazılan yedek outcome (telefon kapanırsa)
    assert _propose(n, v, f"p1:{plan['past_due']}:2026-10-16") == "readback"
    assert plan["wording"] in v["readback_say"] and "Friday 16 October" in v["readback_say"]
    assert v["readback_say"].endswith("Do you confirm?") and "recorded" not in v["readback_say"]
    assert n["readback"]["on_enter"] == {"type": "tts", "text": "{{readback_say}}"}
    targets = [t["target_node"] for t in n["readback"]["transitions"] if t["condition"]["operator"] == "matches_intent"]
    assert targets[:2] == ["record_promise", "readback_reset"]
    assert v["rec_pid"] == "p1" and v["rec_date"] == "2026-10-16"
    v["rec_r_ok"] = ""  # 500: mapping boş kalır
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "record" and v["commit"] == ""
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "end_nr" and v["promises_ok"] == "1"
    assert v["close_outcome"] == "promise" and v["close_kind"] == "noreason"
    assert "text message" in v["closing_speech"] and "recorded" in v["closing_speech"]
    assert set(_body(n["send_close_nr"])) == {"customer_id", "outcome"}
    assert n["send_close_nr"]["on_enter"] == {"type": "tts", "text": "{{closing_speech}}"}
    assert n["send_close_nr"]["pre_actions"][0]["config"]["maxRetries"] == 2


def test_readback_rejected_goes_back_without_recording(cat, public_cases):
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    plan = _account(n, v, public_cases["PUB-10"], "spec_a")[0]
    _propose(n, v, f"p1:{plan['past_due']}:2026-10-16")
    run_snippet(_code_of(n["readback_reset"]), vars=v)
    assert v["commit"] == "" and v["rec_queue"] == "[]"
    assert _route(n["readback_reset"], v) == "negotiate_fix"
    assert n["negotiate_fix"]["on_enter"] == {"type": "llm", "prompt": "{{fix_prompt}}"}
    assert "recorded" not in v["fix_prompt"].replace("nothing was recorded", "")


def test_invalid_proposal_is_said_by_tts(cat, public_cases):
    """Dürüstlük: geçersiz teklifte müşteriye söylenen cümle kodla üretilir (model 'recorded' diyemez)."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    plan = _account(n, v, public_cases["PUB-06"], "spec_a")[0]
    assert _propose(n, v, "p1:1:2026-10-16") == "commit_fix"
    run_snippet(_code_of(n["commit_fix"]), vars=v)
    assert _route(n["commit_fix"], v) == "negotiate_fix_say"
    assert n["negotiate_fix_say"]["on_enter"] == {"type": "tts", "text": "{{commit_say}}"}
    assert "cannot accept less than" in v["commit_say"] and str(int(plan["floor"])) in v["commit_say"]
    assert _propose(n, v, "px:1:2026-10-16", "negotiate_fix_say") == "commit_fix"
    run_snippet(_code_of(n["commit_fix"]), vars=v)
    assert _route(n["commit_fix"], v) == "negotiate_fix" and "unknown product_id" in v["fix_prompt"]


def test_record_fails_twice_service_error(cat, public_cases):
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    plan = _account(n, v, public_cases["PUB-10"], "spec_a")[0]
    _propose(n, v, f"p1:{plan['past_due']}:2026-10-16")
    for _ in range(2):
        v["rec_r_ok"] = ""
        run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "end_r"
    assert (v["close_outcome"], v["close_reason"]) == ("no_promise", "service_error")
    assert "could not record" in v["closing_speech"]


def test_multi_product_notes(cat, public_cases):
    """PUB-12: bir promise, iki 'refused' notu."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _propose(n, v, f"p1:{plans[0]['past_due']}:2026-10-15; p2:refused; p3:refused") == "readback"
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    notes = []
    while v["next_step"] == "note":
        notes.append((v["note_pid"], v["note_reason"]))
        v["note_r_ok"] = "true"
        run_snippet(_code_of(n["note_step"]), vars=v)
    assert notes == [("p2", "refused"), ("p3", "refused")]
    assert v["next_step"] == "end_nr" and v["close_outcome"] == "promise"


def test_statuses_only_go_straight_to_notes(cat, public_cases):
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _propose(n, v, "p1:paid; p2:dispute; p3:paid") == "record_note"


def test_per_product_mode(cat, public_cases):
    """recording.mode=per_product: her ürün onaylanınca kaydedilir, sonra sıradaki ürüne dönülür; notlar en sonda."""
    s = spec("spec_ab.json")
    s.recording.mode = "per_product"
    wf = build_workflow(s, cat)
    assert _lint(wf, s, cat) == []
    n = wf["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _propose(n, v, f"p1:{plans[0]['past_due']}:2026-10-15") == "readback"
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "more" and _route(n["rec_step"], v) == "negotiate_more"
    assert "recorded" in v["progress_say"] and plans[1]["wording"] in v["progress_say"]
    assert _propose(n, v, "p2:refused; p3:refused", "negotiate_more") == "record_note"
    for _ in range(2):
        v["note_r_ok"] = "true"
        run_snippet(_code_of(n["note_step"]), vars=v)
    assert v["next_step"] == "end_nr" and v["close_outcome"] == "promise"
    assert "recorded" not in v["closing_speech"]  # zaten söylendi


def test_transfers_are_static(cat):
    """Transfer kodsuz: sabit kuyruk, ardından sabit outcome/reason ile kapanış (PUB-09)."""
    s = spec("spec_ab.json")
    n = build_workflow(s, cat)["nodes"]
    t = n["transfer_restructuring"]
    assert t["node_type"] == "api_request" and _body(t)["queue"]["default"] == "restructuring"
    c = n["close_transfer_restructuring"]
    assert _body(c)["outcome"]["default"] == "transferred" and _body(c)["reason"]["default"] == "restructuring"
    say = [x.say for x in s.transfers if x.id == "restructuring"][0]
    assert say not in c["on_enter"]["text"] and c["on_enter"]["text"].endswith("Goodbye.")
    assert _body(n["close_transfer_human"])["reason"]["default"] == "human"


def test_lifecycle_close_backup(cat):
    """Müşteri telefonu kapatırsa: yedek close_call durumdan kurulur. Normal yolda (close_r_ok) istek gitmez."""
    wf = build_workflow(spec("spec_a.json"), cat)
    backup = wf["tools"][0]
    assert backup["config"]["alwaysRunsAt"] == ["end_of_call"] and backup["function"]["name"] == "close_call"
    hook = backup["pre_process_code"]
    config = {"url": "https://x/close_call", "body": {"customer_id": "c", "outcome": "", "reason": ""}}
    run_snippet(hook, vars={"promises_ok": "1"}, config=config)
    assert config["body"] == {"customer_id": "c", "outcome": "promise"} and config["url"]
    config = {"url": "https://x/close_call", "body": {"customer_id": "c", "outcome": "x", "reason": "y"}}
    run_snippet(hook, vars={"id_state": "verified"}, config=config)
    assert config["body"]["outcome"] == "no_promise" and config["body"]["reason"] == "refused"
    config = {"url": "https://x/close_call", "body": {"customer_id": "c", "outcome": "x"}}
    run_snippet(hook, vars={"close_r_ok": "true", "promises_ok": "1"}, config=config)
    assert config["url"] == ""


def test_static_closes_have_no_code(cat):
    s = spec("spec_a.json")
    n = build_workflow(s, cat)["nodes"]
    c = n["close_id_failed"]
    assert c["node_type"] == "api_request"
    assert _body(c)["outcome"]["default"] == "not_verified" and _body(c)["reason"]["default"] == "failed"
    assert c["on_enter"]["text"].startswith(s.identity.fail_sentence)
    assert c["on_enter"]["text"].endswith("{{title}} {{last_name}}. Goodbye.")
    # PUB-02: telefonu açan eşe müşterinin adıyla veda edilmez
    cb = n["close_callback"]
    assert "{{last_name}}" not in cb["on_enter"]["text"] and cb["on_enter"]["text"].endswith("Goodbye.")
    assert (_body(cb)["outcome"]["default"], _body(cb)["reason"]["default"]) == ("not_reached", "callback")
    assert all(t["target_node"] == "end_main" for t in c["transitions"])


def test_every_code_node_has_failure_guard(cat):
    """Kod servisi çalışmazsa değişkenler güncellenmez; koruma olmazsa döngü sonsuza kadar döner (10 Ekim)."""
    wf = build_workflow(spec("spec_ab.json"), cat)
    for name, node in wf["nodes"].items():
        if node["node_type"] == "code":
            targets = [t["target_node"] for t in node["transitions"] if t["target_node"] != "fallback_promise"][:2]
            assert targets == ["fallback_close_nr", "fallback_close"], name
    fb = wf["nodes"]["fallback_close"]
    assert fb["node_type"] == "api_request" and "{{last_name}}" not in fb["on_enter"]["text"]
    assert set(_body(wf["nodes"]["fallback_close_nr"])) == {"customer_id", "outcome"}


def test_third_party_sets_early_outcome(cat):
    wf = build_workflow(spec("spec_a.json"), cat)
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(wf["nodes"]["third_party"]), vars=v)
    assert (v["close_outcome"], v["close_reason"]) == ("not_reached", "no_callback")
    assert v["cb_days"] == "2026-10-14,2026-10-15"
    assert _route(wf["nodes"]["third_party_book"], {"cb_r_ok": "true"}) == "close_callback"
    assert _route(wf["nodes"]["third_party_book"], {"cb_r_ok": ""}) == "close_no_callback"


def test_multi_product_prompt_leaves_readback_to_system(cat):
    task = build_workflow(spec("spec_ab.json"), cat)["nodes"]["negotiate"]["task_message"]
    assert "Do NOT read the promises back" in task and "propose_results ONCE" in task


def test_opener_uses_max_asks(cat):
    s = spec("spec_a.json")
    s.opening.max_asks = 3
    task = build_workflow(s, cat)["nodes"]["opener"]["task_message"]
    assert "3 times in total" in task and "third ask" in task


def test_customer_callback(cat):
    s = spec("spec_a.json")
    s.customer_callback.enabled = True
    s.customer_callback.trigger = "The customer says they cannot talk now and asks to be called later."
    s.customer_callback.ask = "When should we call you back?"
    s.customer_callback.outcome.outcome = "no_promise"
    s.customer_callback.outcome.reason = "refused"
    wf = build_workflow(s, cat)
    assert _lint(wf, s, cat) == []
    n = wf["nodes"]
    assert any(t["target_node"] == "cust_cb" for t in n["negotiate"]["transitions"])
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(n["cust_cb"]), vars=v)
    assert v["cb_kind"] == "customer"
    v.update({"check_callback_time_args.date": "2026-10-15", "check_callback_time_args.time": "11:00"})
    run_snippet(_tool_code(n["cust_cb_talk"], "check_callback_time"), vars=v)
    assert v["cb_state"] == "ok" and _route(n["cust_cb_talk"], v) == "cust_cb_book"


def _variant_catalog(tmp_path):
    """Gizli brief provası: alan adları ve cevap alanları değişmiş, fazladan zorunlu alanlı bir openapi."""
    api = json.loads((KIT / "tools" / "openapi.json").read_text())
    paths = api["paths"]
    vi = paths["/verify_identity"]["post"]
    vi["requestBody"]["content"]["application/json"]["schema"]["properties"]["field"]["enum"] = ["postcode",
                                                                                                "birth_year"]
    resp = vi["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
    resp["passed"] = resp.pop("verified")
    resp["all_passed"] = resp.pop("all_verified")
    resp["attempts_remaining"] = resp.pop("wrong_answers_left")
    acc = paths["/get_account"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
    acc["accounts"] = acc.pop("products")
    items = acc["accounts"]["items"]["properties"]
    items["account_id"] = items.pop("product_id")
    items["kind"] = items.pop("type")
    items["kind"]["enum"] = ["mortgage", "overdraft"]
    items["amount_overdue"] = items.pop("past_due")
    items["days_overdue"] = items.pop("days_late")
    cp = paths["/create_promise"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    cp["properties"]["currency"] = {"type": "string", "enum": ["EUR"]}
    cp["properties"]["channel"] = {"type": "string"}
    cp["required"] += ["currency", "channel"]
    cp_resp = paths["/create_promise"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    cp_resp["properties"].pop("ok")
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(api))
    return load_catalog(path)


def test_variant_openapi_does_not_crash(tmp_path):
    """G-01 / review B.7-10: alan adları değişse de build çökmez, cevap alanları eşlenir, eksik zorunlu alan uyarıdır."""
    vcat = _variant_catalog(tmp_path)
    data = json.loads((FIX / "spec_a.json").read_text())
    data["identity"]["questions"] = [
        {"field": "postcode", "ask": "What is the postcode of your address?", "answer_type": "postcode",
         "example": "SW1A 1AA"},
        {"field": "birth_year", "ask": "Which year were you born?", "answer_type": "year", "example": ""}]
    data["disclosure"]["product_wording"] = {"mortgage": "mortgage", "overdraft": "overdraft"}
    data["disclosure"]["floor_field"] = {}
    data["disclosure"]["floor_rule"] = {"*": "percent:10"}
    s = PolicySpec.model_validate(data)
    notes = resolve_response_fields(s, vcat)
    assert s.response_fields.verified == "passed" and s.response_fields.all_verified == "all_passed"
    assert s.response_fields.wrong_answers_left == "attempts_remaining"
    assert s.response_fields.products == "accounts" and s.response_fields.product_id == "account_id"
    assert s.response_fields.product_type == "kind" and s.response_fields.past_due == "amount_overdue"
    assert s.response_fields.days_late == "days_overdue" and notes
    assert cross_check(s, vcat) == []
    wf = build_workflow(s, vcat)
    warnings = []
    assert _lint(wf, s, vcat, warnings) == []
    assert any("channel" in w for w in warnings)  # tek değerli enum (currency) doldurulur; 'channel' uyarı
    n = wf["nodes"]
    assert _body(n["record_promise"])["currency"]["default"] == "EUR"
    assert n["record_promise"]["response_mapping"][0]["path"] == "status"  # ok alanı yok → zarfın status'u
    assert n["fetch_account"]["response_mapping"][0]["path"] == "data.accounts"
    s.tool_constants = {"create_promise": {"channel": "phone"}}
    warnings = []
    assert _lint(build_workflow(s, vcat), s, vcat, warnings) == [] and warnings == []
    # ürünler yeni alan adlarıyla okunur
    v = {"now": "2026-10-14T11:00", "products": [{"account_id": "a1", "kind": "mortgage", "amount_overdue": 900,
                                                 "days_overdue": 10}]}
    run_snippet(_code_of(n["prep_account"]), vars=v)
    plan = json.loads(v["plans_json"])[0]
    assert plan["product_id"] == "a1" and plan["past_due"] == 900 and plan["floor"] == 90 and plan["band"] == "late"
    v["submit_answer_args.answer"] = "S W one A one A A"
    run_snippet(_tool_code(n["ask_q0"], "submit_answer"), vars=v)
    assert v["id_answer"] == "SW1A 1AA"
    v.update({"id_r_all": "True"})
    assert _route(n["verify_q0"], v) == "fetch_account"


def test_per_question_body_fields(tmp_path):
    """verify_identity soru başına ayrı gövde alanı isterse ('field' alanı yok)."""
    api = json.loads((KIT / "tools" / "openapi.json").read_text())
    sch = api["paths"]["/verify_identity"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    sch["properties"] = {"customer_id": {"type": "string"}, "date_of_birth": {"type": "string"},
                         "phone_last4": {"type": "string"}}
    sch["required"] = ["customer_id"]
    path = tmp_path / "o.json"
    path.write_text(json.dumps(api))
    vcat = load_catalog(path)
    s = spec("spec_a.json")
    wf = build_workflow(s, vcat)
    assert _lint(wf, s, vcat) == []
    assert set(_body(wf["nodes"]["verify_q1"])) == {"customer_id", "phone_last4"}
    s.identity.verify_mode = "all_at_once"
    wf = build_workflow(s, vcat)
    assert _lint(wf, s, vcat) == []
    assert _body(wf["nodes"]["verify_all"])["date_of_birth"]["default"] == "{{id_ans_0}}"
    assert _route(wf["nodes"]["ask_q0"], {"id_go": "ask_q0:0"}) == "ask_q1"
    assert _route(wf["nodes"]["ask_q1"], {"id_go": "ask_q1:1"}) == "verify_all"


def test_model_argument_with_quotes_does_not_break_snippet(cat):
    """ARG_x şablonu: argüman tırnakla ya da ters bölüyle bitse de snippet derlenir."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    code = _tool_code(n["ask_q0"], "submit_answer")
    for arg in ["it's 14 March 1988'", "14 March 1988\\", 'he said "fourteenth"']:
        filled = code.replace("{{answer}}", arg)
        compile(filled, "<x>", "exec")
        v = {}
        run_snippet(filled, vars=v)
        assert v.get("runtime_error") is None


def _offer(n, v, result, node="negotiate", amount="", date=""):
    v["check_offer_answer_args.result"] = result
    v["check_offer_answer_args.agreed_amount"] = amount
    v["check_offer_answer_args.agreed_date"] = date
    run_snippet(_tool_code(n[node], "check_offer_answer"), vars=v)
    route = _step(n, v, _route(n[node], v))
    if route == "commit_fix":
        run_snippet(_code_of(n["commit_fix"]), vars=v)
        route = _route(n["commit_fix"], v)
    return route


def test_floor_offered_once_on_attempt_date(cat, public_cases):
    """PUB-06: 'tam tutar çok fazla' → floor bir kez, 1. denemenin tarihiyle (bugün değil) ve kalan-borç notuyla."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    plan = _account(n, v, public_cases["PUB-06"], "spec_a")[0]
    assert plan["band"] == "late" and "refusal 1" not in v["product_facts"]
    assert _offer(n, v, "too_much") == "negotiate_fix_say"
    floor = f"{plan['floor']:.2f}"
    assert floor in v["commit_say"] and "Friday 16 October" in v["commit_say"]
    assert v["commit_say"].endswith("The rest stays overdue.") and "today" not in v["commit_say"]
    assert n["negotiate_fix_say"]["on_enter"] == {"type": "tts", "text": "{{commit_say}}"}
    assert _offer(n, v, "too_much", "negotiate_fix_say") == "negotiate_fix_say"  # ikinci 'çok fazla' = ret
    assert "Friday 23 October" in v["commit_say"] and "overdue" not in v["commit_say"]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "send_close"  # deneme kalmadı → refused ile kapanış
    assert v["close_outcome"] == "no_promise" and v["close_reason"] == "refused"


def test_floor_agreed_goes_to_readback(cat, public_cases):
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    plan = _account(n, v, public_cases["PUB-06"], "spec_a")[0]
    assert _offer(n, v, "too_much") == "negotiate_fix_say"
    assert _offer(n, v, "agreed", "negotiate_fix_say", "10", "2026-10-16") == "negotiate_fix_say"  # floor altı
    assert f"{plan['floor']:.2f}" in v["commit_say"] and v["offers_json"].count("p1:") == 0
    assert _offer(n, v, "agreed", "negotiate_fix_say", str(plan["floor"]), "2026-10-16") == "readback"
    assert "Friday 16 October" in v["readback_say"]


def test_offers_per_product_follow_bands(cat, public_cases):
    """PUB-12: 'bugün' ürün başına tekrar sorulmaz; ürün sırası ve deneme sayısı kodda (late 2, early 1); ürün
    bitince sıradaki ürünün 1. teklifi; hepsi bitince read-back."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert [len(p["attempts"]) for p in plans] == [2, 2, 1]
    p1 = plans[0]
    assert _offer(n, v, "agreed", amount=str(p1["past_due"]), date="2026-10-15") == "negotiate_fix_say"
    said = [v["commit_say"]]
    assert said[0].startswith("Let us continue with your") and plans[1]["product_id"] in v["commit_msg"]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"
    said.append(v["commit_say"])
    assert all("today" not in x for x in said) and said[0] != said[1]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"  # 2. ürün bitti → 3. ürün
    assert v["commit_say"].startswith("Let us continue with your") and plans[2]["product_id"] in v["commit_msg"]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "readback"
    queue = json.loads(v["rec_queue"])
    assert [q["product_id"] for q in queue] == [p1["product_id"]]
    assert sorted(x["reason"] for x in json.loads(v["statuses_json"])) == ["refused", "refused"]


def test_one_day_for_all_products_keeps_each_deadline(cat, public_cases):
    """PUB-13: 'ikisini de 30 Ekim'de' → kart 30 Ekim, kredi kendi deadline'ı 23 Ekim; read-back ikisini de söyler."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-13"], "spec_ab")
    assert _offer(n, v, "agreed_all", date="2026-10-30") == "readback"
    queue = {q["product_id"]: q["date"] for q in json.loads(v["rec_queue"])}
    assert queue == {"p1": "2026-10-30", "p2": "2026-10-23"}
    assert "Friday 30 October" in v["readback_say"] and "Friday 23 October" in v["readback_say"]


def test_propose_results_keeps_offers_already_agreed(cat, public_cases):
    """Bir ürün check_offer_answer ile anlaşıldıktan sonra diğerinde dispute: model sadece dispute'u yazsa da önceki anlaşma
    kaybolmaz (eksik ürün hatası yok)."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    p1, p2, p3 = (p["product_id"] for p in plans)
    assert _offer(n, v, "agreed", amount=str(plans[0]["past_due"]), date="2026-10-15") == "negotiate_fix_say"
    assert _propose(n, v, f"{p2}:dispute; {p3}:refused", "negotiate_fix_say") == "readback"
    assert [q["product_id"] for q in json.loads(v["rec_queue"])] == [p1]
    assert {x["product_id"] for x in json.loads(v["statuses_json"])} == {p2, p3}


def test_offer_goes_straight_to_speech(cat, public_cases):
    """Ret turunda tool + offer_step dışında code node'u yok (commit_fix ile ~10 sn sessizlik oluyordu)."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-12"], "spec_ab")
    v.update({"check_offer_answer_args.result": "refused", "check_offer_answer_args.agreed_amount": "",
              "check_offer_answer_args.agreed_date": ""})
    run_snippet(_tool_code(n["negotiate"], "check_offer_answer"), vars=v)
    assert _route(n["negotiate"], v) == "offer_step"
    run_snippet(_code_of(n["offer_step"]), vars=v)
    assert _route(n["offer_step"], v) == "negotiate_fix_say" and v["commit"] == ""
    assert _route(n["negotiate_fix_say"], v) is None  # eski bayrakla tekrar tetiklenmez


def test_readback_rejection_reopens_offers(cat, public_cases):
    """Model 'agreed_all' dedi ama müşteri sadece ilk ürünü kabul etmişti: read-back reddi teklif durumunu geri alır,
    ikna denemeleri sıradaki ürünlerde yine yapılır (11 Eki PUB-12)."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _offer(n, v, "agreed_all", amount="510", date="2026-10-15") == "readback"
    run_snippet(_code_of(n["readback_reset"]), vars=v)
    assert "check_offer_answer" in v["fix_prompt"]
    assert _offer(n, v, "agreed", "negotiate_fix", str(plans[0]["past_due"]), "2026-10-15") == "negotiate_fix_say"
    assert v["commit_say"].startswith("Let us continue with your")


def test_hardship_decline_closes_without_new_offer(cat, public_cases):
    """PUB-05: teklifi model bir kez yapar; ret 'hardship' ile gelince ürün ikna denemesi ve yeni teklif olmadan
    hardship ile kapanır (birçok koşuda teklif iki kez söylenmişti)."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-05"], "spec_a")
    assert _offer(n, v, "hardship") == "send_close"
    assert (v["close_outcome"], v["close_reason"]) == ("no_promise", "hardship")


def test_hardship_closes_every_remaining_product(cat, public_cases):
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _offer(n, v, "agreed", amount=str(plans[0]["past_due"]), date="2026-10-15") == "negotiate_fix_say"
    assert _offer(n, v, "hardship", "negotiate_fix_say") == "readback"
    assert sorted(x["reason"] for x in json.loads(v["statuses_json"])) == ["hardship", "hardship"]


def test_hardship_without_spec_status_is_left_to_the_model(cat):
    s = spec("spec_a.json")
    s.negotiation.hardship_status = ""
    n = build_workflow(s, cat)["nodes"]
    desc = [t for t in n["negotiate"]["tools"] if t["function"]["name"] == "check_offer_answer"][0]
    assert "hardship" not in json.dumps(desc["function"]["parameters"]["properties"]["result"])
    assert "result='hardship'" not in n["negotiate"]["task_message"]


def test_hardship_declined_after_model_offer_closes_without_repeat(cat, public_cases):
    """talkative PUB-05: model teklifi kendisi yaptı; ret 'hardship_declined' ile gelince kod teklifi tekrarlamaz."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-05"], "spec_a")
    assert _offer(n, v, "hardship_declined") == "send_close"
    assert (v["close_outcome"], v["close_reason"]) == ("no_promise", "hardship")


def test_per_product_with_check_offer_answer(cat, public_cases):
    """Faz 3.1: per_product'ta kabul edilen ürün hemen okunur ve kaydedilir; kayıttan sonra 'kaydedildi' + sıradaki
    ürünün ilk teklifi; retler sonda not olarak (transfer yoksa)."""
    s = spec("spec_ab.json")
    s.recording.mode = "per_product"
    n = build_workflow(s, cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    p1, p2, p3 = plans
    assert _offer(n, v, "agreed", amount=str(p1["past_due"]), date="2026-10-15") == "readback"
    assert [q["product_id"] for q in json.loads(v["rec_queue"])] == ["p1"] and p2["wording"] not in v["readback_say"]
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert _route(n["rec_step"], v) == "negotiate_more"
    assert "is recorded" in v["progress_say"] and p2["wording"] in v["progress_say"]
    assert "Could you pay" in v["progress_say"]  # p2'nin 1. teklifi kayıt cümlesiyle birlikte
    assert _offer(n, v, "refused", "negotiate_more") == "negotiate_fix_say"   # p2 2. deneme
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"  # p2 bitti → p3 1. deneme
    assert p3["wording"] in v["commit_say"]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "record_note"       # p3 bitti → notlar
    notes = []
    while v.get("next_step") in ("note", None) or _route(n["note_step"], v) == "record_note":
        notes.append(v["note_pid"])
        v["note_r_ok"] = "true"
        run_snippet(_code_of(n["note_step"]), vars=v)
        if v["next_step"] != "note":
            break
    assert notes == ["p2", "p3"] and v["next_step"] == "end_nr" and v["close_outcome"] == "promise"
    assert "is recorded" not in v["closing_speech"]  # p1 zaten duyuruldu


def test_per_product_last_product_agreed_after_refusals(cat, public_cases):
    """per_product: önceki ürünler reddedildi, sonuncusu kabul: bekleyen durumlar da aynı öneriye girer, döngü yok."""
    s = spec("spec_ab.json")
    s.recording.mode = "per_product"
    n = build_workflow(s, cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _offer(n, v, "refused") == "negotiate_fix_say"
    for _ in range(4):  # p1: 2. deneme + ret, p2: 2 deneme + ret → p3ün 1. teklifi
        assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"
    assert plans[2]["wording"] in v["commit_say"]
    assert _offer(n, v, "agreed", "negotiate_fix_say", str(plans[2]["past_due"]), "2026-10-16") == "readback"
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert v["next_step"] == "note"  # sıradaki ürün yok, notlara geçilir (negotiate_more döngüsü yok)


def _negotiation_specs():
    pp = spec("spec_ab.json")
    pp.recording.mode = "per_product"
    return [("spec_a", spec("spec_a.json"), "PUB-06"), ("spec_ab", spec("spec_ab.json"), "PUB-12"),
            ("per_product", pp, "PUB-12")]


@pytest.mark.parametrize("name,s,case", _negotiation_specs(), ids=lambda x: x if isinstance(x, str) else "")
def test_every_model_tool_call_routes(name, s, case, cat, public_cases):
    """Faz 3.5 ("no speakable content", 10 Eki 23:36): code_exec tool'unun sonucu modele boş döner. Tool çağrısından
    sonra hiçbir geçiş tutmazsa model söyleyecek bir şey bulamaz ve çağrı takılır. Her cevap dizisinde (ret, çok
    fazla, hardship, geçerli/floor altı/deadline sonrası kabul, dispute) her tool çağrısı bir geçişe gitmeli."""
    import copy
    n = build_workflow(s, cat)["nodes"]
    v0 = {}
    plans = _account(n, v0, public_cases[case], name)
    full = str(plans[0]["past_due"])
    actions = [("offer", "refused", "", ""), ("offer", "too_much", "", ""), ("offer", "hardship", "", ""),
               ("offer", "agreed", full, "2026-10-16"), ("offer", "agreed", "1", "2026-10-16"),
               ("offer", "agreed", full, "2027-03-01"),
               ("propose", "; ".join(f"{p['product_id']}:dispute" for p in plans), "", ""),
               ("propose", f"{plans[-1]['product_id']}:dispute", "", ""), ("propose", "p1:paid", "", ""),
               ("both", "refused", "", f"{plans[-1]['product_id']}:dispute")]
    talk = {k for k, x in n.items() if any(t["function"]["name"] == "check_offer_answer" for t in x.get("tools", []))}
    frontier, calls = [("negotiate", v0, ())], 0
    for _depth in range(3):
        nxt = []
        for node, v, path in frontier:
            for act in actions:
                w = copy.deepcopy(v)
                if act[0] == "offer":
                    w.update({"check_offer_answer_args.result": act[1], "check_offer_answer_args.agreed_amount": act[2],
                              "check_offer_answer_args.agreed_date": act[3]})
                    run_snippet(_tool_code(n[node], "check_offer_answer"), vars=w)
                elif act[0] == "both":
                    w.update({"check_offer_answer_args.result": act[1], "check_offer_answer_args.agreed_amount": "",
                              "check_offer_answer_args.agreed_date": "", "propose_results_args.results": act[3]})
                    run_snippet(_tool_code(n[node], "check_offer_answer"), vars=w)
                    run_snippet(_tool_code(n[node], "propose_results"), vars=w)
                else:
                    w["propose_results_args.results"] = act[1]
                    run_snippet(_tool_code(n[node], "propose_results"), vars=w)
                calls += 1
                route = _route(n[node], w)
                assert route is not None, f"{name}: {node} {path + (act[1],)}: tool çağrısından sonra geçiş yok"
                route = _step(n, w, route)
                if route == "commit_fix":
                    run_snippet(_code_of(n["commit_fix"]), vars=w)
                    route = _route(n["commit_fix"], w)
                assert route in n, f"{name}: {path + (act[1],)} → {route}"
                if route == "readback" and name == "per_product":
                    # read-back onaylandı ve kayıt başarılı: per_product'ta sıradaki ürüne negotiate_more ile dönülür
                    w["rec_r_ok"] = "true"
                    run_snippet(_code_of(n["rec_step"]), vars=w)
                    route = _route(n["rec_step"], w)
                    assert route in n, f"{name}: {path + (act[1],)} kayıttan sonra → {route}"
                if route in talk:
                    # platform konuşma node'unun geçişlerini her müşteri turunda yeniden değerlendirir: eski bayrak
                    # tetiklenirse node kendine döner (SC-03: negotiate_more go_more ile 70 tur)
                    assert _route(n[route], w) is None, f"{name}: {path + (act[1],)}: {route} eski bayrakla döner"
                    nxt.append((route, w, path + (act[1],)))
        frontier = nxt
    assert calls > 50


@pytest.mark.parametrize("name,s,case", _negotiation_specs(), ids=lambda x: x if isinstance(x, str) else "")
def test_every_code_node_has_service_failure_exit(name, s, case, cat):
    """Faz 3.6: kod servisi bir code node'unu çalıştıramazsa değişkenler değişmez ve döngü sonsuza döner (10 Eki).
    Her code node'unun İLK geçişleri `<node>_failure_count > 0` → yedek kapanış olmalı (offer_step, propose_step dahil)."""
    wf = build_workflow(s, cat)
    for k, x in wf["nodes"].items():
        if x["node_type"] != "code":
            continue
        heads = [t for t in x["transitions"][:5] if f"{k}_failure_count" in json.dumps(t["condition"])]
        assert heads, f"{k}: kod servisi hatası geçişi yok"
        assert {t["target_node"] for t in heads} <= {"fallback_close", "fallback_close_nr", "fallback_promise"}
        v = {f"{k}_failure_count": 1}
        assert _route(x, v) == "fallback_close"
        v["close_kind"] = "noreason"
        assert _route(x, v) in ("fallback_close", "fallback_close_nr")
    for k in ("offer_step", "propose_step"):
        assert k in wf["nodes"]


def _both_tools(n, v, node, offer_args, propose_raw, propose_first=False):
    """Model aynı turda iki tool çağırır (SC-03, 11 Eki): ikisinin kodu art arda çalışır, sonra route edilir."""
    def offer():
        v.update({"check_offer_answer_args.result": offer_args[0], "check_offer_answer_args.agreed_amount": offer_args[1],
                  "check_offer_answer_args.agreed_date": offer_args[2]})
        run_snippet(_tool_code(n[node], "check_offer_answer"), vars=v)

    def propose():
        v["propose_results_args.results"] = propose_raw
        run_snippet(_tool_code(n[node], "propose_results"), vars=v)
    for f in ((propose, offer) if propose_first else (offer, propose)):
        f()
    route = _step(n, v, _route(n[node], v))
    if route == "commit_fix":
        run_snippet(_code_of(n["commit_fix"]), vars=v)
        route = _route(n["commit_fix"], v)
    return route


def _drain_notes(n, v):
    notes = []
    while v.get("next_step") == "note":
        notes.append((v["note_pid"], v.get("note_reason")))
        v["note_r_ok"] = "true"
        run_snippet(_code_of(n["note_step"]), vars=v)
    return notes


@pytest.mark.parametrize("propose_first", [False, True])
def test_agree_one_and_dispute_another_in_one_turn_per_product(propose_first, cat, public_cases):
    """SC-03 (canlı, 11 Eki): 'kredi kartını yarın öderim, krediyi ödemem, araç kredisi benim değil' → model aynı turda
    check_offer_answer(agreed p1) + propose_results(p3:dispute). Eskiden ikinci tool bayrağı ezdi, p1 kayboldu ve
    negotiate_more 'go_more' ile kendine döndü (70 tekrar). Şimdi: önce durum işlenir, sonra teklif cevabı; p3 teklif
    sırasında atlanır."""
    s = spec("spec_ab.json")
    s.recording.mode = "per_product"
    n = build_workflow(s, cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    route = _both_tools(n, v, "negotiate", ("agreed", str(p1["past_due"]), "2026-10-15"), "p3:dispute",
                        propose_first)
    assert route == "readback"
    assert [q["product_id"] for q in json.loads(v["rec_queue"])] == ["p1"]
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert _route(n["rec_step"], v) == "negotiate_more"
    assert _route(n["negotiate_more"], v) is None  # eski bayrak düz bir müşteri turunda tekrar tetiklenmez
    assert p2["wording"] in v["progress_say"] and p3["wording"] not in v["progress_say"]
    assert _offer(n, v, "refused", "negotiate_more") == "negotiate_fix_say"   # p2 2. deneme
    assert p2["wording"] in v["commit_say"] or "p2" in v["commit_msg"]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "record_note"       # p2 bitti, p3 zaten dispute
    assert sorted(_drain_notes(n, v)) == [("p2", "refused"), ("p3", "dispute")]
    assert v["close_outcome"] == "promise"


@pytest.mark.parametrize("propose_first", [False, True])
def test_agree_one_and_dispute_another_in_one_turn_batch(propose_first, cat, public_cases):
    """Aynı tur, batch modu (Brief B): p1 kabulü kaybolmaz, p3 teklif sırasında atlanır, p2'ye teklif sürer; sonda
    tek read-back (p1) ve notlar (p2 refused, p3 dispute)."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    route = _both_tools(n, v, "negotiate", ("agreed", str(p1["past_due"]), "2026-10-15"), "p3:dispute",
                        propose_first)
    assert route == "negotiate_fix_say" and p2["wording"] in v["commit_say"]
    assert _route(n["negotiate_fix_say"], v) is None
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"  # p2 2. deneme
    assert _offer(n, v, "refused", "negotiate_fix_say") == "readback"
    assert [q["product_id"] for q in json.loads(v["rec_queue"])] == ["p1"]
    assert sorted(s["product_id"] + ":" + s["reason"] for s in json.loads(v["statuses_json"])) == \
        ["p2:refused", "p3:dispute"]


def test_status_for_current_product_moves_to_check_offer_answer(cat, public_cases):
    """Teklif sürerken şu anki ürün için durum (ör. p1:paid): sıradaki açık ürünün 1. teklifi söylenir."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _propose(n, v, "p1:paid") == "negotiate_fix_say"
    assert p2["wording"] in v["commit_say"]
    assert _route(n["negotiate_fix_say"], v) is None


def test_callback_day_only(cat):
    """SC-05 (11 Eki): müşteri saat vermeden gün söyler. Geçerli gün → sadece saat sorulur (tekrar sayılmaz);
    geçersiz gün (Cumartesi) → kuralın tek 'başka zaman' sorusu; ikinci geçersiz cevap → vazgeç."""
    n = build_workflow(spec("spec_a.json"), cat)["nodes"]
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(n["third_party"]), vars=v)

    def propose(date, time, node="third_party_talk"):
        v.update({"check_callback_time_args.date": date, "check_callback_time_args.time": time})
        run_snippet(_tool_code(n[node], "check_callback_time"), vars=v)
        route = _route(n[node], v)
        if route == "third_party_fix":
            run_snippet(_code_of(n["third_party_fix"]), vars=v)
        return route

    assert propose("2026-10-15", "") == "third_party_fix" and v["cb_bad"] == "0"
    assert v["cb_say"] == "What time on that day would suit you?"
    assert n["third_party_retry"]["on_enter"] == {"type": "tts", "text": "{{cb_say}}"}
    assert propose("2026-10-17", "", "third_party_retry") == "third_party_fix" and v["cb_bad"] == "1"  # Cumartesi
    assert v["cb_say"].startswith("I am sorry, I cannot book that time.") and "outside the allowed days" in v["cb_msg"]
    assert "between 10:00 and 19:00" in v["cb_say"] and "scheduled" not in v["cb_say"]
    assert propose("2026-10-19", "20:00", "third_party_retry") == "close_no_callback"


def test_customer_callback_no_callback_outcome(cat):
    """Brief'in müşteri için ayrı bir 'geçerli zaman yok' kapanışı varsa: tekrar sonrası o outcome'la kapanır."""
    from fbb.spec import OutcomeRef
    s = spec("spec_a.json")
    s.customer_callback.enabled = True
    s.customer_callback.trigger = "The customer says they cannot talk now and asks to be called later."
    s.customer_callback.outcome = OutcomeRef(outcome="no_promise", reason="hardship")
    s.customer_callback.no_callback_outcome = OutcomeRef(outcome="no_promise", reason="dispute")
    wf = build_workflow(s, cat)
    assert _lint(wf, s, cat) == []
    n = wf["nodes"]
    assert "close_cust_no_callback" in n
    body = _body(n["close_cust_no_callback"])
    assert body["outcome"]["default"] == "no_promise" and body["reason"]["default"] == "dispute"
    assert any(t["target_node"] == "close_cust_no_callback" for t in n["cust_cb_talk"]["transitions"])
    assert "transition_to_close_cust_no_callback" in n["cust_cb_talk"]["task_message"]
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(n["cust_cb"]), vars=v)
    for node, date in (("cust_cb_talk", "2026-10-17"), ("cust_cb_retry", "2026-10-18")):
        v.update({"check_callback_time_args.date": date, "check_callback_time_args.time": "10:00"})
        run_snippet(_tool_code(n[node], "check_callback_time"), vars=v)
        route = _route(n[node], v)
        if route == "cust_cb_fix":
            run_snippet(_code_of(n["cust_cb_fix"]), vars=v)
    assert route == "close_cust_no_callback"


def test_system_prompt_answers_pending_questions(cat):
    """asks_back PUB-04: kod adımı sırasında sorulan soru (robot mu?) sonraki turda önce cevaplanır."""
    wf = build_workflow(spec("spec_a.json"), cat)
    assert "still unanswered" in wf["system_prompt"] and "answer it in one short sentence first" in wf["system_prompt"]


def test_readback_rejection_keeps_folded_statuses(cat, public_cases):
    """Review (11 Eki): batch'te p3 itirazı katlandı, sonra read-back reddedildi → son teklif cevabı geri alınır ama
    p3'ün itirazı kalır; p3'e yeniden teklif yapılmaz."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    _both_tools(n, v, "negotiate", ("agreed", str(p1["past_due"]), "2026-10-15"), "p3:dispute")
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"
    assert _offer(n, v, "refused", "negotiate_fix_say") == "readback"
    run_snippet(_code_of(n["readback_reset"]), vars=v)
    assert _route(n["readback_reset"], v) == "negotiate_fix" and _route(n["negotiate_fix"], v) is None
    results = json.loads(v["offers_json"])["results"]
    assert "p3:dispute" in results and not any(r.startswith("p2:") for r in results)  # p2'nin son cevabı geri alındı
    assert _offer(n, v, "refused", "negotiate_fix") == "readback"                  # p2 tekrar bitti → p3'e teklif yok
    assert sorted(s["product_id"] + ":" + s["reason"] for s in json.loads(v["statuses_json"])) == \
        ["p2:refused", "p3:dispute"]


def test_fold_then_hardship_keeps_folded_status(cat, public_cases):
    """p3 itiraz (katlandı), sonra zorluk → kalan açık ürünler hardship, p3 dispute kalır."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _propose(n, v, "p3:dispute") == "commit_fix"  # şu anki ürün değişmedi: model kısa cevap verip sürdürür
    run_snippet(_code_of(n["commit_fix"]), vars=v)
    route = _offer(n, v, "hardship", "negotiate_fix")
    assert route in ("record_note", "send_close", "send_close_nr")
    statuses = json.loads(v.get("statuses_json") or "[]")
    assert sorted(s["product_id"] + ":" + s["reason"] for s in statuses) == ["p1:hardship", "p2:hardship", "p3:dispute"]


def test_agreed_all_skips_disputed_product(cat, public_cases):
    """p2 itiraz edildi, sonra 'hepsini Cuma öderim' (agreed_all) → p2 promise'e girmez."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-12"], "spec_ab")
    _propose(n, v, "p2:dispute")
    run_snippet(_code_of(n["commit_fix"]), vars=v)
    assert _offer(n, v, "agreed_all", "negotiate_fix", "", "2026-10-16") == "readback"
    assert [q["product_id"] for q in json.loads(v["rec_queue"])] == ["p1", "p3"]
    assert [s["product_id"] for s in json.loads(v["statuses_json"])] == ["p2"]


def test_two_tools_after_a_recorded_product_per_product(cat, public_cases):
    """per_product: p1 kaydedildi; negotiate_more'da aynı turda p2 ret + p3 itiraz → p2 2. deneme sürer, p3 atlanır."""
    s = spec("spec_ab.json")
    s.recording.mode = "per_product"
    n = build_workflow(s, cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _offer(n, v, "agreed", amount=str(p1["past_due"]), date="2026-10-15") == "readback"
    v["rec_r_ok"] = "true"
    run_snippet(_code_of(n["rec_step"]), vars=v)
    assert _route(n["rec_step"], v) == "negotiate_more"
    assert _both_tools(n, v, "negotiate_more", ("refused", "", ""), "p3:dispute") == "negotiate_fix_say"
    assert _route(n["negotiate_fix_say"], v) is None and p3["wording"] not in v["commit_say"]
    assert _offer(n, v, "refused", "negotiate_fix_say") == "record_note"
    assert sorted(_drain_notes(n, v)) == [("p2", "refused"), ("p3", "dispute")]


def test_propose_with_promise_and_status_uses_normal_validation(cat, public_cases):
    """Promise + durum içeren propose_results katlanmaz, normal doğrulamaya gider (batch: hepsi listelenmeli)."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _propose(n, v, f"p1:{p1['past_due']}:2026-10-15; p3:dispute") == "commit_fix"
    assert "missing products" in v["commit_msg"]
    assert json.loads(v.get("offers_json") or "null") is None


def test_readback_rejection_after_final_fold(cat, public_cases):
    """Son eylem katlama: p1 kabul, p2 iki ret, p3'e teklif sırası gelince itiraz → read-back → ret. Geri alma yalnız
    son tool çağrısının etkisini (p3 itirazını) kaldırır; p2'nin retleri ve p1 kabulü kalır."""
    n = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v = {}
    p1, p2, p3 = _account(n, v, public_cases["PUB-12"], "spec_ab")
    assert _offer(n, v, "agreed", amount=str(p1["past_due"]), date="2026-10-15") == "negotiate_fix_say"
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"
    assert _offer(n, v, "refused", "negotiate_fix_say") == "negotiate_fix_say"   # p2 bitti → p3 1. teklif
    assert p3["wording"] in v["commit_say"]
    assert _propose(n, v, "p3:dispute", "negotiate_fix_say") == "readback"
    run_snippet(_code_of(n["readback_reset"]), vars=v)
    results = json.loads(v["offers_json"])["results"]
    assert results[:2] == [f"p1:{p1['past_due']}:2026-10-15", "p2:refused"] and "p3:dispute" not in results
    assert json.loads(v["offers_json"])["cur"] == 2  # p3 yeniden açık


def _renamed_request_catalog(tmp_path, extra=None):
    api = json.loads((KIT / "tools" / "openapi.json").read_text())

    def rename(path, old, new):
        sch = api["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        sch["properties"][new] = sch["properties"].pop(old)
        sch["required"] = [new if r == old else r for r in sch.get("required", [])]
        return sch
    rename("/schedule_callback", "date", "callback_date")
    rename("/schedule_callback", "time", "callback_time")
    rename("/create_promise", "amount", "promise_amount")
    rename("/create_promise", "date", "promise_date")
    rename("/close_call", "outcome", "result")
    rename("/close_call", "reason", "reason_code")
    rename("/transfer_to_agent", "queue", "team")
    rename("/add_note", "reason", "note_reason")
    if extra:
        extra(api)
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(api))
    return load_catalog(path)


def test_renamed_request_fields_are_mapped(tmp_path):
    """Gizli openapi'de istek alanları yeniden adlandırılırsa ve Claude tool_fields'i kaçırırsa: tek aday eşlenir,
    gövdeler doğru alanlarla kurulur, lint temiz."""
    from fbb.spec import resolve_request_fields
    vcat = _renamed_request_catalog(tmp_path)
    s = spec("spec_ab.json")
    notes = resolve_request_fields(s, vcat)
    assert s.tool_fields["schedule_callback"] == {"date": "callback_date", "time": "callback_time"}
    assert s.tool_fields["create_promise"] == {"amount": "promise_amount", "date": "promise_date"}
    assert s.tool_fields["close_call"] == {"outcome": "result", "reason": "reason_code"}
    assert s.tool_fields["transfer_to_agent"] == {"queue": "team"}
    assert s.tool_fields["add_note"] == {"reason": "note_reason"} and len(notes) == 8
    wf = build_workflow(s, vcat)
    warnings = []
    assert _lint(wf, s, vcat, warnings) == [] and not any("zorunlu" in w for w in warnings)
    n = wf["nodes"]
    assert set(_body(n["third_party_book"])) == {"customer_id", "callback_date", "callback_time"}
    assert set(_body(n["record_promise"])) == {"customer_id", "product_id", "promise_amount", "promise_date"}
    assert set(_body(n["transfer_restructuring"])) == {"customer_id", "team"}
    assert {"result", "reason_code"} <= set(_body(n["close_unclear"]))
    assert resolve_request_fields(s, vcat) == []  # ikinci kez: değişiklik yok


def test_ambiguous_request_field_is_left_alone(tmp_path):
    """İki aday varsa (callback_date ve backup_date) tahmin edilmez."""
    from fbb.spec import resolve_request_fields

    def extra(api):
        sch = api["paths"]["/schedule_callback"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        sch["properties"]["backup_date"] = {"type": "string"}
    vcat = _renamed_request_catalog(tmp_path, extra)
    s = spec("spec_ab.json")
    resolve_request_fields(s, vcat)
    assert "date" not in s.tool_fields.get("schedule_callback", {})
    assert s.tool_fields["schedule_callback"]["time"] == "callback_time"


def test_request_fields_noop_on_kit_openapi(cat):
    from fbb.spec import resolve_request_fields
    s = spec("spec_ab.json")
    assert resolve_request_fields(s, cat) == [] and s.tool_fields == spec("spec_ab.json").tool_fields


def test_callback_min_lead_minutes(cat):
    """Brief F (11 Eki): 'aynı gün en az 2 saat sonra' → 12:30 reddedilir, 13:00 kabul; pencere metni söyler."""
    s = spec("spec_a.json")
    s.third_party.callback.min_lead_minutes = 120
    n = build_workflow(s, cat)["nodes"]
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(n["third_party"]), vars=v)
    assert "Today only from 13:00" in v["cb_facts"]
    v.update({"check_callback_time_args.date": "2026-10-14", "check_callback_time_args.time": "12:30"})
    run_snippet(_tool_code(n["third_party_talk"], "check_callback_time"), vars=v)
    assert v["cb_state"] == "invalid" and "not before 13:00" in v["cb_msg"]
    run_snippet(_code_of(n["third_party_fix"]), vars=v)
    v.update({"check_callback_time_args.date": "2026-10-14", "check_callback_time_args.time": "13:00"})
    run_snippet(_tool_code(n["third_party_retry"], "check_callback_time"), vars=v)
    assert v["cb_state"] == "ok"


def _close_of(n, v):
    run_snippet(_code_of(n["close_final"]), vars=v)
    return v["close_outcome"], v["close_reason"], v["close_kind"]


def test_promise_and_paid_reasons(cat, public_cases):
    """Brief F: promise kapanışı da reason alır; kaydedilenlerden biri kısmiyse 'kısmi' reason; ödemiş → kendi reason'ı.
    Alanlar boşsa (A/B) promise reason'sız kalır."""
    s = spec("spec_ab.json")
    s.closing.promise_reason, s.closing.promise_reason_partial, s.closing.paid_reason = "P01", "P02", "A07"
    s.closing.no_reason_outcomes = []
    n = build_workflow(s, cat)["nodes"]
    v = {}
    plans = _account(n, v, public_cases["PUB-12"], "spec_ab")
    v["recorded_json"] = json.dumps([{"product_id": "p1", "amount": plans[0]["past_due"], "date": "2026-10-15"}])
    v["promises_ok"] = "1"
    assert _close_of(n, dict(v))[:2] == ("promise", "P01")
    v["recorded_json"] = json.dumps([{"product_id": "p1", "amount": plans[0]["floor"], "date": "2026-10-15"}])
    o, r, kind = _close_of(n, dict(v))
    assert (o, r, kind) == ("promise", "P02", "reason")
    w = {k: x for k, x in v.items() if k not in ("recorded_json", "promises_ok")}
    w["statuses_json"] = json.dumps([{"product_id": p["product_id"], "reason": "paid"} for p in plans])
    assert _close_of(n, w)[:2] == ("paid", "A07")
    base = build_workflow(spec("spec_ab.json"), cat)["nodes"]
    v2 = {}
    _account(base, v2, public_cases["PUB-12"], "spec_ab")
    v2.update({"recorded_json": v["recorded_json"], "promises_ok": "1"})
    assert _close_of(base, v2) == ("promise", "", "noreason")


@pytest.mark.parametrize("k", ["c", "d", "e", "f", "g"])
def test_rehearsal_briefs_build_cleanly(k):
    """Prova brief'leri (C/D/E/F, tests/fixtures/variants): beklenen spec + kendi openapi'si → cross_check boş, lint 0."""
    from fbb.spec import resolve_request_fields
    vcat = load_catalog(FIX / "variants" / f"openapi_{k}.json")
    s = PolicySpec.model_validate(json.loads((FIX / "variants" / f"spec_{k}_expected.json").read_text()))
    resolve_response_fields(s, vcat)
    resolve_request_fields(s, vcat)
    assert cross_check(s, vcat) == []
    wf = build_workflow(s, vcat)
    assert _lint(wf, s, vcat) == []


def test_single_result_code_close_and_datetime_callback(public_cases):
    """Brief G (11 Eki): close_call tek 'result_code' alır → durumun/kuyruğun kodu outcome olur (hardship →
    NO_PROMISE_HARDSHIP); schedule_callback tek 'callback_at' alır → 'YYYY-MM-DDTHH:MM'."""
    from fbb.spec import resolve_request_fields
    vcat = load_catalog(FIX / "variants" / "openapi_g.json")
    s = PolicySpec.model_validate(json.loads((FIX / "variants" / "spec_g_expected.json").read_text()))
    resolve_response_fields(s, vcat)
    resolve_request_fields(s, vcat)
    n = build_workflow(s, vcat)["nodes"]
    assert _body(n["third_party_book"])["callback_at"]["default"] == "{{cb_at}}"
    assert _body(n["close_transfer_hardship_care"])["result_code"]["default"] == "TRANSFERRED_CARE"
    assert "reason" not in _body(n["send_close"])
    v = {"now": "2026-10-14T11:00"}
    run_snippet(_code_of(n["third_party"]), vars=v)
    v.update({"check_callback_time_args.date": "2026-10-15", "check_callback_time_args.time": "15:00"})
    run_snippet(_tool_code(n["third_party_talk"], "check_callback_time"), vars=v)
    assert v["cb_state"] == "ok" and v["cb_at"] == "2026-10-15T15:00"
    w = {"id_state": "verified", "statuses_json": json.dumps([{"product_id": "p1", "reason": "hardship"}])}
    run_snippet(_code_of(n["close_final"]), vars=w)
    assert (w["close_outcome"], w["close_reason"], w["close_kind"]) == ("NO_PROMISE_HARDSHIP", "", "noreason")
    w = {"id_state": "verified", "statuses_json": json.dumps([{"product_id": "p1", "reason": "paid"}])}
    run_snippet(_code_of(n["close_final"]), vars=w)
    assert w["close_outcome"] == "PAID"


def test_status_sentence_is_said_by_the_system(cat, public_cases):
    """Faz 7, LLM spec'li A (PUB-08): model propose_results'tan önce konuşmadığı için 'ödemeler bir iş günü içinde
    görünür' cümlesi hiç söylenmedi. Durumun cümlesini kapanış konuşması söyler, bir kez."""
    s = spec("spec_a.json")
    n = build_workflow(s, cat)["nodes"]
    v = {}
    _account(n, v, public_cases["PUB-08"], "spec_a")
    assert _propose(n, v, "p1:paid") == "send_close_nr"
    paid = [x.say for x in s.statuses if x.id == "paid"][0]
    assert v["closing_speech"].startswith(paid) and v["closing_speech"].count(paid) == 1


def test_code_failure_right_after_recorded_promise_closes_as_promise(cat):
    """11 Eki A-LLM PUB-04: create_promise ok, ardından rec_step'te kod servisi düştü → outcome 'refused' gitti.
    Son kayıt başarılıysa kodsuz promise kapanışı."""
    s = spec("spec_a.json")
    n = build_workflow(s, cat)["nodes"]
    v = {"rec_step_failure_count": 1, "rec_r_ok": "true", "close_kind": "reason"}
    assert _route(n["rec_step"], v) == "fallback_promise"
    fb = n["fallback_promise"]
    assert _body(fb)["outcome"]["default"] == "promise" and "reason" not in _body(fb)
    assert fb["on_enter"]["text"].startswith(s.recording.success_sentence)
    assert _route(n["rec_step"], {"rec_step_failure_count": 1, "rec_r_ok": "", "close_kind": "reason"}) == \
        "fallback_close"
