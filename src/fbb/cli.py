"""Komut satırı.

    uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json
    uv run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools kit/tools/openapi.json
    uv run export-agent --slot brief-a
    uv run fbb cases <agent_id> --brief A [--reps 3] [--style pieces]
    uv run fbb chat <slot> "Hello?" --case PUB-01
    uv run fbb specdiff out/<slot>.spec.json tests/fixtures/spec_a.json
"""
from __future__ import annotations

import argparse
import json
import sys

from fbb import config


def build_main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="build-agent", description="Brief(ler)den Freya telefon agent'ı kurar.")
    ap.add_argument("briefs", nargs="+", help="brief .md dosyaları; sonraki öncekini değiştirir")
    ap.add_argument("--tools", required=True, help="brief'in tool API dosyası (openapi.json)")
    ap.add_argument("--slot", default="", help="workflow slot adı (varsayılan: son brief'in adı)")
    ap.add_argument("--spec", default="", help="hazır spec JSON (LLM çıkarımını atlar; sadece geliştirme)")
    ap.add_argument("--no-audit", action="store_true", help="spec denetim geçişini atla")
    ap.add_argument("--no-deploy", action="store_true", help="Freya'ya gönderme, sadece yerel çıktı")
    ap.add_argument("--selftest", default="none", help="none | cases:A | cases:B")
    ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args(argv)
    from fbb.build import BuildOptions, run_build

    res = run_build(BuildOptions(briefs=a.briefs, tools=a.tools, slot=a.slot, spec_file=a.spec,
                                 audit=not a.no_audit, deploy=not a.no_deploy, selftest=a.selftest, reps=a.reps))
    print(json.dumps(res, indent=1, ensure_ascii=False))


def export_main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="export-agent")
    ap.add_argument("--slot", required=True)
    a = ap.parse_args(argv)
    from fbb import kitapi

    state = json.loads(kitapi.STATE_FILE.read_text())
    wid = state[a.slot]["workflow_id"]
    print(kitapi.export(wid, config.EXPORTS / f"{a.slot}.workflow.json"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fbb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cases", help="kitin run_cases.py'si")
    c.add_argument("agent_id", help="agent ID ya da slot adı (ör. dev-a)")
    c.add_argument("--brief", default="")
    c.add_argument("--only", default="")
    c.add_argument("--reps", type=int, default=1)
    c.add_argument("--style", default="")
    h = sub.add_parser("chat", help="yayınlanmış workflow ile tek tur sohbet")
    h.add_argument("slot")
    h.add_argument("message")
    h.add_argument("--case", default="PUB-01", help="çağrı değişkenleri için pratik vaka")
    h.add_argument("--call-id", default="")
    k = sub.add_parser("call", help="bir çağrının zaman çizelgesi: konuşma, node'lar, tool çağrıları, hatalar")
    k.add_argument("call_id")
    k.add_argument("--all", action="store_true", help="route ve değişken olaylarını da göster")
    r = sub.add_parser("report", help="bir run_cases sonucunun özeti ve başarısız çağrıların ID'leri")
    r.add_argument("path", help="results/*.json")
    d = sub.add_parser("specdiff", help="iki spec'i karşılaştırır (PUAN / METİN / BİLGİ farkları)")
    d.add_argument("spec", help="incelenen spec (ör. out/<slot>.spec.json)")
    d.add_argument("reference", help="referans spec (ör. tests/fixtures/spec_a.json)")
    d.add_argument("--info", action="store_true", help="BİLGİ düzeyindeki farkları da yaz")
    a = ap.parse_args(argv)
    if a.cmd == "specdiff":
        from fbb.specdiff import report

        text, n_score = report(a.spec, a.reference, show_info=a.info)
        print(text)
        sys.exit(1 if n_score else 0)
    from fbb import kitapi

    if a.cmd == "call":
        print_call(kitapi.get_call(a.call_id), show_all=a.all)
        return
    if a.cmd == "report":
        res = json.loads(open(a.path).read())
        print(f"{res.get('passed')}/{res.get('total')} geçti, {res.get('runs')} tekrar, simülasyon {res.get('simulation_id')}")
        for f in res.get("final", []):
            print(("PASS" if f["pass"] else "FAIL"), f["id"], f"{f['passes']}/{f['runs']}")
        for row in res.get("rows", []):
            if not row["pass"]:
                print(f"\n{row['id']}  call_id={row.get('call_id')}  tools: {' > '.join(row.get('tools', []))}")
                for reason in row.get("failed", []):
                    print("   -", reason[:300])
        return
    if a.cmd == "cases":
        res = kitapi.run_cases(kitapi.agent_for(a.agent_id), brief=a.brief, only=a.only, reps=a.reps, style=a.style)
        print(res.get("stdout", ""))
    elif a.cmd == "chat":
        state = json.loads(kitapi.STATE_FILE.read_text())
        variables = None
        if not a.call_id:
            variables = kitapi.practice_session(a.case).get("variables")
        print(json.dumps(kitapi.chat(state[a.slot]["workflow_id"], a.message, call_id=a.call_id or None,
                                     variables=variables), indent=1, ensure_ascii=False))


def print_call(call: dict, show_all: bool = False) -> None:
    print("bitiş sebebi:", call.get("endedReason"))
    for m in call.get("messages", []):
        t = m.get("secondsFromStart") or 0
        role = m.get("role")
        if role != "system":
            print(f"{t:7.1f}  {role.upper()}: {m.get('message', '')}")
            continue
        try:
            e = json.loads(m.get("message") or "{}")
        except ValueError:
            continue
        ev = e.get("event", "")
        if ev == "node_enter":
            print(f"{t:7.1f}    > {e.get('node')}")
        elif ev == "function_call_start":
            args = e.get("args") or {}
            shown = args.get("params") or args.get("body") or {k: v for k, v in args.items() if k != "code"}
            print(f"{t:7.1f}    * {e.get('function')} {json.dumps(shown, ensure_ascii=False)[:200]}")
        elif ev == "function_call_complete":
            res = e.get("result") or {}
            if res.get("status") != "success" or show_all:
                print(f"{t:7.1f}    ! {e.get('function')} sonuç: {json.dumps(res, ensure_ascii=False)[:200]}")
            elif isinstance(res.get("data"), dict):
                print(f"{t:7.1f}      = {json.dumps(res['data'], ensure_ascii=False)[:200]}")
        elif ev in ("error", "function_call_error"):
            print(f"{t:7.1f}    !! HATA: {(e.get('error') or e.get('message') or '')[:200]}")
        elif show_all and ev == "route_evaluated" and e.get("matched"):
            print(f"{t:7.1f}    → {e.get('target')} ({e.get('reason', '')[:80]})")


if __name__ == "__main__":
    main(sys.argv[1:])
