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


def _prompt(cases: list[str], work: Path, mock_url: str, slot: str, minutes: int, first: bool, api: str) -> str:
    state = (f"- There is no workflow yet: read the whole case, then write the first version to {work / 'workflow.json'}"
             f" (write it in several steps if it is long), check and save it early, then test and fix.\n"
             if not first else
             f"- First version of the workflow (already deployed to slot `{slot}`): {work / 'workflow.json'}\n")
    return f"""Build, test and fix the phone agent for this client case.

- Case folder(s) (original files; open PDFs and images with the Read tool): {', '.join(cases)}
{state}- The bank's service API as the builder extracted it from the documents (OpenAPI; check it against the
  documents): {api}
- Your work folder: {work} — keep the workflow in {work / 'workflow.json'}; write your decisions to {work / 'DECISIONS.md'}
- Mock address of the bank's services (every tool URL starts with it): {mock_url}
- Slot name for save/chat: {slot}
- Time budget: {minutes} minutes, until {time.strftime("%H:%M", time.localtime(time.time() + minutes * 60))} local time
  (check with `date`). Use all of it: keep testing every flow branch, every service error and every example
  conversation, and fixing, until about two minutes before that time. Save a valid version after every fix.

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


def refine(cases: list[str], wf_path: Path | None, mock_url: str, slot: str, trace: Trace, budget_s: float,
           api: str = "") -> Path:
    """`wf_path`'teki workflow'u Claude'a test ettirip düzelttirir; `wf_path` yoksa workflow'u Claude baştan yazar.
    Dönen yol: Claude'un bıraktığı workflow dosyası (olmayabilir)."""
    work = config.OUT / f"{slot}-refine"
    if wf_path is None and work.exists():  # baştan yazım: önceki çalıştırmanın dosyaları kullanılmaz
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / "workflow.json").unlink(missing_ok=True)
    (work / "last_saved.json").unlink(missing_ok=True)
    if wf_path is not None:
        shutil.copy2(wf_path, work / "workflow.json")
    os.environ["FBB_MOCK_URL"] = mock_url
    model = config.builder_model()
    trace.event("refine_start", f"chat test + fix, budget {budget_s / 60:.0f} min, model {model}")
    t0 = time.time()
    summary = asyncio.run(_agent(_prompt(cases, work, mock_url, slot, int(budget_s // 60), wf_path is not None, api), trace, model, budget_s))
    trace.model_call(model, "agentic build: " + ("review" if wf_path else "write") + " the workflow, chat-test it on the mock, fix it",
                     seconds=time.time() - t0, cost_usd=summary.get("cost"), ok=not summary.get("error"))
    trace.event("refine_done", json.dumps(summary, ensure_ascii=False)[:600])
    return work / "workflow.json"
