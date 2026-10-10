"""Spec'ten modelin göreceği metinleri üretir: system_prompt ve node task_message'ları.

Modelin gördüğü talimatlar brief'in dilinde değil, İngilizce yazılır (agent modeli için en güvenli);
müşteriye söylenen sabit cümleler brief'ten birebir gelir. Brief'e özgü hiçbir değer burada sabit değildir.
"""
from __future__ import annotations

import re

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


def opener_task(spec: PolicySpec) -> str:
    o = spec.opening
    return "\n".join([
        f'You have just said: "{o.first_sentence} {tpl(o.confirm_question)}"',
        "Your only job in this step is to find out who is on the line.",
        f"Only these count as confirmation that you are speaking with the customer: {', '.join(o.accepted_confirmations)}.",
        (f"These are NOT confirmation: {', '.join(o.not_confirmations)}." if o.not_confirmations else ""),
        "Decide after each answer:",
        "- The customer clearly confirms → call transition_to_identity_check at once, without speaking.",
        "- Someone else answered (a relative, a colleague) → call transition_to_third_party at once, without speaking.",
        "- The person says the number does not belong to the customer → call transition_to_close_wrong_number.",
        "- The person says the customer has died → call transition_to_close_deceased.",
        f'- Anything else (a question, "hello", "who is this", silence): answer the question briefly if there is one '
        f'(you may repeat the opening sentence), then ask again: "{tpl(o.confirm_question)}". If the answer to that '
        f"second ask is still not a confirmation, call transition_to_close_unclear.",
        "- The person refuses to talk a second time → call transition_to_close_id_declined.",
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


def identity_task(spec: PolicySpec) -> str:
    i = spec.identity
    return "\n".join([
        "This step is the security check. You have just asked the customer: \"{{id_say}}\"",
        "- When the customer answers that question, call submit_answer with their answer exactly as they said it "
        "(words are fine, do not convert). Do not speak before the call. Never guess or fill in an answer yourself.",
        "- If they give only part of a number or a date, ask for the rest, then call submit_answer with the whole answer.",
        "- If they ask a question back, answer it briefly in one sentence and ask the security question again.",
        f'- If they refuse to answer or ask what the call is about instead: the first time say "{i.decline_explain}" '
        "and ask the question again. The second time, call transition_to_close_id_declined.",
        "- Never say why you are calling and never mention any product or amount in this step.",
        _human_rule(spec, "pre_identity"),
        "Note from the last check: {{id_msg}}",
    ]).strip()


def negotiate_task(spec: PolicySpec) -> str:
    n, c, mp = spec.negotiation, spec.confirmation, spec.multi_product
    statuses = "\n".join(f'  - {s.id}: {s.trigger}' + (f' Say: "{s.say}"' if s.say else "") for s in spec.statuses)
    transfers = "\n".join(
        f'- {t.trigger} ' + (f'First ask once: "{t.ask_first}". If they insist, ' if t.ask_first else "")
        + (f'say "{t.say}" and ' if t.say else "") + f"call transition_to_transfer_{t.id}."
        for t in spec.transfers if "post_verify" in t.stages)
    parts = [
        "The customer is verified. You have just told them: \"{{debt_statement}} {{first_ask}}\"",
        "",
        "FACTS FROM THE BANK (already computed for today; use them exactly, never compute dates yourself):",
        "Today is {{today_spoken}} ({{today_iso}}). Tomorrow is {{tomorrow_spoken}} ({{tomorrow_iso}}).",
        "Products (in the bank's order):",
        "{{product_facts}}",
        "Calendar (use it to turn any day the customer says into a YYYY-MM-DD date):",
        "{{day_table}}",
        "",
        "DATES THE CUSTOMER SAYS: look up any day the customer names (today, tomorrow, a weekday, 'this'/'next' "
        "weekday, a date in words) in the calendar table and use exactly that date. The attempt dates in the facts are "
        "only for your own proposals; never replace a date the customer named with one of them.",
        "",
        "RULES:",
        bullets(n.rules),
        bullets(mp.rules) if mp.enabled else "",
        bullets(c.rules),
        bullets(spec.general_rules),
        bullets(spec.unmapped),
        ("Never offer: " + ", ".join(n.forbidden_offers) + ".") if n.forbidden_offers else "",
        "Persuasion attempts are listed per product in the facts. Use them in order and only as many as allowed.",
        "",
        "TRANSFERS:",
        transfers,
        "",
        "FINISHING THIS STEP (very important):",
        "When every product has either a confirmed promise or a final status, call submit_results ONCE with one "
        "entry per product, separated by ';':",
        f'  - a promise: <product_id>:<amount as a number>:<YYYY-MM-DD>. Only after you read the product, the amount '
        f'and the date back and the customer clearly said yes to "{c.confirm_question}".',
        "  - no promise: <product_id>:<status>, where status is one of:",
        statuses,
        "  Example: p1:250.50:2026-10-16; p2:refused",
        "- Do not say that anything is recorded: the system records the promises after submit_results and tells the "
        "customer. Do not say goodbye: the system closes the call.",
        "- If submit_results answers that nothing was recorded, explain the problem in one sentence and continue.",
        "Last check result: {{commit_msg}}",
    ]
    return "\n".join(p for p in parts if p is not None).strip()


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
