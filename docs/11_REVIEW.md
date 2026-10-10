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
