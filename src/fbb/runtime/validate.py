"""Modelin önerdiği sonuçları ve geri arama tekliflerini kurallara göre doğrular. Freya code node'larında çalışır.

Model müzakereyi bitirince sonucu önerir (propose_results). Kod:
- kurala göre düzeltilebilen her şeyi düzeltir (deadline'dan sonraki tarih → deadline; iş günü olmayan gün → sonraki
  iş günü; borçtan fazla tutar → borç) ve bunu read-back cümlesinde söyler,
- düzeltilemeyeni (floor altı tutar, geçmiş tarih) müşteriye söylenecek bir cümleye çevirir,
- read-back cümlesini kendisi üretir. Kayıt ancak müşteri bu cümleyi onaylayınca başlar.
"""
import json
import re


def parse_results(text):
    """'p1:510:2026-10-15; p2:refused' → [{"product_id", "kind": "promise"|<sebep>, "amount", "date"}]."""
    out = []
    for part in re.split(r"[;\n|]+", str(text or "")):
        bits = [b.strip() for b in part.strip().split(":")]
        if not bits or not bits[0]:
            continue
        entry = {"product_id": bits[0], "kind": "", "amount": None, "date": ""}
        if len(bits) >= 3:
            entry["kind"] = "promise"
            amount = normalize_amount(re.sub(r"[^0-9a-zA-Z.,\- ]", "", bits[1]).replace(",", ""))
            entry["amount"] = amount
            entry["date"] = bits[2][:10]
        elif len(bits) == 2:
            entry["kind"] = bits[1].lower()
        out.append(entry)
    return out


def say(RT, key, values):
    return fill((RT.get("locale") or dict()).get(key, ""), values)


def adjust_promise(plan, amount, when, today, RT):
    """Bir promise'i kurallara göre düzeltir.

    Dönüş: (durum, tutar, tarih, not). durum 'ok' ise tutar/tarih kaydedilecek değerlerdir ve not read-back'te
    söylenir; 'say' ise not müşteriye söylenecek cümledir ve hiçbir şey kaydedilmez."""
    cal = RT["cal"]
    deadline = to_date(plan["deadline"])
    product = plan.get("wording") or plan["product_id"]
    low = plan["floor"] if plan["floor"] else plan["past_due"]
    notes = []
    if amount < low - 0.005:
        return "say", amount, when, say(RT, "below_floor", {"amount": fmt_money(low, RT), "product": product})
    if amount > plan["past_due"] + 0.005:
        amount = plan["past_due"]
        notes.append(say(RT, "capped_amount", {"amount": fmt_money(amount, RT), "product": product}))
    if when < today:
        nxt = next_business_day(today, cal, include_today=True)
        return "say", amount, when, say(RT, "past_date", {"date": spoken_date(min(nxt, deadline), RT),
                                                          "product": product})
    if when > deadline:
        when = deadline
        notes.append(say(RT, "moved_deadline", {"date": spoken_date(deadline, RT), "product": product}))
    elif not is_business_day(when, cal):
        asked = when
        when = min(next_business_day(when, cal), deadline)
        notes.append(say(RT, "moved_business_day", {"asked": spoken_date(asked, RT), "date": spoken_date(when, RT),
                                                    "product": product}))
    return "ok", round(amount, 2), when, " ".join(n for n in notes if n)


def readback_text(promises, notes, plans, RT):
    by_id = dict((p["product_id"], p) for p in plans)
    items = []
    for p in promises:
        plan = by_id.get(p["product_id"], dict())
        items.append(say(RT, "readback_item", {"amount": fmt_money(p["amount"], RT), "date": spoken_date(p["date"], RT),
                                               "product": plan.get("wording") or p["product_id"]}))
    loc = RT.get("locale") or dict()
    parts = [loc.get("readback_intro", "")] + [n for n in notes if n] + ["; ".join(items) + "."]
    parts.append(RT.get("confirm_question", ""))
    return " ".join(x.strip() for x in parts if x and x.strip())


def settled_ids(vars):
    """per_product modunda bitmiş ürünler: kaydedilen promise'ler ve durumu belli olanlar."""
    done = [r["product_id"] for r in json.loads(vars.get("recorded_json") or "[]")]
    done += [s["product_id"] for s in json.loads(vars.get("statuses_json") or "[]")]
    return done


def validate_results(vars, text, RT):
    """propose_results girdisini doğrular ve düzeltir.

    Dönüş: (durum, model_mesajı, müşteri_cümlesi). durum: 'confirm' (read-back gerekli), 'go' (promise yok, sadece
    durumlar), 'invalid' (biçim hatası: model düzeltir), 'invalid_say' (müşteriye cümle söylenir)."""
    today, _ = parse_now(vars.get(RT.get("now_var", "now")))
    RT = effective_rt(RT, today)
    try:
        plans = json.loads(vars.get("plans_json") or "[]")
    except Exception:
        plans = []
    by_id = dict((p["product_id"], p) for p in plans)
    per_product = (RT.get("recording") or dict()).get("mode") == "per_product"
    settled = settled_ids(vars) if per_product else []
    entries = parse_results(text)
    reasons = RT.get("status_reasons", [])
    errors, says, notes, seen, promises, statuses = [], [], [], [], [], []
    for e in entries:
        pid = e["product_id"]
        if pid not in by_id:
            errors.append(pid + ": unknown product_id; valid ids are " + ", ".join(by_id))
            continue
        if pid in seen or pid in settled:
            errors.append(pid + ": listed twice or already finished")
            continue
        seen.append(pid)
        if e["kind"] == "promise":
            try:
                when = to_date(e["date"])
            except Exception:
                errors.append(pid + ": the date must be YYYY-MM-DD")
                continue
            if e["amount"] is None:
                errors.append(pid + ": the amount is missing")
                continue
            state, amount, when, note = adjust_promise(by_id[pid], e["amount"], when, today, RT)
            if state == "say":
                says.append(note)
                continue
            promises.append({"product_id": pid, "amount": amount, "date": when.isoformat()})
            if note:
                notes.append(note)
        elif e["kind"] in reasons:
            statuses.append({"product_id": pid, "reason": e["kind"]})
        else:
            errors.append(pid + ": unknown status '" + e["kind"] + "'; use amount:date or one of " + ", ".join(reasons))
    missing = [pid for pid in by_id if pid not in seen and pid not in settled]
    if not entries:
        errors.append("no entries; use <product_id>:<amount>:<YYYY-MM-DD> or <product_id>:<status>")
    elif missing and not per_product and not errors:
        errors.append("missing products: " + ", ".join(missing) + "; every product needs a promise or a status")
    if errors:
        return "invalid", "NOT ACCEPTED: " + " | ".join(errors), ""
    if says:
        return "invalid_say", "NOT ACCEPTED, the customer was told: " + " ".join(says), " ".join(says)
    order = [p["product_id"] for p in plans]
    promises.sort(key=lambda p: order.index(p["product_id"]))
    statuses.sort(key=lambda s: order.index(s["product_id"]))
    old = json.loads(vars.get("statuses_json") or "[]") if per_product else []
    vars["rec_queue"] = json.dumps(promises)
    vars["statuses_json"] = json.dumps(old + statuses)
    vars["readback_say"] = readback_text(promises, notes, plans, RT) if promises else ""
    return ("confirm" if promises else "go"), "accepted", ""


def check_callback(vars, date_text, time_text, RT):
    """Geri arama penceresi. Dönüş: (geçerli_mi, sebep)."""
    days = [d for d in str(vars.get("cb_days", "")).split(",") if d]
    try:
        when = to_date(date_text).isoformat()
    except Exception:
        return False, "the date is not YYYY-MM-DD"
    m = re.match(r"^(\d{1,2}):(\d{2})", str(time_text or "").strip())
    if not m:
        return False, "the time is not HH:MM"
    minutes = int(m.group(1)) * 60 + int(m.group(2))
    today, now_min = parse_now(vars.get(RT.get("now_var", "now")))
    RT = effective_rt(RT, today)
    cb = RT.get("customer_callback" if vars.get("cb_kind") == "customer" else "callback", dict())
    if when not in days:
        return False, "the day is outside the allowed days (" + ", ".join(days) + ")"
    start_t, end_t = callback_window(when, cb)
    start = int(start_t[:2]) * 60 + int(start_t[3:5])
    end = int(end_t[:2]) * 60 + int(end_t[3:5])
    inclusive = cb.get("inclusive", True)
    if minutes < start or minutes > end or (not inclusive and (minutes == start or minutes == end)):
        return False, "the time is outside " + start_t + "-" + end_t
    if cb.get("after_now", True) and when == today.isoformat() and minutes <= now_min:
        return False, "the time is not later than now"
    lead = as_int(cb.get("min_lead_minutes"))
    if lead and when == today.isoformat() and minutes < now_min + lead:
        first = now_min + lead
        return False, ("on the same day the time must be at least " + str(lead) + " minutes after now (not before "
                       + "%02d:%02d" % (first // 60 % 24, first % 60) + ")")
    return True, ""
