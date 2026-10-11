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
from fbb.spec import PolicySpec, cross_check, resolve_request_fields, resolve_response_fields
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
    base_url: str = ""           # verilirse tool API'sinin sunucusu (final: kendi mock'umuz)
    refine: bool = True          # genel yol: kayıttan sonra chat testi + düzeltme aşaması (fbb.refine)
    notes: list[str] = field(default_factory=list)


def run_build(opts: BuildOptions) -> dict:
    config.load_env()
    slot = opts.slot or slot_for(opts.briefs)
    trace = Trace(slot)
    trace.event("start", f"build başladı: slot={slot}", briefs=opts.briefs, tools=opts.tools,
                builder_model=config.builder_model(), spec_file=opts.spec_file or None)
    result: dict = {"slot": slot, "trace": str(trace.txt)}
    try:
        tools_path = opts.tools
        if not tools_path:  # final formatı: klasörde openapi yoksa API vaka belgelerinden çıkarılır
            from fbb.generic import openapi_for_case
            from fbb.ingest.sources import find_openapi

            found = find_openapi(opts.briefs)
            if found:
                tools_path = str(found)
                trace.event("tools_file", f"tool API dosyası klasörde bulundu: {found}")
            else:
                config.OUT.mkdir(parents=True, exist_ok=True)
                tools_path = str(openapi_for_case(read_sources(opts.briefs), config.OUT / f"{slot}.openapi.json", trace))
        cat = load_catalog(tools_path)
        if opts.base_url:
            cat.base_url = with_base(opts.base_url, cat.base_url)
        trace.event("tools", f"{len(cat.tools)} tool, base {cat.base_url}", tools=sorted(cat.tools))
        from fbb.generic import is_collection_case

        if not opts.spec_file and not is_collection_case(list(cat.tools)):
            trace.event("mode", "vaka tahsilat formatında değil (yedi tahsilat tool'u yok): genel yol, workflow'u "
                        "Claude yazar")
            return _run_generic(opts, slot, trace, cat, tools_path, result)
        if opts.spec_file:
            spec = PolicySpec.model_validate(json.loads(Path(opts.spec_file).read_text()))
            trace.event("spec", f"spec dosyadan okundu: {opts.spec_file}")
        else:
            from fbb.ingest.extract import extract_spec

            spec = extract_spec(read_sources(opts.briefs), cat, trace, audit=opts.audit)
        fixes = resolve_response_fields(spec, cat)
        if fixes:
            trace.event("response_fields", f"{len(fixes)} cevap alanı openapi'ye göre eşlendi", fixes=fixes)
        req = resolve_request_fields(spec, cat)
        if req:
            trace.event("request_fields", f"{len(req)} istek alanı openapi'ye göre eşlendi", fixes=req)
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


def _run_generic(opts: BuildOptions, slot: str, trace: Trace, cat, tools_path: str, result: dict) -> dict:
    """Genel yol (fbb.generic): Claude workflow'u yazar; lint ve Freya dryRun hataları en fazla iki kez geri verilir."""
    from fbb.generic import write_workflow

    docs = read_sources(opts.briefs)
    api_text = Path(tools_path).read_text()
    problems: list[str] = []
    previous = ""
    wf: dict = {}
    warnings: list[str] = []
    for attempt in range(3):
        out = write_workflow(docs, api_text, cat.base_url, trace, problems or None, previous)
        try:
            wf = json.loads(out.workflow_json)
        except ValueError as e:
            problems, previous = [f"workflow_json is not valid JSON: {e}"], out.workflow_json[:300000]
            continue
        warnings = []
        problems = lint(wf, cat, call_vars=out.call_variables, forbidden_pre_verify=[], warnings=warnings,
                        check_tools=False)
        if not problems and opts.deploy:
            from fbb import kitapi

            try:
                kitapi.validate(f"{slot} dry-run", wf)
            except Exception as e:  # dryRun hatası düzeltme turuna gider
                problems = [f"Freya dry run rejected the workflow: {str(e)[:3000]}"]
        trace.event("generic_workflow", f"deneme {attempt + 1}: {len(wf.get('nodes', {}))} node, "
                    f"{len(problems)} sorun, {len(warnings)} uyarı", problems=problems, warnings=warnings,
                    notes=out.notes, call_variables=out.call_variables)
        if not problems:
            break
        previous = json.dumps(wf, ensure_ascii=False)
    config.OUT.mkdir(parents=True, exist_ok=True)
    wf_path = config.OUT / f"{slot}.workflow.json"
    wf_path.write_text(json.dumps(wf, indent=1, ensure_ascii=False))
    n_tools = sum(len(n.get("tools", [])) + len(n.get("pre_actions", [])) for n in wf.get("nodes", {}).values())
    trace.event("workflow", f"{len(wf.get('nodes', {}))} node, {n_tools} tool, hash {workflow_hash(wf)}, "
                f"lint {len(problems)} sorun", path=str(wf_path), lint=problems, bytes=len(json.dumps(wf)))
    result.update(workflow=str(wf_path), lint=problems, warnings=warnings, openapi=tools_path)
    if problems:
        raise RuntimeError("workflow düzeltilemedi: " + "; ".join(problems[:5]))
    if not opts.deploy:
        trace.event("end", "deploy kapalı, yerel çıktı hazır")
        return result
    from fbb import kitapi

    ids = kitapi.save(slot, wf)
    trace.event("freya_saved", f"workflow {ids['workflow_id']} agent {ids['agent_id']}", **ids)
    result.update(ids)
    budget = REFINE_UNTIL_S - trace.elapsed()
    if opts.base_url and opts.refine and budget > 180:
        wf = _refined(opts, slot, trace, wf_path, wf, budget)
    stored = kitapi.get(ids["workflow_id"])["workflow"]
    lost = _diff_stored(wf, stored)
    trace.event("freya_readback", f"platformda saklanan workflow kontrol edildi ({len(lost)} fark)", lost=lost)
    export_path = kitapi.export(ids["workflow_id"], config.EXPORTS / f"{slot}.workflow.json")
    trace.event("export", f"export yazıldı: {export_path}")
    result["export"] = str(export_path)
    trace.event("end", f"build bitti: {trace.elapsed():.0f} s, {trace.model_calls} model çağrısı, ${trace.cost_usd:.2f}")
    return result


REFINE_UNTIL_S = 25 * 60  # brief başına 30 dk sınırı: refine en geç build'in 25. dakikasında biter


def _refined(opts: BuildOptions, slot: str, trace: Trace, wf_path: Path, wf: dict, budget: float) -> dict:
    """Refine aşaması (fbb.refine): Claude chat ile test edip düzeltir. Sonuç yerel kontrol + dryRun'dan geçerse
    kaydedilir ve `wf_path`'e yazılır; geçmezse ilk sürüm kalır (son başarılı kayıt geri yüklenir)."""
    from fbb import kitapi
    from fbb.agent_tools import local_check
    from fbb.refine import refine

    try:
        new_path = refine(opts.briefs, wf_path, opts.base_url, slot, trace, budget)
        new = json.loads(new_path.read_text())
        problems = local_check(new)
        if not problems:
            kitapi.validate(f"{slot} dry-run", new)
    except Exception as e:  # refine hiçbir durumda build'i düşürmez
        problems = [f"{type(e).__name__}: {str(e)[:300]}"]
    if problems:
        trace.event("refine_rejected", f"{len(problems)} sorun: ilk sürüm kalıyor", problems=problems)
        kitapi.save(slot, wf)
        return wf
    kitapi.save(slot, new)
    wf_path.write_text(json.dumps(new, indent=1, ensure_ascii=False))
    trace.event("refine_saved", f"{len(new.get('nodes', {}))} node, hash {workflow_hash(new)}", path=str(wf_path))
    return new


def with_base(mock_url: str, server_url: str) -> str:
    """Verilen mock adresi yolsuzsa sözleşmedeki sunucunun yolunu (ör. /v1) korur."""
    from urllib.parse import urlparse

    mock = mock_url.rstrip("/")
    if urlparse(mock).path in ("", "/"):
        return mock + urlparse(server_url or "").path.rstrip("/")
    return mock


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
