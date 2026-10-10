"""Müşterinin söylediği değerleri tool'un beklediği biçime çevirir. Freya hook'larında çalışır.

Sadece `datetime` ve `re`. Kelimeyle söylenen sayıları ("nineteen eighty-eight", "four four seven one")
ve tarih biçimlerini ("14 March 1988", "the fourteenth of March", "14/03/1988") tanır.
"""
import datetime
import re

UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ORDINALS = ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
            "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
            "nineteenth"]
TENS_ORD = ["", "", "twentieth", "thirtieth"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def word_value(word):
    """Tek kelime → (değer, tür). tür: 'unit' 0-19, 'ten' 20-90, 'ord' sıra sayısı. Tanınmazsa None."""
    w = word.lower().strip()
    if w in ("oh", "o", "nought"):
        return 0, "unit"
    if w in UNITS:
        return UNITS.index(w), "unit"
    if w in TENS[2:]:
        return TENS.index(w) * 10, "ten"
    if w in ORDINALS[1:]:
        return ORDINALS.index(w), "ord"
    if w in TENS_ORD[2:]:
        return TENS_ORD.index(w) * 10, "ord"
    return None


def tokens(text):
    t = str(text or "").lower().replace("-", " ").replace(",", " ")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    return [x for x in re.split(r"[^a-z0-9.]+", t) if x]


def words_to_number(text):
    """'two hundred ten point five' → 210.5; 'two thousand and five' → 2005; rakamlar da olur."""
    total, current, decimals, seen = 0, 0, None, False
    for tok in tokens(text):
        if re.fullmatch(r"\d+(\.\d+)?", tok):
            current += float(tok) if "." in tok else int(tok)
            seen = True
            continue
        if tok == "and":
            continue
        if tok == "point":
            decimals = ""
            continue
        val = word_value(tok)
        if decimals is not None and val is not None:
            decimals += str(val[0])
            continue
        if val is not None:
            current += val[0]
            seen = True
        elif tok == "hundred":
            current = (current or 1) * 100
            seen = True
        elif tok == "thousand":
            total += (current or 1) * 1000
            current = 0
            seen = True
        elif tok in ("dollars", "dollar", "pounds", "euros", "lira"):
            continue
        elif tok in ("cents", "cent", "pence"):
            continue
    if not seen:
        return None
    value = total + current
    if decimals:
        value = float(str(int(value)) + "." + decimals)
    return value


def digits_from_speech(text):
    """'one two three four' / '12 34' / 'twelve thirty-four' → '1234'."""
    out = ""
    pending_ten = None
    for tok in tokens(text):
        if tok.isdigit():
            if pending_ten is not None:
                out += str(pending_ten)
                pending_ten = None
            out += tok
            continue
        val = word_value(tok)
        if val is None:
            continue
        num, kind = val
        if kind == "ten":
            if pending_ten is not None:
                out += str(pending_ten)
            pending_ten = num
        elif pending_ten is not None and num < 10:
            out += str(pending_ten + num)
            pending_ten = None
        else:
            if pending_ten is not None:
                out += str(pending_ten)
                pending_ten = None
            out += str(num)
    if pending_ten is not None:
        out += str(pending_ten)
    return out


def year_from_words(toks):
    """['nineteen','eighty','eight'] → 1988; ['two','thousand','five'] → 2005; ['1988'] → 1988."""
    if not toks:
        return None
    if len(toks) == 1 and toks[0].isdigit() and len(toks[0]) == 4:
        return int(toks[0])
    if "thousand" in toks:
        v = words_to_number(" ".join(toks))
        return int(v) if v else None
    first = word_value(toks[0])
    if first and first[1] == "unit" and 10 <= first[0] <= 99 and len(toks) > 1:
        rest = words_to_number(" ".join(toks[1:]))
        if rest is not None and rest < 100:
            return first[0] * 100 + int(rest)
    if first and first[1] == "ten" and len(toks) > 1:
        # "twenty twenty-one" / "twenty oh five"
        head = first[0]
        idx = 1
        nxt = word_value(toks[1]) if len(toks) > 1 else None
        if nxt and nxt[1] == "unit" and nxt[0] < 10 and toks[1] not in ("oh", "o"):
            head += nxt[0]
            idx = 2
        rest = words_to_number(" ".join(toks[idx:])) if idx < len(toks) else None
        if rest is not None:
            return head * 100 + int(rest)
    v = words_to_number(" ".join(toks))
    return int(v) if v and 1900 <= v <= 2100 else None


def safe_date(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d))
    except Exception:
        return None


def parse_spoken_date(text, numeric_order="DMY"):
    """Doğum tarihi gibi tam tarihleri ISO'ya çevirir. Okunamazsa None.

    Sadece rakamla söylenmiş tarihlerde sıra `numeric_order`'dan gelir (brief'ten)."""
    raw = str(text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        d = safe_date(m.group(1), m.group(2), m.group(3))
        return d.isoformat() if d else None
    m = re.fullmatch(r"(\d{1,2})[./ -](\d{1,2})[./ -](\d{2,4})", raw)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 1900 if y > 30 else 2000
        d = safe_date(y, b, a) if numeric_order.startswith("D") else safe_date(y, a, b)
        return d.isoformat() if d else None
    toks = tokens(raw)
    month_idx = None
    for i, tok in enumerate(toks):
        for k, name in enumerate(MONTHS):
            if tok == name or (len(tok) >= 3 and name.startswith(tok)):
                month_idx = (i, k + 1)
                break
        if month_idx:
            break
    if not month_idx:
        return None
    i, month = month_idx
    before = [t for t in toks[:i] if t not in ("the", "of", "on")]
    after = [t for t in toks[i + 1:] if t not in ("the", "of", "on", "in")]
    day = None
    year_toks = after
    if before:
        day = words_to_number(" ".join(before))
    else:
        # "March fourteenth nineteen eighty-eight" / "March 14 1988"
        if after and after[0].isdigit() and len(after[0]) <= 2:
            day, year_toks = int(after[0]), after[1:]
        elif after:
            first = word_value(after[0])
            if first and first[1] in ("ord", "unit") and first[0] <= 31:
                day, year_toks = first[0], after[1:]
            elif first and first[1] == "ten" and first[0] <= 30:
                sec = word_value(after[1]) if len(after) > 1 else None
                if sec and sec[1] in ("ord", "unit") and sec[0] < 10:
                    day, year_toks = first[0] + sec[0], after[2:]
                else:
                    day, year_toks = first[0], after[1:]
    year = year_from_words(year_toks)
    if day is None or year is None:
        return None
    d = safe_date(year, month, int(day))
    return d.isoformat() if d else None


def normalize_answer(answer_type, text, numeric_order="DMY"):
    """answer_type: 'date' | 'digits:N' | 'year' | 'text'. → (değer, durum). durum: ok | partial | unreadable."""
    raw = str(text or "").strip()
    if answer_type == "date":
        iso = parse_spoken_date(raw, numeric_order)
        return (iso, "ok") if iso else (raw, "unreadable")
    if answer_type.startswith("digits"):
        want = int(answer_type.split(":", 1)[1]) if ":" in answer_type else 0
        dig = digits_from_speech(raw)
        if want and len(dig) < want:
            return dig, "partial"
        if want and len(dig) > want:
            return dig[-want:], "ok"
        return dig, "ok" if dig else "unreadable"
    if answer_type == "year":
        y = year_from_words(tokens(raw))
        return (str(y), "ok") if y else (raw, "unreadable")
    return raw, "ok"


def normalize_amount(text):
    v = words_to_number(text)
    return round(float(v), 2) if v is not None else None
