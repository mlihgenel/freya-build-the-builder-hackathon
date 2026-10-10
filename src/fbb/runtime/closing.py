"""Çağrının sonucunu (outcome, reason) durumdan hesaplar. close_call pre-hook'unda ve set_close'da çalışır.

Kapanış tablosu spec'ten gelir (RT["closing"]). Müşteri telefonu kapatsa bile mevcut duruma göre
doğru sonuç yazılsın diye karar sadece değişkenlere dayanır, konuşmaya değil.
"""
import json


def as_int(x):
    try:
        return int(float(x))
    except Exception:
        return 0


def decide_close(vars, RT):
    """Dönüş: (outcome, reason). reason '' ise close_call'a hiç gönderilmez."""
    c = RT["closing"]
    queue = str(vars.get("transfer_queue") or "")
    if queue:
        return c["transfer_outcome"], c.get("transfer_reasons", dict()).get(queue, queue)
    if as_int(vars.get("promises_ok")) > 0:
        return c["promise_outcome"], ""
    explicit = str(vars.get("close_outcome") or "")
    if explicit:
        return explicit, str(vars.get("close_reason") or "")
    try:
        statuses = json.loads(vars.get("statuses_json") or "[]")
    except Exception:
        statuses = []
    if statuses:
        paid = c.get("paid_status", "paid")
        if all(s.get("reason") == paid for s in statuses):
            return c["paid_outcome"], ""
        for s in statuses:
            if s.get("reason") != paid:
                return c["no_promise_outcome"], c.get("status_to_reason", dict()).get(s["reason"], s["reason"])
    if str(vars.get("id_state") or "") == "verified":
        return c["hangup_verified"][0], c["hangup_verified"][1]
    return c["hangup_unverified"][0], c["hangup_unverified"][1]


def apply_close_body(vars, body, RT):
    """close_call isteğinin gövdesini durumdan yeniden kurar."""
    outcome, reason = decide_close(vars, RT)
    body["outcome"] = outcome
    if reason and outcome not in RT["closing"].get("no_reason_outcomes", []):
        body["reason"] = reason
    elif "reason" in body:
        body.pop("reason")
    return body
