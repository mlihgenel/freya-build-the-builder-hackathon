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
10. `10_TEST_REHBERI.md`: **ekip için** kurulum, test komutları, sonuç okuma, düzeltme döngüsü
11. `11_REVIEW.md`: review ve madde madde uygulama durumu
12. `12_RAPOR.md`: review düzeltmeleri ve ölçüm raporu (10 Ekim)
13. `13_FINAL_HAZIRLIK.md`: **finale hazırlık planı ve takibi** (kaldığımız yer: "📍 Şu an" satırı)
14. `BUGFIX_LOG.md`: gizli brief'ler açıldıktan sonraki değişiklikler

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

## Durum (10 Ekim 2026, ~20:35 TR)
- `11_REVIEW.md`'deki düzeltmeler uygulandı (madde madde durum: `11_REVIEW.md` §F). Özet:
  - close_call: kapanış node'larında + müşteri kapatırsa lifecycle yedeği; erken outcome yazımı; retries 2.
  - Read-back/onay kodda (`propose_results` → `readback`); geçersiz teklif tts ile söylenir.
  - Kimlik: soru başına sabit node, sonuç kodsuz route; parçalı cevap birleştirme; ret sayacı; 500'de "eşleşmiyor" denmez.
  - Openapi esnekliği: `response_fields`, `tool_constants`, soru başına gövde alanı / all_at_once, postcode/alnum; lint çökmez.
  - Spec genişletme: deadline/floor/tutar/callback kuralları, tarihli `overrides`, `customer_callback`, `recording.mode`, `locale`; LLM gevşek modu.
- `uv run pytest`: 83 test yeşil; ruff temiz. Workflow ≈300 KB, 43 node.
- Freya'ya kuruldu (`mert-a`, `mert-b`): dryRun + kayıt + geri okuma 0 fark. Chat smoke: açılış, parçalı DOB, hata yolu doğru.
- **Ölçüm (VPN ile):** A **9/10** pass³, B **3/3** pass³, en yavaş tur medyanı 1–2 sn. F-09 ✅. Mock bazı TR ağlarından erişilemiyor (VPN gerekli).
- Stiller (tek tekrar): in_words A 9/10, B 3/3; pieces A 9/10, B 2/3. asks_back/corrects/talkative son düzeltmelerden sonra ölçülmedi.
- Açık: PUB-06 ve PUB-12 ikna sayımı (model; kalıcı çözüm adayı: denemeleri koda taşımak), varyant provası (simülasyonla).
- Ham materyal provası (uydurma Brief C + varyant openapi, `tests/fixtures/variants/`): LLM çıkarımıyla uçtan uca build başarılı (lint 0). Bulunan tek eksik (floor = iki kuralın büyüğü) `floor_rule` `max:`/`min:` ile kapandı; 85 test yeşil.
- **11 Eki ~00:30: ikna teklifleri koda taşındı** (`next_offer` + `offer_step`, `propose_step`): ürün sırası, deneme sayısı ve teklif cümleleri kodda; model sadece müşterinin cevabını bildirir. Ölçüm (dev-a/dev-b, altın spec): **A 10/10 pass³ (iki kez), B 3/3 pass³**. Workflow ≈301/305 KB (önce 315/319). Stiller bu sürümle ölçülmedi.
- **11 Eki ~01:45, finale hazırlık Faz 1 ✅** (`13_FINAL_HAZIRLIK.md`): Claude'un çıkardığı spec'le (finaldeki zincir) A **10/10** ve B **3/3** pass³. Üç ayrı çıkarımda puan alanlarında fark yok (`fbb specdiff`). Build: A 87 sn / $0.63, A+B 100 sn / $0.91.
- Sonuç tablosu ve test komutları: `10_TEST_REHBERI.md` §9.
