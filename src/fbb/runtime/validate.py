"""Modelin verdiği sonuçları ve geri arama tekliflerini kurallara göre doğrular. Freya hook'larında çalışır."""
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
            amount = normalize_amount(bits[1].replace("$", "").replace("£", "").replace("€", ""))
            entry["amount"] = amount
            entry["date"] = bits[2][:10]
        elif len(bits) == 2:
            entry["kind"] = bits[1].lower()
        out.append(entry)
    return out


def check_promise(plan, amount, date_text, today, RT):
    """Bir promise'i doğrular. Dönüş: (geçerli_mi, sebep, öneri)."""
    cal = RT["cal"]
    try:
        when = to_date(date_text)
    except Exception:
        return False, "the date is not a valid YYYY-MM-DD date", plan["deadline"]
    deadline = to_date(plan["deadline"])
    if amount is None:
        return False, "the amount is missing", str(plan["past_due"])
    low = plan["floor"] if plan["floor"] else plan["past_due"]
    if amount < low - 0.005:
        return False, "the amount is below the floor " + str(low) + " and cannot be recorded", str(low)
    if amount > plan["past_due"] + 0.005:
        return False, "the amount is above the past-due amount " + str(plan["past_due"]), str(plan["past_due"])
    if when < today:
        return False, "the date is in the past", next_business_day(today, cal, include_today=True).isoformat()
    if when > deadline:
        return False, "the date is after the deadline " + deadline.isoformat() + "; the latest date is the deadline", \
            deadline.isoformat()
    if not is_business_day(when, cal):
        nxt = next_business_day(when, cal)
        if nxt > deadline:
            return False, "the date is not a business day and the next business day is after the deadline", \
                deadline.isoformat()
        return False, "the date is not a business day; offer the next business day " + nxt.isoformat(), nxt.isoformat()
    return True, "", ""


def validate_results(vars, text, RT):
    """submit_results girdisini doğrular. Geçerliyse kuyrukları yazar. Dönüş: (ok, mesaj)."""
    today, _ = parse_now(vars.get(RT.get("now_var", "now")))
    try:
        plans = json.loads(vars.get("plans_json") or "[]")
    except Exception:
        plans = []
    by_id = dict((p["product_id"], p) for p in plans)
    entries = parse_results(text)
    reasons = RT.get("status_reasons", [])
    errors, seen, promises, statuses = [], [], [], []
    for e in entries:
        pid = e["product_id"]
        if pid not in by_id:
            errors.append(pid + ": unknown product_id; valid ids are " + ", ".join(by_id))
            continue
        if pid in seen:
            errors.append(pid + ": listed twice")
            continue
        seen.append(pid)
        if e["kind"] == "promise":
            ok, why, hint = check_promise(by_id[pid], e["amount"], e["date"], today, RT)
            if not ok:
                errors.append(pid + ": " + why + (" (suggest " + hint + ")" if hint else ""))
            else:
                promises.append({"product_id": pid, "amount": round(e["amount"], 2), "date": e["date"]})
        elif e["kind"] in reasons:
            statuses.append({"product_id": pid, "reason": e["kind"]})
        else:
            errors.append(pid + ": unknown status '" + e["kind"] + "'; use amount:date or one of " + ", ".join(reasons))
    missing = [pid for pid in by_id if pid not in seen]
    if missing and not errors:
        errors.append("missing products: " + ", ".join(missing) + "; every product needs a promise or a status")
    if errors:
        return False, "NOTHING WAS RECORDED. " + " | ".join(errors)
    order = [p["product_id"] for p in plans]
    promises.sort(key=lambda p: order.index(p["product_id"]))
    statuses.sort(key=lambda s: order.index(s["product_id"]))
    vars["rec_queue"] = json.dumps(promises)
    vars["statuses_json"] = json.dumps(statuses)
    vars["commit"] = "ready"
    return True, "accepted"


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
    cb = RT.get("callback", dict())
    start = int(cb.get("start", "00:00")[:2]) * 60 + int(cb.get("start", "00:00")[3:5])
    end = int(cb.get("end", "23:59")[:2]) * 60 + int(cb.get("end", "23:59")[3:5])
    if when not in days:
        return False, "the day is outside the allowed days (" + ", ".join(days) + ")"
    inclusive = cb.get("inclusive", True)
    if minutes < start or minutes > end or (not inclusive and (minutes == start or minutes == end)):
        return False, "the time is outside " + cb.get("start", "") + "-" + cb.get("end", "")
    today, now_min = parse_now(vars.get(RT.get("now_var", "now")))
    if cb.get("after_now", True) and when == today.isoformat() and minutes <= now_min:
        return False, "the time is not later than now"
    return True, ""
