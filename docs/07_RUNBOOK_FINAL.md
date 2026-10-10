# 07: Runbook

## Cumartesi → Pazar planı

| Faz | İş | Çıkış kriteri | Durum |
|---|---|---|---|
| F0a | iskelet, uv, kit kopyası | `make test` yeşil | ✅ |
| F1 | runtime + testler | tarih ve normalizasyon testleri yeşil | ✅ |
| F2 | spec + openapi + altın fixture'lar | şema testleri yeşil | ✅ |
| F3a | graf + lint + yerel akış testleri | lint temiz | ✅ |
| F5a | LLM çıkarımı (Claude SDK) | Brief A spec'i altın spec'e çok yakın | ✅ |
| F0b | Freya key'leri → deneyler F-01…F-11 | `02`'deki tablo dolu | 🟡 F-01,03–06,08 ✅; F-10 kısmen; F-09/F-11 mock erişimi bekliyor |
| F3b | Brief A simülasyonu | A tek çalışmada ≥ 9/10, iki kez | 🟡 eski graf 10/10 ×1; `--reps 3` 3/10 (kesinti + review hataları) |
| R1 | Review düzeltmeleri (`11_REVIEW.md` C.1–C.6) | testler yeşil, L1/L2 temiz | ✅ kod + test (10 Eki 20:35); L4 ölçümü bekliyor |
| F4 | Brief B | 13/13 bir kez, `--reps 3` ile ≥ 11/13 | ⏳ yeni graf ölçülmedi |
| F6 | varyant provası (C/D/E), G-01 cevap alanı eşlemesi | çökme yok, ≥ %80 | 🟡 G-01 ✅, varyant openapi birim testi ✅ (`test_variant_openapi_does_not_crash`); simülasyon provası yok |
| F7 | stiller + 3 tekrar | bilinmeyen sebeple 3/3 altında vaka yok | |
| F8 | teslim provası: temiz kopyadan 2 brief art arda | tek komut, brief başına ≤ 10 dk | |
| — | **Özellik dondurma: Pazar 18:00 TR** | | |

## Final penceresi (Pazar 20:00–23:00 TR)

1. **19:30** Hazırlık:
   - `git status` temiz olmalı.
   - `make test lint secrets-check freeze-check` yeşil olmalı.
   - `env.sh` yüklü olmalı.
   - Claude girişi `claude` CLI ile kontrol edilmeli.
   - Workspace'te çalışan bir simülasyon olmamalı.
2. **20:00** Brief'ler açılır. Dosyalar `final/<ad>/` altına indirilir; brief ve openapi'nin içine hiçbir şey yazılmaz.
3. **20:05** Önce temiz spesifikasyon olan brief:
   ```bash
   uv run build-agent final/<x>/brief.md --tools final/<x>/openapi.json --slot final-<x>
   ```
   Kontrol: trace'te `lint 0`, `cross_check` boş, `unmapped` mantıklı, export yazılmış.
4. **20:15** Ham materyal brief'i: bütün dosyalar sırayla verilir (mail, poliçe, memo, kod listesi; ilgili sırayla).
5. **20:30** Gözle kontrol:
   - `out/<slot>.spec.json`: tatiller, bantlar, kimlik soruları, outcome tablosu brief'le aynı mı?
   - Hata varsa sadece **genel** bir bug fix yapılır ve `BUGFIX_LOG.md`'ye yazılır. Brief'ten değer **yazılmaz**.
   - Builder yeniden çalıştırılır.
6. **21:00** Chat smoke:
   ```bash
   uv run fbb chat final-<x> "Hello?" --case PUB-01
   ```
   Açılışın ve ilk turun çalıştığı görülmeli.
7. **21:30** `exports/` + `traces/` → kullanıcı commit ve push yapar → commit hash → form gönderilir (bkz. 09).
8. **22:30** Son güvenli teslim anı.

## Acil durumlar
| Durum | Ne yapılır |
|---|---|
| Claude girişi ya da kotası sorun çıkarırsa | `ANTHROPIC_API_KEY` ile tekrar dene; `BUILDER_MODEL=claude-sonnet-5-5` |
| Lint hatası (beklenmeyen tablo ya da alan) | Hata genel bir bug ise düzelt ve kaydet. Spec alanı eksikse prompt'u genel olarak düzelt |
| Freya 5xx ya da `1010` | Tekrar dene. `User-Agent`'ı `freya.py` ayarlıyor |
| Platform workflow'un bir kısmını sildiyse | Trace'teki `freya_readback` farkına bak, `02`'yi güncelle |
