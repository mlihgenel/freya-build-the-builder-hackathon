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
| F-08 | ~235 KB'lık workflow (snippet'ler gömülü) kaydediliyor mu? | boyut | ✅ 35 node, ≈235 KB workflow; dryRun + kayıt + geri okuma: 0 fark, lifecycle tool korunmuş |

Yedek planlar `08_KARARLAR_VE_ACIK_SORULAR.md` dosyasında.

## Ölçümler (10 Ekim)
- Node gecikmesi: code node 0.2–1.1 sn, api_request 0.1–0.4 sn. Müşteri onayı → veda cümlesi ≈ 4 sn (kayıt + not + kapanış zinciri).
- `/chat/message` uzun bir passthrough zincirinde **502** dönebilir, ama çağrı arka planda tamamlanıyor. Chat smoke'ta 502 hata sayılmaz; `get_call` ile sonuca bakılır.
- PUB-01 uçtan uca (chat): ledger beklenenle birebir aynı (promise p1 420 2026-10-14, outcome promise, reason null, son çağrı close_call).
