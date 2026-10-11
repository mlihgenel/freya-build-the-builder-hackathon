"""Genel yolun ikinci aşaması: Claude (Agent SDK, araçlı) ilk workflow'u belgelere göre gözden geçirir, mock'a karşı
chat ile test eder, dosyayı düzeltir ve yeniden kaydeder (`fbb.agent_tools`). Süre bütçesi aşılırsa durdurulur ve
son kaydedilen dosya kullanılır. Bilgi: `refine_knowledge.md`. Bu modülde vakaya özgü hiçbir değer yoktur.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shutil
import time
from pathlib import Path

from fbb import config
from fbb.trace import Trace, redact

KNOWLEDGE = Path(__file__).with_name("refine_knowledge.md")


def _prompt(cases: list[str], work: Path, mock_url: str, slot: str, minutes: int) -> str:
    return f"""Review, test and fix the phone agent built from this client case.

- Case folder(s) (original files; open PDFs and images with the Read tool): {', '.join(cases)}
- First version of the workflow (already deployed to slot `{slot}`): {work / 'workflow.json'}
- Your work folder: {work} — keep the workflow in {work / 'workflow.json'}; write your decisions to {work / 'DECISIONS.md'}
- Mock address of the bank's services (every tool URL starts with it): {mock_url}
- Slot name for save/chat: {slot}
- Time budget: about {minutes} minutes. Save a valid version after every fix; stop testing in time.

Follow the builder knowledge in your system prompt step by step."""


async def _agent(prompt: str, trace: Trace, model: str, timeout_s: float) -> dict:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

    opts = ClaudeAgentOptions(
        cwd=str(config.ROOT),
        model=model,
        system_prompt={"type": "preset", "preset": "claude_code", "append": KNOWLEDGE.read_text()},
        setting_sources=[],
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        permission_mode="dontAsk",
        max_turns=400,
        env={"BASH_DEFAULT_TIMEOUT_MS": "300000", "BASH_MAX_TIMEOUT_MS": "600000",
             "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "FBB_MOCK_URL": os.environ.get("FBB_MOCK_URL", "")},
    )
    summary: dict = {}

    async def consume():
        async for msg in query(prompt=prompt, options=opts):
            trace.event("refine_message", type(msg).__name__,
                        message=json.loads(json.dumps(dataclasses.asdict(msg), default=str)))
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(redact(block.text), flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(redact(f"  [{block.name}] {json.dumps(block.input, ensure_ascii=False)[:200]}"), flush=True)
            elif isinstance(msg, ResultMessage):
                summary.update(turns=msg.num_turns, cost=msg.total_cost_usd, result=(msg.result or "")[:500],
                               error=msg.is_error)

    try:
        await asyncio.wait_for(consume(), timeout=timeout_s)
    except TimeoutError:
        print("[refine] time budget reached: stopping; the last saved workflow is used", flush=True)
        summary["timeout"] = True
    return summary


def refine(cases: list[str], wf_path: Path, mock_url: str, slot: str, trace: Trace, budget_s: float) -> Path:
    """`wf_path`'teki workflow'u Claude'a test ettirip düzelttirir. Dönen yol: son geçerli workflow dosyası."""
    work = config.OUT / f"{slot}-refine"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy2(wf_path, work / "workflow.json")
    os.environ["FBB_MOCK_URL"] = mock_url
    model = config.builder_model()
    trace.event("refine_start", f"chat test + fix, budget {budget_s / 60:.0f} min, model {model}")
    t0 = time.time()
    summary = asyncio.run(_agent(_prompt(cases, work, mock_url, slot, int(budget_s // 60)), trace, model, budget_s))
    trace.model_call(model, "refine: review against the case, chat-test on the mock, fix the workflow",
                     seconds=time.time() - t0, cost_usd=summary.get("cost"), ok=not summary.get("error"))
    trace.event("refine_done", json.dumps(summary, ensure_ascii=False)[:600])
    return work / "workflow.json"
