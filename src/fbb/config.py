"""Ortam ve yollar. Key'ler env.sh (export SATIRLARI) ya da .env'den okunur; hiçbir yere yazılmaz."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "kit"
OUT = ROOT / "out"
EXPORTS = ROOT / "exports"
TRACES = ROOT / "traces"
RESULTS = ROOT / "results"

BUILD_LIMIT_S = 30 * 60
SELFTEST_STOP_S = 20 * 60


def load_env() -> None:
    """env.sh / .env içindeki `export AD=değer` satırlarını os.environ'a yükler (zaten varsa dokunmaz)."""
    for name in ("env.sh", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$", line)
            if not m:
                continue
            val = m.group(2).split(" #", 1)[0].strip().strip('"').strip("'")
            os.environ.setdefault(m.group(1), val)


def builder_model() -> str:
    return os.environ.get("BUILDER_MODEL", "claude-opus-5-5")


def secrets() -> list[str]:
    """Trace'ten silinecek değerler."""
    out = []
    for k in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(k, "")
        if len(v) >= 8:
            out.append(v)
    return out
