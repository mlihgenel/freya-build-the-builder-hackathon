"""Kitin Freya istemcisi (kit/freya.py) ve test araçları üzerinde ince bir katman. Kit dosyalarına dokunulmaz.

freya.py key'i import anında okuduğu için önce config.load_env() çağrılır.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from fbb import config

STATE_FILE = config.ROOT / ".freya-agents.json"


@lru_cache(maxsize=1)
def freya():
    config.load_env()
    if not os.environ.get("FREYA_API_KEY"):
        raise RuntimeError("FREYA_API_KEY yok: .env dosyasını doldurun (şablon: env.example)")
    sys.path.insert(0, str(config.KIT))
    sys.path.insert(0, str(config.KIT / "tools"))
    import freya as kit_freya  # noqa: E402

    return kit_freya


def validate(name: str, workflow: dict):
    return freya().validate_workflow(name, workflow)


def save(slot: str, workflow: dict) -> dict:
    """Aynı slot aynı workflow'u günceller ve yayınlar (kitin save_workflow'u)."""
    return freya().save_workflow(slot, workflow, state_file=str(STATE_FILE))


def get(workflow_id: str) -> dict:
    f = freya()
    return f.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=f.workspace_id())["workflow"]


def export(workflow_id: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    freya().export_workflow(workflow_id, str(path))
    return path


def chat(workflow_id: str, message: str, *, call_id: str | None = None, variables: dict | None = None) -> dict:
    body = {"workflowId": workflow_id, "message": message}
    if call_id:
        body["callId"] = call_id
    if variables:
        body["customerVariables"] = variables
    return freya().api("POST", "/api/v2/chat/message", body)


def chat_end(call_id: str):
    return freya().api("POST", "/api/v2/chat/end", {"callId": call_id})


def get_call(call_id: str) -> dict:
    return freya().get_call(call_id)


def practice_session(case_id: str) -> dict:
    """Pratik müşteri oturumu aç (kitin score.http'si, takım key'iyle). Dönen 'variables' çağrı değişkenleridir."""
    freya()
    import score  # kit/tools/score.py

    return score.http("/v1/practice/sessions", {"case": case_id})


def ledger(customer_id: str) -> dict:
    freya()
    import score

    return score.http("/v1/practice/ledger/" + customer_id)


def run_cases(agent_id: str, *, brief: str = "", only: str = "", reps: int = 1, style: str = "",
              out: Path | None = None, timeout_s: int = 1500) -> dict:
    """Kitin run_cases.py'sini çalıştırır; --out JSON'unu döner."""
    config.load_env()
    import time

    out = (out or (config.RESULTS / f"run-{agent_id[:8]}-{time.strftime('%m%d-%H%M%S')}.json")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(config.KIT / "tools" / "run_cases.py"), agent_id, "--out", str(out)]
    if brief:
        cmd += ["--brief", brief]
    if only:
        cmd += ["--only", only]
    if reps > 1:
        cmd += ["--reps", str(reps)]
    if style:
        cmd += ["--style", style]
    proc = subprocess.run(cmd, cwd=config.KIT, capture_output=True, text=True, timeout=timeout_s, env=os.environ.copy())
    result = json.loads(out.read_text()) if out.exists() else {}
    result["stdout"] = proc.stdout[-6000:] + f"\nsonuç dosyası: {out}\n" + (proc.stderr[-2000:] if proc.returncode else "")
    result["returncode"] = proc.returncode
    return result


def agent_for(slot_or_id: str) -> str:
    """Slot adı verilirse (.freya-agents.json) agent ID'sine çevirir; ID verilirse aynen döner."""
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        if slot_or_id in state:
            return state[slot_or_id]["agent_id"]
    return slot_or_id
