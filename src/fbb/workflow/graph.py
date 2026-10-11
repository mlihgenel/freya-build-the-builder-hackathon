"""PolicySpec + ToolCatalog → Freya workflow (docs/05_GRAF_TASARIMI.md).

İlke: model sadece konuşur ve az sayıda şeyi bildirir (submit_answer, decline_questions, propose_results,
check_callback_time). Bankaya yazan her çağrıyı engine yapar (api_request node'ları). Kararlar ya code node'larında
ya da doğrudan cevap değişkenleri üzerinden route'larda verilir. Aynı spec her zaman aynı workflow'u üretir.

Gecikme: her code node'u yük altında 2-8 sn sürüyor. Bu yüzden code node'u sadece gerçekten hesap gereken yerde
var: kimlik sonucu, sabit kapanışlar ve transferler kodsuz.
"""
from __future__ import annotations

import hashlib
import json
import re

from fbb.ingest.openapi import ToolCatalog
from fbb.runtime.emit import build_snippet
from fbb.spec import PolicySpec, to_runtime
from fbb.workflow import texts
from fbb.workflow.nodes import (
    api_request,
    conversation,
    end_call,
    intent,
    tool_transition,
    when_eq,
)
from fbb.workflow.nodes import code as _code
from fbb.workflow.tools import bank_call, model_tool

END = "end_main"
SEND = "send_close"            # veda + close_call (reason ile)
SEND_NR = "send_close_nr"      # veda + close_call (reason alanı yok: promise, paid)
FALLBACK = "fallback_close"    # kod servisi çalışmazsa: o ana kadar yazılmış outcome/reason ile kapanış
FALLBACK_NR = "fallback_close_nr"
TRUE = ("true", "True")
OK = ("true", "True", "success")


def code(*args, **kw) -> dict:
    """Her code node'u kod servisi hatasına karşı korumalı: hata olursa yedek kapanışa gider."""
    kw.setdefault("guard", FALLBACK)
    kw.setdefault("guard_nr", FALLBACK_NR)
    return _code(*args, **kw)


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


def body_for(spec: PolicySpec, cat: ToolCatalog, tool: str, values: dict[str, str]) -> dict[str, str]:
    """Rollerden gövde + brief'in sabitleri + openapi'nin varsayılan/tek değerli zorunlu alanları."""
    body = field_map(spec, cat, tool, values)
    for fname, value in spec.tool_constants.get(tool, {}).items():
        if fname in cat.tools[tool].fields and fname not in body:
            body[fname] = value
    for fname, f in cat.tools[tool].fields.items():
        if fname in body or not f.required:
            continue
        if f.default:
            body[fname] = f.default
        elif len(f.enum) == 1:
            body[fname] = f.enum[0]
    return body


def callback_body(spec: PolicySpec, cat: ToolCatalog, cid: str) -> dict[str, str]:
    """schedule_callback gövdesi. Tarih ayrı bir alana eşlenemiyorsa (ör. tek 'callback_at' alanı) tarih ve saat tek
    alanda 'YYYY-MM-DDTHH:MM' olarak gider: saatin eşlendiği alan ya da biçimi/açıklaması tarih-saat olan alan."""
    body = body_for(spec, cat, "schedule_callback", {"customer_id": cid, "date": "{{cb_date}}", "time": "{{cb_time}}"})
    if "{{cb_date}}" in body.values():
        return body
    fields = cat.tools["schedule_callback"].fields
    target = next((k for k, v in body.items() if v == "{{cb_time}}"), "") or next(
        (k for k, f in fields.items() if k not in body and (f.format == "date-time" or re.search(
            r"date.?time|YYYY-MM-DD.?T|_at$", k + " " + (f.description or ""), re.I))), "")
    if target:
        body[target] = "{{cb_at}}"
    return body


def ok_path(spec: PolicySpec, cat: ToolCatalog, tool: str) -> str:
    """Yazma çağrısının başarı alanı: cevap şemasında ok alanı varsa o, yoksa zarfın status'u ('success')."""
    resp = cat.tools[tool].response if cat.has(tool) else {}
    name = spec.response_fields.ok
    return f"data.{name}" if (name in resp or not resp) else "status"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def build_workflow(spec: PolicySpec, cat: ToolCatalog) -> dict:
    rt = to_runtime(spec)
    close_body_names = field_map(spec, cat, "close_call", {"outcome": "o", "reason": "r"})
    rt["close_fields"] = {("outcome" if v == "o" else "reason"): k for k, v in close_body_names.items()}
    # close_call'da reason alanı yoksa (tek sonuç kodu): durumun/kuyruğun kodu outcome olarak gider
    single_code = "reason" not in rt["close_fields"]
    if single_code:
        rt["closing"]["single_code"] = True
    cid = "{{" + spec.call_variables.customer_id + "}}"
    o = spec.opening
    i = spec.identity
    loc = spec.locale
    rf = spec.response_fields
    qs = i.questions
    cc = spec.customer_callback

    def call(tool: str, values: dict[str, str], **kw) -> dict:
        return bank_call(cat, tool, body_for(spec, cat, tool, values), **kw)

    def snip(entry: str, fallback: str = "") -> str:
        return build_snippet(entry, rt, fallback=fallback)

    goodbye = texts.tpl(spec.closing.goodbye_sentence)
    goodbye_anon = texts.tpl(texts.without_placeholders(spec.closing.goodbye_sentence))
    no_reason = set(spec.closing.no_reason_outcomes)

    def close_call(outcome: str, reason: str) -> dict:
        if single_code and reason:
            outcome, reason = reason, ""
        values = {"customer_id": cid, "outcome": outcome}
        if reason and outcome not in no_reason:
            values["reason"] = reason
        return call("close_call", values, retries=2)

    close_ok = [(ok_path(spec, cat, "close_call"), "close_r_ok")]

    def static_close(name: str, outcome: str, reason: str, speech: str, anonymous: bool) -> dict:
        """Kodsuz kapanış: sabit veda (tts) + sabit outcome/reason ile close_call + telefonu kapat."""
        text = " ".join(x for x in (texts.tpl(speech), goodbye_anon if anonymous else goodbye) if x).strip()
        return api_request(name, close_call(outcome, reason), close_ok, END, on_enter={"type": "tts", "text": text})

    nodes: dict[str, dict] = {}

    pre_transfers = [t for t in spec.transfers if "pre_identity" in t.stages]
    post_transfers = [t for t in spec.transfers if "post_verify" in t.stages]
    cc_pre = cc.enabled and "pre_identity" in cc.stages
    cc_post = cc.enabled and "post_verify" in cc.stages
    pre_extra = [tool_transition(f"transfer_{t.id}", t.trigger) for t in pre_transfers]
    if cc_pre:
        pre_extra.append(tool_transition("cust_cb", cc.trigger))
    post_extra = [tool_transition(f"transfer_{t.id}", t.trigger) for t in post_transfers]
    if cc_post:
        post_extra.append(tool_transition("cust_cb", cc.trigger))

    # --- açılış ---------------------------------------------------------------------------------------
    opener_transitions = [
        tool_transition("ask_q0", "The person clearly confirmed they are the customer."),
        tool_transition("third_party", "Someone other than the customer answered the phone."),
        tool_transition("close_wrong_number", "The number does not belong to the customer."),
        tool_transition("close_deceased", "The customer has died."),
        tool_transition("close_unclear", "Still no clear confirmation after the allowed number of asks."),
        tool_transition("close_id_declined", "The person refuses to talk a second time."),
    ] + pre_extra
    nodes["opener"] = conversation(
        "opener", texts.opener_task(spec),
        on_enter={"type": "tts", "text": f"{o.first_sentence} {texts.tpl(o.confirm_question)}".strip()},
        first_entry_only=True, transitions=opener_transitions, max_turns=12, max_turn_target="close_unclear")

    # --- kimlik: her soru sabit cümleli kendi node'unda sorulur; doğrulama sonucu doğrudan cevap alanlarıyla
    # route edilir (kod yok). Mutlu yol dışı (yanlış, gün/ay ipucu, okunamadı, servis hatası, ret açıklaması)
    # id_fix kod adımında cümleye çevrilir ve tek bir 'reask' node'unda söylenir.
    all_at_once = i.verify_mode == "all_at_once" and len(qs) > 1
    decline_desc = ("CALL it when the customer refuses to answer the security question"
                    + (" or asks what the call is about instead of answering."
                       if i.purpose_question_counts_as_decline else ".")
                    + " Never call it when the message contains an answer.")

    def answer_target(k: int) -> str:
        if all_at_once:
            return f"ask_q{k + 1}" if k + 1 < len(qs) else "verify_all"
        return f"verify_q{k}"

    def ask_node(name: str, spoken: str, idx_expr: str, swap_expr: str, targets: list[tuple[str, str]],
                 decline_idx: str = "None") -> dict:
        decline = model_tool("decline_questions", decline_desc, {}, f"id_decline(vars, RT, {decline_idx})", rt)
        submit = model_tool(
            "submit_answer",
            "CALL it every time the customer answers the security question you just asked, with their answer "
            "exactly as they said it (also when it is only part of the answer). The system checks it.",
            {"answer": "The customer's answer to the current security question, exactly as said."},
            f"id_take_answer(vars, RT, tool_arg(vars, 'submit_answer', 'answer', ARG_answer), {idx_expr}, "
            f"{name!r}, {swap_expr})", rt)
        trans = [when_eq(t, "an answer is ready to check", "id_go", tok) for tok, t in targets]
        trans += [when_eq("id_fix", "only part of the answer: ask for the rest", "id_go", "partial"),
                  when_eq("close_id_failed", "too many answers", "id_go", "fail"),
                  when_eq("close_id_declined", "the customer refused the questions", "id_decl", "close"),
                  when_eq("id_fix", "explain why the questions are needed", "id_decl", "explain")]
        return conversation(name, texts.identity_task(spec, spoken), on_enter={"type": "tts", "text": spoken},
                            tools=[submit, decline], transitions=trans + pre_extra, max_turns=30,
                            max_turn_target="close_id_declined")

    for k, q in enumerate(qs):
        nodes[f"ask_q{k}"] = ask_node(f"ask_q{k}", texts.tpl(q.ask), str(k), "False",
                                      [(f"ask_q{k}:{k}", answer_target(k))], decline_idx=str(k))
    nodes["reask"] = ask_node("reask", "{{id_say}}", "as_int(vars.get('id_q'))", "vars.get('id_swap') == '1'",
                              [(f"reask:{k}", answer_target(k)) for k in range(len(qs))])
    nodes["id_fix"] = code("id_fix", snip("id_fix(vars, RT)",
                                          "vars['id_say'] = " + repr(f"{loc.could_not_check} {qs[0].ask}")), [],
                           "reask")

    verify_map = [(f"data.{rf.ok}", "id_r_ok"), (f"data.{rf.verified}", "id_r_verified"),
                  (f"data.{rf.all_verified}", "id_r_all"), (f"data.{rf.wrong_answers_left}", "id_r_left"),
                  (f"data.{rf.hint}", "id_r_hint"), ("status_code", "id_go")]

    def verify_transitions(nxt: str) -> list[dict]:
        """Hepsi doğru → hesap; hak bitti → başarısız kapanış; bu soru doğru → sıradaki soru. Gerisi (yanlış,
        ipucu, okunamadı, servis hatası) passthrough varsayılanıyla id_fix'e."""
        out = [when_eq("fetch_account", "identity verified", "id_r_all", *TRUE)]
        if i.swap_hint:
            out.append(when_eq("id_fix", "day and month swapped", "id_r_hint", i.swap_hint))
        out.append(when_eq("close_id_failed", "no wrong answers left", "id_r_left", "0"))
        out.append(when_eq(nxt, "answer correct", "id_r_verified", *TRUE))
        return out

    one_moment = {"type": "tts", "text": loc.one_moment}
    if all_at_once:
        body = body_for(spec, cat, "verify_identity", {"customer_id": cid})
        for k, q in enumerate(qs):
            body[q.field] = "{{id_ans_%d}}" % k
        nodes["verify_all"] = api_request(
            "verify_all", bank_call(cat, "verify_identity", body, retries=1), verify_map, "id_fix",
            verify_transitions("fetch_account"), on_enter=one_moment, first_entry_only=True)
    else:
        verify_fields = cat.tools["verify_identity"].fields
        role_field = spec.tool_fields.get("verify_identity", {}).get("field", "field")
        for k, q in enumerate(qs):
            if role_field in verify_fields:
                req = call("verify_identity", {"customer_id": cid, "field": q.field, "answer": "{{id_answer}}"},
                           retries=1)
            else:  # soru başına ayrı gövde alanı
                body = body_for(spec, cat, "verify_identity", {"customer_id": cid})
                body[q.field] = "{{id_answer}}"
                req = bank_call(cat, "verify_identity", body, retries=1)
            nxt = f"ask_q{k + 1}" if k + 1 < len(qs) else "fetch_account"
            nodes[f"verify_q{k}"] = api_request(
                f"verify_q{k}", req, verify_map, "id_fix", verify_transitions(nxt),
                on_enter=one_moment if k == 0 else None, first_entry_only=k == 0)

    # --- hesap ve müzakere ----------------------------------------------------------------------------
    nodes["fetch_account"] = api_request(
        "fetch_account", call("get_account", {"customer_id": cid}, retries=2),
        [(f"data.{rf.products}", "products")], "prep_account", on_enter=one_moment)
    nodes["prep_account"] = code("prep_account", snip("prep_account(vars, RT)\nvars['commit_msg'] = ''",
                                                      "vars['account_state'] = 'error'"), [], "negotiate")
    propose = model_tool(
        "propose_results",
        "CALL it as soon as the products are settled (see the step rules). Format: <product_id>:<amount>:<YYYY-MM-DD> "
        "or <product_id>:<status>, entries separated by ';'. The system checks it and reads it back to the customer.",
        {"results": "One entry per product separated by ';', e.g. 'p1:250.50:2026-10-16; p2:refused'."},
        # Tool sadece argümanı kaydeder; doğrulama tek bir propose_step node'unda (boyut: neg node'ları küçük kalır).
        # aynı turda check_offer_answer da çağrılabilir: ikisi de bekleyen olarak işaretlenir, önce durumlar işlenir
        "vars['propose_args'] = tool_arg(vars, 'propose_results', 'results', ARG_results)\n"
        "vars['propose_pending'] = '1'\nvars['commit'] = 'propose_in'", rt)
    # ad "check": hakem next_offer(result='agreed') çağrısını 'promise kaydedildi' saydı (SC-01, 11 Eki); kayıt yalnız
    # read-back onayından sonra create_promise ile olur
    offer = model_tool(
        "check_offer_answer",
        "CALL it, instead of speaking, every time the customer answers about the CURRENT product (the one the system "
        "proposed last; at the start the first product): a flat refusal or no answer, 'the amount is too much', or "
        "an agreed amount and date. A question or a vague reply ('you tell me', 'I don't know', 'what can I do?') is "
        "NOT a refusal: do not call it then; answer in one sentence and ask only whether the proposal works. Never "
        "call it on a message that is cut off (it ends with a comma, 'and', 'on the' or without a full stop): say "
        "only a short varied acknowledgement ('Mm-hm.', 'I'm listening.') and wait for the rest, which may correct "
        "what they said. The system then makes the next proposal itself (also the first one for the next "
        "product) or, when every product is settled, reads the promises back. Never propose an amount, a date or "
        "'today' yourself.",
        {"result": "'refused' (flat no or no answer), 'too_much' (the amount is too high), 'agreed' (this product "
                   "only) or 'agreed_all' (ONLY when the customer explicitly agrees one day for this and every later "
                   "product, each in full). If they agree to this product and refuse others, use 'agreed'."
                   + (" 'hardship' when the customer declines the support transfer you offered for a hardship (or "
                      "says again they cannot pay after it): every open product then ends with the hardship status."
                      if spec.negotiation.hardship_status else ""),
         "agreed_amount": "Only for 'agreed': the amount as a number, e.g. 250.50. Otherwise ''.",
         "agreed_date": "Only for 'agreed' and 'agreed_all': the date the customer named as YYYY-MM-DD (from the "
                        "calendar), exactly as named. Otherwise ''."},
        # Tool sadece argümanları kaydeder; iş tek bir offer_step node'unda (her neg node'una gömülen kod küçük kalır).
        "vars['offer_args'] = json.dumps([tool_arg(vars, 'check_offer_answer', 'result', ARG_result), "
        "tool_arg(vars, 'check_offer_answer', 'agreed_amount', ARG_agreed_amount), "
        "tool_arg(vars, 'check_offer_answer', 'agreed_date', ARG_agreed_date)])\nvars['offer_pending'] = '1'\n"
        "vars['commit'] = 'propose_in' if vars.get('propose_pending') == '1' else 'offer_in'", rt)
    per_product = spec.recording.mode == "per_product"
    loop = [when_eq("record_promise", "a promise to record", "next_step", "record")]
    if per_product:
        loop.append(when_eq("negotiate_more", "continue with the next product", "next_step", "more"))
    loop += [when_eq("record_note", "a note to record", "next_step", "note"),
             when_eq(SEND, "nothing left to record", "next_step", "end_r"),
             when_eq(SEND_NR, "nothing left to record", "next_step", "end_nr")]
    neg_transitions = [
        when_eq("offer_step", "the customer answered about the current product", "commit", "offer_in"),
        when_eq("propose_step", "results proposed", "commit", "propose_in"),
        when_eq("readback", "results accepted, read them back", "commit", "confirm"),
        when_eq("record_note", "only statuses: notes", "commit", "go_note"),
        when_eq(SEND, "only statuses: close", "commit", "go_end_r"),
        when_eq(SEND_NR, "only statuses: close", "commit", "go_end_nr"),
        when_eq("commit_fix", "results not accepted", "commit", "invalid", "invalid_say"),
    ] + post_extra
    task = texts.negotiate_task(spec)

    def neg_node(name: str, on_enter: dict, first_only: bool = False) -> dict:
        return conversation(name, task, on_enter=on_enter, first_entry_only=first_only, tools=[offer, propose],
                            transitions=neg_transitions, max_turns=60, max_turn_target="close_final")

    nodes["negotiate"] = neg_node("negotiate", {"type": "tts", "text": "{{debt_statement}} {{first_ask}}"}, True)
    # go_more sadece kod adımından çıkar: konuşma node'unda (negotiate_more → negotiate_more) temizlenmemiş bayrak her
    # müşteri turunda tekrar tetikleniyordu (SC-03, 11 Eki: aynı cümle 70 kez)
    step_routes = [t for t in neg_transitions if t["target_node"] not in ("offer_step", "propose_step")
                   and not t.get("is_tool_call")]
    if per_product:
        step_routes.append(when_eq("negotiate_more", "only statuses: next product", "commit", "go_more"))
    nodes["offer_step"] = code("offer_step", snip("check_offer_answer(vars, RT, *json.loads(vars.get('offer_args') or '[]'))",
                                                  "vars['commit'] = 'invalid'"),
                               [when_eq("negotiate_fix_say", "say the next proposal", "offer_go", "say"),
                                when_eq("propose_step", "every product settled", "commit", "propose_in")] + step_routes,
                               "commit_fix")
    nodes["propose_step"] = code("propose_step", snip("propose_step(vars, RT)", "vars['commit'] = 'invalid'"),
                                 [when_eq("negotiate_fix_say", "say the next proposal", "offer_go", "say"),
                                  when_eq("offer_step", "the answer about the current product, same turn", "commit",
                                          "offer_in")] + step_routes, "commit_fix")
    nodes["commit_fix"] = code("commit_fix", snip("commit_reset(vars)"),
                               [when_eq("negotiate_fix_say", "tell the customer", "fix_kind", "say")], "negotiate_fix")
    nodes["negotiate_fix"] = neg_node("negotiate_fix", {"type": "llm", "prompt": "{{fix_prompt}}"})
    nodes["negotiate_fix_say"] = neg_node("negotiate_fix_say", {"type": "tts", "text": "{{commit_say}}"})
    if per_product:
        nodes["negotiate_more"] = neg_node("negotiate_more", {"type": "tts", "text": "{{progress_say}}"})

    # --- read-back ve onay: cümle kodla üretilir; kayıt ancak açık bir evetten sonra başlar ------------------
    c = spec.confirmation
    nodes["readback"] = conversation(
        "readback", texts.readback_task(spec), on_enter={"type": "tts", "text": "{{readback_say}}"},
        transitions=[intent("record_promise", f'The customer clearly says yes to "{c.confirm_question}".'),
                     intent("readback_reset", "The customer does not confirm, says no, or wants to change an amount, "
                                              "a date or a product.")] + post_extra,
        max_turns=8, max_turn_target="readback_reset")
    nodes["readback_reset"] = code("readback_reset", snip("readback_reset(vars, RT)"), [], "negotiate_fix")

    # --- kayıt ve not döngüsü (her adım tek code node'u) -----------------------------------------------
    rec_call = call("create_promise",
                    {"customer_id": cid, "product_id": "{{rec_pid}}", "amount": "{{rec_amount:json}}",
                     "date": "{{rec_date}}"})
    nodes["record_promise"] = api_request("record_promise", rec_call, [(ok_path(spec, cat, "create_promise"),
                                                                        "rec_r_ok")], "rec_step",
                                          on_enter=one_moment, first_entry_only=True)
    nodes["rec_step"] = code("rec_step", snip("after_record_step(vars, RT)", "vars['next_step'] = 'end_r'"), loop,
                             SEND)
    if cat.has("add_note"):
        note_call = call("add_note", {"customer_id": cid, "product_id": "{{note_pid}}", "reason": "{{note_reason}}"},
                         retries=1)
        nodes["record_note"] = api_request("record_note", note_call, [(ok_path(spec, cat, "add_note"), "note_r_ok")],
                                           "note_step")
    else:
        nodes["record_note"] = code("record_note", snip("vars['note_r_ok'] = 'true'"), [], "note_step")
    nodes["note_step"] = code("note_step", snip("after_note_step(vars, RT)", "vars['next_step'] = 'end_r'"), loop,
                              SEND)
    nodes["close_final"] = code("close_final", snip("set_close(vars, RT, '', '', '')"),
                                [when_eq(SEND_NR, "close without reason", "close_kind", "noreason")], SEND)

    # --- transferler: kodsuz (kuyruk ve kapanış sabit) -------------------------------------------------
    for t in spec.transfers:
        reason = spec.closing.transfer_reasons.get(t.queue, t.queue)
        nodes[f"transfer_{t.id}"] = api_request(
            f"transfer_{t.id}", call("transfer_to_agent", {"customer_id": cid, "queue": t.queue}, retries=1),
            [(ok_path(spec, cat, "transfer_to_agent"), "transfer_ok_" + _safe(t.queue))], f"close_transfer_{t.id}")
        nodes[f"close_transfer_{t.id}"] = static_close(f"close_transfer_{t.id}", spec.closing.transfer_outcome,
                                                       reason, "", False)

    # --- geri arama (üçüncü kişi ve, brief isterse, müşterinin kendisi) ----------------------------------
    tp = spec.third_party
    propose_cb = model_tool(
        # ad "check": hakem "propose/schedule" adlı bir tool çağrısını kurulmuş callback sanıyordu (SC-05, 11 Eki)
        "check_callback_time",
        "CALL it when the person names a day for the callback, with the time if they gave one. The system checks "
        "the day and the time.",
        {"date": "The day as YYYY-MM-DD.", "time": "The time as HH:MM, 24-hour clock; '' if they named only a day."},
        "take_callback(vars, RT, tool_arg(vars, 'check_callback_time', 'date', ARG_date), "
        "tool_arg(vars, 'check_callback_time', 'time', ARG_time))", rt)
    cb_ok_path = ok_path(spec, cat, "schedule_callback")

    def callback_flow(prefix: str, kind: str, task: str, first_prompt: str, done: str, gave_up: str,
                      extra: list[dict], early: str) -> None:
        nodes[prefix] = code(prefix, snip((early + "\n" if early else "") + f"prep_callback(vars, RT, {kind!r})\n"
                                          "vars['cb_msg'] = ''\nvars['cb_state'] = ''\nvars['cb_bad'] = '0'"), [],
                             f"{prefix}_talk")
        # müşteri zamanı geçişi tetikleyen mesajda zaten söylediyse tekrar sorulmaz (SC-04/05: hakem "iki kez sordu")
        first_prompt = ("If their last message already said when to call (a day or a time), do not ask again: repeat "
                        "that day and time back in one short question, e.g. 'Monday at 8 pm, is that right?'. "
                        "Otherwise: " + first_prompt)
        trans = [when_eq(f"{prefix}_book", "callback time accepted", "cb_state", "ok"),
                 when_eq(gave_up, "no valid callback time", "cb_state", "gave_up"),
                 when_eq(f"{prefix}_fix", "callback time rejected or missing", "cb_state", "invalid",
                         "need_time")] + extra
        nodes[f"{prefix}_talk"] = conversation(
            f"{prefix}_talk", task, on_enter={"type": "llm", "prompt": first_prompt}, tools=[propose_cb],
            transitions=trans, max_turns=12, max_turn_target=gave_up)
        nodes[f"{prefix}_fix"] = code(f"{prefix}_fix", snip("vars['cb_state'] = ''"), [], f"{prefix}_retry")
        nodes[f"{prefix}_retry"] = conversation(
            f"{prefix}_retry", task,
            on_enter={"type": "tts", "text": "{{cb_say}}"},
            tools=[propose_cb], transitions=trans, max_turns=8, max_turn_target=gave_up)
        cb_call = bank_call(cat, "schedule_callback", callback_body(spec, cat, cid), retries=1)
        nodes[f"{prefix}_book"] = api_request(f"{prefix}_book", cb_call, [(cb_ok_path, "cb_r_ok")], gave_up,
                                              [when_eq(done, "callback booked", "cb_r_ok", *OK)])

    nb = tp.no_callback_outcome
    callback_flow(
        "third_party", "third_party", texts.third_party_task(spec),
        f'Without saying why you are calling, ask: "{tp.ask_reachability}"', "close_callback", "close_no_callback",
        [tool_transition("close_wrong_number", "The number does not belong to the customer."),
         tool_transition("close_deceased", "The customer has died."),
         tool_transition("close_no_callback", "The person will not give any time to reach the customer.")],
        f"set_close_default(vars, RT, {nb.outcome!r}, {nb.reason!r})")
    if cc.enabled:
        gave_up = "close_cust_no_callback" if cc.no_callback_outcome else "close_final"
        callback_flow("cust_cb", "customer", texts.customer_callback_task(spec, gave_up),
                      f'Ask: "{cc.ask}"' if cc.ask else "Ask when they can be called back.",
                      "close_cust_callback", gave_up,
                      [tool_transition(gave_up, "The customer will not give any time for a callback.")], "")
        nodes["close_cust_callback"] = static_close("close_cust_callback", cc.outcome.outcome, cc.outcome.reason,
                                                    "", False)
        if cc.no_callback_outcome:
            nodes[gave_up] = static_close(gave_up, cc.no_callback_outcome.outcome, cc.no_callback_outcome.reason,
                                          "", False)

    # --- sabit kapanışlar (kodsuz) ---------------------------------------------------------------------
    # müşteri olduğu doğrulanmamış kişiye müşterinin adıyla veda edilmez
    for name, ref, speech, anonymous in [
        ("close_unclear", o.unclear, "", True),
        ("close_wrong_number", tp.wrong_number_outcome, "", True),
        ("close_deceased", tp.deceased_outcome, tp.deceased_sentence, True),
        ("close_callback", tp.callback_outcome, "", True),
        ("close_no_callback", tp.no_callback_outcome, "", True),
        ("close_id_failed", i.fail_outcome, i.fail_sentence, False),
        ("close_id_declined", i.decline_outcome, "", False),
    ]:
        nodes[name] = static_close(name, ref.outcome, ref.reason, speech, anonymous)

    # --- hesaplanan kapanış: veda (tts) + close_call (her zaman son banka çağrısı) + telefonu kapat --------
    say = {"type": "tts", "text": "{{closing_speech}}"}
    nodes[SEND] = api_request(SEND, call("close_call", {"customer_id": cid, "outcome": "{{close_outcome}}",
                                                        "reason": "{{close_reason}}"}, retries=2),
                              close_ok, END, on_enter=say)
    nodes[SEND_NR] = api_request(SEND_NR, call("close_call", {"customer_id": cid, "outcome": "{{close_outcome}}"},
                                               retries=2), close_ok, END, on_enter=say)
    # kod servisi çalışmazsa: o ana kadar yazılmış outcome ile, değişken gerektirmeyen vedayla kapanış
    bye = {"type": "tts", "text": goodbye_anon}
    nodes[FALLBACK] = api_request(FALLBACK, call("close_call", {"customer_id": cid, "outcome": "{{close_outcome}}",
                                                                "reason": "{{close_reason}}"}, retries=2),
                                  close_ok, END, on_enter=bye)
    nodes[FALLBACK_NR] = api_request(FALLBACK_NR, call("close_call", {"customer_id": cid,
                                                                      "outcome": "{{close_outcome}}"}, retries=2),
                                     close_ok, END, on_enter=bye)
    nodes[END] = end_call(END, "call_closed")

    # --- yedek: müşteri telefonu kapatırsa close_call yine gider. Normal yolda pre-hook isteği iptal eder ---
    backup = call("close_call", {"customer_id": cid, "outcome": "{{close_outcome}}", "reason": "{{close_reason}}"},
                  retries=2, lifecycle="end_of_call")
    backup["pre_process_code"] = snip("lifecycle_close(vars, config, RT)")

    test_vars = {v: "" for v in spec.call_variables.all}
    return {
        "initial_node": "opener",
        "system_prompt": texts.system_prompt(spec),
        "nodes": nodes,
        "global_nodes": {},
        "tools": [backup],
        "test_variables": test_vars,
    }


def workflow_hash(workflow: dict) -> str:
    return hashlib.sha256(json.dumps(workflow, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
