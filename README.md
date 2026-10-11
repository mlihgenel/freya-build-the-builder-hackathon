# fbb: Freya Bank builder

Freya × YC "Build the Builder" hackathon'u için yazdığımız builder. Bir bankanın brief'ini (Markdown) ve tool API'sini (`openapi.json`) okur, Freya'da bir telefon agent'ı kurar ve yayınlar. Agent, gecikmiş ödemeler için müşteriyi arar.

```
brief.md (+ brief2.md) + openapi.json
      │  1. Claude: brief → PolicySpec (JSON); ikinci geçiş denetler
      │  2. Python: PolicySpec → Freya workflow (kurallar kodda: code node, hook, route)
      │  3. Freya: dryRun → kaydet + yayınla → geri oku → export
      ▼
exports/<slot>.workflow.json  +  traces/<slot>-<zaman>.txt/.jsonl
```

## Kurulum

```bash
uv sync                      # Python 3.12, claude-agent-sdk, pydantic
# .env dosyasında FREYA_API_KEY ve FREYA_BANK_TEAM_KEY'i doldur (.env git'e girmez; şablon: env.example)
```

Builder, Claude'u `claude-agent-sdk` üzerinden kullanır. Bunun için makinede Claude girişi ya da `ANTHROPIC_API_KEY` gerekir. Model `BUILDER_MODEL` ile seçilir (varsayılan `claude-opus-5-5`).

## Tek komut

```bash
uv run build-agent <brief.md> [<brief2.md> ...] --tools <openapi.json>
# örnek:
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json
uv run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools kit/tools/openapi.json
```

Çıktılar:
- `out/<slot>.spec.json`: brief'ten çıkarılan kurallar
- `out/<slot>.workflow.json`: Freya'ya gönderilen workflow
- `exports/<slot>.workflow.json`: platformdan export edilen dosya (**teslim edilen dosya**)
- `traces/<slot>-<zaman>.txt` ve `.jsonl`: build trace'i (**teslim edilir**). Başlangıç/bitiş zamanı, her model çağrısının modeli ve amacı, Freya ID'leri ve self-test'ler burada. Key'ler temizlenmiştir.

Seçenekler:
- `--slot <ad>`: workflow slot adı (varsayılan: son brief'in adı). Aynı slot aynı workflow'u günceller (200 workflow sınırı).
- `--no-deploy`: Freya'ya hiçbir şey göndermez, sadece yerel çıktı üretir.
- `--no-audit`: spec'i denetleyen ikinci LLM geçişini atlar.
- `--selftest cases:A` / `cases:B`: kitin pratik vakalarıyla test eder; `--reps N` tekrar sayısı.
- `--spec <dosya>`: LLM adımını atlar, hazır spec'ten kurar. Geliştirmede ve Freya kesintisinde yeniden deploy için (`docs/07_RUNBOOK_FINAL.md`).

## Test

```bash
make test lint secrets-check freeze-check            # birim testleri, ruff, key taraması, src/'de brief değeri yok mu
uv run fbb cases <slot|agent_id> --brief A --reps 3  # kitin run_cases.py'si (Freya simülasyonu)
#   --only PUB-04,PUB-07   --style pieces   --rerun-if-slow 1 (model yavaşken koşuyu at, tekrarla)
uv run fbb chat <slot> "Hello?" --case PUB-01        # yayınlanmış workflow ile tek tur sohbet
```

Diğer `fbb` komutları: `call` (bir çağrının zaman çizelgesi), `report` (run_cases özeti ve başarısız çağrılar), `specdiff` (iki spec'in PUAN/METİN/BİLGİ farkları), `days` (başka `now` günlerinde koşu), `scenarios` (kendi senaryolarımız). Ayrıntı: `uv run fbb <komut> --help`.

Bu klasörün dışında aktif bir venv varsa komutların başına `env -u VIRTUAL_ENV` ekleyin (Makefile bunu kendisi yapar).

## Dizinler

| Yol | İçerik |
|---|---|
| `kit/` | organizatörün kiti v3, **değiştirilmeden** |
| `src/fbb/ingest/` | brief ve openapi okuma, LLM ile spec çıkarımı |
| `src/fbb/spec.py` | PolicySpec şeması |
| `src/fbb/runtime/` | Freya code node'larında çalışan Python (tarih, normalizasyon, doğrulama, kapanış) |
| `src/fbb/workflow/` | workflow grafı, tool'lar, metinler, lint |
| `src/fbb/build.py` | pipeline |
| `docs/` | tasarım, kurallar, runbook (Türkçe) |

Kurallar ve tasarım için `docs/00_INDEX.md`'den başlayın. **Test etmek için: `docs/10_TEST_REHBERI.md`.** Final penceresi: `docs/07_RUNBOOK_FINAL.md`; teslim: `docs/09_TESLIM.md`; brief açıldıktan sonraki değişiklikler: `docs/BUGFIX_LOG.md`.
