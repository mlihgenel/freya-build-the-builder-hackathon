"""Tool tanımları: bankanın API'si (openapi'den) ve modelin çağırdığı code_exec tool'ları."""
from __future__ import annotations

from fbb.ingest.openapi import ToolCatalog
from fbb.runtime.emit import build_snippet


def bank_call(cat: ToolCatalog, tool: str, body_defaults: dict[str, str], *, pre_hook: str = "",
              post_hook: str = "", timeout_ms: int = 12000, retries: int = 0, lifecycle: str = "") -> dict:
    """Bankanın bir uç noktasına api_call. Gövde alanları openapi'den; değerler `default` ile baked."""
    t = cat.tools[tool]
    props = {}
    for fname, f in t.fields.items():
        if fname not in body_defaults:
            continue
        leaf = {"type": f.type if f.type in ("string", "number", "integer", "boolean") else "string",
                "default": body_defaults[fname]}
        if f.description:
            leaf["description"] = f.description[:300]
        if f.enum:
            leaf["enum"] = list(f.enum)
        props[fname] = leaf
    config = {"timeoutMs": timeout_ms, "maxRetries": retries}
    if lifecycle:
        config["alwaysRunsAt"] = [lifecycle]
    fn = {
        "type": "function",
        "config": config,
        "function": {
            "name": tool,
            "handler": "__function__:api_call",
            "description": t.summary or tool,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": cat.url(tool)},
                "method": {"type": "string", "default": t.method},
                "headers": {"type": "object", "properties": {
                    "Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": props,
                         "required": [k for k in props if t.fields[k].required]},
            }},
        },
    }
    if pre_hook:
        fn["pre_process_code"] = pre_hook
    if post_hook:
        fn["post_process_code"] = post_hook
    return fn


def model_tool(name: str, description: str, params: dict[str, str], entry: str, rt: dict) -> dict:
    """Modelin çağırdığı code_exec tool'u. Argümanlar modelden gelir, iş kuralı kodda çalışır."""
    snippet = build_snippet(entry, rt, template_args=list(params))
    props = {
        "code": {"type": "string", "default": snippet},
        "timeout_ms": {"type": "number", "default": 30000},
    }
    for p, desc in params.items():
        props[p] = {"type": "string", "description": desc}
    return {
        "type": "function",
        "config": {"timeoutMs": 35000},
        "function": {
            "name": name,
            "handler": "__function__:code_exec",
            "description": description,
            "parameters": {"type": "object", "properties": props, "required": list(params)},
        },
    }


STRIP_HEADER = (
    "try:\n"
    "    if isinstance(result, dict):\n"
    "        result.pop('header', None)\n"
    "except Exception:\n"
    "    pass\n"
)
