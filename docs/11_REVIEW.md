# Genel review: koşu analizi, hatalar, gizli brief'e uyum riskleri ve düzeltme planı

## Context
Kullanıcı, skoru etkileyebilecek her şeyin ayrıntılı bir review'unu istedi: önceki koşulardaki bizden kaynaklı hatalar, tool hataları, gizli brief'ler ve vakalar değiştiğinde kırılacak yerler. Düzeltmeler bu review onaylandıktan sonra yapılacak.

İncelenenler: `docs/00–10`, kit (README, brief A/B, openapi, `score.py`, `run_cases.py`, public test set), `src/fbb/**` (spec, ingest, runtime, workflow, build), `results/*.json` ve başarısız çağrıların transcript'leri (`fbb call`). `uv run pytest` yeşil.

Kısa durum: platform sağlıklıyken çekirdek akış çalışıyor (A 10/10 ×1, B 3/3 ×1). Ama `--reps 3` ölçümü: **A 3/10, B 2/3**. A'daki düşüşün büyük kısmı 2. turdaki snekbox kesintisi. Kalan başarısızlıkların hepsi bizden kaynaklı ve tekrarlanabilir. HEAD (8c400d6) **hiç ölçülmedi**: dev-a/dev-b 18:03'te kuruldu, sonrasında koşu yok.

---

## A. Önceki koşularda görülen başarısızlıklar (kanıtlı)

| Vaka / koşu | Ne oldu | Sebep | Sınıf |
|---|---|---|---|
| PUB-03 r0 (`4250e8ad`) | 3. DOB "twenty one July nineteen ninety. …how much do I owe?" submit edilmedi; model `decline_explain`'i **iki kez** söyledi, sonra `declined` ile kapattı (beklenen `failed`) | Cevap ve soru aynı mesajda gelince model bunu ret saydı. Prompt'a kural eklendi ama ölçülmedi. "Explain once" sayacı yok (`decl_n` yazılıyor ama hiç kullanılmıyor) | prompt + deterministik eksik |
| PUB-07 r0 (`9f629c16`) | Müşteri "Monday the 26th" dedi, agent "latest date I can record is Monday 2 November" dedi; promise 11-02'ye kaydedildi (beklenen 10-27) | Model day_table'da yanlış satıra baktı (26 Eki tatil → 27 Eki). Validator 11-02'yi geçerli saydığı için yakalayamadı | model tarih okuma |
| PUB-07 r0 | close_call yok | Lifecycle pre-hook'u snekbox'ta düştü (bu yüzden HEAD'de close_call api_request node'una taşındı) | platform |
| PUB-10 r1 ve r2 | Hakem: "agent 'recorded' dedi, başarılı çağrıdan önce" → **açılıştaki "This call is recorded."** cümlesi | Hakem kelimeye takılıyor. 3 koşunun 2'sinde aynı gerekçe geçti | hakem riski |
| PUB-10 r2 | Read-back'te ürün adı yok ("That would be Friday 16 October. Do you confirm…") | Read-back modele bırakılmış (kural 34 ürün, tutar ve tarih istiyor) | prompt / deterministik eksik |
| PUB-13 r1 (`756c4d8e`) | Model p2'yi kendi deadline'ı (23 Eki) yerine 30 Eki'ye koydu. submit reddedildi, ardından `negotiate_fix` modeli **"Your payment promises have been recorded." dedi (YALAN)**, müşteri kapattı. Kanıt: 63 sn sessizlik | (1) per-product deadline modele bırakılmış; (2) `negotiate_fix` on_enter `llm` prompt'u yok sayıldı → dürüstlük ihlali | tasarım |
| A r1 (7 vaka) | 0.4 sn'de `end_fallback` | snekbox kesintisi (koruma çalıştı ama close_call yok) | platform |
| Bütün koşular | En yavaş tur medyanı **12–24 sn** (kit 10 sn üstünü uyarı sayıyor; müşteri ~10 sn sessizlikte kapatıyor) | Her code node yük altında 2–8 sn. Kimlik turunda 2, kayıtta ürün başına 1 code exec var | performans |

---

## B. Bulgular, önceliğe göre

### P0: Skoru doğrudan düşürenler ve kesin regresyon riski

1. **Müşteri telefonu kapatırsa close_call hiç gitmiyor (HEAD regresyonu).**
   - HEAD'de close_call sadece `send_close`/`send_close_nr` api_request node'larında var (`graph.py` SEND).
   - PUB-13 r1 transcript'i lifecycle `end_of_call`'ın kapatmadan sonra da çalıştığını kanıtlıyor. Bu, F-02'yi fiilen ✅ yapıyor.
   - Sonuç: HEAD'de her erken kapanma = "not closed with close_call" + outcome None.
   - Düzeltme: lifecycle close_call'ı **yedek** olarak geri ekle, hook'suz ve baked `{{close_outcome}}`/`{{close_reason}}` ile.
     - Normal yolda close_call iki kez gitmesin diye ya lifecycle'ı tek kapanış yap (reason boşsa alan gitmesin; F-03'teki "çözülmeyen tek placeholder gönderilmez" kuralı) ya da ikinci çağrının ledger'a etkisini deneyle ölç (F-09).
   - Ek olarak `set_close` her durumda `close_outcome`'u erkenden yazsın: kimlik doğrulanınca hangup varsayılanı, negotiate'e girince o anki durum.
   - Dosya: `src/fbb/workflow/graph.py`.
2. **Ret sonrası dürüstlük açığı (`negotiate_fix`).**
   - `on_enter: llm` prompt'u modele "nothing was recorded" diyor, model yine "recorded" diyebiliyor (PUB-13'te gözlendi).
   - Düzeltme: B.3'teki read-back tasarımıyla bu yol tamamen ortadan kalkar. Kalırsa on_enter **tts** olmalı ve kodla üretilmiş müşteri dilinde cümle içermeli.
3. **Read-back ve onay modele bırakılmış. Validasyon onaydan SONRA yapılıyor.**
   - Bunun sonuçları: PUB-13 (yanlış tarih onaylatıldı, sonra reddedildi), PUB-10 (read-back'te ürün yok), PUB-07 (yanlış öneri).
   - Önerilen yapı:
     - Model müzakere bitince `propose_results(...)` çağırır.
     - Kod doğrular, kurala göre düzeltir (B kural 6: ortak tarih bir ürünün deadline'ını aşıyorsa o ürünü kendi deadline'ına çeker) ve **read-back cümlesini kendisi üretir**: ürün ifadesi, tutar, tarih ve hafta günü, kaydırılan ürün için açıklama, `confirm_question`.
     - `readback` node'u tts ile okur. Ardından bir onay node'u: "yes" → kayıt zinciri; değişiklik/ret → negotiate'e geri.
   - Geçersiz girişte (tarih geçmiş, floor altı) kod müşteri cümlesi + öneri üretir (tts).
   - Dosyalar: `runtime/validate.py`, `runtime/flow.py`, `workflow/graph.py`, `workflow/texts.py`.
4. **Gecikme (customer-ended-call ve hakem riski).** Code exec sayısını azalt:
   - `identity_check` (id_init) gereksiz. İlk soru, sabit tts'li ayrı bir node'la sorulabilir; açılışta 3–7 sn kazanılır.
   - `id_result` code node'u yerine `verify_answer` mapping değişkenleri üzerinden doğrudan route edilebilir: `all_verified ∈ {true, True}`, `wrong_answers_left == 0`, `hint == swap`. Soru başına ayrı `ask_q<i>` node'u spec listesinden üretilir. Kimlik turu başına ~5 sn kazanılır. Boolean'ın metin gelmesi (`"true"`/`"True"`) OR koşuluyla karşılanır.
   - Uzun zincirlerden önce kısa tts eklenir ("One moment, please."): `verify_answer`, `fetch_account`, `record_promise` ilk girişte. "Recorded" kelimesi kullanılmaz.
   - Kayıt döngüsü: ürün başına `rec_step` code'u yerine ≤3 ürün için açılmış sabit api zinciri (F-05 yedek planı). Retry node'ları ayrı olur, karar `{{recN_*}}` değişkenleriyle verilir.
5. **`pieces` stilinde kimlik cevabı birleştirilmiyor.**
   - `id_take_answer` "partial" görünce kısmi değeri **saklamıyor**. Sonraki submit sadece kalan parçayı görür ("44" + "71" → yine partial).
   - Tarihte yılsız cevap ("14 March") "partial" değil "unreadable" sayılıyor: verify'a gönderiliyor ve "Sorry, I did not catch that" + baştan sorma oluyor.
   - Düzeltme: `id_partial` biriktir ve birleştir; tarihte gün+ay var, yıl yoksa partial say.
   - Dosyalar: `runtime/flow.py`, `runtime/normalize.py`. Önce test yazılır.
6. **Hakem: açılıştaki "recorded" kelimesi.**
   - Promise vakalarında "recorded'ı başarıdan önce söyleme" check'i oldukça 2/3 düşme var.
   - Seçenek: ifadeyi "this call is being recorded for quality and security" gibi açıkça çağrı kaydına bağlamak ya da extract prompt'una "açılış bildirimini promise kaydıyla karışmayacak biçimde yaz" demek. A/B ile ölçülmeli. Kural 1 gereği kelime tamamen atılamaz.

### P1: Gizli brief / farklı openapi geldiğinde kırılacak yerler

7. **get_account cevap alanları kodda sabit.**
   - `facts.py` içinde `past_due`, `days_late`, `type`, `product_id` sabit; `graph.py` içinde `data.products` sabit.
   - Kit: "fields and allowed values can change". Alan adı değişirse bant `bands[-1]`'e düşer, borç 0 olur ve agent sessizce yanlış çalışır.
   - Düzeltme: spec'e `account_fields` ekle (rol → alan adı: products yolu, id, type, past_due, days_late). LLM openapi'den doldurur, `cross_check` response şemasında var mı diye kontrol eder.
8. **verify_identity cevap alanları sabit.** `ok`, `verified`, `all_verified`, `wrong_answers_left`, `hint`. Aynı yaklaşım: `verify_fields` rolleri. Bunu daha önce G-01 diye planlamıştık, henüz yapılmadı.
9. **Kimlik modeli tek `field`+`answer` çağrısını varsayıyor.**
   - Gizli API soru başına ayrı alan isteyebilir (`date_of_birth`, `postcode` aynı gövdede) ya da tek çağrı olabilir.
   - Persona kodu `postcode`, `birth_year`, `company_number`, `founded_year` alanlarını tanıyor. Bu, gizli brief'te **şirket müşterisi** ve **posta kodu** sorusu olabileceğine işaret.
   - Gerekenler: `answer_type` için `postcode`/`alnum` normalizasyonu (harf harf ve rakam rakam söylenen "S W one A…" → "SW1A1AA"), `company_number` için harf+rakam desteği. Şu an `text` tipi ham geçiyor; yanlış cevap sayılır ve 3 hak çabuk biter.
10. **Lint'te zorunlu alan eksikse build ÇÖKÜYOR.**
    - `lint` "zorunlu alanı eksik" → `RuntimeError` → agent hiç oluşmuyor.
    - Gizli openapi'ye fazladan bir zorunlu alan eklenirse (ör. create_promise'e `currency`, close_call'a `note`) sonuç 0 puan olur.
    - Düzeltme: `tool_fields` + spec'te `tool_constants` (sabit değer) ya da model-dolduran alan. Lint bunu uyarıya çevirsin, deploy devam etsin.
11. **Spec'te Literal ve sabit seçenekler dar.** Pydantic hatası 2 retry'dan sonra build'i düşürür.
    - `Callback.days` sadece today/next_business_day. Gizli brief'te "within N business days" ya da güne göre saat aralığı olabilir.
    - `Attempt.amount` sadece full/floor. Yüzde ya da yarım tutar desteklenmiyor.
    - Floor sadece "üründeki bir alan". "past_due'nun %X'i" ya da sabit minimum tutar desteklenmiyor.
    - Deadline sadece "N. iş günü". Takvim günü, ay sonu ya da sabit tarih desteklenmiyor.
    - Düzeltme: bu alanları genişlet (`floor_rule: field|percent|fixed`, `deadline_rule: business_days|calendar_days|end_of_month`, `callback.days: business_days:N`). Ayrıca `ask_json` son hatada "gevşek" moda düşsün: bilinmeyen değeri en yakın desteklenen değere çevir ve `unmapped`'e yaz. Build asla çökmemeli.
12. **Tarihle yürürlüğe giren memo değişiklikleri.**
    - Ham brief'te "memo X'i değiştirir" var. Değişiklik "1 Kasım'dan itibaren" gibi bir tarihe bağlı olabilir.
    - Testler birden fazla `now` gününde koşuyor. Şu an extract prompt'u tek değer seçip diğerini `unmapped`'e yazıyor; bu, günlerin bir kısmında yanlış sonuç demek.
    - Düzeltme: bant, tatil, callback ve floor için `effective_from` override listesi. Runtime `now`'a göre seçer.
13. **Doğrulanmış müşteri için callback yok.**
    - Callback sadece üçüncü kişi yolunda var. Müşteri "şu an müsait değilim, sonra arayın" derse opener ve negotiate'te transition yok.
    - Gizli brief'te muhtemel bir aile (outcome tablosu "another outcome table").
    - Düzeltme: spec'e `customer_callback` (stage + outcome) ekle; propose_callback tool'unu opener/negotiate'e koşullu ekle.
14. **Kayıt modeli toplu.** Promise'ler sadece en sonda, tek onaydan sonra kaydediliyor.
    - Gizli brief "her ürünü onaylanınca hemen kaydet" ya da "transferden önce kaydedilenler kalır" (B kural 10) derse tasarım uymaz.
    - Spec'e `record_mode: batch|per_product` eklenip per-product modunda kayıt zincirinin negotiate'ten ara ara çağrılması gerekir. Önce gizli brief türünü düşünerek düşük maliyetli bir yol seç.
15. **Sabit metin ve sayılar.**
    - `opener_task`/`identity_task` "second ask" ve "second time" diyor; `opening.max_asks` ve `identity.decline_close_after` kullanılmıyor.
    - `note_after` tek retry'ı sabit kodluyor.
    - `spoken_date`, gün/ay adları ve sayı kelimeleri sadece İngilizce (brief dili İngilizce dışında olursa).
16. **Tool hata yolları.**
    - `verify_identity` 500 dönerse `id_after` müşteriye "That does not match our records" der. Bu yanlış ve dürüstlük ihlali. 500/ok:false+error için ayrı mesaj ve `retries=1` olmalı.
    - `close_call` `maxRetries=0`: bir 500 = vaka kaybı. 2 olmalı.
    - `transfer_to_agent`/`schedule_callback`/`add_note` hatasında kapanış hâlâ "başarılı" outcome'la gidiyor. Kit faults alanı sadece create_promise'te görüldü; gizli vakalarda başka tool'larda olabilir.
    - create_promise cevabında `ok` alanı yoksa (B.8'e bağlı) her kayıt başarısız sayılır ve `service_error`'a düşer.
17. **Snekbox bağımlılığı.**
    - Çağrı başına ~8–12 code exec var. Kesintide `end_fallback` close_call'sız kapanıyor.
    - Close node'larının outcome'u statik (close_final hariç). Fallback, outcome'u baked bir close_call api node'una gitsin.
    - B.4'teki node azaltımı riski de azaltır.

### P2: Daha küçük ama gerçek riskler
18. `ARG_x = '''{{x}}'''`: model argümanı `'''` içerir ya da `'` veya `\` ile biterse snippet SyntaxError verir ve tool sessizce başarısız olur. `tool_arg` önce `vars`'a bakıyor ama F-03'e göre asıl yol ARG. Kaçışlı bir şablon kullanılmalı.
19. Hafta sonu ve tatil `now`'unda `prep_callback` "today"yi iş günü olmasa da ekliyor.
20. `digits_from_speech` "double four" / "triple" tanımıyor (`in_words` ve İngiliz konuşması).
21. `amount` create_promise'e metin olarak gidiyor ("540.0"); mock kabul ediyor, başka bir mock reddedebilir. `coerce_body` tanımlı ama hiç kullanılmıyor.
22. Workflow ~322 KB (lint sınırı 400 KB). Uzun bir gizli brief, RT'nin her snippet'e gömülmesiyle sınırı aşabilir. F-08'de sadece 235 KB test edildi.
23. Dokümanlar koddan geri kaldı: `docs/05` close_call'ı hâlâ lifecycle olarak anlatıyor; `00` ve `07` durumu eski.
24. Persuasion sayımı tamamen modelde. PUB-12 3/3 geçti ama stillerle ölçülmedi.

### Test kapsamı boşlukları
- 5 konuşma stilinin hiçbiri ölçülmedi. Finalde müşteriler bu stillerde konuşacak.
- HEAD (SEND close, yeni day_table) için hiç `--reps 3` koşusu yok.
- Varyant provası (farklı alan adlı openapi, farklı kimlik soruları, ham materyal formatı) yapılmadı (F6).
- LLM çıkarımı sadece Brief A'da denendi. A+B birlikte ve ham materyal formatında denenmedi.

---

## C. Düzeltme sırası (onaydan sonra)

1. **P0 güvenlik ağı:** lifecycle close_call yedeği + erken `close_outcome` + `close_call` retries + fallback close (1, 16, 17). F-09 deneyi: çift close_call ledger'da nasıl görünüyor.
2. **Read-back/onay redesign'ı** (2, 3) + `pieces` birleştirme (5) + verify 500 mesajı (16). Önce birim testleri.
3. **Gecikme azaltımı** (4): id_init ve id_result'ı kaldır, "one moment" tts'leri ekle. Kayıt zincirini sadece ölçüm hâlâ >10 sn gösterirse aç.
4. **Openapi esnekliği** (7, 8, 9, 10): rol eşlemeleri, postcode/alnum normalizasyonu, lint'in çökmemesi. Varyant fixture'ı: `tests/fixtures/` altında alan adları değiştirilmiş bir openapi kopyası (test içinde, brief değeri yok).
5. **Spec genişletme** (11, 12, 13), ardından 14 için karar.
6. P2 maddeleri ve doküman güncellemesi (00, 05, 07, 10 §9).

Her adım: `uv run pytest` + ruff → `--spec` ile kur → `fbb cases --only` → `--reps 3` → stiller. CLAUDE.md gereği her başarısızlığın transcript'i okunmadan prompt değiştirilmez.

## D. Açık deneyler
- **F-09:** normal kapanıştan sonra lifecycle close_call çalışırsa mock ne döner, ledger'da `calls[-1]` ve outcome ne olur?
- **F-10:** api_request mapping değişkenleriyle doğrudan route (`"true"`/`"True"` OR, `"0"` equals) güvenilir mi?
- **F-11:** api_request `on_enter` tts + passthrough sırasında müşteri konuşursa ne oluyor?
- **F-07:** kredi tüketimi hâlâ ölçülmedi (bütçe: kaç tane `--reps 3` koşabiliriz).

## E. Doğrulama
- L0: `env -u VIRTUAL_ENV uv run pytest`, `uv run ruff check src tests`. Yeni testler: partial birleştirme, readback üretimi, auto-clamp, alan rol eşlemesi, varyant openapi'de lint'in çökmemesi, `test_deterministic`, `test_no_hardcoded_brief`.
- L1: `build-agent … --spec tests/fixtures/spec_ab.json --no-deploy`. Ayrıca varyant openapi ile no-deploy, crash olmamalı.
- L4: `fbb cases <slot> --brief A --reps 3` ve `--brief B --reps 3`. Ardından her stil için `--style X` (en azından `pieces`, `in_words`, `asks_back`). Hedef: medyan en yavaş tur <10 sn, A ≥9/10 ve B 3/3 pass^3.
- Sonuçlar `docs/10` §9 tablosuna, platform dersleri `docs/02`'ye yazılır.

---

## F. Uygulama durumu (10 Ekim, ~20:35 TR)

Her madde kodda, birim testte ve (mümkünse) platformda. "Ölçüm bekliyor" = `fbb cases` için mock'a erişim gerekiyor (bu makineden `*.workers.dev` erişilemiyor).

| # | Durum | Ne yapıldı | Nerede / test |
|---|---|---|---|
| 1 | ✅ kod, ölçüm bekliyor | close_call kapanış node'larında (hook'suz, retries 2) + üst seviye lifecycle yedeği. Pre-hook: `close_r_ok` doluysa URL boşaltılır (istek gitmez), değilse gövde `decide_close` ile kurulur (reason kuralı dahil). URL boşaltma çalışmasa bile ikinci çağrı birincinin aynısı. Erken outcome: üçüncü kişi → no_callback, hesap hazırlanınca → hangup_verified, her kayıttan sonra güncel durum. Platformda pre-hook'un saklandığı doğrulandı | `graph.py` (backup), `closing.lifecycle_close`, `test_lifecycle_close_backup`, `test_third_party_sets_early_outcome` |
| 2 | ✅ | `negotiate_fix` llm on_enter'ı sadece biçim hatası ve read-back reddi için (müşteriye kayıt hakkında bir şey söylememe talimatıyla). Müşteriye söylenecek ret cümlesi kodla üretilip `negotiate_fix_say` tts ile söyleniyor | `validate.adjust_promise`, `test_invalid_proposal_is_said_by_tts` |
| 3 | ✅ | `propose_results` → kod doğrular ve düzeltir (deadline'a çekme, iş gününe kaydırma, borçtan fazla tutarı borca indirme) → read-back cümlesi (ürün, tutar, hafta günüyle tarih, düzeltme notu, onay sorusu) → `readback` node'u tts → routing: evet → kayıt, hayır/değişiklik → `readback_reset` → müzakere. Model artık read-back yapmıyor ve müşterinin söylediği tarihi olduğu gibi veriyor | `validate.py`, `flow.propose_results`, `test_readback_*`, `test_validate_moves_weekend_and_deadline` |
| 4 | ✅ (kayıt zinciri hariç) | `identity_check` ve `id_result` kaldırıldı; soru başına sabit node, sonuç cevap alanlarıyla route; mutsuz yollar tek `id_fix` + `reask`. Sabit kapanışlar ve transferler kodsuz. "One moment, please." tts: ilk verify, fetch_account, ilk kayıt. Kayıt zinciri açılmadı (C.3: ölçüm >10 sn gösterirse) | `graph.py`, `test_identity_happy_path_has_no_code_nodes`; chat'te submit exec 0,2–0,7 sn |
| 5 | ✅ | `id_partial` birleştirme (rakam ve tarih parçaları), yılsız/günsüz tarih = partial, "cevap + soru" aynı mesajda (sondaki noktalama) okunuyor; ipucundan sonra sadece ay söylenirse gün önceki cevaptan | `normalize.combine_answer/date_parts`, `test_identity_pieces_are_joined`, `test_swap_hint_month_only_answer`; chat'te doğrulandı |
| 6 | ✅ kod, A/B ölçümü bekliyor | Çıkarım prompt'u: açılış "we record this call" biçiminde, "recorded" kelimesi yok (agent_role dahil); altın spec'ler güncellendi; lint açılışta "recorded" görürse uyarır | `prompts/extract.md`, `lint.py`, fixture'lar |
| 7 | ✅ | `spec.response_fields` + `resolve_response_fields` (openapi cevap şemasından en yakın alan) + `cross_check`; LLM özetine "returns:" satırları eklendi | `test_variant_openapi_does_not_crash` |
| 8 | ✅ | verify alanları aynı yapıyla (`ok/verified/all_verified/wrong_answers_left/hint`) | aynı test |
| 9 | ✅ | Soru başına ayrı gövde alanı ve `verify_mode=all_at_once`; `postcode`/`alnum` normalizasyonu (harf harf, NATO alfabesi, "double"), `example`'a göre boşluk | `test_per_question_body_fields`, `test_postcode`, `test_alnum_and_partial` |
| 10 | ✅ | Eksik zorunlu alan lint uyarısı; `spec.tool_constants`; openapi `default` ve tek değerli enum otomatik dolduruluyor | `graph.body_for`, varyant testi |
| 11 | ✅ | `deadline_rule`, `floor_rule`, `attempts.amount` (percent/fixed), `callback.days` (`business_days:N`) ve `hours_by_weekday`; `llm.lenient_validate`: son çare olarak desteklenmeyen değeri atar/çevirir ve `unmapped`'e yazar | `test_floor_and_amount_rules`, `test_deadline_rules` |
| 12 | ✅ | `spec.overrides` (`effective_from/until`), runtime `effective_rt` (`prep_account`, `prep_callback`, doğrulama, callback kontrolü) | `test_overrides_by_date` |
| 13 | ✅ | `spec.customer_callback` (tetikleyici, soru, outcome, pencere, aşama); `cust_cb*` node'ları opener/kimlik/negotiate'ten | `test_customer_callback` |
| 14 | ✅ | `recording.mode=per_product`: her onaydan sonra kayıt, `negotiate_more` ile sıradaki ürün; notlar en sonda (transferde not yok kuralı korunur); duyurulmuş kayıtlar kapanışta tekrarlanmaz | `test_per_product_mode` |
| 15 | ✅ (sayı kelimeleri hariç) | `opening.max_asks`, `identity.decline_close_after` (kodda sayaç), not tekrar sayısı `recording.retries`; gün/ay adları ve kodun ürettiği bütün cümleler `spec.locale`'de. İngilizce dışı sayı kelimeleri okunmuyor (G-04) | `test_opener_uses_max_asks` |
| 16 | ✅ | verify 500 → "could not check" (yanlış denmez), verify retries 1; close_call retries 2; transfer/callback/not retries 1; callback hatasında `close_no_callback`; `ok` alanı yoksa zarfın `status`'u | `test_identity_wrong_swap_and_service_error`, varyant testi |
| 17 | ✅ | Code node guard'ı → `fallback_close[_nr]` (baked `{{close_outcome}}` ile close_call); sabit kapanışlar ve transferler kodsuz | `test_every_code_node_has_failure_guard`, `test_static_closes_have_no_code` |
| 18 | ✅ | `ARG_x = r'''{{x}}~'''`: tırnak/ters bölüyle biten argüman sözdizimini bozmaz (içinde üç tek tırnak geçmesi hâlâ risk) | `test_model_argument_with_quotes_does_not_break_snippet` |
| 19 | ✅ | `today` sadece iş günüyse | `test_callback_today_only_on_business_day` |
| 20 | ✅ | "double"/"triple" | `test_identity_pieces_are_joined` |
| 21 | ⚠️ bilinçli karar | `rec_amount` kodda sayı olarak yazılıyor ve `{{rec_amount:json}}` ile gidiyor; pre-hook ile tip çevirme eklenmedi (her kayıtta +1 code exec ve kod servisine bağımlılık). Kullanılmayan `coerce_body` kaldırıldı. Bir sonraki koşuda `fbb call` ile gövdedeki tip kontrol edilecek | `flow.rec_pick` |
| 22 | ✅ | Snippet'ler yorumsuz/docstring'siz (`ast.unparse`), RT sadece kullanılan anahtarlarla gömülü; kimlik varyantları tek `reask`'te. 43 node ≈300 KB (önce 322 KB), test sınırı 340 KB | `emit.prune_rt/_compact`, `test_workflow_lints_clean` |
| 23 | ✅ | 00, 02, 03, 04, 05, 06, 07, 08, 10 güncellendi | |
| 24 | 🟡 | Sayım hâlâ modelde. PUB-12 0/3–1/3 düştü (ürün başına 'bugün' tekrar soruldu, late bandında 2. deneme atlandı) → negotiate görevine genel ikna kuralları; sonra B 3/3 pass³. A'da PUB-06 1/3 benzer bir sapma (1. deneme atlandı) | `texts.negotiate_task` |

**Ölçüm (VPN ile, 20:41–20:56):** A 9/10 pass³ (önce 3/10), B 3/3 pass³ (önce 2/3); en yavaş tur medyanı 1–2 sn. Ayrıntı `10_TEST_REHBERI.md` §9. Ölçüm sırasında bir bug bulundu ve düzeltildi: `id_take_answer` `id_q`'yu yazmıyordu (yanlış 2. cevaptan sonra 1. soru soruluyordu).

**Açık deneyler:** F-09 ✅ (mock'a doğrudan, bkz. 02). F-11: lifecycle yedeğinin URL boşaltmayla iptal edildiği platformda görüldü (`Missing required field: url`, ledger'da tek close_call). F-10 kısmen ✅ (belirteçle route ve hata dalı chat'te çalıştı). F-07 ölçülmedi.

**Doğrulama:** L0 ✅ (`pytest` 83 test, ruff temiz). L1 ✅ (`make local-a local-b`, varyant openapi birim testinde). L2 ✅ (`mert-a`, `mert-b`: dryRun, kayıt, 0 fark, export). L3 kısmen (elle değişkenlerle chat). L4 ⏳.

**Ek bulgu (20:36, LLM çıkarımı ile L1):** Brief A tam build (`--no-deploy`, 2 dk 18 sn, $1.82) geçerli spec üretti: 0 uyumsuzluk, lint temiz, açılış "We record this call.". Ama `agent_role` aramanın amacını içeriyordu ("state the debt, get a payment promise") ve bu satır system prompt'la her adımda, doğrulamadan önce de modele gidiyor. Düzeltme: çıkarım prompt'una `agent_role` kuralı, lint'e "system prompt'un ilk satırında doğrulama öncesi yasaklı kelime" uyarısı.

**Stil koşuları (21:08–22:53):** Bulunan ve düzeltilen bizden kaynaklı hatalar (hepsine test): rakam rakam söylenen yıl; iki/üç parça yıl ("19"+"88"); eksik cevapta sistemin eksik kısmı sabit cümleyle sorması (`id_fix` → `reask`, model artık beklemiyor); ret açıklamasından sonra doğru sorunun tekrar sorulması. Model davranışı için genel prompt kuralları: parçalı tutar/tarih, ret sayısına göre açık deneme senaryosu (`product_facts`), teklifin tekrar edilmemesi. Son durum: in_words A 9/10, B 3/3; pieces A 9/10, B 2/3. Açık: PUB-06 (floor ikinci kez söyleniyor, 2/3) ve PUB-12 (ikna sayımı) model kaynaklı ve tekrarlıyor; asks_back/corrects/talkative düzeltmelerden sonra yeniden ölçülmedi. Kalıcı çözüm adayı: ikna denemelerini koda taşımak (modelin `product_refused(pid)` çağırdığı, deneme cümlesini kodun ürettiği bir adım).
