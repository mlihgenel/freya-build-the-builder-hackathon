"""İki PolicySpec'i karşılaştırır: Claude'un çıkardığı spec ile elle yazılmış (ya da başka bir çıkarımın) spec'i.

Farklar üç düzeyde raporlanır:
- PUAN: ledger'ı ya da kuralı değiştiren alanlar (bantlar, takvim, deneme planı, floor, outcome/reason, kimlik,
  callback penceresi, kayıt modu, alan eşlemeleri).
- METİN: brief'in birebir söylenmesini istediği cümleler (onay sorusu, ilk soru, başarı cümlesi …).
- BİLGİ: geri kalan cümleler ve kural listeleri.

Kullanım: uv run fbb specdiff out/dev-a-llm.spec.json tests/fixtures/spec_a.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fbb.spec import PolicySpec

SCORE = (
    "bands", "calendar", "overrides", "negotiation.attempts", "floor", "statuses", "transfers", "closing",
    "identity.questions.*.field", "identity.questions.*.answer_type", "identity.verify_mode",
    "identity.numeric_date_order", "identity.max_wrong_total", "identity.swap_hint", "identity.decline_close_after",
    "identity.fail_outcome", "identity.decline_outcome", "identity.purpose_question_counts_as_decline",
    "identity.one_at_a_time", "opening.max_asks", "opening.unclear", "third_party.callback",
    "third_party.callback_outcome", "third_party.no_callback_outcome", "third_party.wrong_number_outcome",
    "third_party.deceased_outcome", "recording.mode", "recording.retries", "recording.failure_status",
    "multi_product.enabled", "multi_product.notes_enabled", "multi_product.no_notes_on_transfer",
    "customer_callback.enabled", "customer_callback.outcome", "customer_callback.stages", "customer_callback.window",
    "customer_callback.no_callback_outcome",
    "tool_constants", "tool_fields", "response_fields", "money", "call_variables.customer_id", "call_variables.now",
    "negotiation.hardship_status",
)
# Brief'in birebir istediği cümleler: hakem bunları arar.
VERBATIM = (
    "confirmation.confirm_question", "negotiation.first_ask_single", "negotiation.first_ask_multi",
    "negotiation.floor_note", "recording.success_sentence", "third_party.deceased_sentence",
    "opening.confirm_question", "confirmation.change_after_record_sentence",
)
INFO_EXCEPT = ("closing.goodbye_sentence", "overrides.*.note")  # puan alanının altında ama sadece açıklama


def load(path: str | Path) -> dict:
    """Spec'i şemadan geçirir (varsayılanlar dolsun); geçmezse ham JSON'u kullanır."""
    data = json.loads(Path(path).read_text())
    try:
        return PolicySpec.model_validate(data).model_dump()
    except Exception:
        return data


def canonical(spec: dict) -> dict:
    """Sıra ve adlandırma farklarını kaldırır: bantlar min'e göre, durumlar id'ye, transferler kuyruğa göre."""
    s = json.loads(json.dumps(spec))
    s["bands"] = sorted(s.get("bands") or [], key=lambda b: (b.get("min", 0), b.get("max", 0)))
    for b in s["bands"]:
        b.pop("name", None)  # bant adı spec içinde tutarlı olduğu sürece önemsiz
        if b.get("deadline_rule"):
            b.pop("deadline_bd", None)  # kural varken deadline_bd okunmaz (dates.deadline_for)
    cal = s.get("calendar") or {}
    cal["holidays"] = sorted(set(cal.get("holidays") or []))
    s["statuses"] = {st["id"]: {"persuade": st.get("persuade", False)} for st in s.get("statuses") or []}
    failure = (s.get("recording") or {}).get("failure_status")
    if failure:  # to_runtime kayıt hatası durumunu zaten durumlara ekler; listede olup olmaması fark değildir
        s["statuses"].setdefault(failure, {"persuade": False})
    s["transfers"] = {t["queue"]: {"stages": sorted(t.get("stages") or [])} for t in s.get("transfers") or []}
    disc = s.get("disclosure") or {}
    floor = {t: "field:" + f for t, f in (disc.get("floor_field") or {}).items() if f}
    floor.update(disc.get("floor_rule") or {})
    s["floor"] = floor
    clo = s.get("closing") or {}
    # kapanış durumu kendi adıyla eşlenir (closing.py: .get(r, r)): kimlik eşlemesi yokla aynıdır
    # ödenmiş durumu reason'a hiç eşlenmez (decide_close onu atlar; hepsi ödenmişse paid_reason)
    paid = clo.get("paid_status", "paid")
    clo["status_to_reason"] = {k: v for k, v in (clo.get("status_to_reason") or {}).items() if k != v and k != paid}
    names = {b2.get("name") for b2 in spec.get("bands") or []}
    for a in (s.get("negotiation") or {}).get("attempts") or []:
        a["bands"] = sorted(a.get("bands") or [])
        if set(a["bands"]) - names:
            a["bands_unknown"] = sorted(set(a["bands"]) - names)
    return s


def flatten(value, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
        for i, v in enumerate(value):
            out.update(flatten(v, f"{prefix}.{i}"))
        out[prefix + ".#"] = len(value)
    else:
        out[prefix] = value
    return out


def level(path: str) -> str:
    generic = re.sub(r"\.\d+(?=\.|$)", ".*", path)
    if any(path == p or path.startswith(p + ".") or generic == p for p in INFO_EXCEPT):
        return "BİLGİ"
    if any(path == p or path.startswith(p + ".") for p in VERBATIM):
        return "METİN"
    if any(generic == p or generic.startswith(p + ".") or path == p or path.startswith(p + ".") for p in SCORE):
        return "PUAN"
    return "BİLGİ"


def norm_text(x) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip().casefold().rstrip(".?!")


def diff(a: dict, b: dict) -> dict[str, list[tuple[str, object, object]]]:
    """a = incelenen spec, b = referans. Düzey → [(yol, a'daki, b'deki)]."""
    fa, fb = flatten(canonical(a)), flatten(canonical(b))
    out: dict[str, list] = {"PUAN": [], "METİN": [], "BİLGİ": []}
    for path in sorted(set(fa) | set(fb)):
        va, vb = fa.get(path), fb.get(path)
        lv = level(path)
        if isinstance(va, list) and isinstance(vb, list):  # düz değer listesi: sıra önemsiz
            same = sorted(map(str, va)) == sorted(map(str, vb))
        elif lv == "METİN":
            same = norm_text(va) == norm_text(vb)
        else:
            same = va == vb
        if not same:
            out[lv].append((path, va, vb))
    return out


def report(a_path: str, b_path: str, show_info: bool = False) -> tuple[str, int]:
    d = diff(load(a_path), load(b_path))
    lines = [f"specdiff: {a_path}  ↔  {b_path} (referans)"]
    for lv in ("PUAN", "METİN", "BİLGİ"):
        rows = d[lv]
        lines.append(f"\n{lv}: {len(rows)} fark")
        if lv == "BİLGİ" and not show_info:
            if rows:
                lines.append("  (ayrıntı için --info) " + ", ".join(sorted({p.split('.')[0] for p, _, _ in rows})))
            continue
        for path, va, vb in rows:
            lines.append(f"  {path}\n      inceleme: {json.dumps(va, ensure_ascii=False)[:200]}"
                         f"\n      referans: {json.dumps(vb, ensure_ascii=False)[:200]}")
    return "\n".join(lines), len(d["PUAN"])
