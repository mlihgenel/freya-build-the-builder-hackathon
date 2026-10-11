"""Farklı `now` günlerinde pratik vakalar (docs/13 Faz 4): `fbb days <slot> --now 2026-10-16T11:00 [--brief A]`.

Kitin koşucusuyla aynı zincir: persona (kitin `persona_for`) → pratik oturum → simülasyon → ledger (`score_ledger`)
+ hakem. Değişen tek şey: çağrının `now` değişkeni ve o güne göre yeniden yazılmış senaryo/beklenti/checks
(`tests/fixtures/days.json`, elle hesaplanmış). Kit dosyalarına dokunulmaz.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time

from fbb import config, kitapi

DAYS_FILE = config.ROOT / "tests" / "fixtures" / "days.json"
PERSONAS = config.ROOT / ".personas-days.json"


def cases_for(now: str, brief: str = "", only: str = "") -> list[dict]:
    """Public vakaları o günün senaryosu, beklentisi ve checks'i ile döner."""
    public = {c["id"]: c for c in json.loads((config.KIT / "public-test-set.json").read_text())}
    day = json.loads(DAYS_FILE.read_text())["days"].get(now)
    if day is None:
        raise SystemExit(f"{now} için gün tanımı yok: {DAYS_FILE}")
    out = []
    for cid, over in day.items():
        c = copy.deepcopy(public[cid])
        if brief and c["brief"] != brief or only and cid not in only.split(","):
            continue
        for key in ("script", "expected", "checks"):
            if key in over:
                c[key] = over[key]
        c["variables"]["now"] = now
        c["title"] = c["title"] + " @" + now[:10]
        out.append(c)
    return out


def run_days(agent_id: str, now: str, *, brief: str = "", only: str = "", style: str = "", reps: int = 1) -> dict:
    kit = kitapi.freya()
    import run_cases  # kit/tools (kitapi.freya() yolu ekler)
    from score import http, score_ledger

    cases = cases_for(now, brief, only)
    store = json.loads(PERSONAS.read_text()) if PERSONAS.exists() else {}
    spec = {c["id"]: run_cases.persona_for(c, {"identity": c["identity"]}, style or None) for c in cases}
    key = {i: i + ":" + hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10] for i, p in spec.items()}
    new = [c for c in cases if key[c["id"]] not in store]
    if new:
        made = kit.create_personas([spec[c["id"]] for c in new])["personas"]
        store.update({key[c["id"]]: p["id"] for c, p in zip(new, made, strict=True)})
        PERSONAS.write_text(json.dumps(store, indent=1))
    ids = {c["id"]: store[key[c["id"]]] for c in cases}
    all_rows = []
    for rep in range(reps):
        sessions = {}
        for c in cases:
            v = http("/v1/practice/sessions", {"case": c["id"]})["variables"]
            v["now"] = now
            sessions[c["id"]] = v
        t0 = time.time()
        sim_id, it_id, status = kit.run_simulation(agent_id, f"days {now} {time.strftime('%H:%M:%S')}",
                                                   {ids[c["id"]]: sessions[c["id"]] for c in cases})
        judge = {r["personaId"]: r for r in kit.get_iteration(sim_id, it_id)["runs"]}
        rows = []
        for c in cases:
            led = http("/v1/practice/ledger/" + sessions[c["id"]]["customer_id"])
            r = score_ledger(c, led)
            j = judge.get(ids[c["id"]], {})
            if j.get("outcome") != "pass":
                r["failed"].append("conversation: " + " ".join(str(j.get("reason") or "no verdict").split())[:500])
            rows.append({"id": c["id"], "pass": not r["failed"], "failed": r["failed"], "call_id": j.get("callId"),
                         "tools": [x["tool"] for x in led["calls"]], "slowest_turn_s": _slowest(kit, j.get("callId"))})
            tools = " > ".join(x["tool"].replace("verify_identity", "verify").replace("create_promise", "promise")
                               for x in led["calls"])
            print(("PASS" if not r["failed"] else "FAIL"), c["id"], now[:10], "|", tools, flush=True)
            for f in r["failed"]:
                print("       -", f[:300], flush=True)
        waits = sorted(r["slowest_turn_s"] for r in rows if r["slowest_turn_s"] is not None)
        med = waits[len(waits) // 2] if waits else 0
        print(f"-- {now} run {rep + 1}/{reps}: {sum(r['pass'] for r in rows)}/{len(rows)} passed, "
              f"{time.time() - t0:.0f} s, slowest turn median {med:.0f} s, worst {waits[-1] if waits else 0:.0f} s, "
              f"simulation {sim_id} ({status})\n", flush=True)
        all_rows.append(rows)
    final = [{"id": c["id"], "passes": sum(r[k]["pass"] for r in all_rows), "runs": reps,
              "pass": all(r[k]["pass"] for r in all_rows)} for k, c in enumerate(cases)]
    if reps > 1:
        for f in final:
            print(("PASS" if f["pass"] else "FAIL"), f["id"], f"{f['passes']}/{f['runs']}")
    result = {"agent_id": agent_id, "now": now, "style": style, "runs": reps, "passed": sum(f["pass"] for f in final),
              "total": len(final), "final": final, "all_rows": all_rows}
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS / f"days-{agent_id[:8]}-{now[:10]}-{time.strftime('%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result, indent=1))
    print(f"{result['passed']}/{result['total']} passed on {now}. sonuç dosyası: {out}")
    return result


def _slowest(kit, call_id: str | None) -> float | None:
    """Kitin ölçüsüyle aynı: müşteri mesajından agent'ın ilk cevabına kadar en uzun bekleme (sn)."""
    if not call_id:
        return None
    try:
        call = kit.get_call(call_id)
    except Exception:
        return None
    last_user, worst = None, 0.0
    for m in call.get("messages", []):
        t = m.get("secondsFromStart")
        if t is None:
            continue
        if m.get("role") == "user":
            last_user = t
        elif last_user is not None:
            worst = max(worst, t - last_user)
            last_user = None if m.get("role") == "assistant" else last_user
    return round(worst, 1)


def main_args(sub) -> None:
    d = sub.add_parser("days", help="pratik vakaları başka bir `now` gününde koş (tests/fixtures/days.json)")
    d.add_argument("agent_id", help="agent ID ya da slot adı")
    d.add_argument("--now", required=True, help="ör. 2026-10-16T11:00 (days.json'daki anahtar)")
    d.add_argument("--brief", default="")
    d.add_argument("--only", default="")
    d.add_argument("--style", default="")
    d.add_argument("--reps", type=int, default=1)
