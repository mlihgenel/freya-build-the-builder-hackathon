"""Servis sözleşmesinden (Word/PDF/Markdown, openapi dosyası yoksa) tool API'sini (OpenAPI 3) çıkarır. Claude ile.

Final formatı (11 Eki): vaka bir belge klasörü; tool API'si bir 'service contract' belgesi olabilir. Yedi tool'un adları
kitle aynı kalır; alanlar ve izin verilen değerler belgeden okunur."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from fbb.llm import ask_json
from fbb.trace import Trace

TOOLS = ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent",
         "close_call")

SYSTEM = """You turn a bank's service contract into an OpenAPI 3.0 JSON document for a phone agent's tool API.
The API has exactly these operations (operationId = path name, POST, JSON body): verify_identity, get_account,
create_promise, add_note, schedule_callback, transfer_to_agent, close_call.
For each operation write: the path exactly as the contract gives it (e.g. "/v1/verify_identity" or "/verify_identity"),
the request body schema (properties with type, description, enum where the contract lists allowed values, and
`required`), and the 200 response schema (properties with types and enums, arrays with item properties).
Copy every field name, enum value and code exactly as the contract writes it. Invent nothing. If the contract gives a
base URL put it in servers, otherwise use "https://example.invalid".
Return the whole document as a JSON string in `openapi_json`."""


class ContractOut(BaseModel):
    openapi_json: str = Field(..., description="The complete OpenAPI 3.0 document as a JSON string")
    notes: list[str] = Field(default_factory=list, description="Anything unclear in the contract")


def openapi_from_contract(documents: str, out_path: Path, trace: Trace) -> Path:
    res = ask_json(SYSTEM, "SERVICE CONTRACT AND CASE DOCUMENTS:\n" + documents + "\n\nReturn the OpenAPI JSON.",
                   ContractOut, "servis sözleşmesi → OpenAPI", trace)
    api = json.loads(res.openapi_json)
    found = sorted({(op.get("operationId") or p.strip("/").split("/")[-1])
                    for p, ops in api.get("paths", {}).items() for op in ops.values() if isinstance(op, dict)})
    trace.event("contract", f"{len(found)} tool sözleşmeden çıkarıldı", tools=found, notes=res.notes,
                missing=[t for t in TOOLS if t not in found])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(api, indent=1, ensure_ascii=False))
    return out_path
