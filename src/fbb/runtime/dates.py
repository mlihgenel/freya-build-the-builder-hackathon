"""Tarih motoru. Freya code node'larının ve hook'larının İÇİNDE çalışır.

Kurallar (emit.py bunları zorunlu kılar):
- Sadece `datetime`, `json`, `re` kullanılır, başka import yok.
- Kaynakta iki süslü parantez yan yana geçmez (platform şablonu sanabilir).
- Takvim bilgisi (`cal`) brief'ten gelir: {"weekdays": [0..6], "holidays": ["YYYY-MM-DD", ...]}.
  Pazartesi = 0.
"""
import datetime


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


def weekday_name(day):
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][to_date(day).weekday()]


def month_name(month):
    return ["January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December"][month - 1]


def spoken_date(day):
    day = to_date(day)
    return weekday_name(day) + " " + str(day.day) + " " + month_name(day.month)


def day_table(today, until, cal):
    """Modelin göreceği takvim: her satırda gün adı, ISO tarih, iş günü mü, this/next etiketi.

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
            tags.append("this " + weekday_name(day))
        elif wk == 1:
            tags.append("next " + weekday_name(day))
        status = "business day" if is_business_day(day, cal) else (
            "HOLIDAY, not a business day" if day.isoformat() in cal.get("holidays", []) else "weekend, not a business day")
        nbd = "" if is_business_day(day, cal) else "; next business day " + next_business_day(day, cal).isoformat()
        lines.append(day.isoformat() + " " + weekday_name(day) + " (" + ", ".join(tags) + "): " + status + nbd
                     if tags else day.isoformat() + " " + weekday_name(day) + ": " + status + nbd)
        day = day + datetime.timedelta(days=1)
    return "\n".join(lines)
