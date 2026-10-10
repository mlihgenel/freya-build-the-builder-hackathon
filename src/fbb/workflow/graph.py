"""PolicySpec + ToolCatalog → Freya workflow (docs/05_GRAF_TASARIMI.md).

İlke: model sadece konuşur ve üç şeyi bildirir (submit_answer, submit_results, propose_callback).
Bankaya yazan her çağrıyı engine yapar (api_request node'ları); kararlar code node'larında verilir.
Aynı spec her zaman aynı workflow'u üretir (sıralı sözlükler, rastgelelik yok).
"""
from __future__ import annotations

import hashlib
import json

from fbb.ingest.openapi import ToolCatalog
from fbb.runtime.emit import build_snippet
from fbb.spec import PolicySpec, to_runtime
from fbb.workflow import texts
from fbb.workflow.nodes import api_request, code, conversation, end_call, tool_transition, when_eq
from fbb.workflow.tools import bank_call, model_tool

END = "end_main"


def _types(cat: ToolCatalog, tool: str, optional: list[str] | None = None) -> dict:
    t = {k: f.type for k, f in cat.tools[tool].fields.items() if f.type in ("number", "integer")}
    t["optional"] = optional or []
    return t


def _coerce_hook(cat: ToolCatalog, tool: str, rt: dict, optional: list[str] | None = None) -> str:
    return build_snippet(f"coerce_body(config, {_types(cat, tool, optional)!r})", rt)


def field_map(spec: PolicySpec, cat: ToolCatalog, tool: str, values: dict[str, str]) -> dict[str, str]:
    """Anlamsal rol → openapi'deki gerçek alan adı. Gizli brief'lerde alan adları değişebilir.

    Öncelik: spec.tool_fields[tool][rol] → aynı adlı alan → müşteri kimliği için çağrı değişkeniyle aynı adlı alan.
    Eşleşmeyen rol atlanır (lint uyarır)."""
    fields = cat.tools[tool].fields
    override = spec.tool_fields.get(tool, {})
    out = {}
    for role, value in values.items():
        name = override.get(role) or (role if role in fields else "")
        if not name and role == "customer_id":
            name = spec.call_variables.customer_id if spec.call_variables.customer_id in fields else ""
        if name and name in fields:
            out[name] = value
    return out


def build_workflow(spec: PolicySpec, cat: ToolCatalog) -> dict:
    rt = to_runtime(spec)
    cid = "{{" + spec.call_variables.customer_id + "}}"
    o = spec.opening

    def call(tool: str, values: dict[str, str], **kw) -> dict:
        return bank_call(cat, tool, field_map(spec, cat, tool, values), **kw)

    def snip(entry: str, fallback: str = "") -> str:
        return build_snippet(entry, rt, fallback=fallback)

    def close_node(name: str, outcome: str, reason: str, speech: str) -> dict:
        entry = f"set_close(vars, RT, {outcome!r}, {reason!r}, {speech!r})"
        fb = f"vars['close_outcome'] = {outcome!r}\nvars['close_reason'] = {reason!r}\n" \
             f"vars['closing_speech'] = {(speech + ' ' + spec.closing.goodbye_sentence).strip()!r}"
        return code(name, snip(entry, fb), [], END)

    nodes: dict[str, dict] = {}

    # --- açılış ---------------------------------------------------------------------------------------
    opener_transitions = [
        tool_transition("identity_check", "The person clearly confirmed they are the customer."),
        tool_transition("third_party", "Someone other than the customer answered the phone."),
        tool_transition("close_wrong_number", "The number does not belong to the customer."),
        tool_transition("close_deceased", "The customer has died."),
        tool_transition("close_unclear", "Still no clear confirmation after asking twice."),
        tool_transition("close_id_declined", "The person refuses to talk a second time."),
    ]
    human = [t for t in spec.transfers if "pre_identity" in t.stages]
    for t in human:
        opener_transitions.append(tool_transition(f"transfer_{t.id}", t.trigger))
    nodes["opener"] = conversation(
        "opener", texts.opener_task(spec),
        on_enter={"type": "tts", "text": f"{o.first_sentence} {texts.tpl(o.confirm_question)}".strip()},
        first_entry_only=True, transitions=opener_transitions, max_turns=12, max_turn_target="close_unclear")

    # --- kimlik ---------------------------------------------------------------------------------------
    nodes["identity_check"] = code("identity_check", snip("id_init(vars, RT)\nvars['id_msg'] = ''"), [],
                                   "ask_identity")
    submit_answer = model_tool(
        "submit_answer",
        "CALL it every time the customer answers the security question you just asked, with their answer exactly "
        "as they said it. The system checks it and tells you what to say next.",
        {"answer": "The customer's answer to the current security question, exactly as said."},
        "id_reset_result(vars)\nid_take_answer(vars, RT, tool_arg(vars, 'submit_answer', 'answer', ARG_answer))", rt)
    id_transitions = [when_eq("verify_answer", "An answer is ready to check", "id_ready", "yes"),
                      tool_transition("close_id_declined", "The customer refused the security questions twice.")]
    for t in human:
        id_transitions.append(tool_transition(f"transfer_{t.id}", t.trigger))
    nodes["ask_identity"] = conversation(
        "ask_identity", texts.identity_task(spec), on_enter={"type": "tts", "text": "{{id_say}}"},
        tools=[submit_answer], transitions=id_transitions, max_turns=20, max_turn_target="close_id_declined")
    verify = call("verify_identity",
                       {"customer_id": cid, "field": "{{id_field}}", "answer": "{{id_answer}}"},
                       retries=0)
    nodes["verify_answer"] = api_request(
        "verify_answer", verify,
        [("data.ok", "id_r_ok"), ("data.verified", "id_r_verified"), ("data.all_verified", "id_r_all"),
         ("data.wrong_answers_left", "id_r_left"), ("data.hint", "id_r_hint")], "id_result")
    nodes["id_result"] = code("id_result", snip("id_after(vars, RT)"), [
        when_eq("fetch_account", "identity verified", "id_state", "verified"),
        when_eq("close_id_failed", "identity check failed", "id_state", "failed"),
    ], "ask_identity")

    # --- hesap ve müzakere ----------------------------------------------------------------------------
    nodes["fetch_account"] = api_request(
        "fetch_account", call("get_account", {"customer_id": cid}, retries=2),
        [("data.products", "products")], "prep_account")
    nodes["prep_account"] = code("prep_account", snip("prep_account(vars, RT)\nvars['commit_msg'] = ''",
                                                      "vars['account_state'] = 'error'"), [], "negotiate")
    submit_results = model_tool(
        "submit_results",
        "CALL it once at the end, when every product has a confirmed promise or a final status. Format: "
        "<product_id>:<amount>:<YYYY-MM-DD> or <product_id>:<status>, entries separated by ';'.",
        {"results": "One entry per product separated by ';', e.g. 'p1:250.50:2026-10-16; p2:refused'."},
        "take_results(vars, RT, tool_arg(vars, 'submit_results', 'results', ARG_results))", rt)
    post = [t for t in spec.transfers if "post_verify" in t.stages]
    neg_transitions = [when_eq("rec_pick", "results accepted", "commit", "ready"),
                       when_eq("commit_fix", "results rejected", "commit", "invalid")]
    neg_transitions += [tool_transition(f"transfer_{t.id}", t.trigger) for t in post]
    task = texts.negotiate_task(spec)
    nodes["negotiate"] = conversation(
        "negotiate", task, on_enter={"type": "tts", "text": "{{debt_statement}} {{first_ask}}"},
        first_entry_only=True, tools=[submit_results], transitions=neg_transitions, max_turns=60,
        max_turn_target="close_final")
    nodes["commit_fix"] = code("commit_fix", snip("vars['commit'] = ''"), [], "negotiate_fix")
    nodes["negotiate_fix"] = conversation(
        "negotiate_fix", task,
        on_enter={"type": "llm", "prompt": "Nothing was recorded: {{commit_msg}}. In one or two sentences, tell the "
                                           "customer what you can offer instead under the rules, then continue."},
        tools=[submit_results], transitions=neg_transitions, max_turns=40, max_turn_target="close_final")

    # --- kayıt ve not döngüleri -----------------------------------------------------------------------
    nodes["rec_pick"] = code("rec_pick", snip("rec_pick(vars, RT)", "vars['rec_state'] = 'done'"),
                             [when_eq("record_promise", "a promise to record", "rec_state", "go")], "note_pick")
    rec_call = call("create_promise",
                         {"customer_id": cid, "product_id": "{{rec_pid}}",
                          "amount": "{{rec_amount}}", "date": "{{rec_date}}"},
                         pre_hook=_coerce_hook(cat, "create_promise", rt))
    nodes["record_promise"] = api_request("record_promise", rec_call, [("data.ok", "rec_r_ok")], "rec_after")
    nodes["rec_after"] = code("rec_after", snip("rec_after(vars, RT)"), [], "rec_pick")
    nodes["note_pick"] = code("note_pick", snip("note_pick(vars, RT)", "vars['note_state'] = 'done'"),
                              [when_eq("record_note", "a note to record", "note_state", "go")], "close_final")
    if cat.has("add_note"):
        note_call = call("add_note", {"customer_id": cid, "product_id": "{{note_pid}}",
                                                "reason": "{{note_reason}}"})
        nodes["record_note"] = api_request("record_note", note_call, [("data.ok", "note_r_ok")], "note_after")
    else:
        nodes["record_note"] = code("record_note", snip("vars['note_r_ok'] = 'true'"), [], "note_after")
    nodes["note_after"] = code("note_after", snip("note_after(vars, RT)", "vars['note_i'] = '99'"), [],
                               "note_pick")
    nodes["close_final"] = close_node("close_final", "", "", "")

    # --- transferler ----------------------------------------------------------------------------------
    for t in spec.transfers:
        nodes[f"transfer_{t.id}"] = code(
            f"transfer_{t.id}",
            snip(f"vars['transfer_queue'] = {t.queue!r}\nvars['transfer_say'] = {t.say!r}\n"
                 "vars['rec_queue'] = '[]'"), [], "do_transfer")
    nodes["do_transfer"] = api_request(
        "do_transfer", call("transfer_to_agent", {"customer_id": cid,
                                                            "queue": "{{transfer_queue}}"}),
        [("data.ok", "transfer_r_ok")], "close_transfer")
    nodes["close_transfer"] = code("close_transfer", snip("set_close(vars, RT, '', '', vars.get('transfer_say', ''))"),
                                   [], END)

    # --- üçüncü kişi -----------------------------------------------------------------------------------
    tp = spec.third_party
    nodes["third_party"] = code("third_party", snip("prep_callback(vars, RT)\nvars['cb_msg'] = ''"), [],
                                "third_party_talk")
    propose = model_tool(
        "propose_callback",
        "CALL it when the person names a day and a time to reach the customer. The system checks the time.",
        {"date": "The day as YYYY-MM-DD.", "time": "The time as HH:MM, 24-hour clock."},
        "take_callback(vars, RT, tool_arg(vars, 'propose_callback', 'date', ARG_date), "
        "tool_arg(vars, 'propose_callback', 'time', ARG_time))", rt)
    tp_transitions = [
        when_eq("book_callback", "callback time accepted", "cb_state", "ok"),
        when_eq("close_no_callback", "no valid callback time", "cb_state", "gave_up"),
        when_eq("cb_fix", "callback time rejected", "cb_state", "invalid"),
        tool_transition("close_wrong_number", "The number does not belong to the customer."),
        tool_transition("close_deceased", "The customer has died."),
        tool_transition("close_no_callback", "The person will not give any time to reach the customer."),
    ]
    nodes["third_party_talk"] = conversation(
        "third_party_talk", texts.third_party_task(spec),
        on_enter={"type": "llm", "prompt": f'Without saying why you are calling, ask: "{tp.ask_reachability}"'},
        tools=[propose], transitions=tp_transitions, max_turns=12, max_turn_target="close_no_callback")
    nodes["cb_fix"] = code("cb_fix", snip("vars['cb_state'] = ''"), [], "third_party_retry")
    nodes["third_party_retry"] = conversation(
        "third_party_retry", texts.third_party_task(spec),
        on_enter={"type": "llm", "prompt": "That time cannot be booked ({{cb_msg}}). Ask once for another day and "
                                           "time inside the allowed window, without saying why you are calling."},
        tools=[propose], transitions=tp_transitions, max_turns=8, max_turn_target="close_no_callback")
    cb_call = call("schedule_callback", {"customer_id": cid, "date": "{{cb_date}}",
                                                   "time": "{{cb_time}}"})
    nodes["book_callback"] = api_request("book_callback", cb_call, [("data.ok", "cb_r_ok")], "close_callback")

    # --- kapanışlar -----------------------------------------------------------------------------------
    i = spec.identity
    for name, ref, speech in [
        ("close_unclear", o.unclear, ""),
        ("close_wrong_number", tp.wrong_number_outcome, ""),
        ("close_deceased", tp.deceased_outcome, tp.deceased_sentence),
        ("close_callback", tp.callback_outcome, ""),
        ("close_no_callback", tp.no_callback_outcome, ""),
        ("close_id_failed", i.fail_outcome, i.fail_sentence),
        ("close_id_declined", i.decline_outcome, ""),
    ]:
        nodes[name] = close_node(name, ref.outcome, ref.reason, speech)
    nodes[END] = end_call(END, "call_closed", "{{closing_speech}}")

    # --- close_call: çağrı bittiğinde engine çalıştırır, her zaman son çağrıdır -------------------------
    close_pre = build_snippet(
        "b = config.get('body')\nif isinstance(b, dict):\n    apply_close_body(vars, b, RT)",
        rt, fallback="b = config.get('body')\nif isinstance(b, dict) and not str(b.get('reason', '')).strip("
                     "'{} '):\n    b.pop('reason', None)")
    close_tool = call("close_call", {"customer_id": cid, "outcome": "{{close_outcome}}",
                                               "reason": "{{close_reason}}"},
                           pre_hook=close_pre, lifecycle="end_of_call")

    test_vars = {v: "" for v in spec.call_variables.all}
    return {
        "initial_node": "opener",
        "system_prompt": texts.system_prompt(spec),
        "nodes": nodes,
        "global_nodes": {},
        "tools": [close_tool],
        "test_variables": test_vars,
    }


def workflow_hash(workflow: dict) -> str:
    return hashlib.sha256(json.dumps(workflow, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
