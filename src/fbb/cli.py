"""Komut satırı.

    uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json
    uv run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools kit/tools/openapi.json
    uv run export-agent --slot brief-a
    uv run fbb cases <agent_id> --brief A [--reps 3] [--style pieces]
    uv run fbb chat <slot> "Hello?" --case PUB-01
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
    c.add_argument("agent_id")
    c.add_argument("--brief", default="")
    c.add_argument("--only", default="")
    c.add_argument("--reps", type=int, default=1)
    c.add_argument("--style", default="")
    h = sub.add_parser("chat", help="yayınlanmış workflow ile tek tur sohbet")
    h.add_argument("slot")
    h.add_argument("message")
    h.add_argument("--case", default="PUB-01", help="çağrı değişkenleri için pratik vaka")
    h.add_argument("--call-id", default="")
    a = ap.parse_args(argv)
    from fbb import kitapi

    if a.cmd == "cases":
        res = kitapi.run_cases(a.agent_id, brief=a.brief, only=a.only, reps=a.reps, style=a.style)
        print(res.get("stdout", ""))
    elif a.cmd == "chat":
        state = json.loads(kitapi.STATE_FILE.read_text())
        variables = None
        if not a.call_id:
            variables = kitapi.practice_session(a.case).get("variables")
        print(json.dumps(kitapi.chat(state[a.slot]["workflow_id"], a.message, call_id=a.call_id or None,
                                     variables=variables), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
