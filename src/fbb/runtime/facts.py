"""get_account sonucundan konuşma gerçeklerini üretir. Freya code node'unda çalışır.

`RT`, spec'ten derlenen çalışma zamanı sabitleridir (emit.py snippet'in başına koyar).
Çıktılar `vars`'a yazılır ve prompt'larda `{{değişken}}` olarak kullanılır.
"""
import datetime
import json


def fill(template, values):
    """'{product} ... {past_due}' biçimindeki şablonu doldurur (format() değil, süslü parantez güvenli)."""
    out = str(template or "")
    for key in values:
        out = out.replace("{" + key + "}", str(values[key]))
    return out


def fmt_money(value, RT):
    money = RT.get("money", {})
    v = round(float(value), 2)
    text = str(int(v)) if v == int(v) and not money.get("always_decimals") else "%.2f" % v
    return money.get("prefix", "") + text + money.get("suffix", "")


def field_name(RT, role):
    """Cevap alanının gerçek adı (spec.response_fields); yoksa varsayılan ad."""
    return (RT.get("fields") or dict()).get(role) or ("type" if role == "product_type" else role)


def read_products(vars, RT=None):
    """Ürün listesini mapping'den, JSON metninden ya da düzleştirilmiş anahtarlardan okur."""
    key = field_name(RT or dict(), "products")
    for name in ("products", "get_account_response.data." + key, "fetch_account_response.data." + key):
        val = vars.get(name)
        if isinstance(val, list):
            return val
        if isinstance(val, str) and val.strip().startswith("["):
            try:
                return json.loads(val)
            except Exception:
                pass
    found = dict()
    for k in vars:
        for prefix in ("products.", "get_account_response.data." + key + ".", "fetch_account_response.data." + key + "."):
            if str(k).startswith(prefix):
                rest = str(k)[len(prefix):].split(".", 1)
                if len(rest) == 2 and rest[0].isdigit():
                    found.setdefault(int(rest[0]), dict())[rest[1]] = vars[k]
    return [found[i] for i in sorted(found)]


def num(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def floor_amount(product, ptype, past_due, RT):
    """Ürünün floor'u: 'field:<alan>' | 'percent:N' | 'fixed:X' | 'max:<k1>,<k2>' | 'min:<k1>,<k2>'
    (RT['floor_rule'], '*' bütün tipler)."""
    rules = RT.get("floor_rule") or dict()
    rule = str(rules.get(ptype) or rules.get("*") or "")
    return floor_by_rule(rule, product, past_due)


def floor_by_rule(rule, product, past_due):
    if rule.startswith("max:") or rule.startswith("min:"):
        parts = [floor_by_rule(r.strip(), product, past_due) for r in rule[4:].split(",") if r.strip()]
        if not parts:
            return 0.0
        return max(parts) if rule.startswith("max:") else min(parts)
    if rule.startswith("field:"):
        return num(product.get(rule[6:]), 0.0)
    if rule.startswith("percent:"):
        return round(past_due * num(rule[8:]) / 100.0, 2)
    if rule.startswith("fixed:"):
        return min(num(rule[6:]), past_due)
    return 0.0


def attempt_amount(rule, floor, past_due):
    rule = str(rule or "full")
    if rule == "floor":
        return floor if floor else past_due
    if rule.startswith("percent:"):
        return max(round(past_due * num(rule[8:]) / 100.0, 2), floor)
    if rule.startswith("fixed:"):
        return min(max(num(rule[6:]), floor), past_due)
    return past_due


def product_plan(product, today, RT):
    """Tek ürün için bant, deadline, floor, ifade ve deneme planı."""
    cal = RT["cal"]
    ptype = str(product.get(field_name(RT, "product_type"), ""))
    days_late = product.get(field_name(RT, "days_late"))
    band = band_for(days_late, RT["bands"]) or RT["bands"][-1]
    deadline = deadline_for(band, today, cal)
    past_due = num(product.get(field_name(RT, "past_due")))
    floor = floor_amount(product, ptype, past_due, RT)
    values = dict(product)
    values["past_due"] = fmt_money(past_due, RT)
    values["days_late"] = str(int(num(days_late)))
    values["floor"] = fmt_money(floor, RT) if floor else ""
    wording = fill(RT.get("product_wording", dict()).get(ptype, ptype.replace("_", " ")), values)
    values["product"] = wording
    attempts = []
    for att in RT.get("attempts", []):
        bands = att.get("bands") or []
        if bands and band["name"] not in bands:
            continue
        amount = attempt_amount(att.get("amount"), floor, past_due)
        when = resolve_date_rule(att.get("date", "deadline"), today, deadline, cal)
        if when > deadline:
            when = deadline
        attempts.append({"n": att.get("n", len(attempts) + 1), "amount": round(amount, 2), "date": when.isoformat()})
    return {
        "product_id": str(product.get(field_name(RT, "product_id"), "")),
        "type": ptype,
        "wording": wording,
        "past_due": round(past_due, 2),
        "floor": round(floor, 2),
        "days_late": int(num(days_late)),
        "band": band["name"],
        "max_attempts": int(band.get("attempts", len(attempts))),
        "deadline": deadline.isoformat(),
        "attempts": attempts[: int(band.get("attempts", len(attempts)))],
        "sentence": fill(RT.get("debt_sentence", ""), values),
    }


def prep_account(vars, RT):
    today, minutes = parse_now(vars.get(RT.get("now_var", "now")))
    RT = effective_rt(RT, today)
    vars["id_state"] = "verified"
    products = read_products(vars, RT)
    plans = [product_plan(p, today, RT) for p in products]
    multi = len(plans) > 1
    intro = RT.get("debt_intro", "")
    sentences = " ".join(p["sentence"] for p in plans)
    vars["debt_statement"] = (intro + " " + sentences).strip()
    vars["first_ask"] = RT.get("first_ask_multi" if multi else "first_ask_single", "")
    lines = []
    for p in plans:
        lines.append("- product_id " + p["product_id"] + ": " + p["wording"] + "; past due " + fmt_money(p["past_due"], RT)
                     + " (" + str(p["past_due"]) + "); " + str(p["days_late"]) + " days late; band " + p["band"]
                     + "; floor " + (fmt_money(p["floor"], RT) + " (" + str(p["floor"]) + ")" if p["floor"] else "none")
                     + "; latest allowed promise date (deadline) " + p["deadline"] + " " + weekday_name(p["deadline"], RT)
                     + "; persuasion attempts allowed " + str(p["max_attempts"]))
        lines.append("    if the customer flatly refuses this product (or does not answer):")
        for k, a in enumerate(p["attempts"]):
            lines.append("      refusal " + str(k + 1) + " → attempt " + str(a["n"]) + ": propose " + fmt_money(a["amount"], RT)
                         + " on " + a["date"] + " (" + spoken_date(a["date"], RT) + ")")
        lines.append("      refusal " + str(len(p["attempts"]) + 1) + " → no more proposals; status refused")
    vars["product_facts"] = "\n".join(lines) if lines else "- no late products were returned"
    latest = max([to_date(p["deadline"]) for p in plans] or [today])
    vars["day_table"] = day_table(today, add_business_days(latest, 5, RT["cal"]), RT["cal"], plans, RT)
    vars["today_iso"] = today.isoformat()
    vars["today_spoken"] = spoken_date(today, RT)
    tomorrow = to_date(today) + datetime.timedelta(days=1)
    vars["tomorrow_iso"] = tomorrow.isoformat()
    vars["tomorrow_spoken"] = spoken_date(tomorrow, RT)
    vars["plans_json"] = json.dumps(plans)
    vars["product_ids"] = ",".join(p["product_id"] for p in plans)
    vars["product_count"] = str(len(plans))
    vars["account_state"] = "ready" if plans else "empty"
    mark_close(vars, RT)


def callback_facts(today, minutes, cb, RT):
    days = callback_days(today, cb, RT["cal"])
    parts = []
    for d in days:
        start, end = callback_window(d, cb)
        parts.append(d.isoformat() + " (" + spoken_date(d, RT) + ") between " + start + " and " + end)
    text = ("Now is " + spoken_date(today, RT) + " " + "%02d:%02d" % (minutes // 60, minutes % 60)
            + ". A callback can be booked only on: " + "; ".join(parts)
            + (" (both ends included)" if cb.get("inclusive", True) else " (ends excluded)")
            + (", and only later than now." if cb.get("after_now", True) else "."))
    return text, days


def prep_callback(vars, RT, kind="third_party"):
    """Geri arama penceresini metin olarak hazırlar. kind: third_party | customer."""
    today, minutes = parse_now(vars.get(RT.get("now_var", "now")))
    RT = effective_rt(RT, today)
    cb = RT.get("customer_callback" if kind == "customer" else "callback", dict())
    text, days = callback_facts(today, minutes, cb, RT)
    vars["cb_facts"] = text
    vars["cb_kind"] = kind
    vars["cb_days"] = ",".join(d.isoformat() for d in days)
    vars["cb_now_min"] = str(minutes)
    vars["today_iso"] = today.isoformat()
