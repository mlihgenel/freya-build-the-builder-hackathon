"""Brief dosyalarını okur. Birden fazla dosya verilirse sırası önemlidir: sonraki dosya öncekini değiştirir."""
from __future__ import annotations

from pathlib import Path


def read_sources(paths: list[str | Path]) -> str:
    parts = []
    for i, p in enumerate(paths, 1):
        path = Path(p)
        parts.append(f"===== DOCUMENT {i} of {len(paths)}: {path.name} =====\n{path.read_text().strip()}\n")
    if len(paths) > 1:
        parts.append("NOTE: later documents change or extend earlier ones. Where they conflict, the later document wins.")
    return "\n".join(parts)


def slot_for(paths: list[str | Path]) -> str:
    """Workflow slot adı: son brief dosyasının adı (B, A'yı kapsar)."""
    return Path(paths[-1]).stem
