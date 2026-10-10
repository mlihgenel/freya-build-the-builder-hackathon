"""Brief'le gelen tool API dosyasını (openapi.json) okur. URL'ler, alanlar ve enum'lar buradan gelir."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolField:
    name: str
    type: str = "string"
    description: str = ""
    enum: list[str] = field(default_factory=list)
    required: bool = False
    format: str = ""
    default: str = ""


@dataclass
class ToolDef:
    name: str
    path: str
    method: str
    summary: str
    fields: dict[str, ToolField]
    response: dict  # cevap şeması (properties)


@dataclass
class ToolCatalog:
    base_url: str
    tools: dict[str, ToolDef]
    info: str = ""

    def url(self, tool: str) -> str:
        return self.base_url.rstrip("/") + self.tools[tool].path

    def has(self, tool: str) -> bool:
        return tool in self.tools

    def enum(self, tool: str, field_path: str) -> list[str]:
        """'field' ya da cevap alanı için 'products[].type' biçiminde yol."""
        t = self.tools.get(tool)
        if not t:
            return []
        if field_path in t.fields:
            return list(t.fields[field_path].enum)
        node = {"properties": t.response}
        for part in field_path.split("."):
            arr = part.endswith("[]")
            node = (node.get("properties") or {}).get(part.rstrip("[]"), {})
            if arr:
                node = node.get("items", {})
        return list(node.get("enum", []))

    def summary_text(self) -> str:
        """LLM'e gösterilen özet: istek alanları (* zorunlu, =enum, açıklama) ve cevap alanları."""
        lines = []
        for t in self.tools.values():
            args = ", ".join(f"{f.name}{'*' if f.required else ''}:{f.type}{'=' + '|'.join(f.enum) if f.enum else ''}"
                             for f in t.fields.values())
            lines.append(f"- {t.name}({args}): {t.summary}")
            for f in t.fields.values():
                if f.description:
                    lines.append(f"    {f.name}: {f.description[:300]}")
            if t.response:
                lines.append(f"    returns: {_describe(t.response)}")
        return "\n".join(lines)


def _describe(props: dict) -> str:
    out = []
    for k, v in props.items():
        kind = v.get("type", "")
        if kind == "array" and (v.get("items") or {}).get("properties"):
            out.append(f"{k}: list of {{{_describe(v['items']['properties'])}}}")
        else:
            extra = ("=" + "|".join(str(x) for x in v["enum"])) if v.get("enum") else ""
            desc = f" ({v['description'][:80]})" if v.get("description") else ""
            out.append(f"{k}:{kind}{extra}{desc}")
    return ", ".join(out)


def _resolve(spec: dict, node: dict) -> dict:
    ref = node.get("$ref") if isinstance(node, dict) else None
    if ref and ref.startswith("#/"):
        cur = spec
        for part in ref[2:].split("/"):
            cur = cur[part]
        return _resolve(spec, cur)
    return node


def load_catalog(path: str | Path) -> ToolCatalog:
    spec = json.loads(Path(path).read_text())
    servers = spec.get("servers") or [{"url": ""}]
    tools: dict[str, ToolDef] = {}
    for p, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method.lower() not in ("post", "get", "put", "patch"):
                continue
            body = _resolve(spec, op.get("requestBody", {}).get("content", {}).get("application/json", {})
                            .get("schema", {}))
            req = set(body.get("required", []))
            fields = {}
            for fname, f in (body.get("properties") or {}).items():
                f = _resolve(spec, f)
                dflt = f.get("default")
                fields[fname] = ToolField(fname, f.get("type", "string"), f.get("description", ""),
                                          [str(x) for x in f.get("enum", [])], fname in req, f.get("format", ""),
                                          "" if dflt is None or isinstance(dflt, (dict, list)) else str(dflt))
            ok = op.get("responses", {}).get("200", {})
            resp = _resolve(spec, ok.get("content", {}).get("application/json", {}).get("schema", {}))
            name = op.get("operationId") or p.strip("/").split("/")[-1]
            tools[name] = ToolDef(name, p, method.upper(), op.get("summary") or op.get("description") or "", fields,
                                  _expand(spec, resp.get("properties", {})))
    return ToolCatalog(servers[0].get("url", ""), tools, (spec.get("info") or {}).get("description", ""))


def _expand(spec: dict, props: dict) -> dict:
    out = {}
    for k, v in props.items():
        v = _resolve(spec, v)
        if v.get("type") == "array":
            items = _resolve(spec, v.get("items", {}))
            v = dict(v, items=dict(items, properties=_expand(spec, items.get("properties", {}))))
        elif v.get("properties"):
            v = dict(v, properties=_expand(spec, v["properties"]))
        out[k] = v
    return out
