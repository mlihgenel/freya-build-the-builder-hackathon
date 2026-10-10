# 06: Test ve self-test

## Katmanlar

| Katman | Ne | Komut | Maliyet |
|---|---|---|---|
| L0 birim | runtime (tarih, normalizasyon, doğrulama, kapanış), spec/openapi, graf + lint, yerel akış simülasyonları, brief-sızıntı testi | `make test` | 0 |
| L1 yerel build | altın spec ya da LLM spec → workflow → lint | `make local-a` / `build-agent --no-deploy` | 0 / ~$1 (LLM) |
| L2 platform | dryRun + kaydet + geri oku + export | `build-agent` | Freya |
| L3 chat smoke | tek tek turlar (`/chat/message`) | `fbb chat <slot> "Hello?" --case PUB-01` | düşük |
| L4 simülasyon | kitin run_cases'i, pratik müşteriler + Gemini hakem | `fbb cases <agent_id> --brief A [--reps 3] [--style …]` | 3–11 dk / tur |
| L5 varyant provası | PUB id'leriyle kendi brief'lerimiz, `now` ve persona değişiklikleri | (yapılacak: `fbb variant-run`) | simülasyon |

## L0 ayrıntıları (`tests/`)

| Dosya | Kapsam |
|---|---|
| `test_runtime.py` | Brief A deadline'ları (23 Eki late, 2 Kas early), Cuma kuralları, PUB-07 tatil; DOB'nin kelimeyle söylenmesi; rakamlar ("double four" dahil) ve tutarlar; parçalı cevapların birleştirilmesi; gün/ay ipucundan sonra sadece ay; postcode/alnum; ürün gerçekleri; öneri doğrulama ve otomatik düzeltme (deadline'a çekme, iş gününe kaydırma, read-back cümlesi); floor/tutar/deadline kuralları; tarihli override'lar; hafta sonu callback; kapanış tablosu; 120 günlük diferansiyel test |
| `test_spec.py` | 7 tool, enum'lar; fixture'lar şemadan ve cross_check'ten geçiyor; çakışan bantlar reddediliyor; spec→RT ile elle yazılmış RT aynı |
| `test_graph.py` | lint temiz ve boyut (A ve A+B); hash deterministik; system prompt amaç kelimesi içermiyor; route simülasyonu (`_route`): kodsuz kimlik mutlu yolu, yanlış/ipucu/500, ret açıklaması bir kez; read-back → kayıt + tekrar deneme; read-back reddi; geçersiz teklifin tts ile söylenmesi; PUB-12 notlar; sadece durumlar; per_product modu; statik transfer ve kapanışlar; lifecycle yedeği pre-hook'u; fallback guard'ları; müşteri callback'i; **varyant openapi** (alan adları değişmiş, `ok` yok, fazladan zorunlu alan) çökmeden kurulur; soru başına gövde alanı / all_at_once; tırnaklı model argümanı |
| `test_no_hardcoded_brief.py` | `src/` altında A/B değeri yok |

## L4 ölçütü
- Ana ölçüt **pass^3**: `--reps 3`, bir vaka ancak 3/3 ise sayılır.
- Her stil ayrı denenir: `pieces`, `corrects`, `talkative`, `asks_back`, `in_words`.
- Başarısız her vakada `results/*.json` içindeki `call_id` → `kitapi.get_call(call_id)["messages"]`. Özellikle `route_evaluated`, `function_call_*`, `variable_table` ve `error` olaylarına bakılır.
- Bir mekanizma ancak hata **tekrar ederse** değiştirilir. Her değişiklikten sonra komşu vakalar da yeniden çalıştırılır.

## L5 varyant provası (plan)
- Mock politikayı uygulamıyor. Bu yüzden 13 PUB id'si (kimlik, ürün ve hata verileriyle) farklı kurallara sahip kendi brief'lerimizle yeniden kullanılabilir.
- `variants/` altına yazılacaklar:
  - C: temiz varyant (farklı deadline'lar, tatiller, callback penceresi)
  - D: ham mail + poliçe + memo + kod listesi
  - E: farklı outcome ya da reason adları
- `now` değişikliği: Cuma, tatilden önceki gün, 19:30.
- Beklenen ledger **elle** hesaplanır, builder kodundan türetilmez.
- Kitin `run_cases` mantığı (`create_personas` + `run_simulation` + `score_ledger`) kendi vaka dosyamızla çalıştırılır.
