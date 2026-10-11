#!/usr/bin/env python3
"""Final komutu: python3 builder/build.py {case_folder} {mock_url}

Vaka klasöründeki bütün belgeleri (Markdown, Word, PDF, Excel) okur, tool API'sini klasördeki openapi dosyasından ya da
servis sözleşmesinden alır, sunucu adresi olarak verilen mock'u kullanır, Freya'da workflow'u kurar ve export eder
(exports/final.workflow.json). Trace: traces/final-*.txt/.jsonl (stdout'a da yazılır).
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.path.insert(0, str(ROOT / "src"))
    import claude_agent_sdk  # noqa: F401
    import pydantic  # noqa: F401
except ImportError:  # sistem python'u: proje ortamında yeniden başlat
    uv = shutil.which("uv")
    if not uv or os.environ.get("FBB_REEXEC"):
        sys.exit("bağımlılıklar yok: önce `uv sync` çalıştırın")
    os.environ["FBB_REEXEC"] = "1"
    os.execv(uv, [uv, "run", "--project", str(ROOT), "python", str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("kullanım: python3 builder/build.py <case_folder> <mock_url> [slot]")
    case, mock = sys.argv[1], sys.argv[2]
    slot = sys.argv[3] if len(sys.argv) > 3 else "final"
    import json

    from fbb.build import BuildOptions, run_build

    # sadece geliştirme/test için: FBB_SPEC (hazır spec, LLM yok), FBB_NO_DEPLOY=1 (Freya'ya gönderme),
    # FBB_NO_REFINE=1 (chat testi + düzeltme aşamasını atla)
    res = run_build(BuildOptions(briefs=[case], tools="", slot=slot, base_url=mock,
                                 spec_file=os.environ.get("FBB_SPEC", ""),
                                 deploy=not os.environ.get("FBB_NO_DEPLOY"),
                                 refine=not os.environ.get("FBB_NO_REFINE")))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
