"""Spec'ten modelin göreceği metinleri üretir: system_prompt ve node task_message'ları.

Modelin gördüğü talimatlar brief'in dilinde değil, İngilizce yazılır (agent modeli için en güvenli);
müşteriye söylenen sabit cümleler brief'ten birebir gelir. Brief'e özgü hiçbir değer burada sabit değildir.
"""
from __future__ import annotations

import re

from fbb.runtime.flow import without_placeholders  # noqa: F401  (graph.py kullanır)
from fbb.spec import PolicySpec


def tpl(text: str) -> str:
    """Spec şablonundaki {değişken} → Freya'nın {{değişken}} biçimi."""
    return re.sub(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})", lambda m: "{{" + m.group(1) + "}}", text)


def bullets(items: list[str]) -> str:
    return "\n".join("- " + i.strip() for i in items if i and i.strip())


def system_prompt(spec: PolicySpec) -> str:
    o = spec.opening
    lines = [
        spec.agent_role.strip(),
        f"Speak {spec.language}. Keep every turn to one or two short sentences. Ask one question at a time.",
        "Rules for every step:",
        "- Say only what the current step allows. Never mention why you are calling, any product, amount or account "
        "detail unless the current step gives it to you.",
    ]
    if o.robot_answer:
        lines.append(f'- If asked whether you are a robot, a machine or an AI, say: "{o.robot_answer}" Then continue.')
    if o.scam_answer:
        lines.append(f'- If asked whether this call is a scam or genuine, say: "{o.scam_answer}" Then continue.')
    lines.append(f'- If asked something you cannot answer from the facts you were given, say: '
                 f'"{o.unknown_answer or "I do not have that information."}" Never invent figures, dates or reasons.')
    lines += [
        "- After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing.",
        "- Call only the tools of the current step, one tool per message.",
        "- Never say goodbye or end the call yourself: the system ends the call with the closing words.",
    ]
    return "\n".join(lines)


def _nth(n: int) -> str:
    return {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(n, f"{n}th")


def opener_task(spec: PolicySpec) -> str:
    o = spec.opening
    cc = spec.customer_callback
    asks = max(o.max_asks, 1)
    return "\n".join([
        f'You have just said: "{o.first_sentence} {tpl(o.confirm_question)}"',
        "Your only job in this step is to find out who is on the line.",
        f"Only these count as confirmation that you are speaking with the customer: {', '.join(o.accepted_confirmations)}.",
        (f"These are NOT confirmation: {', '.join(o.not_confirmations)}." if o.not_confirmations else ""),
        "Decide after each answer:",
        "- The customer clearly confirms → call transition_to_ask_q0 at once, without speaking.",
        "- Someone else answered (a relative, a colleague) → call transition_to_third_party at once, without speaking.",
        "- The person says the number does not belong to the customer → call transition_to_close_wrong_number.",
        "- The person says the customer has died → call transition_to_close_deceased.",
        f'- Anything else (a question, "hello", "who is this", silence): answer the question briefly if there is one '
        f'(you may repeat the opening sentence), then ask again: "{tpl(o.confirm_question)}". You may ask '
        f"{asks} times in total. If the answer to the {_nth(asks)} ask is still not a confirmation, call "
        "transition_to_close_unclear.",
        "- The person refuses to talk a second time → call transition_to_close_id_declined.",
        (f"- {cc.trigger} → call transition_to_cust_cb." if cc.enabled and "pre_identity" in cc.stages else ""),
        _human_rule(spec, "pre_identity"),
        "Never say why you are calling. Never say any of these words: "
        + ", ".join(o.forbidden_before_verification) + ".",
    ]).strip()


def _human_rule(spec: PolicySpec, stage: str) -> str:
    out = []
    for t in spec.transfers:
        if stage in t.stages and t.ask_first:
            out.append(f'- {t.trigger} First ask once: "{t.ask_first}". If they insist, say "{t.say}" and call '
                       f"transition_to_transfer_{t.id}.")
    return "\n".join(out)


def identity_task(spec: PolicySpec, spoken: str) -> str:
    i = spec.identity
    cc = spec.customer_callback
    purpose = (" Asking what the call is about instead of answering also counts as refusing."
               if i.purpose_question_counts_as_decline else "")
    return "\n".join([
        f'This step is the security check. You have just said: "{tpl(spoken)}"',
        "- When the customer answers that question, call submit_answer with their answer exactly as they said it "
        "(words are fine, do not convert). Do not speak before the call. Never guess or fill in an answer yourself.",
        "- If a message contains an answer AND a question or complaint, it is an answer: call submit_answer first. "
        "Only a message with no answer at all can count as refusing.",
        "- If they give only part of a number or a date, call submit_answer with that part anyway: the system keeps "
        "it and asks for the rest. Call submit_answer again with whatever they add.",
        "- Never stall or say you are waiting or have a technical issue: every answer goes to submit_answer at once.",
        "- If they ask a question back, answer it briefly in one sentence and ask the security question again.",
        f"- If they refuse to answer the security question, call decline_questions. Do not speak before the call: the "
        f"system says what is needed.{purpose}",
        "- Never say why you are calling and never mention any product or amount in this step.",
        (f"- {cc.trigger} → call transition_to_cust_cb." if cc.enabled and "pre_identity" in cc.stages else ""),
        _human_rule(spec, "pre_identity"),
        "Note from the last check: {{id_msg}}",
    ]).strip()


def _transfers_text(spec: PolicySpec) -> str:
    return "\n".join(
        f'- {t.trigger} ' + (f'First ask once: "{t.ask_first}". If they insist, ' if t.ask_first else "")
        + (f'say "{t.say}" and ' if t.say else "") + f"call transition_to_transfer_{t.id}."
        for t in spec.transfers if "post_verify" in t.stages)


def negotiate_task(spec: PolicySpec) -> str:
    n, c, mp = spec.negotiation, spec.confirmation, spec.multi_product
    cc = spec.customer_callback
    per_product = spec.recording.mode == "per_product"
    statuses = "\n".join(f'  - {s.id}: {s.trigger}' + (f' Say: "{s.say}"' if s.say else "") for s in spec.statuses)
    parts = [
        "The customer is verified. You have just told them: \"{{debt_statement}} {{first_ask}}\"",
        "",
        "FACTS FROM THE BANK (already computed for today; use them exactly, never compute dates yourself):",
        "Today is {{today_spoken}} ({{today_iso}}). Tomorrow is {{tomorrow_spoken}} ({{tomorrow_iso}}).",
        "Products (in the bank's order):",
        "{{product_facts}}",
        "Calendar. Each row ends with what to do, per product, if the customer names that day. Follow it exactly:",
        "{{day_table}}",
        "",
        "DATES THE CUSTOMER SAYS: look up any day the customer names (today, tomorrow, a weekday, 'this'/'next' "
        "weekday, a date in words) in the calendar table and use exactly that date. The attempt dates in the facts are "
        "only for your own proposals; never replace a date the customer named with one of them. Whenever you say a "
        "date, take its weekday from the same table row (never work out a weekday yourself). When the customer names "
        "a day, do what that row says for the product: 'OK' means accept the day; otherwise offer exactly the date "
        "the row gives.",
        "",
        "AMOUNTS AND DATES IN PIECES: customers often say a number or a date in two parts or correct themselves. "
        "A message that is only a number ('30.', 'Twenty.', 'Six hundred.') or that stops mid-sentence ('on "
        "October', 'I want to pay both on 3') is usually only the first part: do not use it yet, ask 'Sorry, the "
        "full amount?' or 'Which day exactly?' and wait for the rest. Never treat such a part as an offer or a "
        "refusal. Always use their final, corrected value.",
        "",
        "RULES:",
        bullets(n.rules),
        bullets(mp.rules) if mp.enabled else "",
        bullets(spec.general_rules),
        bullets(spec.unmapped),
        ("Never offer: " + ", ".join(n.forbidden_offers) + ".") if n.forbidden_offers else "",
        "",
        "PERSUASION AND PRODUCT ORDER (the system makes every proposal and keeps the order; you never do):",
        "- Products are settled one at a time, in the bank's order. The CURRENT product is the first one at the "
        "start, then the one the system proposed last (see the check result below).",
        "- Never propose an amount or a date yourself, never ask again whether they can pay today, never repeat a "
        "proposal, and never move on to another product yourself. The first question about paying today counts as "
        "the first ask for every product" + (" at once." if mp.enabled else ".")
        + " Every time the customer answers about the current product, call next_offer: result='refused' for a flat "
        "no or no answer, 'too_much' when they say the amount is too high, 'agreed' with agreed_amount and "
        "agreed_date when they name or accept an amount and a day (look the day up in the calendar)"
        + (", 'agreed_all' with agreed_date when they name ONE day for this and every later product (pass the day "
           "exactly as named, even if it is after a deadline: the system moves each product to its allowed date and "
           "says so)" if mp.enabled else "")
        + ". If they talk about a later product first, keep it in mind and still answer for the current product "
        "first.",
        "- Statuses other than a refusal (" + ", ".join(st.id for st in spec.statuses if not st.persuade)
        + ") and transfers are not next_offer answers: handle them under the rules and call propose_results with "
        "every product.",
        "- If the customer asks a question about the proposal, answer it and ask only whether that works.",
        "- If the customer names their own amount or date, that is not a refusal: settle it under the rules above "
        "and pass it with result='agreed'; the system checks it.",
        (f'- If the customer asks to change a promise that is already recorded, say: "{c.change_after_record_sentence}"'
         if c.change_after_record_sentence else ""),
        "",
        "TRANSFERS:",
        _transfers_text(spec),
        (f"- {cc.trigger} → call transition_to_cust_cb." if cc.enabled and "post_verify" in cc.stages else ""),
        "",
        "FINISHING THIS STEP (very important, this overrides any rule above about reading back or confirming):",
        ("When every product is settled through next_offer, the system reads the promises back by itself. Call "
         "propose_results yourself only when a product ends with a status other than a refusal or a transfer is "
         "needed: "
         + ("with that product only; the system reads it back, records it after the customer confirms, and then you "
            "continue with the next product." if per_product else
            "call propose_results ONCE with one entry per product (also the ones already settled), separated by "
            "';'.")),
        "  - a promise: <product_id>:<amount as a number>:<YYYY-MM-DD>. Use the date the customer agreed, exactly as "
        "named, even if it is not a business day or is after a deadline: the system moves it to the allowed date and "
        "tells the customer.",
        "  - no promise: <product_id>:<status>, where status is one of:",
        statuses,
        "  Example: p1:250.50:2026-10-16; p2:refused",
        f'- Do NOT read the promises back and do NOT ask "{c.confirm_question}" yourself: after propose_results the '
        "system reads every promise back (product, amount, date) and asks for the confirmation.",
        "- Never say that anything is recorded or saved: the system says it after the bank confirms. Do not say "
        "goodbye: the system closes the call.",
        "Last check result: {{commit_msg}}",
    ]
    return "\n".join(p for p in parts if p is not None).strip()


def readback_task(spec: PolicySpec) -> str:
    c = spec.confirmation
    return "\n".join([
        "You have just read the customer's promises back and asked for confirmation: \"{{readback_say}}\"",
        "No tool call is allowed in this step; the system acts on the customer's answer.",
        f'- If the customer asks a question, answer it in one short sentence and ask "{c.confirm_question}" again.',
        "- Never change an amount or a date yourself and never say that anything is recorded or saved.",
        bullets(c.rules),
        "TRANSFERS:",
        _transfers_text(spec),
    ]).strip()


def third_party_task(spec: PolicySpec) -> str:
    tp = spec.third_party
    return "\n".join([
        "The person on the line is NOT the customer.",
        bullets(tp.rules),
        f'Ask when the customer can be reached: "{tp.ask_reachability}"',
        "{{cb_facts}}",
        "When the person names a day and a time, turn them into YYYY-MM-DD and HH:MM (24-hour clock) and call "
        "propose_callback. Do not decide yourself whether the time is allowed: the system checks it.",
        "If the person says the number does not belong to the customer, call transition_to_close_wrong_number. "
        "If they say the customer has died, call transition_to_close_deceased. If they will not give any time, "
        "call transition_to_close_no_callback.",
        "Never say why you are calling and never answer questions about the customer's account.",
        "Last check result: {{cb_msg}}",
    ]).strip()


def customer_callback_task(spec: PolicySpec) -> str:
    cc = spec.customer_callback
    return "\n".join([
        "The customer wants to be called back later.",
        f'Ask when they can be called: "{cc.ask}"' if cc.ask else "Ask when they can be called back.",
        "{{cb_facts}}",
        "When the customer names a day and a time, turn them into YYYY-MM-DD and HH:MM (24-hour clock) and call "
        "propose_callback. Do not decide yourself whether the time is allowed: the system checks it.",
        "If they will not give any time, call transition_to_close_final.",
        "Last check result: {{cb_msg}}",
    ]).strip()
