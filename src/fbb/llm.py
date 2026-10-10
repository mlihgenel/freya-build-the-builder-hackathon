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


def _parent(data, loc):
    cur = data
    for part in loc[:-1]:
        cur = cur[part]
    return cur


def lenient_validate(model_cls: type[BaseModel], data) -> tuple[BaseModel, list[str]]:
    """Son çare: doğrulamadan geçmeyen değerleri atarak (varsayılan kullanılır) ya da desteklenen ilk değere
    çevirerek nesneyi kurtarır. Atılan her şey not olarak döner (spec'te `unmapped`'e yazılır). Build çökmez;
    kurtarılamayan (zorunlu alan eksik) hata yükseltilir."""
    data = json.loads(json.dumps(data))
    notes: list[str] = []
    for _ in range(60):
        try:
            obj = model_cls.model_validate(data)
            return obj, notes
        except ValidationError as e:
            fixed = False
            for err in e.errors():
                loc = list(err.get("loc") or [])
                if not loc:
                    continue
                if err.get("type") == "missing":
                    # zorunlu alan yok (ör. geçersiz değer az önce atıldı): içinde bulunduğu liste öğesini at
                    idx = max((n for n, part in enumerate(loc) if isinstance(part, int)), default=-1)
                    if idx < 0:
                        continue
                    holder = _parent(data, loc[:idx + 1])
                    removed = holder.pop(loc[idx])
                    notes.append(f"{'.'.join(str(x) for x in loc[:idx + 1])}: eksik alanlı öğe atıldı: "
                                 f"{json.dumps(removed, ensure_ascii=False)[:200]}")
                    fixed = True
                    break
                try:
                    parent = _parent(data, loc)
                    key = loc[-1]
                    value = parent[key]
                except (KeyError, IndexError, TypeError):
                    continue
                where = ".".join(str(x) for x in loc)
                expected = (err.get("ctx") or {}).get("expected", "")
                if err.get("type") == "literal_error" and expected:
                    choice = re.findall(r"'([^']*)'", str(expected))
                    if choice:
                        parent[key] = choice[0]
                        notes.append(f"{where}: '{value}' desteklenmiyor, '{choice[0]}' kullanıldı")
                        fixed = True
                        break
                parent.pop(key)
                notes.append(f"{where}: '{json.dumps(value, ensure_ascii=False)[:200]}' desteklenmiyor, atıldı "
                             f"({err.get('msg', '')[:120]})")
                fixed = True
                break
            if not fixed:
                raise
    raise LLMError("gevşek doğrulama sonuçlanmadı")


def ask_json(system: str, prompt: str, model_cls: type[BaseModel], purpose: str, trace: Trace,
             *, retries: int = 2, use_schema: bool = True):
    """Şemaya uygun bir nesne döndürür (pydantic ile doğrulanmış)."""
    model = config.builder_model()
    schema = model_cls.model_json_schema() if use_schema else None
    last_err = ""
    last_data = None
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
            last_data = data
            return model_cls.model_validate(data)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
    if last_data is not None:
        try:
            obj, notes = lenient_validate(model_cls, last_data)
        except (ValidationError, LLMError) as e:
            raise LLMError(f"{purpose}: geçerli çıktı alınamadı: {str(e)[:500]}") from e
        _note_unmapped(obj, notes)
        trace.event("lenient", f"{purpose}: {len(notes)} değer gevşek modda düzeltildi", notes=notes)
        return obj
    raise LLMError(f"{purpose}: geçerli çıktı alınamadı: {last_err[:500]}")


def _note_unmapped(obj: BaseModel, notes: list[str]) -> None:
    """Atılan değerleri spec'in `unmapped` listesine (varsa iç içe) yazar: agent'a kural olarak ulaşırlar."""
    target = obj
    if not hasattr(target, "unmapped") and hasattr(target, "spec"):
        target = target.spec
    if hasattr(target, "unmapped"):
        target.unmapped.extend("Builder could not encode: " + n for n in notes)
