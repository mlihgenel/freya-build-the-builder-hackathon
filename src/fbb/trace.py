"""Builder trace'i (teslimde istenir): başlangıç/bitiş, her model çağrısı (model + amaç), Freya ID'leri, self-test'ler.

İki dosya yazılır: `traces/<slot>-<zaman>.jsonl` (makine) ve aynı adla `.txt` (insan). Key'ler temizlenir.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fbb import config

PATTERNS = [re.compile(r"fak_[A-Za-z0-9_\-]{6,}"), re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
            re.compile(r"(?i)((?:authorization|x-team-key)[\"']?\s*[:=]\s*[\"']?)(?:Bearer\s+)?[^\"',\s}]+")]


def redact(text: str, extra: list[str] | None = None) -> str:
    for secret in (extra if extra is not None else config.secrets()):
        text = text.replace(secret, "[GİZLİ]")
    for p in PATTERNS:
        text = p.sub(lambda m: (m.group(1) if m.groups() else "") + "[GİZLİ]", text)
    return text


class Trace:
    def __init__(self, slot: str, directory: Path | None = None):
        d = directory or config.TRACES
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.jsonl = d / f"{slot}-{stamp}.jsonl"
        self.txt = d / f"{slot}-{stamp}.txt"
        self.t0 = time.time()
        self.model_calls = 0
        self.cost_usd = 0.0

    def elapsed(self) -> float:
        return round(time.time() - self.t0, 1)

    def event(self, kind: str, summary: str = "", **data) -> None:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "t": self.elapsed(), "event": kind, "summary": summary,
               **data}
        line = redact(json.dumps(rec, ensure_ascii=False, default=str))
        with self.jsonl.open("a") as f:
            f.write(line + "\n")
        with self.txt.open("a") as f:
            f.write(redact(f"[{rec['ts']} +{rec['t']:>6}s] {kind}: {summary}") + "\n")

    def model_call(self, model: str, purpose: str, *, seconds: float, cost_usd: float | None = None,
                   tokens: dict | None = None, ok: bool = True) -> None:
        self.model_calls += 1
        self.cost_usd += cost_usd or 0.0
        self.event("model_call", f"{model} — {purpose} ({seconds:.0f} s"
                   + (f", ${cost_usd:.3f}" if cost_usd else "") + (")" if ok else ", HATA)"),
                   model=model, purpose=purpose, seconds=round(seconds, 1), cost_usd=cost_usd, tokens=tokens, ok=ok)
