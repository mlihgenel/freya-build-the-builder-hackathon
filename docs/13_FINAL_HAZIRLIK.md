# 13: Finale hazırlık (test ve düzeltme planı, takip)

> Bu dosya finale kadar yapılacak testlerin ve düzeltmelerin takibidir.
> - Biten madde `[x]` olur ve yanına kısa sonuç ya da commit yazılır.
> - Yarım kalan madde `[~]` ile işaretlenir ve ne kaldığı yazılır.
> - **"📍 Şu an"** satırı her adımda güncellenir.

**📍 Şu an:** Faz 1 ✅ tamamlandı (11 Eki ~01:45). Sıradaki: Faz 2.1 (stiller: `pieces`)

**Son durum (11 Eki ~01:00):**
- `e2e58b2`: altın spec ile A 10/10 ve B 3/3 pass³.
- 89 test yeşil, workflow ≈301/305 KB.

## Context
Bilinen 13 pratik vakada builder temiz. Ama bu ölçümler finalin dört koşulunu kapsamıyor:
1. Hepsi **elle yazılmış altın spec** ile yapıldı; finalde spec'i Claude çıkaracak.
2. Hepsi **tek gün** (`now = 2026-10-14`, çarşamba); final birden çok takvim gününde.
3. **Konuşma stilleri** son sürümle ölçülmedi.
4. **Gizli brief tipi senaryolar** (`per_product` kayıt, müşteri callback'i, farklı kimlik ve outcome tablosu) konuşmada hiç denenmedi.

Amaç: finale en yakın testleri koşmak, sorunları **genel** olarak düzeltmek, her düzeltmeyi `--reps 3` ile doğrulamak.

**Kararlar:**
- Bütün iş bizde.
- Düzeltmeler genel olacak ve ölçümle doğrulanacak.
- Paz 18:00 TR'den sonra sadece bug fix.

**Kurallar:**
- `kit/` değişmez.
- `src/`'ye brief değeri girmez.
- Simülasyonlar tek tek koşulur.
- Slotlar `dev-a`, `dev-b`, `dev-a-llm`, `dev-b-llm`.
- Transcript okunmadan prompt değişmez.
- Her faz sonunda `docs/00`, `docs/07` ve `docs/10` §9 güncellenir.

---

## Faz 0: Takip dosyası
- [x] Bu planı `docs/13_FINAL_HAZIRLIK.md` olarak yaz, `docs/00` okuma listesine ekle (11 Eki ~01:10)

## Faz 1: Finalin birebir provası (Claude spec'i) ⭐ en kritik — ✅
- [x] 1.1 `fbb specdiff <spec> <altın>` aracı (`src/fbb/specdiff.py` + `cli.py`). Puanı etkileyen farkları ayrı listeler: bant, tatil, deneme planı, floor, outcome/reason, `floor_note`, kimlik, callback. Cümle farkları "bilgi" düzeyinde. Birim testiyle → ✅ `src/fbb/specdiff.py`, `tests/test_specdiff.py` (4 test); çıkış kodu PUAN farkı varsa 1
- [x] 1.2 Tam build + deploy: `dev-a-llm` (A) ve `dev-b-llm` (A+B); süre ve maliyet not edilir → A 87 sn / $0.63, A+B 100 sn / $0.91 (Opus); lint 0, dryRun ve geri okuma 0 fark, 45 node
- [x] 1.3 `specdiff` ile altın spec'lere karşı karşılaştırma; farklar sınıflandırılır →
  - A: PUAN farkı yok.
  - B: tek PUAN farkı `hangup_unverified` (Claude `not_reached/unclear`, altın `not_verified/declined`). Brief bunu tanımlamıyor; sadece kimlik sırasında müşteri kapatırsa etkili, not edildi.
  - METİN: `floor_note` ifadesi ("The rest of the amount stays overdue."), brief birebir istemiyor.
  - `service_error` durum farkı gürültüydü, `specdiff`'ten ayıklandı.
- [x] 1.4 `fbb cases dev-a-llm --brief A --reps 3` → 1. koşu 9/10 (PUB-05 2/3: model `propose_results`'tan önce teselli cümlesini tekrarladı) → düzeltmeden sonra **10/10 pass³**
- [x] 1.5 `fbb cases dev-b-llm --brief B --reps 3` → **3/3 pass³**, düzeltmeden önce de sonra da
- [x] 1.6 Tekrar üretilebilirlik: A çıkarımı 2 kez daha (`--no-deploy`) + `specdiff` → 3 çıkarım (dev-a-llm, rep-a2, rep-a3) birbirine ve altın spec'e karşı **0 PUAN farkı**; yalnız `floor_note` ve `change_after_record_sentence` ifadesi değişiyor
- [x] 1.7 Bulunan sorunların genel düzeltmesi (`extract.md`, `audit.md`, `ingest/extract.py`) + yeniden ölçüm →
  - Spec tarafında düzeltme gerekmedi.
  - Tek sorun model dolgusuydu: `texts.py` negotiate görevine "propose_results'tan önce konuşma, bir cümleyi iki kez söyleme" kuralı eklendi.
  - A 10/10, B 3/3 ile doğrulandı.

**Çıkış:** LLM spec'iyle A ≥ 9/10 ve B 3/3 pass³; 3 çıkarımda puan alanlarında fark yok.

## Faz 2: Konuşma stilleri (son sürüm)
- [ ] 2.1 `pieces`: A (dev-a) ×1, B (dev-b) ×1
- [ ] 2.2 `in_words`: A ×1, B ×1
- [ ] 2.3 `asks_back`: A ×1, B ×1
- [ ] 2.4 `corrects`: A ×1, B ×1
- [ ] 2.5 `talkative`: A ×1, B ×1
- [ ] 2.6 Düşen her vakanın transcript analizi ve sınıflandırması (`docs/10` §6)
- [ ] 2.7 Düzeltmeler: önce `--only X --style Y --reps 3`, sonra bütün brief `--reps 3`

**Çıkış:** her stilde A ≥ 9/10 ve B ≥ 2/3; bizden kaynaklı ve tekrarlayan hata yok.
**Beklenen sorun alanları:**
- parça parça söylenen tutarın `agreed_amount`'a girmesi;
- `asks_back`'te modelin kendisinin teklif yapması;
- `talkative`'deki "30'unda düğün" cümlesinin `agreed` sanılması;
- tool çağrısından önce tek başına söylenen "I" parçası.

## Faz 3: Kod yolları (gizli brief tipi senaryolar, birim/graf testi)
- [ ] 3.1 `per_product` kayıt + `next_offer`: `agreed` → anında read-back → kayıt → sıradaki ürünün teklifi. Bugün test edilmedi, büyük ihtimalle eksik; gerekirse `flow.next_offer` düzeltilir
- [ ] 3.2 Müşteri callback'i (`customer_callback`) + `next_offer`
- [ ] 3.3 Bir üründe dispute/paid, diğerinde ret: `propose_results` ↔ `offers_json` uyumu
- [ ] 3.4 Teklif sırasında transfer (B kural 10): kaydedilmemiş anlaşma kaydedilmez, not yazılmaz
- [ ] 3.5 "No speakable content" denetimi: her model tool'u bir geçişle bitiyor mu (test)
- [ ] 3.6 Kod servisi kesintisinde `offer_step` ve `propose_step` → `fallback_close` (test)

## Faz 4: Farklı takvim günleri
- [ ] 4.1 Runtime birim testleri: Cuma 2026-10-16, Cuma 2026-10-23 (26 Ekim tatil öncesi) ve Çarşamba 2026-12-23 (yıl sonu tatilleri) için `prep_account` ve `day_table` beklentileri
- [ ] 4.2 `tests/fixtures/days.json`: PUB-01, 02, 06, 10, 11, 12 (göreli tarih) ve 03, 05, 08, 09 için gün başına **elle hesaplanmış** beklenti ve checks; her satırda dayandığı kural yazılı
- [ ] 4.3 `fbb days <slot> --brief A --now …` runner (`src/fbb/days.py`). Kit fonksiyonlarını import eder: `freya.run_simulation`, `create_personas`, `score.http`, `score_ledger`, `run_cases.persona_for`. Sadece `now` değişir. Persona kaydı `.personas-days.json` (gitignore)
- [ ] 4.4 3 gün × A ×1, düşenler ×3
- [ ] 4.5 3 gün × B ×1, düşenler ×3
- [ ] 4.6 Düzeltmeler (kod: önce birim testi; model: transcript)

**Çıkış:** üç günde ledger farkı yok ya da sebebi ayrılmış ve düzeltilmiş.

## Faz 5: Uydurma brief D ve chat provası
- [ ] 5.1 `tests/fixtures/variants/brief_d.md` + `openapi_d.json` (temiz spec formatı; 3 ürün, 3 bant, `per_product`, müşteri callback'i, farklı outcome tablosu, posta kodu + doğum yılı) + `spec_d_expected.json`
- [ ] 5.2 `build-agent --no-deploy` (C ve D) + `specdiff`
- [ ] 5.3 C ve D deploy + `fbb chat` ile elle prova: açılış, kimlik soruları, hata yolunda dürüst cümle, çökme yok
- [ ] 5.4 D ile workflow boyutu (< 340 KB; aşarsa `prune_rt` ya da tek node deseni)

## Faz 6: Dayanıklılık ve operasyon
- [ ] 6.1 Builder modeli kararı: Opus ve Sonnet ile A+B süresi ve `specdiff` → `docs/07`'ye yazılır
- [ ] 6.2 Teslim provası (F8): temiz klon → `uv sync` → `.env` → iki brief art arda tek komutla; `exports/` ve `traces/` kontrolü
- [ ] 6.3 `make secrets-check freeze-check` hedefleri (yoksa ekle)
- [ ] 6.4 Ağ: final makinesinde mock'a `curl`; DNS 1.1.1.1 / hotspot yedeği `docs/07` acil durum tablosuna
- [ ] 6.5 Kredi durumu; gerekirse yavuz@freyavoice.ai'den ek kredi

## Faz 7: Dondurma (Paz 18:00 TR)
- [ ] 7.1 Bütün slotlar son commit'le yeniden kurulur
- [ ] 7.2 LLM spec'iyle A ve B `--reps 3` son ölçüm
- [ ] 7.3 `docs/00` ve `docs/07` "donduruldu"; kullanıcı commit ve push yapar

---

## Kritik dosyalar
- **Yeni:**
  - `docs/13_FINAL_HAZIRLIK.md`
  - `src/fbb/specdiff.py`, `src/fbb/days.py`
  - `tests/fixtures/days.json`
  - `tests/fixtures/variants/brief_d.md`, `openapi_d.json`, `spec_d_expected.json`
- **Değişebilir:**
  - `src/fbb/cli.py`
  - `src/fbb/runtime/flow.py` (`next_offer`)
  - `src/fbb/workflow/texts.py`
  - `src/fbb/ingest/prompts/extract.md`, `audit.md`
- **Yeniden kullanılacaklar:**
  - `kitapi.freya()`, `agent_for`, `get_call` (`src/fbb/kitapi.py`)
  - kit'ten import: `run_cases.persona_for`, `score.http`, `score_ledger`
  - `tests/test_graph.py` yardımcıları `_account`, `_offer`, `_propose`, `_step`, `_route`

## Doğrulama
- **Her kod değişikliği:** `uv run pytest` + `ruff`; `test_no_hardcoded_brief` ve `test_deterministic` yeşil olmalı.
- **Davranış değişikliği:** `--only X --reps 3` → bütün brief `--reps 3` → ilgili stil.
- **Başarısızlık:** `fbb call <callId>`; çağrılar workspace'ten simülasyon listesiyle çekilebilir.
- **Kayıt:** sonuçlar `docs/10` §9'a, kalıcı dersler `docs/02` ya da `docs/05`'e; ilerleme `docs/13`'teki kutulara.
