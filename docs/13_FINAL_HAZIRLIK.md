# 13: Finale hazırlık (test ve düzeltme planı, takip)

> Bu dosya finale kadar yapılacak testlerin ve düzeltmelerin takibidir.
> - Biten madde `[x]` olur ve yanına kısa sonuç ya da commit yazılır.
> - Yarım kalan madde `[~]` ile işaretlenir ve ne kaldığı yazılır.
> - **"📍 Şu an"** satırı her adımda güncellenir.

**📍 Şu an (11 Eki ~17:30): DONDURULDU.** Faz 0–7 ✅. Son sürüm: altın spec B 3/3 pass³; Claude spec'i B 3/3 pass³, A 7/10 pass³ (3 düşüş: platform sessizliği, robot sorusu zamanlama yarışı, durum cümlesi → düzeltildi: PUB-08 3/3, A-LLM ×1 10/10). Platform 16:20–17:15 arası yavaştı (medyan en yavaş tur 4–61 sn). Bundan sonra sadece bug fix; final penceresi `docs/07`.

**Önceki (14:45):** Freya API kesintide (kimlikli çağrılar 504/403) → Freya'sız işler yapıldı: runtime review + 2 düzeltme (3.14), istek alanı eşlemesi (3.15), Brief E (5.6), runbook kesinti prosedürleri. Ölçülmeyen: `check_offer_answer`, cevaplanmamış soru kuralı ve 3.14 sonrası A/B `--reps 3` (13:00 koşusu platform yüzünden geçersiz). Platform düzelince: slotları kur → A/B `--reps 3` → talkative, SC-01..05 ×1 → Faz 7.

**Önceki (05:00):** Faz 4 ✅, Faz 2 ✅, Faz 3.1/3.3 ✅ (11 Eki ~05:00). Son sürüm: A 10/10 ve B 3/3 pass³, talkative A 10/10 · B 3/3, PUB-05 dört stilde 4/4. Sıradaki: Faz 3.2 (müşteri callback'i canlı), Faz 5 (Brief C/D provası), Faz 6.

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
- [x] 2.1 `pieces`: A (dev-a) ×1, B (dev-b) ×1
- [x] 2.2 `in_words`: A ×1, B ×1
- [x] 2.3 `asks_back`: A ×1, B ×1
- [x] 2.4 `corrects`: A ×1, B ×1
- [x] 2.5 `talkative`: A ×1, B ×1
- [x] 2.6 Düşen her vakanın transcript analizi ve sınıflandırması (`docs/10` §6)
- [x] 2.7 Düzeltmeler: önce `--only X --style Y --reps 3`, sonra bütün brief `--reps 3`
- [x] 2.8 (11 Eki 11:20–12:15) Son kodla 4 stil × A/B, bütün brief ×1: in_words 10/10 · 3/3, pieces 10/10 · 3/3, asks_back 9/10 · 3/3, corrects 10/10 · 3/3 (talkative 05:00'te 10/10 · 3/3). Tek düşüş asks_back PUB-04: kod adımı sırasında sorulan "robot musun?" cevapsız kaldı → sistem prompt'una genel kural

**Sonuç (11 Eki ~03:00–04:30, Mert):** ilk tur (×1): pieces 8/10 · 3/3; in_words 10/10 · 3/3; asks_back 8/10 · 2/3; corrects 10/10 · 2/3; talkative 7/10 · 2/3. Düşenlerin transcript'leri okundu; düzeltmeler (hepsi genel, testli):
- **Kimlik:** ay içermeyen tek sayı ("It is 1…") eksik cevap sayılır; ret açıklamasında ve geri soruya verilen cevapta güvenlik sorusu tekrarlanmaz (hakem her tekrarı ayrı soru sayıyordu); kimlik node'larında tur sınırı 12 → 30 (talkative'de sınır doluyordu).
- **İkna:** belirsiz cevap ("you tell me", soru) `next_offer`'da ret sayılmaz; kesik mesajda `next_offer` çağrılmaz.
- **Kesik mesajlar** (simülasyondaki konuşkan müşterinin mesajları sık sık yarıda kesiliyor): mesajda cevap varsa önce cevap işlenir; yoksa kısa, değişen bir dinleme cevabı ("Mm-hm.", "I'm listening."), soru ya da teklif tekrarı yok.
- **Hardship:** yukarıda (4.6).
- Hedefli ölçümler: asks_back PUB-03/05/07 3/3, pieces PUB-03/05/07 3/3, talkative B 3/3, asks_back B 3/3; regresyon A 10/10, B 3/3 pass³.
- Bilinen sim kaynaklı düşüşler: pieces PUB-09'da müşteri hiçbir şey söylemeden kapattı; talkative'de persona mesajları kesilip baştan başlıyor.

**Çıkış:** her stilde A ≥ 9/10 ve B ≥ 2/3; bizden kaynaklı ve tekrarlayan hata yok.
**Beklenen sorun alanları:**
- parça parça söylenen tutarın `agreed_amount`'a girmesi;
- `asks_back`'te modelin kendisinin teklif yapması;
- `talkative`'deki "30'unda düğün" cümlesinin `agreed` sanılması;
- tool çağrısından önce tek başına söylenen "I" parçası.

## Faz 3: Kod yolları (gizli brief tipi senaryolar, birim/graf testi)
- [x] 3.1 `per_product` kayıt + `next_offer` → eksikti: kabul edilen ürün kaydedilmeden sıradaki ürüne geçiliyordu (fiilen toplu kayıt). Düzeltme: per_product'ta kabul → o ürün (+ bekleyen durumlar) hemen read-back ve kayıt; kayıttan sonra 'kaydedildi' + sıradaki ürünün 1. teklifi tek cümlede (`next_offer_say`); propose edilenler `offers_json.proposed`'da (çift öneri yok). Testler: `test_per_product_with_next_offer`, `test_per_product_last_product_agreed_after_refusals`. Canlı prova (`mert-pp`, spec_ab + per_product): PUB-12, PUB-13 2/2, transcript'te ürün başına kayıt görüldü (11 Eki ~05:00)
- [x] 3.2 Müşteri callback'i (`customer_callback`) + `next_offer` → canlı (11 Eki, `var-cc` = spec_a + customer_callback, `fbb scenarios` SC-04/05). SC-04 (yarın 15:00) ✅ callback kuruldu. SC-05 (pencere dışı iki kez) ledger ✅; hakem 'iki kez sordu' dedi: (1) model saat vermeyen gün için saat soruyordu → `propose_callback` sadece günle de çağrılır, geçerli günde yalnız saat sorulur (tekrar sayılmaz), geçersiz gün tek tekrar sayılır (`test_callback_day_only`); (2) callback node'u müşterinin zaten söylediği zamanı tekrar soruyordu → açılış artık 'Pazartesi 20:00, doğru mu?' onay sorusu. Varyant notu: kit mock'u `no_promise` için sadece refused/hardship/dispute/service_error kabul ediyor
- [x] 3.3 Bir üründe dispute/paid, diğerinde ret: `propose_results` ↔ `offers_json` uyumu → `merge_offer_results`: modelin listesinde olmayan ürünler next_offer sonuçlarından tamamlanır (`test_propose_results_keeps_offers_already_agreed`)
- [x] 3.4 Teklif sırasında transfer (B kural 10): kaydedilmemiş anlaşma kaydedilmez, not yazılmaz → canlı SC-01 (batch, dev-b) ✅ ×2, SC-02 (per_product, 1 kayıt sonra transfer) ✅
- [x] 3.5 "No speakable content" denetimi → `test_every_model_tool_call_routes` (3 spec × 10 aksiyon × 3 derinlik): her tool çağrısı bir geçişe gider VE konuşma node'una girince eski bayrak tetiklenmez. Bu değişmez iki gerçek hata buldu: `negotiate_more` `go_more` self-loop (SC-03'teki 70 tekrar) ve `propose_step`'te önceki `next_offer`'dan kalan `offer_go`
- [x] 3.6 Kod servisi kesintisinde `offer_step` ve `propose_step` → `fallback_close` → `test_every_code_node_has_service_failure_exit` (her code node'unun ilk geçişleri `<node>_failure_count`)

- [x] 3.7 (11 Eki ~02:30, Mert) Ret turu gecikmesi: tool + `offer_step` + `commit_fix` = 3 code node → ~10 sn sessizlik (B koşusu, medyan en yavaş tur 10 sn). `offer_step` artık bayrağı kendisi temizleyip `negotiate_fix_say`'e gidiyor (`offer_go`); medyan 2 sn'ye indi (`test_offer_goes_straight_to_speech`)
- [x] 3.8 (11 Eki ~02:35, Mert) Model sadece 1. ürün kabul edilmişken `agreed_all` dedi; read-back reddinden sonra teklif durumu kapalı kaldığı için diğer ürünlere hiç teklif yapılmadı. `readback_reset` son `next_offer`'ı geri alıyor (`offers_prev`), `agreed_all` açıklaması netleşti (`test_readback_rejection_reopens_offers`)
- [x] 3.9 (11 Eki ~10:50) **Aynı turda iki tool / teklif sırasında durum** (SC-03, canlı bulundu): 'kartı yarın öderim, krediyi ödemem, araç kredisi benim değil' → model `next_offer(agreed p1)` + `propose_results(p3:dispute)`; ikincisi `commit`'i ezdi, p1 kayboldu, `negotiate_more` 70 kez kendine döndü. Düzeltme (genel, iki modda): tool'lar `offer_pending`/`propose_pending` işaretler, önce durumlar işlenir (`fold_statuses`: durumlar `offers_json`'a yazılır, teklif imleci `next_open` ile o ürünleri atlar), sonra teklif cevabı; `go_more` sadece kod adımından çıkar. Testler: `test_agree_one_and_dispute_another_in_one_turn_{per_product,batch}` (iki sıra), `test_status_for_current_product_moves_to_next_offer`. Canlı: SC-03 ✅, B 3/3
- [x] 3.10 (11 Eki) Lint boyut sınırı hata → uyarı: dryRun 450 KB / 700 KB / 1,2 MB'ı kabul etti; 400 KB hatası gizli bir brief'i (callback + per_product + 3 bant ≈ 365 KB) boşuna durdurabilirdi
- [x] 3.11 (11 Eki ~11:20) Callback: (1) `propose_callback` → `check_callback_time` (hakem pencere dışı bir *kontrol* çağrısını 'kurulmuş callback' saydı); (2) callback node'una girişte müşteri zamanı zaten söylediyse onay sorusu; (3) `customer_callback.no_callback_outcome` (yeni, isteğe bağlı): brief müşteriye geçerli zaman verilmezse ayrı bir kapanış istiyorsa (D kural 11) kendi sabit kapanışı; boşsa genel kapanış. Testler: `test_callback_day_only`, `test_customer_callback_no_callback_outcome`. PUB-02 ×3 3/3
- [x] 3.12 (11 Eki ~12:10) `next_offer` → `check_offer_answer` (hakem `result='agreed'`'yi 'promise kaydedildi' saydı, SC-01 2/3). Yeni adla SC-01 2/2, SC-03 3/3
- [x] 3.13 (11 Eki) Platform dayanıklılığı (`kitapi`, kit dosyası değişmez): GET'ler 5xx/ağ hatasında ~5 dk tekrar; 10 dk'yı aşan simülasyonu bekçi iptal eder (belgelenmemiş `POST /simulations/<id>/cancel`); `fbb cases` kit koşucusu aynı süreçte (`fbb.kit_runner`) ve 60 dk süre sınırıyla
- [x] 3.14 (11 Eki ~14:30, Freya kapalıyken) Review + etkileşim testleri: (1) read-back reddi yalnız son tool eyleminin etkisini geri alır — katlama da bir eylem (`offers_prev`); son eylem katlamaysa önceki retler artık silinmiyor; (2) `settled` (kesinleşmiş ürünler) yalnız per_product'ta — batch'te `statuses_json` read-back'e kadar geçici, reddedilince ürün tekrar açılmalı. Testler: `test_readback_rejection_after_final_fold`, `…keeps_folded_statuses`, `test_fold_then_hardship_keeps_folded_status`, `test_agreed_all_skips_disputed_product`, `test_two_tools_after_a_recorded_product_per_product`, `test_propose_with_promise_and_status_uses_normal_validation`; yönlendirme yürüyüşü per_product'ta kayıt sonrası `negotiate_more`'u da kapsıyor (91 → 750 tool çağrısı)
- [x] 3.15 (11 Eki) `resolve_request_fields`: gizli openapi'de istek alanı yeniden adlandırılır ve Claude `tool_fields`'i kaçırırsa, rolün kelimelerini içeren TEK aday alan eşlenir (ör. `schedule_callback.callback_date`); birden çok aday varsa dokunulmaz. Testler: `test_renamed_request_fields_are_mapped`, `test_ambiguous_request_field_is_left_alone`, `test_request_fields_noop_on_kit_openapi`. Tutar tipi: openapi `number` → graph leaf tipi zaten `number`; string'e çeviren platform. Pre-hook ile sayıya çevirme Freya ayakta olunca denenecek (düşük risk: skorlayıcı `float()` okuyor)

## Faz 4: Farklı takvim günleri
- [x] 4.1 Runtime birim testleri: Cuma 2026-10-16, Cuma 2026-10-23 (26 Ekim tatil öncesi) ve Çarşamba 2026-12-23 (yıl sonu tatilleri) için `prep_account` ve `day_table` beklentileri
- [x] 4.2 `tests/fixtures/days.json`: PUB-01, 02, 06, 10, 11, 12 (göreli tarih) ve 03, 05, 08, 09 için gün başına **elle hesaplanmış** beklenti ve checks; her satırda dayandığı kural yazılı
- [x] 4.3 `fbb days <slot> --brief A --now …` runner (`src/fbb/days.py`). Kit fonksiyonlarını import eder: `freya.run_simulation`, `create_personas`, `score.http`, `score_ledger`, `run_cases.persona_for`. Sadece `now` değişir. Persona kaydı `.personas-days.json` (gitignore)
- [x] 4.4 3 gün × A ×1, düşenler ×3
- [x] 4.5 3 gün × B ×1, düşenler ×3
- [x] 4.6 Düzeltmeler (kod: önce birim testi; model: transcript)

**Sonuç (11 Eki ~02:55, Mert):**
- 4.1: `tests/test_days.py` (26 test). Bağımsız takvim (builder kodu yok) ile runtime aynı deadline, ilk teklif, kaydırma, callback günü ve `day_table` etiketlerini üretiyor. Kod düzeltmesi gerekmedi.
- 4.2: 3 gün × 13 vaka = 39 senaryo: Cuma 16 Eki, Cuma 23 Eki (Pzt 26 tatil), Çar 23 Ara (25 Ara ve 1 Oca tatil). Kenar durumlar: Cuma "yarın" (Cumartesi), tatildeki Pazartesi için callback, 25 Aralık'ı ödeme günü olarak söylemek.
- 4.4/4.5: A 10/10, 10/10, 9/10; B 3/3, 3/3, 3/3 → **38/39**. Tek düşüş tarihten bağımsız PUB-05 (destek teklifi iki kez).
- 4.6: PUB-05 için önce prompt kuralı (transfer teklifi bir kez) → PUB-05 `--reps 3` 3/3, corrects 1/1, talkative 1/1. pieces'te yine tekrarlandı → hardship `next_offer`'a bağlandı. İlk sürümde kod teklifi tts ile söylüyordu; model teklifi brief kuralıyla zaten kendisi yaptığı için çift teklif oldu. Son hali: teklifi model bir kez yapar, ret `next_offer(result='hardship')` ile gelince kalan bütün ürünler `negotiation.hardship_status` ile hemen biter (testler: `test_hardship_*`).

**Çıkış:** üç günde ledger farkı yok ya da sebebi ayrılmış ve düzeltilmiş. ✅

## Faz 5: Uydurma brief D ve chat provası
- [x] 5.1 `tests/fixtures/variants/brief_d.md` + `openapi_d.json` (temiz spec formatı; 3 ürün, 3 bant, `per_product`, müşteri callback'i, farklı outcome tablosu, posta kodu + doğum yılı) + `spec_d_expected.json` → yazıldı; beklenen spec LLM çıkarımının elle denetlenmiş hali (bütün puan alanları brief'le aynı)
- [x] 5.2 `build-agent --no-deploy` (C ve D) + `specdiff` → C: 7 README maddesinin hepsi doğru (channel sabiti, cevap alanları, `{card_last4}`, tarihli memo override, overdraft `max:` floor, `business_days:2`, postcode) + memo tatili; `spec_c_expected.json`. D: 52 node, lint 0; 2. çıkarımla tek PUAN farkı `transfers.general.stages` (insan isteği kimlikten önce de geçerli mi; brief söylemiyor) → `extract.md`'ye genel kural: insan isteği brief kısıtlamadıkça iki aşamada
- [x] 5.3 C ve D deploy + `fbb chat` ile elle prova: açılış, kimlik soruları, hata yolunda dürüst cümle, çökme yok → prova-c, prova-d kuruldu (lint 0). Chat: robot sorusu, harf harf posta kodu birleşti (`SW1A1AA`, `EC1A1BB`), mock alanı tanımayınca 'could not check that answer' + tekrar soru (eşleşmiyor denmedi). Chat'te C'nin kayıt cümlesi düştü → sesli simülasyonda birebir söylendiği doğrulandı (chat'e özgü, `docs/02`)
- [x] 5.4 D ile workflow boyutu → D 364 KB, var-cc 352 KB (json.dumps). dryRun 1,2 MB'ı kabul ettiği için lint'te boyut hata değil uyarı (3.10)
- [x] 5.5 İkili çıkarım: C 2 çıkarım → `specdiff` kimlik eşlemesi (`status_to_reason`) ve override notu gürültüsü ayıklandıktan sonra **0 PUAN farkı**; D 3 çıkarım → tek fark (insan isteğinin aşaması) `extract.md` kuralıyla kapandı, 3. çıkarım **0 fark**. Finalde ikinci çıkarım + `specdiff` adımı `docs/07` §3'e eklendi
- [x] 5.6 (11 Eki ~14:40) Brief E (ham materyal: hafta günü callback saatleri, 3 kimlik sorusu, memo'da bant sınırı + tarihe kadar override + kod yeniden adlandırma, dialler export'u) → 2 çıkarım, lint 0, bütün tuzaklar doğru, birbirine 0 PUAN farkı; `spec_e_expected.json`
- [x] 5.7 (11 Eki ~15:10) **Brief F, şirket müşterisi** (kitin persona'sı `company_number`/`founded_year` tanıyor → gizli brief adayı): ilk çıkarımda 3 kural şemaya sığmadı → genel alanlar: `closing.promise_reason`/`promise_reason_partial`/`paid_reason` (**promise ve paid kapanışları reason'sız gidiyordu**), `callback.min_lead_minutes`. Soru başına yanlış hakkı: bankanın `wrong_answers_left`'i karar veriyor, kod gerekmedi. Yeni alanlarla 2 çıkarım 0 PUAN farkı; `specdiff` ödenmiş durumunun eşlemesini yok sayar (kullanılmıyor). Testler: `test_promise_and_paid_reasons`, `test_callback_min_lead_minutes`, `test_rehearsal_briefs_build_cleanly[c-f]`. **Runtime değişti → A/B hash'leri değişti → platform açılınca A/B `--reps 3` zorunlu** (davranış birim testlerinde aynı: alanlar boşken eski yol)
- [x] 5.8 (11 Eki ~15:40) **Brief G, tool yapısı değişiyor** (kit: "the fields can change"): (1) `close_call` tek `result_code` → eskiden hardship/itiraz/sistem hatası ve 3 transfer türü tek koda düşüyordu; şimdi reason alanı yoksa durumun/kuyruğun kodu outcome olarak gider (`closing.single_code`; `cross_check` eksik eşlemeyi denetime 'düzelt' diye verir; `extract.md` kuralı); (2) `schedule_callback` tek `callback_at` → eskiden yalnız saat gidiyordu; şimdi `YYYY-MM-DDTHH:MM` (`callback_body`, `cb_at`). Doğru çıkanlar: tek çağrıda kimlik, Paz–Per iş haftası, sabit kampanya tarihi, `AED` öneki. 2 çıkarım 0 PUAN farkı (`specdiff` kural varken `deadline_bd`'yi yok sayar). Testler: `test_single_result_code_close_and_datetime_callback`, `test_rehearsal_briefs_build_cleanly[g]`

## Faz 6: Dayanıklılık ve operasyon
- [x] 6.1 Builder modeli kararı → **Opus** (varsayılan `claude-opus-5-5`): LLM çıkarımları (A×4, C×2, D×3) puan alanlarında altın/beklenen spec'le 0 fark (kural düzeltmelerinden sonra); A+B 109 sn / $1.00. Sonnet yalnız acil durum yedeği (`docs/07`)
- [x] 6.2 Teslim provası (F8): temiz klon → `uv sync` → `.env` → iki brief art arda tek komutla; `exports/` ve `traces/` kontrolü → (11 Eki 10:34) temiz klonda `uv sync` 1 sn, 130 test yeşil; A+B build **109 sn, $1.00** (Opus: çıkarım 55 sn + denetim 51 sn), 45 node, lint 0, dryRun ✅, geri okuma 0 fark, workflow 359 KB (kaydedildi), export 395 KB ve `close_call` içeriyor; trace'te `workflow_id` export'la aynı; `secrets-check` temiz; `.gitignore` `final-*` trace/export'u içeri alıyor, `prova-*`'yı dışarıda tutuyor. `specdiff` altın spec_ab'ye karşı **0 PUAN farkı** (4. bağımsız çıkarım). Elle müdahale gerekmedi
- [x] 6.3 `make secrets-check freeze-check` hedefleri → zaten `Makefile`'da
- [~] 6.4 Ağ: bu makineden mock'a practice session açıldı (11 Eki 10:25). Final makinesi farklıysa orada tekrar `curl`; yedekler `docs/07` acil durum tablosunda
- [~] 6.5 Kredi: API kredi bilgisini vermiyor (`/api/v2/workspaces`'te yok); panelden kontrol edilmeli. Workspace'te ~15 workflow (sınır 200)

## Faz 7: Dondurma (Paz 18:00 TR)
- [x] 7.1 Bütün slotlar son commit'le yeniden kurulur → (11 Eki 16:23, Mert, `e2957b5` + `--rerun-if-slow`) mert-a/mert-b altın spec, mert-a-llm/mert-b-llm Claude spec'i: 45 node, lint 0, geri okuma 0 fark. LLM build: A 96 sn / $0.88, A+B 110 sn / $0.45. `specdiff`: A tek PUAN farkı `hangup_unverified` (brief tanımlamıyor, Faz 1'deki gibi), B 0 PUAN farkı. Regresyon (altın spec, platform yavaş: medyan en yavaş tur 13–61 sn, en kötü 382 sn): A 4/10 — **bütün düşüşler 60–382 sn sessizlikte müşterinin kapatması**, 2. koşu (medyan 18 sn) 10/10; B **3/3** pass³
- [x] 7.2 LLM spec'iyle A ve B `--reps 3` son ölçüm → (11 Eki 16:54–17:07, platform yavaş: medyan en yavaş tur 4–19 sn) **B 3/3 pass³**; A 7/10:
  - PUB-01: 67 sn sessizlikte müşteri kapattı (platform).
  - PUB-04: müşteri robot sorusunu 'One moment' tts'i sırasında sordu, ardından sabit borç cümlesi söylendi ve soru cevapsız kaldı (zamanlama yarışı, açık risk).
  - PUB-08: brief'in 'ödemeler bir iş günü içinde görünür' cümlesi söylenmedi. Kök neden: 'propose_results'tan önce konuşma' kuralı ile durum cümlesinin modele bırakılması çakışıyordu. Düzeltme: durumun `say` cümlesini kapanış/ara konuşma söyler (`status_say`, `announce`), görev metni 'sistem söyler' diyor (`test_status_sentence_is_said_by_the_system`). Ölçüm (son kod): PUB-08 A-LLM `--reps 3` **3/3**, A-LLM ×1 **10/10**.
- [x] 7.3 `docs/00` ve `docs/07` "donduruldu"; commit ve push (11 Eki ~17:30, Mert). Son kod eklemeleri: `fbb cases --rerun-if-slow N` (kitin seçeneği), durum cümlesini sistem söyler. Bundan sonra sadece bug fix (`BUGFIX_LOG.md`)
- [x] 7.4 (11 Eki 17:30–17:40, Mert, dondurmadan önce) Platform hızlıyken Claude spec'li A `--reps 3`: 6/10 → düşüşlerin hepsi platform (2× 60 sn sessizlik, 2× `Failed to reach snekbox`). Biri bizde zayıflık gösterdi: create_promise başarılı olduktan hemen sonra `rec_step`'te kod servisi düşünce yedek kapanış eski 'refused' outcome'unu gönderdi. Düzeltme: `rec_step` hatası + son kayıt başarılı → kodsuz `fallback_promise` (promise outcome, başarı cümlesi + veda). Test: `test_code_failure_right_after_recorded_promise_closes_as_promise`; dryRun + geri okuma 0 fark

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
