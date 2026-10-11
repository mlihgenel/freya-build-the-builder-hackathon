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


TR_FOLD = dict(zip("ışğüöçâîû", "isguocaiu", strict=True))
TR_WORDS = dict(
    sifir="zero", bir="one", iki="two", uc="three", dort="four", bes="five", alti="six", yedi="seven", sekiz="eight",
    dokuz="nine", on="ten", yirmi="twenty", otuz="thirty", kirk="forty", elli="fifty", altmis="sixty",
    yetmis="seventy", seksen="eighty", doksan="ninety", yuz="hundred", bin="thousand", virgul="point", nokta="point",
    birinci="first", ikinci="second", ucuncu="third", dorduncu="fourth", besinci="fifth", altinci="sixth",
    yedinci="seventh", sekizinci="eighth", dokuzuncu="ninth", onuncu="tenth", yirminci="twentieth",
    otuzuncu="thirtieth", ocak="january", subat="february", mart="march", nisan="april", mayis="may",
    haziran="june", temmuz="july", agustos="august", eylul="september", ekim="october", kasim="november",
    aralik="december", cift="double", ve="and")
TR_ONLY = ("sifir", "iki", "uc", "dort", "bes", "alti", "yedi", "sekiz", "dokuz", "yirmi", "otuz", "kirk", "elli",
           "altmis", "yetmis", "seksen", "doksan", "yuz", "ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz",
           "agustos", "eylul", "ekim", "kasim", "aralik", "birinci", "ikinci", "ucuncu", "dorduncu", "besinci",
           "altinci", "yedinci", "sekizinci", "dokuzuncu", "onuncu")


def tr_fold(word):
    return "".join(TR_FOLD.get(ch, ch) for ch in word)


def tokens(text):
    """Küçük harfli kelimeler. Metin Türkçe görünüyorsa (Türkçe harf ya da yalnız Türkçede olan bir sayı/ay kelimesi)
    Türkçe sayı, sıra ve ay kelimeleri İngilizce karşılıklarına çevrilir; okuma kodu tek dilde kalır."""
    raw = str(text or "").replace("İ", "i").replace("I", "i").lower().replace("-", " ").replace(",", " ")
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw)
    raw = re.sub(r"(\d)[.'’](inci|ıncı|uncu|üncü|nci|ncı|ncu|ncü|ci|cı|cu|cü)\b", r"\1", raw)
    words = [w for w in re.split(r"[^\w.]+", raw) if w]
    folded = [tr_fold(w).strip(".") for w in words]
    turkish = bool(re.search("[ışğüöç]", raw)) or any(w in TR_ONLY for w in folded)
    out = []
    for x, f in zip(words, folded, strict=True):
        if turkish and f in TR_WORDS:
            out.append(TR_WORDS[f])
            continue
        x = x if re.fullmatch(r"\d+\.\d+", x) else x.strip(".")
        if x and re.fullmatch(r"[a-z0-9.]+", x):
            out.append(x)
        elif x and turkish:
            out.append(f)
    return out


def amount_text(text):
    """'637,50' (Türkçe ondalık virgül) ve '1.250,75' → '637.50', '1250.75'; '1,250.75' → '1250.75'."""
    t = str(text or "").strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{1,2}", t):
        return t.replace(".", "").replace(",", ".")
    if re.fullmatch(r"\d+,\d{1,2}", t):
        return t.replace(",", ".")
    return t.replace(",", "")


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


REPEAT = dict(double=2, triple=3)


def digits_from_speech(text):
    """'one two three four' / '12 34' / 'twelve thirty-four' / 'double four seven one' → '1234'."""
    out = ""
    pending_ten = None
    repeat = 1
    for tok in tokens(text):
        if tok in REPEAT:
            repeat = REPEAT[tok]
            continue
        if repeat > 1 and (tok.isdigit() and len(tok) == 1 or (word_value(tok) or (0, ""))[1] == "unit"):
            if pending_ten is not None:
                out += str(pending_ten)
                pending_ten = None
            digit = tok if tok.isdigit() else str(word_value(tok)[0])
            out += digit * repeat
            repeat = 1
            continue
        repeat = 1
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
    if all(t.isdigit() for t in toks) and len("".join(toks)) == 4:
        y = int("".join(toks))  # "19 88"
        return y if 1900 <= y <= 2100 else None
    if any(t.isdigit() and len(t) == 4 for t in toks):
        return year_from_words([[t for t in toks if t.isdigit() and len(t) == 4][-1]])
    singles = [t if t.isdigit() else str((word_value(t) or (None, ""))[0]) for t in toks]
    if len(toks) == 4 and all(x.isdigit() and len(x) == 1 for x in singles):
        y = int("".join(singles))  # "one nine eight eight"
        return y if 1900 <= y <= 2100 else None
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


def date_parts(text, numeric_order="DMY"):
    """Söylenen tarihin parçaları: (yıl, ay, gün); bulunamayan parça None. Yılsız ya da günsüz cevaplar için."""
    raw = str(text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.fullmatch(r"(\d{1,2})[./ -](\d{1,2})[./ -](\d{2,4})", raw)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 1900 if y > 30 else 2000
        return (y, b, a) if numeric_order.startswith("D") else (y, a, b)
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})", raw)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (None, b, a) if numeric_order.startswith("D") else (None, a, b)
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
        if toks and all(t.isdigit() or word_value(t) or t in ("thousand", "and", "hundred") for t in toks):
            y = year_from_words(toks)
            if y:
                return y, None, None
        return None, None, None
    i, month = month_idx
    skip = ("the", "of", "on", "in", "my", "is", "its", "it", "born", "date", "birth")
    before = [t for t in toks[:i] if t not in skip]
    after = [t for t in toks[i + 1:] if t not in skip]
    day = None
    year_toks = after
    if before:
        if len(before) == 1 and before[0].isdigit() and len(before[0]) == 4:
            year_toks = [before[0]] + after
        else:
            day = words_to_number(" ".join(before))
    if day is None and after:
        # "March fourteenth nineteen eighty-eight" / "March 14 1988"
        if after[0].isdigit() and len(after[0]) <= 2:
            day, year_toks = int(after[0]), after[1:]
        else:
            first = word_value(after[0])
            if first and first[1] in ("ord", "unit") and first[0] <= 31 and not (
                    first[1] == "unit" and 10 <= first[0] <= 19 and len(after) > 1 and word_value(after[1])
                    and word_value(after[1])[1] == "ten"):
                day, year_toks = first[0], after[1:]
            elif first and first[1] == "ten" and first[0] <= 30:
                sec = word_value(after[1]) if len(after) > 1 else None
                if sec and sec[1] in ("ord", "unit") and sec[0] < 10:
                    day, year_toks = first[0] + sec[0], after[2:]
                else:
                    day, year_toks = first[0], after[1:]
    lead = []
    for t in year_toks:
        if not (t.isdigit() or word_value(t) or t in ("thousand", "hundred", "and")):
            break
        lead.append(t)
    year = year_from_words(lead) if lead else None
    if day is not None and (day < 1 or day > 31):
        day = None
    return year, month, (int(day) if day is not None else None)


def parse_spoken_date(text, numeric_order="DMY"):
    """Doğum tarihi gibi tam tarihleri ISO'ya çevirir. Okunamazsa None.

    Sadece rakamla söylenmiş tarihlerde sıra `numeric_order`'dan gelir (brief'ten)."""
    y, m, d = date_parts(text, numeric_order)
    if y is None or m is None or d is None:
        return None
    day = safe_date(y, m, d)
    return day.isoformat() if day else None


NATO = dict(alpha="a", alfa="a", bravo="b", charlie="c", delta="d", echo="e", foxtrot="f", golf="g", hotel="h",
            india="i", juliet="j", juliett="j", kilo="k", lima="l", mike="m", november="n", oscar="o", papa="p",
            quebec="q", romeo="r", sierra="s", tango="t", uniform="u", victor="v", whiskey="w", whisky="w",
            xray="x", yankee="y", zulu="z")
FILLER = ("is", "it", "its", "my", "the", "and", "our", "of", "that", "thats", "ok", "okay", "yes", "sure", "so",
          "um", "uh", "er", "erm", "postcode", "post", "code", "zip", "number", "company", "registered", "address",
          "for", "as", "in", "letter", "letters", "capital", "then", "space", "dash", "hyphen", "sorry", "mean",
          "think", "well", "be", "should", "would", "this", "here", "you", "go", "right", "correct", "please")


def alnum_from_speech(text):
    """'S W one A one A A' / 'sw1a 1aa' / 'double four' → 'SW1A1AA'. Harf harf ve rakam rakam söylenenler."""
    out = ""
    repeat = 1
    for tok in tokens(str(text or "").replace("'", "")):
        tok = tok.replace(".", "")
        if not tok or tok in FILLER:
            continue
        if tok in REPEAT:
            repeat = REPEAT[tok]
            continue
        piece = ""
        if tok in NATO:
            piece = NATO[tok]
        elif re.fullmatch(r"[a-z0-9]+", tok) and re.search(r"\d", tok):
            piece = tok
        elif word_value(tok) and word_value(tok)[1] in ("unit", "ten"):
            piece = digits_from_speech(tok)
        elif re.fullmatch(r"[a-z]{1,3}", tok):
            piece = tok
        if piece:
            out += piece[0] * (repeat - 1) + piece if repeat > 1 else piece
        repeat = 1
    return out.upper()


def format_like(value, example):
    """Örnek biçimde boşluk varsa (ör. 'SW1A 1AA') aynı yere boşluk koyar."""
    ex = str(example or "").strip()
    if " " in ex and " " not in value:
        tail = len(ex) - ex.rindex(" ") - 1
        if 0 < tail < len(value):
            return value[:-tail] + " " + value[-tail:]
    return value


def normalize_answer(answer_type, text, numeric_order="DMY", example=""):
    """answer_type: 'date' | 'digits:N' | 'year' | 'postcode' | 'alnum' | 'text' → (değer, durum).

    durum: ok | partial (cevabın bir kısmı geldi, gönderilmez) | unreadable."""
    raw = str(text or "").strip()
    if answer_type == "date":
        y, m, d = date_parts(raw, numeric_order)
        if y is not None and m is not None and d is not None:
            day = safe_date(y, m, d)
            return (day.isoformat(), "ok") if day else (raw, "unreadable")
        if y is not None or m is not None or d is not None:
            return raw, "partial"
        if re.search(r"\d", raw) or any(word_value(t) for t in tokens(raw)):
            return raw, "partial"  # "It is 1…": sayının başı geldi, ay ya da yıl yok
        return raw, "unreadable"
    if answer_type.startswith("digits"):
        want = int(answer_type.split(":", 1)[1]) if ":" in answer_type else 0
        dig = digits_from_speech(raw)
        if want and 0 < len(dig) < want:
            return dig, "partial"
        if want and len(dig) > want:
            return dig[-want:], "ok"
        return dig, "ok" if dig else "unreadable"
    if answer_type == "year":
        y = year_from_words(tokens(raw))
        return (str(y), "ok") if y else (raw, "unreadable")
    if answer_type in ("postcode", "alnum"):
        val = alnum_from_speech(raw)
        want = len(re.sub(r"[^A-Za-z0-9]", "", str(example or "")))
        if want and 0 < len(val) < want - (2 if answer_type == "postcode" else 0):
            return val, "partial"
        if not val:
            return raw, "unreadable"
        return format_like(val, example) if answer_type == "postcode" else val, "ok"
    return raw, "ok"


def combine_answer(q, raw, prev, numeric_order="DMY", swapped_from=""):
    """Parça parça verilen cevabı birleştirir. prev: aynı sorunun önceki parçası (metin).

    swapped_from: gün/ay yer değiştirdi ipucundan sonra önceki ISO cevap; müşteri sadece ayı söylerse gün oradan alınır."""
    kind = q.get("answer_type", "text")
    example = q.get("example", "")
    value, status = normalize_answer(kind, raw, numeric_order, example)
    if status == "ok":
        return value, status
    if kind == "date":
        y, m, d = date_parts(raw, numeric_order)
        if swapped_from and m is not None and (y is None or d is None):
            py, pm, pd = date_parts(swapped_from, "DMY")
            if py and pm and pd:
                day = d if d is not None else (pm if m == pd else pd)
                full = safe_date(y or py, m, day)
                if full:
                    return full.isoformat(), "ok"
        if prev:
            py, pm, pd = date_parts(prev, numeric_order)
            my, mm, md = (y if y is not None else py), (m if m is not None else pm), (d if d is not None else pd)
            if my is not None and mm is not None and md is not None:
                full = safe_date(my, mm, md)
                if full:
                    return full.isoformat(), "ok"
            whole, st = normalize_answer(kind, str(prev) + " " + raw, numeric_order, example)
            if st == "ok":
                return whole, st
            return (prev + " " + raw).strip(), "partial"
        return value, status
    if prev and (kind.startswith("digits") or kind in ("postcode", "alnum")):
        joined, st = normalize_answer(kind, str(prev) + " " + raw, numeric_order, example)
        return joined, st
    return value, status


def normalize_amount(text):
    v = words_to_number(text)
    return round(float(v), 2) if v is not None else None
