"""Builder pipeline: brief(ler) + tool API → spec → workflow → Freya (kaydet + yayınla) → export → trace.

Tek komut: `uv run build-agent <brief.md> [<brief2.md>] --tools <openapi.json>` (docs/03_MIMARI.md).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from fbb import config
from fbb.ingest.openapi import load_catalog
from fbb.ingest.sources import read_sources, slot_for
from fbb.spec import PolicySpec, cross_check, resolve_response_fields
from fbb.trace import Trace
from fbb.workflow.graph import build_workflow, workflow_hash
from fbb.workflow.lint import lint


@dataclass
class BuildOptions:
    briefs: list[str]
    tools: str
    slot: str = ""
    spec_file: str = ""          # verilirse LLM çıkarımı atlanır (geliştirme ve testler için)
    audit: bool = True
    deploy: bool = True          # False: sadece yerel çıktı (Freya'ya dokunmaz)
    selftest: str = "none"       # none | smoke | cases:A | cases:B
    reps: int = 1
    notes: list[str] = field(default_factory=list)


def run_build(opts: BuildOptions) -> dict:
    config.load_env()
    slot = opts.slot or slot_for(opts.briefs)
    trace = Trace(slot)
    trace.event("start", f"build başladı: slot={slot}", briefs=opts.briefs, tools=opts.tools,
                builder_model=config.builder_model(), spec_file=opts.spec_file or None)
    result: dict = {"slot": slot, "trace": str(trace.txt)}
    try:
        cat = load_catalog(opts.tools)
        trace.event("tools", f"{len(cat.tools)} tool, base {cat.base_url}", tools=sorted(cat.tools))
        if opts.spec_file:
            spec = PolicySpec.model_validate(json.loads(Path(opts.spec_file).read_text()))
            trace.event("spec", f"spec dosyadan okundu: {opts.spec_file}")
        else:
            from fbb.ingest.extract import extract_spec

            spec = extract_spec(read_sources(opts.briefs), cat, trace, audit=opts.audit)
        fixes = resolve_response_fields(spec, cat)
        if fixes:
            trace.event("response_fields", f"{len(fixes)} cevap alanı openapi'ye göre eşlendi", fixes=fixes)
        config.OUT.mkdir(parents=True, exist_ok=True)
        spec_path = config.OUT / f"{slot}.spec.json"
        spec_path.write_text(spec.model_dump_json(indent=1))
        errs = cross_check(spec, cat)
        trace.event("spec_ready", f"spec yazıldı ({len(errs)} uyumsuzluk)", path=str(spec_path), cross_check=errs,
                    unmapped=spec.unmapped)

        wf = build_workflow(spec, cat)
        wf_path = config.OUT / f"{slot}.workflow.json"
        wf_path.write_text(json.dumps(wf, indent=1, ensure_ascii=False))
        warnings: list[str] = []
        problems = lint(wf, cat, call_vars=spec.call_variables.all,
                        forbidden_pre_verify=spec.opening.forbidden_before_verification, warnings=warnings)
        trace.event("workflow", f"{len(wf['nodes'])} node, hash {workflow_hash(wf)}, lint {len(problems)} sorun, "
                    f"{len(warnings)} uyarı", path=str(wf_path), lint=problems, warnings=warnings,
                    bytes=len(json.dumps(wf)))
        result.update(spec=str(spec_path), workflow=str(wf_path), lint=problems, warnings=warnings)
        if problems:
            raise RuntimeError("lint hataları: " + "; ".join(problems[:5]))
        if not opts.deploy:
            trace.event("end", "deploy kapalı, yerel çıktı hazır")
            return result

        from fbb import kitapi

        kitapi.validate(f"{slot} dry-run", wf)
        trace.event("freya_validate", "dryRun geçti")
        ids = kitapi.save(slot, wf)
        trace.event("freya_saved", f"workflow {ids['workflow_id']} agent {ids['agent_id']}", **ids)
        result.update(ids)
        stored = kitapi.get(ids["workflow_id"])["workflow"]
        lost = _diff_stored(wf, stored)
        trace.event("freya_readback", f"platformda saklanan workflow kontrol edildi ({len(lost)} fark)", lost=lost)
        export_path = kitapi.export(ids["workflow_id"], config.EXPORTS / f"{slot}.workflow.json")
        trace.event("export", f"export yazıldı: {export_path}")
        result["export"] = str(export_path)

        if opts.selftest.startswith("cases:"):
            brief = opts.selftest.split(":", 1)[1]
            t0 = time.time()
            run = kitapi.run_cases(ids["agent_id"], brief=brief, reps=opts.reps,
                                   out=config.RESULTS / f"{slot}-selftest.json")
            trace.event("selftest", f"run_cases --brief {brief}: {run.get('passed')}/{run.get('total')} "
                        f"({time.time() - t0:.0f} s)", simulation_id=run.get("simulation_id"),
                        failed=[f["id"] for f in run.get("final", []) if not f.get("pass")])
            result["selftest"] = {"passed": run.get("passed"), "total": run.get("total")}
        trace.event("end", f"build bitti: {trace.elapsed():.0f} s, {trace.model_calls} model çağrısı, "
                    f"${trace.cost_usd:.2f}")
        return result
    except Exception as e:
        trace.event("error", f"build başarısız: {e}")
        raise


def _diff_stored(sent: dict, stored: dict) -> list[str]:
    """Platformun sessizce sildiği alanları bulur (kit: validation tanımadığı alanları atar)."""
    lost = []
    for name, node in sent.get("nodes", {}).items():
        s = stored.get("nodes", {}).get(name)
        if s is None:
            lost.append(f"node kayboldu: {name}")
            continue
        for key in ("tools", "pre_actions", "transitions", "response_mapping", "on_enter"):
            if node.get(key) and not s.get(key):
                lost.append(f"{name}.{key} kayboldu")
    if sent.get("tools") and not stored.get("tools"):
        lost.append("üst seviye tools (close_call lifecycle yedeği) kayboldu")
    for a, b in zip(sent.get("tools", []), stored.get("tools", []), strict=False):
        if a.get("pre_process_code") and not b.get("pre_process_code"):
            lost.append("close_call lifecycle yedeğinin pre-hook'u kayboldu")
    return lost
