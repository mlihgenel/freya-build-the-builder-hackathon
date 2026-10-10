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


def read_products(vars):
    """Ürün listesini mapping'den, JSON metninden ya da düzleştirilmiş anahtarlardan okur."""
    for key in ("products", "get_account_response.data.products", "fetch_account_response.data.products"):
        val = vars.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, str) and val.strip().startswith("["):
            try:
                return json.loads(val)
            except Exception:
                pass
    found = {}
    for key in vars:
        for prefix in ("products.", "get_account_response.data.products.", "fetch_account_response.data.products."):
            if str(key).startswith(prefix):
                rest = str(key)[len(prefix):].split(".", 1)
                if len(rest) == 2 and rest[0].isdigit():
                    found.setdefault(int(rest[0]), dict())[rest[1]] = vars[key]
    return [found[i] for i in sorted(found)]


def num(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def product_plan(product, today, RT):
    """Tek ürün için bant, deadline, floor, ifade ve deneme planı."""
    cal = RT["cal"]
    ptype = str(product.get("type", ""))
    band = band_for(product.get("days_late"), RT["bands"]) or RT["bands"][-1]
    deadline = add_business_days(today, int(band["deadline_bd"]), cal)
    floor_field = RT.get("floor_field", dict()).get(ptype, "")
    floor = num(product.get(floor_field), 0.0) if floor_field else 0.0
    past_due = num(product.get("past_due"))
    values = dict(product)
    values["past_due"] = fmt_money(past_due, RT)
    values["floor"] = fmt_money(floor, RT) if floor else ""
    wording = fill(RT.get("product_wording", dict()).get(ptype, ptype.replace("_", " ")), values)
    values["product"] = wording
    attempts = []
    for att in RT.get("attempts", []):
        bands = att.get("bands") or []
        if bands and band["name"] not in bands:
            continue
        amount = floor if att.get("amount") == "floor" and floor else past_due
        when = resolve_date_rule(att.get("date", "deadline"), today, deadline, cal)
        if when > deadline:
            when = deadline
        attempts.append({"n": att.get("n", len(attempts) + 1), "amount": round(amount, 2), "date": when.isoformat()})
    return {
        "product_id": str(product.get("product_id", "")),
        "type": ptype,
        "wording": wording,
        "past_due": round(past_due, 2),
        "floor": round(floor, 2),
        "days_late": int(num(product.get("days_late"))),
        "band": band["name"],
        "max_attempts": int(band.get("attempts", len(attempts))),
        "deadline": deadline.isoformat(),
        "attempts": attempts[: int(band.get("attempts", len(attempts)))],
        "sentence": fill(RT.get("debt_sentence", ""), values),
    }


def prep_account(vars, RT):
    today, minutes = parse_now(vars.get(RT.get("now_var", "now")))
    products = read_products(vars)
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
                     + "; latest allowed promise date (deadline) " + p["deadline"] + " " + weekday_name(p["deadline"])
                     + "; persuasion attempts allowed " + str(p["max_attempts"]))
        for a in p["attempts"]:
            lines.append("    attempt " + str(a["n"]) + ": propose " + fmt_money(a["amount"], RT) + " on "
                         + a["date"] + " (" + spoken_date(a["date"]) + ")")
    vars["product_facts"] = "\n".join(lines) if lines else "- no late products were returned"
    latest = max([to_date(p["deadline"]) for p in plans] or [today])
    vars["day_table"] = day_table(today, add_business_days(latest, 5, RT["cal"]), RT["cal"])
    vars["today_iso"] = today.isoformat()
    vars["today_spoken"] = spoken_date(today)
    tomorrow = to_date(today) + datetime.timedelta(days=1)
    vars["tomorrow_iso"] = tomorrow.isoformat()
    vars["tomorrow_spoken"] = spoken_date(tomorrow)
    vars["plans_json"] = json.dumps(plans)
    vars["product_ids"] = ",".join(p["product_id"] for p in plans)
    vars["product_count"] = str(len(plans))
    vars["account_state"] = "ready" if plans else "empty"


def prep_callback(vars, RT):
    """Üçüncü kişi için geri arama penceresini metin olarak hazırlar."""
    today, minutes = parse_now(vars.get(RT.get("now_var", "now")))
    cb = RT.get("callback", dict())
    days = []
    if "today" in cb.get("days", ["today", "next_business_day"]):
        days.append(today)
    if "next_business_day" in cb.get("days", ["today", "next_business_day"]):
        days.append(next_business_day(today, RT["cal"]))
    vars["cb_facts"] = ("Now is " + spoken_date(today) + " " + "%02d:%02d" % (minutes // 60, minutes % 60)
                        + ". A callback can be booked only on: "
                        + "; ".join(d.isoformat() + " (" + spoken_date(d) + ")" for d in days)
                        + ", between " + cb.get("start", "") + " and " + cb.get("end", "")
                        + (" (both included)" if cb.get("inclusive", True) else "")
                        + (", and only later than now." if cb.get("after_now", True) else "."))
    vars["cb_days"] = ",".join(d.isoformat() for d in days)
    vars["cb_now_min"] = str(minutes)
    vars["today_iso"] = today.isoformat()
