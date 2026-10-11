"""Genel builder'daki Claude'un kullandığı komutlar: `uv run python -m fbb.agent_tools <komut> ...`

  check <workflow.json>                      yerel yapı kontrolü + Freya dryRun
  save <slot> <workflow.json>                kontrol, kaydet + yayınla, geri oku
  chat <slot> <mesaj> [--vars JSON] [--call-id ID]   yayınlanmış workflow ile tek tur sohbet
  call <call_id>                             bir çağrının zaman çizelgesi (konuşma, node'lar, tool çağrıları)
  end <call_id>                              chat çağrısını kapat

Vakaya özgü hiçbir şey bilmez; mock adresi FBB_MOCK_URL ortam değişkeninden okunur.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from fbb import kitapi

VAR = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)(?::json)?\s*\}\}")


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def local_check(wf: dict) -> list[str]:
    errs: list[str] = []
    if "agent_config" in wf:
        errs.append("remove top-level agent_config (the platform sets it)")
    for path, v in _walk(wf):
        if v is None:
            errs.append(f"null value at {path} (the API rejects null; leave the key out)")
    nodes = wf.get("nodes") or {}
    if not isinstance(nodes, dict) or not nodes:
        errs.append("`nodes` must be a non-empty object keyed by node name")
        return errs
    known = set(nodes) | set(wf.get("global_nodes") or {}) | {"__previous__"}
    if wf.get("initial_node") not in nodes:
        errs.append(f"initial_node {wf.get('initial_node')!r} is not a node")
    mock = os.environ.get("FBB_MOCK_URL", "").rstrip("/")
    every = list(nodes.items()) + list((wf.get("global_nodes") or {}).items())
    for nid, n in every:
        ntype = n.get("node_type")
        if ntype != "conversation" and n.get("tools"):
            errs.append(f"{nid}: `tools` only works on conversation nodes (the platform drops it silently)")
        if ntype == "conversation" and n.get("pre_actions"):
            errs.append(f"{nid}: `pre_actions` only works on api_request/code nodes (the platform drops it)")
        if n.get("passthrough") and not any((t.get("condition") or {}).get("operator") == "always"
                                            for t in n.get("transitions") or []) \
                and not n.get("passthrough_default_transition"):
            errs.append(f"{nid}: passthrough node without an `always` transition or passthrough_default_transition")
        for t in n.get("transitions") or []:
            target = t.get("target_node")
            if target not in known:
                errs.append(f"{nid}: transition to unknown node {target!r}")
        for key in ("max_turn_transition", "passthrough_default_transition"):
            if n.get(key) and n[key] not in known:
                errs.append(f"{nid}: {key} points to unknown node {n[key]!r}")
        for path, v in _walk(n):
            if isinstance(v, str) and mock and re.match(r"https?://", v) and "url" in path.lower():
                if not v.startswith(mock):
                    errs.append(f"{nid}{path}: URL {v[:80]} does not start with the mock address {mock}")
    if not any(n.get("node_type") == "end_call" for n in nodes.values()):
        errs.append("no end_call node")
    return errs


def cmd_check(path: str) -> int:
    wf = json.loads(Path(path).read_text())
    errs = local_check(wf)
    for e in errs:
        print("LOCAL:", e)
    try:
        res = kitapi.validate(Path(path).stem, wf)
        print("DRYRUN:", json.dumps(res, ensure_ascii=False)[:3000])
    except Exception as e:
        print("DRYRUN ERROR:", str(e)[:3000])
        return 1
    size = len(json.dumps(wf))
    print(f"nodes={len(wf.get('nodes') or [])} size={size // 1024} KB local_errors={len(errs)}")
    return 1 if errs else 0


def cmd_save(slot: str, path: str) -> int:
    if cmd_check(path):
        print("not saved: fix the errors above")
        return 1
    wf = json.loads(Path(path).read_text())
    ids = kitapi.save(slot, wf)
    # son başarılı kayıt: ajan süre dolarken dosyayı yarım bırakırsa build bu kopyayı kullanır
    Path(path).with_name("last_saved.json").write_text(json.dumps(wf, indent=1, ensure_ascii=False))
    stored = kitapi.get(ids["workflow_id"]).get("workflow") or {}
    lost = sorted(set(wf.get("nodes") or {}) - set(stored.get("nodes") or {}))
    dropped = [k for k, n in (wf.get("nodes") or {}).items()
               for f in ("tools", "pre_actions") if n.get(f) and not ((stored.get("nodes") or {}).get(k) or {}).get(f)]
    print(json.dumps({**ids, "stored_nodes": len(stored.get("nodes") or {}), "missing_after_save": lost,
                      "fields_dropped_by_platform": dropped}))
    return 0


def cmd_chat(slot: str, message: str, variables: str, call_id: str) -> int:
    state = json.loads(kitapi.STATE_FILE.read_text())
    try:
        res = kitapi.chat(state[slot]["workflow_id"], message, call_id=call_id or None,
                          variables=json.loads(variables) if variables and not call_id else None)
    except Exception as e:
        print("CHAT ERROR (on 502/504 the call may still have run; inspect it with `call`):", str(e)[:1500])
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=1)[:6000])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fbb.agent_tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("path")
    s = sub.add_parser("save")
    s.add_argument("slot")
    s.add_argument("path")
    c = sub.add_parser("chat")
    c.add_argument("slot")
    c.add_argument("message")
    c.add_argument("--vars", default="")
    c.add_argument("--call-id", default="")
    sub.add_parser("call").add_argument("call_id")
    sub.add_parser("end").add_argument("call_id")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return cmd_check(a.path)
    if a.cmd == "save":
        return cmd_save(a.slot, a.path)
    if a.cmd == "chat":
        return cmd_chat(a.slot, a.message, a.vars, a.call_id)
    if a.cmd == "call":
        from fbb.cli import print_call

        print_call(kitapi.get_call(a.call_id), show_all=True)
        return 0
    if a.cmd == "end":
        print(json.dumps(kitapi.chat_end(a.call_id), ensure_ascii=False)[:2000])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
