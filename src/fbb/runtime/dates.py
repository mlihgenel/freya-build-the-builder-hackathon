"""Tarih motoru. Freya code node'larının ve hook'larının İÇİNDE çalışır.

Kurallar (emit.py bunları zorunlu kılar):
- Sadece `datetime`, `json`, `re` kullanılır, başka import yok.
- Kaynakta iki süslü parantez yan yana geçmez (platform şablonu sanabilir).
- Takvim bilgisi (`cal`) brief'ten gelir: {"weekdays": [0..6], "holidays": ["YYYY-MM-DD", ...]}.
  Pazartesi = 0.
"""
import datetime
import json


def parse_now(text):
    """'2026-10-14T11:00', '2026-10-14 11:00:00Z', '2026-10-14' → (date, dakika)."""
    s = str(text or "").strip().replace(" ", "T").rstrip("Zz")
    if "+" in s[10:]:
        s = s[: 10 + s[10:].index("+")]
    day = datetime.date.fromisoformat(s[:10])
    minutes = 0
    if "T" in s:
        hm = s.split("T", 1)[1].split(":")
        if hm and hm[0]:
            minutes = int(hm[0]) * 60 + (int(hm[1]) if len(hm) > 1 and hm[1] else 0)
    return day, minutes


def to_date(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value).strip()[:10])


def is_business_day(day, cal):
    day = to_date(day)
    return day.weekday() in cal.get("weekdays", [0, 1, 2, 3, 4]) and day.isoformat() not in cal.get("holidays", [])


def add_business_days(day, n, cal):
    """`day`'den SONRAKİ n'inci iş günü. n=0 → day'in kendisi (iş günü değilse sonraki iş günü)."""
    day = to_date(day)
    if n <= 0:
        return next_business_day(day, cal, include_today=True)
    count = 0
    while count < n:
        day = day + datetime.timedelta(days=1)
        if is_business_day(day, cal):
            count += 1
    return day


def next_business_day(day, cal, include_today=False):
    day = to_date(day)
    if include_today and is_business_day(day, cal):
        return day
    for _ in range(60):
        day = day + datetime.timedelta(days=1)
        if is_business_day(day, cal):
            return day
    return day


def week_start(day):
    day = to_date(day)
    return day - datetime.timedelta(days=day.weekday())


def last_business_day_of_week(day, cal):
    """`day`'in takvim haftasındaki (Pzt–Paz) son iş günü. Hafta içinde iş günü yoksa None."""
    start = week_start(day)
    for back in range(6, -1, -1):
        cand = start + datetime.timedelta(days=back)
        if is_business_day(cand, cal):
            return cand
    return None


def this_weekday(day, weekday):
    """Bu takvim haftasındaki o gün (geçmişte kalmış olabilir)."""
    return week_start(day) + datetime.timedelta(days=weekday)


def next_weekday(day, weekday):
    """'next <gün>': bir sonraki takvim haftasındaki o gün."""
    return week_start(day) + datetime.timedelta(days=7 + weekday)


def end_of_week_offer(today, cal):
    """1. ikna denemesi: bu haftanın son iş günü; bugün o günse (ya da geçtiyse) gelecek haftanınki."""
    cand = last_business_day_of_week(today, cal)
    if cand is None or cand <= today:
        cand = last_business_day_of_week(week_start(today) + datetime.timedelta(days=7), cal)
    return cand


def band_for(days_late, bands):
    """bands: [{"name", "min", "max", "deadline_bd", "attempts"}] → eşleşen bant ya da None."""
    try:
        d = int(float(days_late))
    except Exception:
        return None
    for band in bands:
        if int(band["min"]) <= d <= int(band["max"]):
            return band
    return None


def resolve_date_rule(rule, today, deadline, cal):
    """Spec'teki tarih kuralı adı → somut tarih."""
    if rule == "deadline":
        return deadline
    if rule == "today":
        return today
    if rule == "next_business_day":
        return next_business_day(today, cal)
    if rule == "end_of_week":
        return end_of_week_offer(today, cal)
    if rule.startswith("business_days:"):
        return add_business_days(today, int(rule.split(":", 1)[1]), cal)
    return deadline


WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]


def weekday_name(day, RT=None):
    names = ((RT or dict()).get("locale") or dict()).get("weekday_names") or WEEKDAYS_EN
    return names[to_date(day).weekday()]


def month_name(month, RT=None):
    names = ((RT or dict()).get("locale") or dict()).get("month_names") or MONTHS_EN
    return names[month - 1]


def spoken_date(day, RT=None):
    day = to_date(day)
    return weekday_name(day, RT) + " " + str(day.day) + " " + month_name(day.month, RT)


def last_business_day_on_or_before(day, cal):
    day = to_date(day)
    for _ in range(60):
        if is_business_day(day, cal):
            return day
        day = day - datetime.timedelta(days=1)
    return day


def deadline_for(band, today, cal):
    """Bandın son tarihi. deadline_rule boşsa deadline_bd (bugünden sonraki N. iş günü)."""
    rule = str(band.get("deadline_rule") or "")
    today = to_date(today)
    if rule.startswith("business_days:"):
        return add_business_days(today, int(rule.split(":", 1)[1]), cal)
    if rule.startswith("calendar_days:"):
        last = to_date(today) + datetime.timedelta(days=int(rule.split(":", 1)[1]))
        return max(last_business_day_on_or_before(last, cal), next_business_day(today, cal, include_today=True))
    if rule == "end_of_month":
        nxt = datetime.date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
        last = last_business_day_on_or_before(nxt - datetime.timedelta(days=1), cal)
        return last if last >= today else next_business_day(today, cal, include_today=True)
    if rule.startswith("date:"):
        return to_date(rule[5:])
    return add_business_days(today, int(band.get("deadline_bd", 0)), cal)


def effective_rt(RT, today):
    """Memo'ların tarihli değişikliklerini (RT['overrides']) `today`'e göre uygular; RT'nin kopyasını döner."""
    overrides = RT.get("overrides") or []
    if not overrides:
        return RT
    out = json.loads(json.dumps(RT))
    iso = to_date(today).isoformat()
    for o in overrides:
        start = str(o.get("effective_from") or "")
        until = str(o.get("effective_until") or "")
        if (start and iso < start) or (until and iso > until):
            continue
        if o.get("bands"):
            out["bands"] = o["bands"]
        if o.get("weekdays"):
            out["cal"]["weekdays"] = o["weekdays"]
        hol = [h for h in out["cal"].get("holidays", []) if h not in (o.get("holidays_remove") or [])]
        out["cal"]["holidays"] = sorted(set(hol + list(o.get("holidays_add") or [])))
        if o.get("callback"):
            out["callback"] = o["callback"]
        if o.get("floor_rule"):
            merged = dict(out.get("floor_rule") or dict())
            merged.update(o["floor_rule"])
            out["floor_rule"] = merged
        if o.get("attempts"):
            out["attempts"] = o["attempts"]
    return out


def callback_days(today, cb, cal):
    """Geri arama yapılabilecek günler. 'today' sadece bugün iş günüyse sayılır."""
    days = []
    for rule in cb.get("days") or ["today", "next_business_day"]:
        if rule == "today" and is_business_day(today, cal):
            days.append(to_date(today))
        elif rule == "next_business_day":
            days.append(next_business_day(today, cal))
        elif str(rule).startswith("business_days:"):
            day = to_date(today)
            for _ in range(int(str(rule).split(":", 1)[1])):
                day = next_business_day(day, cal)
                days.append(day)
    out = []
    for d in days:
        if d not in out:
            out.append(d)
    return sorted(out)


def callback_window(day, cb):
    """O günün saat aralığı: (başlangıç, bitiş) 'HH:MM'."""
    by_day = cb.get("hours_by_weekday") or dict()
    win = by_day.get(str(to_date(day).weekday()))
    if win:
        return win.get("start", cb.get("start", "00:00")), win.get("end", cb.get("end", "23:59"))
    return cb.get("start", "00:00"), cb.get("end", "23:59")


def promise_verdict(day, plan, cal, RT=None):
    """Müşteri bu günü söylerse bu ürün için ne yapılır: 'OK' ya da önerilecek tarih."""
    deadline = to_date(plan["deadline"])
    if day > deadline:
        return "after its deadline: offer the deadline " + deadline.isoformat() + " " + weekday_name(deadline, RT)
    if not is_business_day(day, cal):
        nxt = next_business_day(day, cal)
        if nxt > deadline:
            return "not a business day and the next one is after its deadline: offer the deadline " + \
                deadline.isoformat() + " " + weekday_name(deadline, RT)
        return "not a business day: offer the next business day " + nxt.isoformat() + " " + weekday_name(nxt, RT)
    return "OK, can be recorded"


def day_table(today, until, cal, plans=None, RT=None):
    """Modelin göreceği takvim. Her satır: ISO tarih, gün adı, this/next etiketi, iş günü mü ve (ürünler verilirse)
    müşteri o günü söylerse her ürün için hazır karar. Model tarih hesabı yapmaz, satırı okur.

    Platformun tarih extraction'ı gerçek saati kullanır; bu tablo `now` çağrı değişkeninden üretilir.
    """
    lines = []
    day = to_date(today)
    end = to_date(until)
    this_week = week_start(day)
    while day <= end:
        tags = []
        if day == today:
            tags.append("TODAY")
        elif day == today + datetime.timedelta(days=1):
            tags.append("tomorrow")
        wk = (week_start(day) - this_week).days // 7
        if wk == 0:
            tags.append("this " + weekday_name(day, RT))
        elif wk == 1:
            tags.append("next " + weekday_name(day, RT))
        if is_business_day(day, cal):
            status = "business day"
        elif day.isoformat() in cal.get("holidays", []):
            status = "HOLIDAY"
        else:
            status = "weekend"
        line = day.isoformat() + " " + weekday_name(day, RT) + (" (" + ", ".join(tags) + ")" if tags else "") + ": " + status
        for plan in plans or []:
            line += " | " + plan["product_id"] + ": " + promise_verdict(day, plan, cal, RT)
        lines.append(line)
        day = day + datetime.timedelta(days=1)
    return "\n".join(lines)
