# 00: Dizin

Freya × YC "Build the Builder" (10–11 Ekim 2026) builder'ının dokümanları. Kod sıfırdan, hackathon başladıktan sonra yazıldı.

## Okuma sırası
1. `01_KURALLAR_VE_PUANLAMA.md`: neyi, neye göre yapıyoruz (R1–R12)
2. `03_MIMARI.md`: pipeline ve modüller
3. `05_GRAF_TASARIMI.md`: workflow grafı, değişken sözleşmesi, PUB vaka izleri
4. `04_POLICYSPEC.md`: spec şeması ve Brief A/B eşlemesi
5. `02_FREYA_PLATFORM_GERCEKLERI.md`: platformun kesin davranışları ve deney sonuçları
6. `06_TEST_VE_SELFTEST.md`: test katmanları
7. `07_RUNBOOK_FINAL.md`: saat planı ve final penceresi
8. `08_KARARLAR_VE_ACIK_SORULAR.md`: kararlar ve organizatöre sorular
9. `09_TESLIM.md`: teslim adımları
10. `BUGFIX_LOG.md`: gizli brief'ler açıldıktan sonraki değişiklikler

## Hızlı komutlar
```bash
make test lint                    # ağsız testler + ruff
make local-a                      # altın spec → workflow (LLM ve Freya yok)
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json            # tam build
uv run fbb cases <agent_id> --brief A --reps 3                                      # Freya simülasyonu
uv run fbb chat brief-a "Hello?" --case PUB-01                                      # tek tur sohbet
```

## Kod ↔ doküman
| Kod | Doküman |
|---|---|
| `src/fbb/ingest/` (sources, openapi, extract, prompts) | 03, 04 |
| `src/fbb/spec.py` | 04 |
| `src/fbb/runtime/` (dates, normalize, facts, validate, closing, flow, emit) | 05, 06 |
| `src/fbb/workflow/` (nodes, tools, texts, graph, lint) | 05, 02 |
| `src/fbb/build.py`, `cli.py`, `trace.py`, `kitapi.py` | 03, 09 |
| `tests/` | 06 |

## Durum (10 Ekim 2026, 17:00 TR)
- Yapıldı: iskelet, runtime + testler, spec + openapi, graf + lint, LLM çıkarımı (Brief A: 2 dk, ~$1, altın spec'e çok yakın), trace, build/export CLI. 47 test yeşil.
- Bekleyen: Freya key'leri. Ardından Faz 0 deneyleri (F-01…F-07), Brief A/B simülasyonları, varyant provası.
