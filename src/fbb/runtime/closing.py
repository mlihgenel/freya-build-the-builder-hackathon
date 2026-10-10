"""Çağrının sonucunu (outcome, reason) durumdan hesaplar. set_close'da ve close_call lifecycle pre-hook'unda çalışır.

Kapanış tablosu spec'ten gelir (RT["closing"]). Müşteri telefonu kapatsa bile mevcut duruma göre
doğru sonuç yazılsın diye karar sadece değişkenlere dayanır, konuşmaya değil.
"""
import json


def as_int(x):
    try:
        return int(float(x))
    except Exception:
        return 0


def ok_true(x):
    """Bankanın 'işlem yapıldı' cevabı: ok alanı (metin olarak 'true'/'True') ya da zarfın status'u ('success')."""
    return str(x).strip().lower() in ("true", "1", "yes", "success")


def transfer_queue_of(vars, RT):
    queue = str(vars.get("transfer_queue") or "")
    if queue:
        return queue
    for q in RT.get("closing", dict()).get("transfer_reasons", dict()):
        if ok_true(vars.get("transfer_ok_" + q)):
            return q
    return ""


def decide_close(vars, RT):
    """Dönüş: (outcome, reason). reason '' ise close_call'a hiç gönderilmez."""
    c = RT["closing"]
    queue = transfer_queue_of(vars, RT)
    if queue:
        return c["transfer_outcome"], c.get("transfer_reasons", dict()).get(queue, queue)
    if as_int(vars.get("promises_ok")) > 0:
        return c["promise_outcome"], ""
    explicit = str(vars.get("close_fixed_outcome") or "")
    if explicit:
        return explicit, str(vars.get("close_fixed_reason") or "")
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


def mark_close(vars, RT):
    """O anki duruma göre close_outcome/close_reason/close_kind yazar (yedek kapanışlar bu değerleri kullanır)."""
    o, r = decide_close(vars, RT)
    vars["close_outcome"] = o
    vars["close_reason"] = r
    has_reason = bool(r) and o not in RT["closing"].get("no_reason_outcomes", [])
    vars["close_kind"] = "reason" if has_reason else "noreason"


def apply_close_body(vars, body, RT):
    """close_call isteğinin gövdesini durumdan yeniden kurar (alan adları RT['close_fields']'tan)."""
    names = RT.get("close_fields") or dict()
    out_f = names.get("outcome", "outcome")
    reason_f = names.get("reason", "reason")
    outcome, reason = decide_close(vars, RT)
    body[out_f] = outcome
    if reason and outcome not in RT["closing"].get("no_reason_outcomes", []):
        body[reason_f] = reason
    elif reason_f in body:
        body.pop(reason_f)
    return body


def lifecycle_close(vars, config, RT):
    """Çağrı bittikten sonra çalışan yedek close_call'ın pre-hook'u.

    Normal yolda close_call zaten gönderildi (close_r_ok): istek URL'siz bırakılır ve gitmez. Müşteri telefonu
    kapattıysa gövde durumdan kurulur. Gövde her durumda düzeltilir: URL boşaltma işe yaramazsa ikinci çağrı
    birincinin aynısıdır."""
    body = config.get("body")
    if isinstance(body, dict):
        apply_close_body(vars, body, RT)
    if ok_true(vars.get("close_r_ok")):
        config["url"] = ""
