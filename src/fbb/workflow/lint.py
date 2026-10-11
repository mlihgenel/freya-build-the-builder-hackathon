"""Workflow'un yerel statik kontrolleri. Platforma göndermeden önce çalışır; hata listesi döner."""
from __future__ import annotations

import json
import re

from fbb.ingest.openapi import ToolCatalog

VAR = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)(?::json)?\s*\}\}")
SYSTEM_PREFIXES = ("system.", "call.", "extractor.", "date.", "time.")


def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


def _code_strings(node: dict) -> list[str]:
    out = []
    for fn in node.get("pre_actions", []) + node.get("tools", []):
        props = fn.get("function", {}).get("parameters", {}).get("properties", {})
        if "code" in props:
            out.append(props["code"].get("default", ""))
        for k in ("pre_process_code", "post_process_code"):
            if fn.get(k):
                out.append(fn[k])
    return out


def lint(workflow: dict, cat: ToolCatalog, *, call_vars: list[str], forbidden_pre_verify: list[str],
         warnings: list[str] | None = None, check_tools: bool = True) -> list[str]:
    """Hata listesi döner (build bunlarda durur). `warnings` verilirse deploy'u durdurmayan bulgular oraya yazılır:
    gizli bir openapi'de beklenmeyen zorunlu alan agent'ı hiç kurmamaktan iyidir."""
    errs: list[str] = []
    warns = warnings if warnings is not None else []
    nodes = workflow.get("nodes", {})
    if workflow.get("initial_node") not in nodes:
        errs.append("initial_node yok")
    if any(v is None for v in _walk(workflow)):
        errs.append("workflow içinde null değer var")
    targets_ok = set(nodes)
    for name, n in nodes.items():
        t = n.get("node_type")
        if n.get("name") != name:
            errs.append(f"{name}: name alanı anahtarla aynı değil")
        if t != "conversation" and n.get("tools"):
            errs.append(f"{name}: tools sadece conversation node'unda olur")
        if t == "conversation" and n.get("pre_actions"):
            errs.append(f"{name}: conversation node'unda pre_actions olmaz")
        if n.get("passthrough"):
            tr = n.get("transitions", [])
            if not tr or tr[-1].get("condition", {}).get("operator") != "always":
                errs.append(f"{name}: passthrough node 'always' ile bitmeli")
            if n.get("passthrough_default_transition") not in targets_ok:
                errs.append(f"{name}: passthrough_default_transition geçersiz")
        for tr in n.get("transitions", []):
            if tr.get("target_node") not in targets_ok:
                errs.append(f"{name}: hedef yok → {tr.get('target_node')}")
        if t == "end_call" and n.get("transitions"):
            errs.append(f"{name}: end_call node'unun transition'ı olmaz")
        if t == "conversation" and len(n.get("tools", [])) > 3:
            errs.append(f"{name}: 3'ten fazla tool")
        if n.get("max_turn_transition") and n["max_turn_transition"] not in targets_ok:
            errs.append(f"{name}: max_turn_transition geçersiz")
        for c in _code_strings(n):
            body = "\n".join(line for line in c.splitlines() if not line.startswith("ARG_"))
            if "{{" in body or "}}" in body:
                errs.append(f"{name}: kod içinde süslü parantez çifti")
    for fn in workflow.get("tools", []):
        if not fn.get("config", {}).get("alwaysRunsAt"):
            errs.append("üst seviye tool alwaysRunsAt olmadan asla çalışmaz")

    # her yol end_call'a varıyor mu
    reach_end = {n for n, v in nodes.items() if v.get("node_type") == "end_call"}
    changed = True
    while changed:
        changed = False
        for name, n in nodes.items():
            if name in reach_end:
                continue
            nxt = [tr.get("target_node") for tr in n.get("transitions", [])]
            if n.get("max_turn_transition"):
                nxt.append(n["max_turn_transition"])
            if any(x in reach_end for x in nxt):
                reach_end.add(name)
                changed = True
    for name in nodes:
        if name not in reach_end:
            errs.append(f"{name}: hiçbir yoldan end_call'a varmıyor")

    # erişilebilirlik
    seen, stack = set(), [workflow.get("initial_node")]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in nodes:
            continue
        seen.add(cur)
        n = nodes[cur]
        stack += [tr.get("target_node") for tr in n.get("transitions", [])]
        if n.get("max_turn_transition"):
            stack.append(n["max_turn_transition"])
    for name in nodes:
        if name not in seen:
            errs.append(f"{name}: başlangıçtan erişilemiyor")

    # kullanılan {{değişken}} bir yerde üretiliyor mu
    produced = set(call_vars)
    blob = json.dumps(workflow)
    produced |= set(re.findall(r"vars\[\\?[\"']([\w.]+)\\?[\"']\]\s*=", blob))
    produced |= set(re.findall(r'"variable": "([\w.]+)"', blob))
    prefixes = set(re.findall(r"vars\[\\?[\"']([\w.]+)\\?[\"']\s*\+", blob))
    for name, n in nodes.items():
        texts = [n.get("task_message", ""), json.dumps(n.get("on_enter", {}))]
        for fn in n.get("pre_actions", []):
            texts.append(json.dumps(fn.get("function", {}).get("parameters", {}).get("properties", {}).get("body", {})))
        for txt in texts:
            for v in VAR.findall(txt):
                if v not in produced and not v.startswith(SYSTEM_PREFIXES) and not v.startswith(tuple(prefixes)):
                    errs.append(f"{name}: {{{{{v}}}}} hiçbir yerde üretilmiyor")

    # doğrulamadan önceki sabit cümlelerde yasaklı kelime
    for name in ("opener",):
        n = nodes.get(name, {})
        spoken = (n.get("on_enter", {}).get("text") or "").lower()
        for w in forbidden_pre_verify:
            if re.search(r"\b" + re.escape(w.lower()) + r"\b", spoken):
                errs.append(f"{name}: açılış cümlesi yasaklı kelime içeriyor: {w}")
        system = ((workflow.get("system_prompt") or "").splitlines() or [""])[0].lower()  # agent_role satırı
        for w in forbidden_pre_verify:
            if re.search(r"\b" + re.escape(w.lower()) + r"\b", system):
                warns.append(f"system prompt doğrulama öncesi yasaklı kelime içeriyor: {w} (agent_role?)")
        if re.search(r"\brecorded\b", spoken):
            warns.append(f"{name}: açılışta 'recorded' kelimesi var: brief cümleyi birebir veriyorsa doğru, vermiyorsa hakem promise kaydı sanabilir")

    # bankaya giden alanlar openapi'de var mı (genel yolda tool adları vakanın API'sine göre: denetlenmez)
    for name, n in (list(nodes.items()) if check_tools else []) + [("tools", {"pre_actions": workflow.get("tools", [])})]:
        for fn in n.get("pre_actions", []):
            f = fn.get("function", {})
            if f.get("handler") != "__function__:api_call":
                continue
            tool = cat.tools.get(f.get("name"))
            if not tool:
                errs.append(f"{name}: bilinmeyen tool {f.get('name')}")
                continue
            body = f.get("parameters", {}).get("properties", {}).get("body", {}).get("properties", {})
            for field in body:
                if field not in tool.fields:
                    errs.append(f"{name}: {tool.name}.{field} openapi'de yok")
            for req in (r for r, fd in tool.fields.items() if fd.required):
                if req not in body:
                    warns.append(f"{name}: {tool.name} zorunlu alanı eksik: {req} (spec.tool_constants ile doldurulabilir)")
    # boyut build'i durdurmaz: platformun dryRun'ı 1,2 MB'ı kabul etti (11 Eki); asıl kontrol deploy öncesi dryRun
    size = len(json.dumps(workflow))
    if size > 400_000:
        warns.append(f"workflow büyük: {size} bayt (dryRun 1,2 MB'a kadar kabul etti; kayıt ve gecikmeye dikkat)")
    return errs
