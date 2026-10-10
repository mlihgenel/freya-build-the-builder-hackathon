# 03: Mimari

## İlke
**Hibrit.** LLM brief'i anlar ve yapısal bir `PolicySpec` yazar. Deterministik Python bu spec'ten workflow'u kurar.

Kurallar prompt'ta değil, mümkün olduğunca kodda durur:
- tarih ve tutar hesapları code node'larında
- bankaya yapılan yazmalar engine'in api_request node'larında
- kararlar string bayraklarla route'larda

Telefon agent'ının modeli sabit (`experimental-5`) ve zayıf. Bu yüzden ona konuşmayı bırakıyoruz, kararları ve yazmaları vermiyoruz.

## Pipeline (`src/fbb/build.py`)

| Adım | Modül | Süre |
|---|---|---|
| 1. Brief dosyalarını sırayla oku (sonraki dosya öncekini değiştirir) | `ingest/sources.py` | < 1 sn |
| 2. Tool API → `ToolCatalog` (URL'ler, alanlar, enum'lar, cevap şeması) | `ingest/openapi.py` | < 1 sn |
| 3. Claude: brief → `PolicySpec` (JSON şeması ile structured output) | `ingest/extract.py`, `llm.py` | ~1 dk |
| 4. Claude: denetim, cümle cümle karşılaştırıp düzeltilmiş spec | `ingest/extract.py` | ~1–1.5 dk |
| 5. `cross_check`: spec'teki enum'lar openapi'de var mı | `spec.py` | anlık |
| 5b. `resolve_response_fields`: cevap alanı adlarını openapi'ye göre düzelt | `spec.py` | anlık |
| 6. Spec → workflow (~43 node, ~300 KB; snippet'ler yorumsuz, RT sadece kullanılan anahtarlarla gömülü) | `workflow/graph.py` | anlık |
| 7. Lint: null, tools/pre_actions yeri, passthrough `always`, end'e ulaşma, değişken üretimi, alanlar (eksik zorunlu alan ve açılışta 'recorded' = uyarı) | `workflow/lint.py` | anlık |
| 8. Freya `dryRun` → `save_workflow(slot)` (oluştur/güncelle + publish) | `kitapi.py` | ~5–20 sn |
| 9. Geri oku: platformun sessizce sildiği alan var mı | `build._diff_stored` | ~2 sn |
| 10. `export_workflow` → `exports/<slot>.workflow.json` | `kitapi.py` | ~2 sn |
| 11. (opsiyonel) `run_cases` self-test | `kitapi.run_cases` | 3–11 dk |

Ölçülen (10 Ekim, Brief A, LLM adımları): 2 dk 7 sn, $1.01 (çıkarım $0.23 + denetim $0.78).

## Modüller

| Modül | Görev |
|---|---|
| `config.py` | yollar, `env.sh`/`.env` yükleme, builder modeli, trace'ten silinecek gizli değerler |
| `trace.py` | `traces/<slot>-<zaman>.jsonl` + `.txt`. `model_call(model, purpose, seconds, cost)`, `event(...)`. Redaction |
| `llm.py` | `ask_json(system, prompt, PydanticModel, purpose, trace)`: claude-agent-sdk, araç yok, `output_format=json_schema`. Doğrulama hatasında 2 kez daha sorar, sonra gevşek moda düşer (`lenient_validate`) |
| `ingest/openapi.py` | `ToolCatalog.url/enum/summary_text` |
| `ingest/extract.py` + `prompts/` | çıkarım ve denetim prompt'ları (genel; brief içeriği yok) |
| `spec.py` | `PolicySpec` (pydantic, `extra=forbid`), `cross_check`, `to_runtime` (spec → `RT`) |
| `runtime/*.py` | Freya'da çalışan saf Python. `emit.build_snippet(entry, RT)` sadece gereken fonksiyonları AST ile toplar, `RT`'yi JSON olarak gömer, try/except ile sarar ve `{{` yasağını denetler |
| `workflow/nodes.py` | conversation/code/api_request/end_call kurucuları, `when_eq`, `tool_transition`, `always` |
| `workflow/tools.py` | `bank_call` (openapi'den api_call), `model_tool` (modelin çağırdığı code_exec) |
| `workflow/texts.py` | system prompt ve node görev metinleri |
| `workflow/graph.py` | graf (bkz. 05) ve `field_map` (openapi alan adı eşleme) |
| `workflow/lint.py` | statik kontroller |
| `kitapi.py` | `kit/freya.py` + `kit/tools/score.py` + `run_cases.py` sarmalayıcısı |
| `cli.py` | `build-agent`, `export-agent`, `fbb cases`, `fbb chat` |

## Zaman bütçesi (final)
- Brief başına build ≤ 5 dk (LLM ~2–3 dk + Freya ~30 sn).
- İki brief toplam ≤ 15 dk. Kalan süre yeniden çalıştırma ve teslim için.
- Self-test gizli brief'te yapılmaz (bilinen vaka yok, eşitlikte build süresi sayılıyor). Bunun yerine lint + dryRun + geri okuma + kısa chat smoke yapılır.

## Bilinen boşluklar
- **G-01 (kapandı, 10 Eki):** cevap alanları `spec.response_fields`'ta. LLM openapi'nin "returns:" satırlarından doldurur; `resolve_response_fields` alan openapi'de yoksa en yakın alanı seçer ve trace'e yazar; `cross_check` ürün alanlarını denetler. Yazma çağrılarında `ok` alanı yoksa zarfın `status`'u (`success`) kullanılır.
- **G-02 (kapandı, 10 Eki):** tarihli memo değişiklikleri `spec.overrides` (`effective_from`/`effective_until`); runtime `effective_rt` ile o günün değerlerini seçer.
- **G-03:** Consensus (2 çıkarım + karşılaştırma) henüz yok. Determinizm için düşünülecek.
- **G-04:** Sayı kelimelerinin okunması (`normalize.py`) sadece İngilizce. Kodun ürettiği cümleler ve gün/ay adları `spec.locale`'den gelir.
- Build çökmez: LLM çıktısı iki düzeltme denemesinden sonra da geçersizse `llm.lenient_validate` desteklenmeyen değerleri atar ve `unmapped`'e yazar; openapi'de beklenmeyen zorunlu alan lint uyarısıdır (`tool_constants` ya da openapi `default`/tek enum ile doldurulur).
