"""Freya workflow node'ları ve koşulları için küçük kurucular (kit docs/workflow-format.md şeması).

Kurallar: `null` yok; `tools` sadece conversation'da; `pre_actions` sadece api_request/code'da;
passthrough node'lar `always` transition ile biter.
"""
from __future__ import annotations


def always(target: str, desc: str = "always") -> dict:
    return {"target_node": target, "description": desc, "condition": {"operator": "always"}}


def when_eq(target: str, desc: str, variable: str, *values: str) -> dict:
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": [
        {"variable": variable, "operator": "equals", "operand": v} for v in values]}}


def when_gt(target: str, desc: str, variable: str, value: int) -> dict:
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": [
        {"variable": variable, "operator": "greater_than", "operand": value}]}}


def tool_transition(target: str, desc: str) -> dict:
    """Model bu transition'ı `transition_to_<target>` tool'u olarak görür ve çağırarak tetikler."""
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def conversation(name: str, task: str, *, on_enter: dict | None = None, tools: list | None = None,
                 transitions: list | None = None, first_entry_only: bool = False, max_turns: int = 30,
                 max_turn_target: str = "", extraction: list | None = None, loop_prompt: str = "") -> dict:
    node = {
        "name": name,
        "node_type": "conversation",
        "task_message": task,
        "on_enter": on_enter or {"type": "llm"},
        "on_enter_first_entry_only": first_entry_only,
        "tools": tools or [],
        "transitions": transitions or [],
        "max_node_turns": max_turns,
    }
    if max_turn_target:
        node["max_turn_transition"] = max_turn_target
    if extraction:
        node["extraction_schema"] = extraction
    if loop_prompt:
        node["loop_prompt"] = loop_prompt
    return node


def code(name: str, snippet: str, transitions: list, default_target: str, timeout_ms: int = 30000,
         guard: str = "") -> dict:
    """Code node. `guard`: kod servisi bu node'u çalıştıramazsa (platformun `<node>_failure_count` sayacı)
    gidilecek node. Yoksa değişkenler güncellenmez ve döngüler sonsuza kadar döner (10 Ekim'de görüldü)."""
    if guard:
        transitions = [when_gt(guard, f"code service failed in {name}", f"{name}_failure_count", 0)] + transitions
    return {
        "name": name,
        "node_type": "code",
        "passthrough": True,
        "passthrough_default_transition": default_target,
        "on_enter": {"type": "silent"},
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec",
                "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": snippet},
                    "timeout_ms": {"type": "number", "default": timeout_ms},
                }},
            },
        }],
        "transitions": transitions + [always(default_target)],
    }


def api_request(name: str, call: dict, mapping: list[tuple[str, str]], default_target: str,
                transitions: list | None = None, on_enter: dict | None = None) -> dict:
    return {
        "name": name,
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": default_target,
        "on_enter": on_enter or {"type": "silent"},
        "pre_actions": [call],
        "response_mapping": [{"path": p, "variable": v} for p, v in mapping],
        "transitions": (transitions or []) + [always(default_target)],
    }


def end_call(name: str, function_name: str, speech: str = "") -> dict:
    """speech boşsa sessiz kapanır (veda bir önceki node'da söylenmiştir)."""
    return {
        "name": name,
        "node_type": "end_call",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {
            "name": function_name,
            "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {
                "message_mode": {"type": "string", "default": "custom" if speech else "none"},
                **({"spoken_message": {"type": "string", "default": speech}} if speech else {}),
            }},
        }},
    }
