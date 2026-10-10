# 12: Review düzeltmeleri ve ölçüm raporu (10 Ekim 2026)

Bu rapor `11_REVIEW.md`'deki düzeltme planının uygulanmasını ve sonrasındaki Freya ölçümlerini özetler. Madde madde durum tablosu `11_REVIEW.md` §F'de, ham sonuç tablosu `10_TEST_REHBERI.md` §9'da.

## 1. Özet

| Ölçüt | Review öncesi (HEAD 8c400d6 öncesi ölçüm) | Şimdi |
|---|---|---|
| Brief A, `--reps 3` (pass³) | 3/10 | **9/10** |
| Brief B, `--reps 3` (pass³) | 2/3 | **3/3** |
| En yavaş agent turu (medyan) | 12–24 sn | 1–2 sn |
| Müşterinin telefonu kapattığı başarısız çağrı | var | 0 |
| Workflow boyutu | 322 KB | ≈300 KB (43 node) |
| Birim testleri | ~50 | 83 (hepsi yeşil), ruff temiz |

Konuşma stilleri (tek tekrar, son sürüm): in_words A 9/10, B 3/3; pieces A 9/10, B 2/3. asks_back, corrects ve talkative son düzeltmelerden sonra yeniden ölçülmedi.

Açık kalan iki vaka modelin ikna davranışından: PUB-06 (asgari ödeme bazen iki kez teklif ediliyor) ve PUB-12 (ürün başına deneme sayısı bazen tutmuyor).

## 2. Yapılan değişiklikler

### 2.1 Kapanış güvenliği (review B.1, B.16, B.17)
- `close_call` normal yolda kapanış node'larında, hook'suz ve 2 tekrar hakkıyla gidiyor.
- Ek olarak çağrı bitince çalışan bir **lifecycle yedeği** var. Pre-hook'u:
  - normal yolda close_call zaten başarılıysa (`close_r_ok`) isteğin URL'sini boşaltıp iptal ediyor (platformda görüldü: `Missing required field: url`, ledger'da tek close_call);
  - müşteri telefonu kapattıysa gövdeyi o anki durumdan kuruyor (`decide_close`).
- Outcome erken yazılıyor: üçüncü kişi akışına girince `no_callback`, hesap hazırlanınca `hangup_verified`, her kayıttan sonra güncel durum.
- Kod servisi hatasında her code node'u `fallback_close[_nr]` node'una gidiyor ve o ana kadar yazılmış outcome ile kapanıyor.
- Sabit kapanışlar (unclear, wrong_number, deceased, callback, id_failed, id_declined) ve transferler artık kodsuz: sabit tts veda + sabit outcome/reason.
- **F-09 deneyi (mock'a doğrudan):** ikinci close_call `ok:false, "the call is already closed"` döner, ledger değişmez, son çağrı yine close_call. Yedek bu yüzden zararsız. Boş `reason: ""` gönderilen close_call ise reddedilir; tasarım boş reason göndermiyor.

### 2.2 Read-back ve onay kodda (review B.2, B.3)
- Model müzakere bitince `propose_results` çağırıyor, read-back yapmıyor.
- Kod öneriyi doğruluyor ve kurala göre düzeltiyor:
  - deadline'dan sonraki tarih deadline'a çekilir (Brief B kural 6),
  - iş günü olmayan gün sonraki iş gününe kaydırılır,
  - borçtan fazla tutar borca indirilir,
  - floor altı tutar ya da geçmiş tarih müşteriye söylenecek bir cümleye çevrilir (tts, kayıt yok).
- Read-back cümlesini kod üretiyor: ürün, tutar, hafta günüyle tarih, düzeltme notu, onay sorusu. `readback` node'u bunu tts ile okuyor; routing "evet" → kayıt, "hayır/değişiklik" → müzakereye dönüş.
- PUB-13 r1'deki dürüstlük ihlali ("Your payment promises have been recorded" yalanı) yolu kapandı: geçersiz teklifte müşteriye giden cümle tts.

### 2.3 Kimlik ve gecikme (review B.4, B.5)
- `identity_check` ve `id_result` code node'ları kaldırıldı. Her soru sabit cümleli kendi node'unda; doğrulama sonucu cevap alanlarıyla kodsuz route ediliyor (`"true"`/`"True"` OR).
- Mutlu yol dışı her şey (yanlış, gün/ay ipucu, okunamadı, servis hatası, ret açıklaması, eksik cevap) tek `id_fix` kod adımında sabit cümleye çevriliyor ve tek `reask` node'unda söyleniyor.
- Parçalı cevaplar birleştiriliyor ("44" + "71", "14 March" + "1988", "19" + "88"). Eksik cevapta sistem eksik kısmı soruyor ("Thank you. And the year, please?").
- Ret açıklaması bir kez (sayaç kodda), sonra kapanış. Ret, açıklama ve tekrar sorma hep doğru soruya bağlı.
- verify 500 döndüğünde "That does not match our records" denmiyor ("Sorry, I could not check that answer").
- "One moment, please." tts: ilk verify, hesap çekme ve ilk kayıt adımında.
- Sonuç: kimlik cevabından sonraki tur ≈1 sn; en yavaş tur medyanı 12–24 sn'den 1–2 sn'ye indi.

### 2.4 Gizli brief / farklı openapi esnekliği (review B.7–B.12)
- `spec.response_fields`: cevap alanı adları; openapi'de yoksa `resolve_response_fields` en yakın alanı seçer. Yazma çağrılarında `ok` alanı yoksa zarfın `status`'u kullanılır.
- `spec.tool_constants`: rollere uymayan zorunlu istek alanları. openapi `default`'u ve tek değerli enum otomatik doldurulur. Eksik zorunlu alan artık build'i durdurmuyor, lint uyarısı.
- Kimlik: soru başına ayrı gövde alanı ve tek çağrıda bütün cevaplar (`verify_mode: all_at_once`); `postcode`/`alnum` cevap tipleri (harf harf, NATO alfabesi, "double four").
- Kural biçimleri genişletildi:
  - deadline: `business_days:N`, `calendar_days:N`, `end_of_month`, `date:…`
  - floor: `field:`, `percent:`, `fixed:`
  - deneme tutarı: `full`, `floor`, `percent:`, `fixed:`
  - callback: `business_days:N` günleri, güne göre saat aralığı
- `spec.overrides`: memo'ların tarihli değişiklikleri; runtime çağrının gününe göre seçer.
- `spec.customer_callback`, `recording.mode: per_product`, `spec.locale` (kodun ürettiği cümleler ve gün/ay adları).
- LLM çıktısı iki düzeltmeden sonra da şemaya uymazsa `lenient_validate` desteklenmeyen değerleri atar ve `unmapped`'e yazar: build çökmez.
- Varyant openapi (alan adları değişmiş, `ok` yok, fazladan zorunlu alan) birim testinde çökmeden kuruluyor (`test_variant_openapi_does_not_crash`).

### 2.5 Diğer (review B.6, B.18–B.23)
- Açılışta "recorded" kelimesi yok ("Please note that we record this call."); çıkarım prompt'u bunu genel kural olarak istiyor, lint uyarıyor.
- `agent_role` aramanın amacını içermemeli (LLM çıkarımında görüldü); prompt kuralı + lint uyarısı.
- `ARG_x` şablonu tırnak/ters bölüyle biten argümanda bozulmuyor.
- Hafta sonu `now`'unda "today" callback günü sayılmıyor.
- Snippet'ler yorumsuz, RT sadece kullanılan anahtarlarla gömülü (boyut).

## 3. Ölçüm sırasında bulunan ve düzeltilen hatalar

| Bulgu | Sebep | Düzeltme | Test |
|---|---|---|---|
| B PUB-12 0/3: yanlış telefondan sonra DOB soruldu | `id_take_answer` `id_q` yazmıyordu | `id_q` yazılıyor | `test_wrong_second_answer_reasks_the_second_question` |
| B PUB-12: ürün başına "bugün" tekrar soruldu, late bandında 2. deneme atlandı | model | negotiate'e genel ikna kuralları; deneme listesi "1. ret → …, 2. ret → …, sonra refused" senaryosu | B 3/3 pass³ |
| in_words/pieces: kimlik hiç tamamlanmadı ("one moment" döngüsü) | "one nine eight eight" okunmuyordu; eksik cevapta model bekliyordu | yıl okuma; eksik kısmı sistem soruyor | `test_partial_dates_from_style_runs` |
| pieces PUB-01: doğum yılı 2095 | "19 88 1988" toplanıyordu | rakam parçaları birleştirilir, bileşen birleştirme önce | `test_full_year_after_pieces_wins` |
| asks_back PUB-12: 2. soruda ret açıklamasından sonra DOB | `decline_questions` soru numarasını yazmıyordu | yazıyor | `test_decline_on_second_question_reasks_second_question` |
| pieces PUB-11/PUB-13: "Six hundred", "30.", "Twenty" ilk parçaları kullanıldı | model | parçalı tutar/tarih kuralı (somut örneklerle) | pieces B'de PUB-13 düzeldi |
| PUB-06: asgari ödeme iki kez teklif edildi | model | "her teklif bir kez; soruya yeni teklifle cevap verme" kuralı | 1/3 → 2/3, bitmedi |

## 4. Açık işler ve riskler

1. ✅ **(11 Eki 00:30'da kapandı: teklifler ve ürün sırası kodda, `next_offer`/`offer_step`; A 10/10, B 3/3 pass³; ayrıntı `10_TEST_REHBERI.md` §9 ve `05`.)** Eski not: **İkna sayımı modelde (PUB-06, PUB-12).** Prompt kuralları düşüşü azalttı ama bitirmedi. Kalıcı çözüm adayı: model "müşteri bu ürünü reddetti" diye bir tool çağırır, kod deneme sayısını tutar ve teklif cümlesini üretir. Risk: brief'in istediği ek cümleler (ör. "kalan borç gecikmiş kalır") koda spec'ten taşınmalı.
2. **asks_back, corrects, talkative** son düzeltmelerden sonra ölçülmedi. İlk turdaki (eski kod) açık sorunlar: talkative'de PUB-08 promise ile kapandı, PUB-09'da transfer yapılmadı, PUB-05'te destek ekibi birden fazla teklif edildi.
3. **Kayıt zinciri** hâlâ ürün başına bir code node'u (review C.3: ölçüm >10 sn göstermedikçe açılmayacak; şu an en yavaş tur 1–2 sn).
4. **Tutarın tipi** (`{{rec_amount:json}}`): mock kabul ediyor, bilinçli olarak pre-hook eklenmedi.
5. **Varyant provası** sadece birim testinde; simülasyonla yapılmadı (F6).
6. **Ölçüm ortamı:**
   - mock (`*.workers.dev`) bazı TR ağlarından erişilemiyor, VPN gerekiyor;
   - `FREYA_SIM_CONCURRENCY=10` koşuyu 3–4 kat hızlandırıyor ama agent turları 30 sn'ye kadar yavaşlıyor; ölçümde varsayılan 5 kullanılmalı;
   - 22:53'te Freya `503 API key validation is temporarily unavailable` döndü (geçici).

## 5. Tekrar üretmek

```bash
make test lint
make local-a local-b                                    # L1: altın spec → workflow
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json --spec tests/fixtures/spec_a.json --slot <ad>-a
uv run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools kit/tools/openapi.json --spec tests/fixtures/spec_ab.json --slot <ad>-b
uv run fbb cases <ad>-a --brief A --reps 3
uv run fbb cases <ad>-b --brief B --reps 3
for st in pieces in_words asks_back corrects talkative; do uv run fbb cases <ad>-a --brief A --style $st; uv run fbb cases <ad>-b --brief B --style $st; done
```

Brief A vakaları A agent'ında, B vakaları A+B agent'ında koşulmalı (Brief A not kullanmaz; notları açık agent'ta koşulursa PUB-05/PUB-08 geçersiz düşer).

## 6. Maliyet
- Claude (builder LLM, tek tam çıkarım): $1.82.
- Freya simülasyonları: yaklaşık 15 koşu (A/B `--reps 3`, stiller, tekil vakalar); kredi tüketimi ölçülmedi (F-07).

## 7. Değişen dosyalar
- `src/fbb/spec.py`, `ingest/openapi.py`, `ingest/prompts/*.md`, `llm.py`, `build.py`
- `src/fbb/runtime/` (dates, normalize, facts, validate, closing, flow, emit)
- `src/fbb/workflow/` (graph, nodes, texts, lint, tools)
- `tests/` (conftest, test_graph, test_runtime, test_spec, fixture'lar)
- `docs/` 00, 02–08, 10, 11, 12
