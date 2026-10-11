"""Genel yol: vaka kitteki tahsilat formatında değilse (yedi tahsilat tool'u yok) workflow'u Claude yazar.

Bir vaka tahsilattan farklı bir çağrı tipi ve farklı bir API olabilir. PolicySpec şeması
tahsilata özel olduğu için bu durumda:
  1. Claude vakanın API'sini (servis/entegrasyon belgesinden) OpenAPI 3 olarak çıkarır,
  2. Claude, Freya'nın workflow belgelerini ve örnek agent'ı referans alarak workflow JSON'unu yazar,
  3. bizim lint + dryRun hataları Claude'a geri verilip en fazla iki kez düzelttirilir.
Kayıt, geri okuma, export ve trace tahsilat yoluyla aynıdır (build.py). Bu modülde vakaya özgü hiçbir değer yoktur.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from fbb import config
from fbb.llm import ask_json
from fbb.trace import Trace

COLLECTION_TOOLS = ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
                    "transfer_to_agent", "close_call")

API_SYSTEM = """You turn a bank's service and integration documents into an OpenAPI 3.0 JSON document for the phone
agent's tool API. Include every service the phone agent needs, with the path, method, request body or query parameters
and every response (status codes included) exactly as the integration document defines them: same paths, same field
names, same shapes, same enum values and codes. Use the operationId the documents use for the service (or a short
snake_case name). When documents disagree, the latest one (newest mail, version, memo or meeting note) wins; say so in
`notes`. Invent nothing. Put the base URL in servers if given, otherwise "https://example.invalid".
Return the whole document as a JSON string in `openapi_json`."""

WF_SYSTEM = """You write a Freya voice-agent workflow (JSON) for a bank's phone line, from the bank's documents.
A deterministic program then validates it (lint, dry run) and deploys it, so the JSON must be complete and valid.

Follow the Freya workflow reference below exactly (node types, fields, tools, transitions, variables). Hard rules:
- The agent speaks the language of the case to the caller (the documents say which); write task_message instructions
  in English and every sentence the agent must say word for word in the caller's language.
- Tools that call the bank are `__function__:api_call` functions on conversation nodes (`tools`) or engine calls on
  api_request nodes (`pre_actions`); urls are the given API base URL + the path, bodies as leaves under
  body.properties with `default` values. Call variables (e.g. the customer number) are baked with "{{var}}"; fields the
  model fills have no default (or a default naming an unset variable) and a description. If the documents or test
  data say a service can answer slowly, set the call's config.timeoutMs above the longest documented delay.
- The platform skips the entry actions of the initial node: start with a passthrough code node that only routes
  (`always`) into the first api_request node. response_mapping maps leaf values only; a list arrives flattened as
  `<tool>_response.data.<path>.0.<field>`, ... and is rebuilt in a code node from those `vars` keys.
- Never ask the caller for something the call already gives as a variable. Use every call variable the documents list.
- Every date decision uses the call variable for the current date/time, never the real clock. Where dates must be
  computed, compute them in a code node (`code_exec`, only json/re/datetime, never raise, never write two braces next to
  each other) and put the result in variables the prompts use.
- Route on string flags, never on booleans ("true"/"True" both, if you must). Passthrough nodes end with an `always`
  transition. Every path ends at an end_call node; say the closing words before it.
- Tell the model in every step: after every tool result, speak or call the next tool; never invent figures, dates or
  reasons; never claim an action happened unless its tool returned success; read out exactly what the tool returned.
- Cover everything the documents require: every request type, every error and empty response of every service
  (status codes included), hand-over to a person, out-of-scope questions, the exact announcements, and the edge cases
  in the example conversations. Keep turns short.
Return the workflow object as a JSON string in `workflow_json` and the call variable names in `call_variables`."""


class ApiOut(BaseModel):
    openapi_json: str = Field(..., description="The complete OpenAPI 3.0 document as a JSON string")
    notes: list[str] = Field(default_factory=list)


class WorkflowOut(BaseModel):
    workflow_json: str = Field(..., description="The complete workflow object as a JSON string")
    call_variables: list[str] = Field(default_factory=list, description="Call variable names the workflow uses")
    notes: list[str] = Field(default_factory=list)


def is_collection_case(tool_names: list[str]) -> bool:
    return all(t in tool_names for t in COLLECTION_TOOLS)


def reference() -> str:
    kit = config.KIT
    parts = []
    for name in ("docs/workflow-format.md", "docs/tools-and-code.md"):
        parts.append(f"===== FREYA REFERENCE: {name} =====\n" + (kit / name).read_text())
    parts.append("===== EXAMPLE WORKFLOW (examples/base-agent.json, another bank case) =====\n"
                 + (kit / "examples" / "base-agent.json").read_text())
    return "\n".join(parts)


def openapi_for_case(documents: str, out_path: Path, trace: Trace) -> Path:
    res = ask_json(API_SYSTEM, "CASE DOCUMENTS:\n" + documents + "\n\nReturn the OpenAPI JSON.", ApiOut,
                   "vaka belgeleri → API (OpenAPI)", trace)
    api = json.loads(res.openapi_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(api, indent=1, ensure_ascii=False))
    trace.event("generic_api", f"{len(api.get('paths', {}))} yol çıkarıldı", paths=sorted(api.get("paths", {})),
                notes=res.notes)
    return out_path


def write_workflow(documents: str, api_text: str, base_url: str, trace: Trace, problems: list[str] | None = None,
                   previous: str = "") -> WorkflowOut:
    prompt = (reference() + "\n\nAPI BASE URL: " + base_url + "\nTOOL API (OpenAPI):\n" + api_text
              + "\n\nCASE DOCUMENTS:\n" + documents)
    if problems:
        prompt += ("\n\nYOUR PREVIOUS WORKFLOW:\n" + previous + "\n\nIT FAILED THESE CHECKS (fix all of them and return "
                   "the complete corrected workflow):\n- " + "\n- ".join(problems))
    else:
        prompt += "\n\nWrite the workflow."
    return ask_json(WF_SYSTEM, prompt, WorkflowOut,
                    "vaka belgeleri → workflow" + (" (düzeltme)" if problems else ""), trace)
