# 02: Freya platformu: kesin bilgiler ve deneyler

Kaynak: `kit/docs/workflow-format.md`, `tools-and-code.md`, `api.md` (kit v3). Faz 0 deney sonuçları bu dosyaya eklenir.

## Kitten gelen kesin bilgiler (tasarımı belirleyenler)

**Model çağrıları ve tool'lar**
1. **Her turda 3 ayrı model çağrısı yapılır:** extraction → routing → dialogue.
   - Routing sadece transition açıklamalarını görür; `task_message` routing'i etkilemez.
   - Dialogue modeli sadece o node'un `tools` listesindeki tool'ları çağırabilir.
2. **`tools` sadece conversation node'unda, `pre_actions` sadece api_request/code node'unda kalır.** Yanlış yerdeki alanları platform hata vermeden siler. Bu yüzden build sonrası workflow geri okunur ve karşılaştırılır (`build._diff_stored`).
3. **`default` = baked değer.**
   - `{{var}}` node'a girerken çözülür. Çözülmeyen alanı model doldurur.
   - `const` hiçbir değer göndermez.
   - Engine'in kendi yaptığı çağrılarda (pre_actions ve lifecycle) tek placeholder'lık bir alan çözülmezse alan **hiç gönderilmez**.

**Kod ve hook'lar**

4. **Code node:**
   - `vars` sözlüğünü okur ve yazar. Sadece `json`, `re`, `datetime` modüllerinin çalıştığı doğrulanmış.
   - Kodda `{{`/`}}` yazılmamalı. Snippet hata fırlatmamalı.
   - Sonuç `data: null` olarak döner; çıktı sadece `vars` üzerinden çıkar.
5. **api_call sonucu bir zarfın içinde gelir:** `{status, data, message, status_code, header}`.
   - Mapping yolları `data.` ile başlar.
   - Boolean değerler metin olarak gelir (`"true"`/`"True"`). Bu yüzden boolean'a göre route edilmez.
   - Her sonuç ayrıca `<tool>_response.data.*` anahtarlarıyla düzleştirilmiş olarak değişken tablosuna yazılır.
6. **Post-hook (`post_process_code`):**
   - `result` envelope'unu değiştirebilir; `data` içine eklenen alan modele ulaşır.
   - `vars`'ı okuyup yazabilir (10 Ekim testi).
   - Pre-hook'ta `vars` ve `config` adları vardır.

**Tarih ve değişkenler**

7. **Platformun tarih extraction'ı ve `{{system.*}}` tarihleri gerçek saati kullanır.** Bizim tarihlerimiz `now` çağrı değişkeninden code node'unda hesaplanır.
8. **Prompt'a yerleştirilen tarih değişkenleri seslendirme için biçimlendirilir.** ISO tarihler bu yüzden çok satırlı blokların içinde verilir.
9. **`context_variables` kaydedilirken kaybolabiliyor.** Kullanılmıyor; bilgiler prompt'a `{{değişken}}` olarak yazılıyor.

**Node ve çağrı yapısı**

10. **End-call node:** veda cümlesi `terminal.spoken_message`'dan gelir, `on_enter` silent olur. `endedReason` = terminal `function.name`.
11. **Lifecycle tool (`alwaysRunsAt: ["end_of_call"]`):**
    - Modele görünmez ve çağrı bittikten sonra çalışır.
    - Çözülmeyen `{{var}}` kalırsa parametreleri bir model çağrısı doldurur.
    - Hatalı tanımlanmış bir lifecycle tool sessizce düşürülür.
    - Kitin örnek agent'ı `close_call`'ı bu şekilde kullanıyor.
12. **`max_node_turns` varsayılan olarak 10.** Bu sınır aşıldığında `max_turn_transition` yoksa hiçbir şey olmaz.

**Bilinen agent hataları ve API kuralları**

13. **Tool sonucundan sonra agent susabilir ya da olumsuz bir sonucu görmezden gelebilir.** Kit bunu belgelemiş. Çözüm: sabit tts cümleleri, engine'in yaptığı yazmalar, `what_to_do_next`.
14. **REST:**
    - Tarayıcı benzeri bir `User-Agent` şart.
    - `PUT` sadece kaydeder; ayrıca publish gerekir.
    - `agent_config` gönderilmez.
    - `null` değer yasak.
    - `dryRun=true` workflow'u kaydetmeden doğrular.

## Faz 0 deneyleri (sonuçlar eklenecek)

| F | Soru | Tasarımdaki yeri | Sonuç |
|---|---|---|---|
| F-01 | Lifecycle `close_call` pre-hook'u `vars`'ı görüyor mu? | close_call pre-hook | ✅ (10 Eki) PUB-01 chat'inde close_call gövdesi `{outcome: promise, customer_id}` ile gitti; `reason` silinmişti; ledger `reason: null` |
| F-02 | Müşteri telefonu kapatınca `end_of_call` çalışıyor mu? | kapanış | ⏳ |
| F-03 | Model-çağrılı `code_exec` tool'unun argümanları nereye düşüyor (`ARG_x` şablonu / `vars['x']` / `<tool>_args.x`)? | `submit_answer`, `submit_results`, `propose_callback` | ✅ `code` alanındaki `{{results}}` şablonu modelin argümanıyla dolduruluyor (`ARG_results = 'p1:420:2026-10-14'`). Argüman ayrıca `args.params.results` içinde görünüyor |
| F-04 | Bir code_exec tool'unun yazdığı `vars` aynı turda route'u tetikliyor mu? | `id_ready`, `commit`, `cb_state` route'ları | ✅ submit_answer/submit_results sonrası `id_ready`/`commit` route'ları aynı turda tetiklendi |
| F-05 | Passthrough code ↔ api_request döngüsü (kayıt kuyruğu) sorunsuz mu? | `rec_pick` ↔ `record_promise` | ✅ rec_pick → record_promise → rec_after → rec_pick → note_pick → close_final zinciri tek turda çalıştı (≈3 sn) |
| F-06 | tts içinde çok değişkenli ve çok satırlı metin doğru okunuyor mu? | `{{id_say}}`, `{{debt_statement}}`, `{{closing_speech}}` | ✅ `{{debt_statement}} {{first_ask}}` ve `{{closing_speech}}` doğru okundu |
| F-07 | Bir simülasyon ve bir chat ne kadar kredi harcıyor? ($100 workspace kredisi) | test bütçesi | ⏳ |
| F-08 | ~235 KB'lık workflow (snippet'ler gömülü) kaydediliyor mu? | boyut | ✅ 35 node, ≈235 KB workflow; dryRun + kayıt + geri okuma: 0 fark, lifecycle tool korunmuş. 10 Eki 20:30: 43 node ≈300 KB (A) ve ≈305 KB (A+B) de 0 farkla kaydedildi. 11 Eki: 45 node, 359 KB (A+B, LLM spec) 0 farkla kaydedildi. Boyut sınırı (11 Eki, dryRun): 450 KB, 700 KB ve 1,2 MB workflow `valid: true` → lint'te boyut artık hata değil uyarı (400 KB üstü) |
| F-09 | Normal kapanıştan sonra lifecycle close_call çalışırsa ledger ne olur? | kapanış yedeği | ✅ (10 Eki, mock'a doğrudan): ikinci close_call `ok:false, "the call is already closed"` döner; ledger'daki outcome/reason ilk çağrınınki kalır; `calls[-1]` yine close_call. Yani yedek normal yolda iptal edilemese de zararsız. Ayrıca `reason: ""` gönderilen close_call reddedilir (`this outcome needs one of these reasons`) → boş reason asla gönderilmemeli (tasarım göndermiyor) |
| F-10 | api_request mapping değişkenleriyle doğrudan route güvenilir mi? | kimlik route'u | ✅ kısmen (10 Eki 20:31 chat): `id_go=ask_q0:0` belirteci aynı turda `verify_q0`'a götürdü; HTTP hatasında mapping boş kaldı ve passthrough varsayılanı (`id_fix`) çalıştı. `"true"` başarı dalı gerçek bir müşteriyle henüz denenmedi |
| F-11 | api_request `on_enter` tts + passthrough sırasında müşteri konuşursa? | "One moment" cümleleri | ⏳ Kit belgesi passthrough node'da kısa tts'i öneriyor. Chat'te tts söylendi ve akış devam etti; araya konuşma denenmedi |

Yedek planlar `08_KARARLAR_VE_ACIK_SORULAR.md` dosyasında.

## Ölçümler (10 Ekim)
- 20:31 chat (yeni graf): `submit_answer` code exec 0,2–0,7 sn; kimlik cevabından sonraki tur ≈1 sn (eskiden 2 code node).
- Node gecikmesi: code node 0.2–1.1 sn, api_request 0.1–0.4 sn. Müşteri onayı → veda cümlesi ≈ 4 sn (kayıt + not + kapanış zinciri).
- `/chat/message` uzun bir passthrough zincirinde **502** dönebilir, ama çağrı arka planda tamamlanıyor. Chat smoke'ta 502 hata sayılmaz; `get_call` ile sonuca bakılır.
- **Chat'te açılış tts'i söylenmez (11 Eki):** chat müşterinin mesajıyla başladığı için ilk cevabı model `opener.task_message`'tan üretir ve cümleleri atlayabilir (Brief C'de kayıt cümlesi düştü; `on_enter` metni değiştirilse de cevap aynı kaldı). Sesli simülasyonda (finaldeki mod) `on_enter` tts birebir söylendi (prova-c PUB-02). Açılış kontrolü chat'le değil simülasyonla yapılır.
- **Takılan simülasyon (11 Eki 12:19):** çağrısı hiç başlamayan bir simülasyon 8+ dk `running` kaldı; dashboard'da hiçbir şey görünmedi. Belgelenmemiş `POST /api/v2/simulations/<id>/cancel` iptal etti (durum `completed` oldu, vaka 'no verdict' sayıldı). `kitapi` bekçisi 10 dk'yı aşan simülasyonu kendisi iptal eder. Simülasyon API'si 11:30 civarı dakikalarca 502/503/504 verdi → GET'ler ~5 dk tekrar denenir.
- **Hakem tool adlarını okur (11 Eki):** `propose_callback(…20:00)` çağrısını 'pencere dışında callback kurdu' saydı; ledger'da callback yoktu. Tool `check_callback_time` olarak yeniden adlandırıldı. Aynı sebeple `next_offer(result='agreed')` 'promise kaydedildi' sayıldı (SC-01, ledger'da promise yok) → `check_offer_answer`. Model tool adları 'kontrol' bildirmeli; kayıt yalnız `create_promise`.
- PUB-01 uçtan uca (chat): ledger beklenenle birebir aynı (promise p1 420 2026-10-14, outcome promise, reason null, son çağrı close_call).
