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
    assert "four digits" in v["id_say"] and "date of birth" not in v["id_say"]


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
    return _route(n[node], v)


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
            targets = [t["target_node"] for t in node["transitions"][:2]]
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
    v.update({"propose_callback_args.date": "2026-10-15", "propose_callback_args.time": "11:00"})
    run_snippet(_tool_code(n["cust_cb_talk"], "propose_callback"), vars=v)
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
