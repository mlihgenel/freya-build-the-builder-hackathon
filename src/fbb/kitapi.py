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
SIM_WATCHDOG_S = 600  # bir simülasyon en çok bu kadar 'running' kalabilir (çağrı sınırı 420 sn)


@lru_cache(maxsize=1)
def freya():
    config.load_env()
    if not os.environ.get("FREYA_API_KEY"):
        raise RuntimeError("FREYA_API_KEY yok: .env dosyasını doldurun (şablon: env.example)")
    sys.path.insert(0, str(config.KIT))
    sys.path.insert(0, str(config.KIT / "tools"))
    import freya as kit_freya  # noqa: E402

    _retry_gets(kit_freya)
    return kit_freya


def _retry_gets(mod) -> None:
    """Kitin api'sine GET tekrarı: 5xx ve ağ hataları 10, 20, sonra 30'ar sn arayla 11 kez daha denenir (~5 dk; POST
    denenmez: simülasyon iki kez başlamasın). Durum sorgusundaki tek bir 504 bütün koşuyu düşürüyordu; platform
    kesintileri 2 dk'yı aştı (11 Eki)."""
    if getattr(mod.api, "_fbb_retry", False):
        return
    import re
    import time
    import urllib.error

    orig = mod.api

    def api(method, path, body=None, **params):
        for attempt in range(12):
            try:
                return orig(method, path, body, **params)
            except (RuntimeError, urllib.error.URLError, TimeoutError) as e:
                transient = isinstance(e, (urllib.error.URLError, TimeoutError)) or any(
                    f"-> {code}" in str(e) for code in (500, 502, 503, 504))
                if method != "GET" or not transient or attempt == 11:
                    raise
                wait = min(10 * (attempt + 1), 30)
                print(f"[fbb] {method} {path}: {str(e)[:60]} → {wait} sn sonra tekrar", flush=True)
                time.sleep(wait)

    started: dict[str, float] = {}

    def watched(method, path, body=None, **params):
        """Bekçi: simülasyon 10 dk'dan uzun 'running' kalırsa iptal edilir (11 Eki: çağrısı hiç başlamayan bir
        simülasyon sonsuza kadar 'running' kaldı; kitin döngüsünde zaman aşımı yok ve workspace tek simülasyon
        çalıştırabildiği için sonraki koşular da bekliyordu). Belgelenmemiş uç nokta: POST .../cancel."""
        out = api(method, path, body, **params)
        m = re.fullmatch(r"/api/v2/simulations/([0-9a-f-]{36})", path)
        if method == "GET" and m and isinstance(out, dict):
            s = out.get("simulation") or out
            if s.get("status") in ("completed", "failed", "paused"):
                started.pop(m.group(1), None)
            elif time.time() - started.setdefault(m.group(1), time.time()) > SIM_WATCHDOG_S:
                print(f"[fbb] simülasyon {m.group(1)[:8]} {SIM_WATCHDOG_S} sn'dir bitmedi → iptal", flush=True)
                try:
                    orig("POST", f"/api/v2/simulations/{m.group(1)}/cancel", {})
                except Exception as e:  # iptal olmazsa kitin döngüsü beklemeye devam eder
                    print(f"[fbb] iptal edilemedi: {str(e)[:80]}", flush=True)
                started.pop(m.group(1), None)
        return out

    api._fbb_retry = True
    watched._fbb_retry = True
    mod.api = watched


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
              out: Path | None = None, timeout_s: int = 3600, rerun_if_slow: int = 0) -> dict:
    """Kitin run_cases.py'sini çalıştırır; --out JSON'unu döner."""
    config.load_env()
    import time

    out = (out or (config.RESULTS / f"run-{agent_id[:8]}-{time.strftime('%m%d-%H%M%S')}.json")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "fbb.kit_runner", agent_id, "--out", str(out)]
    if brief:
        cmd += ["--brief", brief]
    if only:
        cmd += ["--only", only]
    if reps > 1:
        cmd += ["--reps", str(reps)]
    if style:
        cmd += ["--style", style]
    if rerun_if_slow:  # kitin seçeneği: medyan en yavaş tur 10 sn'yi aşan koşu atılır, 5 dk sonra tekrarlanır
        cmd += ["--rerun-if-slow", str(rerun_if_slow)]
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
