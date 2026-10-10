"""Brief → PolicySpec (Claude). İki geçiş: çıkarım ve denetim. Sonuç pydantic + openapi çapraz kontrolünden geçer."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from fbb.ingest.openapi import ToolCatalog
from fbb.llm import ask_json
from fbb.spec import PolicySpec, cross_check
from fbb.trace import Trace

PROMPTS = Path(__file__).parent / "prompts"


class Audit(BaseModel):
    issues: list[str] = Field(default_factory=list)
    spec: PolicySpec


def _user(brief_text: str, cat: ToolCatalog, extra: str = "") -> str:
    return (f"TOOL API (base URL {cat.base_url}):\n{cat.summary_text()}\n"
            + (f"Tool API notes: {cat.info}\n" if cat.info else "")
            + f"\nBRIEF:\n{brief_text}\n" + extra)


def extract_spec(brief_text: str, cat: ToolCatalog, trace: Trace, *, audit: bool = True) -> PolicySpec:
    system = (PROMPTS / "extract.md").read_text()
    spec = ask_json(system, _user(brief_text, cat, "\nReturn the PolicySpec JSON."), PolicySpec,
                    "brief → PolicySpec çıkarımı", trace)
    errs = cross_check(spec, cat)
    if audit or errs:
        extra = "\nSPEC TO CHECK:\n" + spec.model_dump_json(indent=1)
        if errs:
            extra += "\nKNOWN PROBLEMS (fix them):\n- " + "\n- ".join(errs)
        result = ask_json((PROMPTS / "audit.md").read_text(), _user(brief_text, cat, extra), Audit,
                          "spec denetimi (brief ile karşılaştırma)", trace)
        trace.event("audit", f"{len(result.issues)} düzeltme", issues=result.issues)
        spec = result.spec
    errs = cross_check(spec, cat)
    if errs:
        trace.event("cross_check", "openapi uyumsuzlukları kaldı", errors=errs)
    return spec
