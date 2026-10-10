"""Builder'ın LLM çağrıları: claude-agent-sdk üzerinden Claude (makinedeki Claude girişi ya da ANTHROPIC_API_KEY).

Araç yok, dosya ayarı yok: model sadece metin okur ve şemaya uygun JSON döner. Her çağrı trace'e
model + amaç + süre + maliyet olarak yazılır. Doğrulama hatasında hata mesajıyla en fazla 2 kez yeniden sorulur.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from pydantic import BaseModel, ValidationError

from fbb import config
from fbb.trace import Trace


class LLMError(RuntimeError):
    pass


async def _query(system: str, prompt: str, schema: dict | None, model: str) -> tuple[object, str, float | None, dict]:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    opts = ClaudeAgentOptions(
        system_prompt=system,
        model=model,
        tools=[],
        setting_sources=[],
        max_turns=4,
        permission_mode="dontAsk",
        output_format={"type": "json_schema", "schema": schema} if schema else None,
        cwd=str(config.ROOT),
    )
    structured, text, cost, usage = None, "", None, {}
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, ResultMessage):
            if msg.is_error:
                raise LLMError(f"Claude hatası: {msg.result or msg.errors}")
            structured = msg.structured_output
            text = msg.result or ""
            cost = msg.total_cost_usd
            usage = msg.usage or {}
    return structured, text, cost, usage


def _extract_json(text: str):
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def ask_json(system: str, prompt: str, model_cls: type[BaseModel], purpose: str, trace: Trace,
             *, retries: int = 2, use_schema: bool = True):
    """Şemaya uygun bir nesne döndürür (pydantic ile doğrulanmış)."""
    model = config.builder_model()
    schema = model_cls.model_json_schema() if use_schema else None
    last_err = ""
    for attempt in range(retries + 1):
        p = prompt if not last_err else (
            prompt + "\n\nYour previous answer failed validation:\n" + last_err[:3000]
            + "\nReturn the corrected, complete JSON object.")
        t0 = time.time()
        try:
            structured, text, cost, usage = asyncio.run(_query(system, p, schema, model))
        except Exception as e:  # SDK / ağ / kota
            trace.model_call(model, f"{purpose} (deneme {attempt + 1})", seconds=time.time() - t0, ok=False)
            last_err = f"call failed: {e}"
            if "credit" in str(e).lower() or "quota" in str(e).lower() or "login" in str(e).lower():
                raise LLMError(str(e)) from e
            continue
        trace.model_call(model, f"{purpose} (deneme {attempt + 1})", seconds=time.time() - t0, cost_usd=cost,
                         tokens={k: usage.get(k) for k in ("input_tokens", "output_tokens") if k in usage})
        try:
            data = structured if structured is not None else _extract_json(text)
            return model_cls.model_validate(data)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
    raise LLMError(f"{purpose}: geçerli çıktı alınamadı: {last_err[:500]}")
