# 04: PolicySpec

Şema: `src/fbb/spec.py` (pydantic, `extra="forbid"`). Altın örnekler: `tests/fixtures/spec_a.json`, `spec_ab.json` (elle, brief'ten). LLM bu şemayı structured output ile doldurur. `cross_check` enum değerlerini openapi ile karşılaştırır.

## Bölümler

| Alan | İçerik | Kullanıldığı yer |
|---|---|---|
| `bank_name`, `agent_role`, `language` | kimlik | system prompt |
| `call_variables` | `customer_id` ve `now` değişken adları, hitap şablonu, bütün değişkenler | baked `{{…}}`, `parse_now`, kapanış cümlesinin doldurulması |
| `opening` | ilk cümle, onay sorusu, kabul edilen ve edilmeyen onaylar, doğrulama öncesi yasaklı kelimeler, robot/scam/bilinmiyor cevapları, `unclear` outcome'u | `opener` node'u, system prompt, lint |
| `third_party` | ulaşma sorusu, callback penceresi (günler, saatler, uçlar dahil mi, `now` sonrası mı, tekrar hakkı), 4 outcome, taziye cümlesi, kurallar | `third_party*` node'ları, `check_callback` |
| `identity` | sorular (alan, cümle, cevap tipi), sayısal tarih sırası, en fazla yanlış sayısı, swap hint, başarısızlık/ret cümleleri ve outcome'ları | `id_*` fonksiyonları, `ask_identity` |
| `disclosure` | doğrulama sonrası giriş cümlesi, ürün cümlesi şablonu, ürün tipine göre ifade ve floor alanı | `prep_account` |
| `calendar`, `bands` | iş günleri, tatiller; days_late aralığı → deadline (iş günü), deneme sayısı | `dates.py`, `facts.py`, `validate.py` |
| `negotiation` | ilk soru (tek/çok ürün), deneme planı (`full`/`floor` × `end_of_week`/`deadline`/…), kurallar, yasak teklifler | `facts.py` (deneme tarihleri), `negotiate` görevi |
| `confirmation`, `recording` | onay sorusu, kayıt yeniden deneme sayısı, başarı ve başarısızlık cümleleri, başarısızlık durumu | `negotiate` görevi, `rec_after`, `closing_speech` |
| `transfers[]` | id, kuyruk (openapi enum'u), tetikleyici, cümle, önce sorulacak soru, aşamalar | `transfer_<id>` node'ları ve tool-call transition'ları |
| `statuses[]` | promise'siz bitiş durumları (= not sebebi = kapanış sebebi) | `submit_results` doğrulaması, notlar, kapanış |
| `multi_product` | açık mı, kurallar, notlar açık mı, transferde not yok kuralı | `negotiate` görevi, `note_pick` |
| `closing` | outcome eşlemesi, kuyruk → reason, reason almayan outcome'lar, telefon kapanınca yedek outcome, veda | `decide_close`, `apply_close_body` |
| `money` | para birimi ön ek/son ek | `fmt_money` |
| `tool_fields` | openapi alan adları rol adlarından farklıysa eşleme | `graph.field_map` |
| `tool_constants` | rollere uymayan zorunlu istek alanlarına sabit değer (ör. para birimi) | `graph.body_for` |
| `response_fields` | cevap alanı adları (ok, verified, all_verified, wrong_answers_left, hint, products, product_id, product_type, past_due, days_late) | verify/fetch mapping'leri, `facts.field_name` |
| `overrides[]` | tarihli memo değişiklikleri: bands, holidays_add/remove, weekdays, callback, floor_rule, attempts | `dates.effective_rt` |
| `customer_callback` | müşterinin kendisi sonra aranmak isterse: tetikleyici, soru, outcome, pencere, aşamalar | `cust_cb*` node'ları |
| `recording.mode` | `batch` (tek onay, sonra kayıt) ya da `per_product` (her ürün onaylanınca kayıt) | `next_step`, `negotiate_more` |
| `locale` | kodun ürettiği cümleler (read-back, "one moment", düzeltme notları) ve gün/ay adları | `say`, `spoken_date` |
| `identity.verify_mode`, `questions[].example` | `each` / `all_at_once`; cevap biçimi örneği (postcode boşluğu) | verify node'ları, `normalize_answer` |
| `bands[].deadline_rule`, `disclosure.floor_rule`, `attempts[].amount`, `callback.days`/`hours_by_weekday` | genişletilmiş kurallar (aşağıda) | `deadline_for`, `floor_amount`, `attempt_amount`, `callback_days` |

**Kural biçimleri:** `deadline_rule`: `business_days:N` · `calendar_days:N` · `end_of_month` · `date:YYYY-MM-DD` (boşsa `deadline_bd`). `floor_rule`: tip (ya da `*`) → `field:<alan>` · `percent:N` · `fixed:X`. `attempts[].amount`: `full` · `floor` · `percent:N` · `fixed:X`. `callback.days`: `today` (sadece iş günüyse) · `next_business_day` · `business_days:N`. `answer_type`: `date` · `digits:N` · `year` · `postcode` · `alnum` · `text`.

LLM çıktısı şemaya uymazsa iki kez düzeltme istenir; sonra `llm.lenient_validate` desteklenmeyen değeri atar (varsayılan kullanılır) ya da desteklenen ilk değere çevirir ve notu `unmapped`'e yazar. Build bu yüzden çökmez.
| `general_rules`, `unmapped` | her yerde geçerli kurallar, yerleştirilemeyenler | `negotiate` görevi |

## Brief A → spec eşlemesi (kural numaraları)

| Brief A kuralı | Spec yolu |
|---|---|
| 1–2 açılış, onay sorusu | `opening.first_sentence`, `opening.confirm_question`, `forbidden_before_verification` |
| 3 onay kuralları, ikinci kez sorma, `unclear` | `opening.accepted_confirmations/not_confirmations/max_asks/unclear` |
| 4 robot, 43 scam, 44 bilinmeyen | `opening.robot_answer/scam_answer/unknown_answer` |
| 5–10 üçüncü kişi | `third_party.*` |
| 11–15 kimlik | `identity.*` (DMY, `max_wrong_total` 3, `swap_hint` `day_month_swapped`, ret açıklaması, 2 ret → declined) |
| 16–17 borcun söylenmesi | `disclosure.*` |
| 18 bantlar, iş günleri, tatiller | `bands`, `calendar` |
| 19–23 tarih kuralları | `negotiation.rules` + kod (`adjust_promise`, `day_table`) |
| 24–27 tutar ve floor | `disclosure.floor_field`/`floor_rule`, `negotiation.rules`, `adjust_promise` |
| 28–31 ikna denemeleri | `negotiation.first_ask_single`, `negotiation.attempts` |
| 32 hardship | `transfers[support]`, `statuses[hardship]`, kural |
| 33 yasak teklifler | `negotiation.forbidden_offers` |
| 34–36 onay ve read-back | `confirmation.*` + kod (`readback_text`, `readback` node'u) |
| 37–38 kayıt, hata, SMS cümlesi | `recording.*` + engine kayıt döngüsü |
| 39 paid, 40 dispute | `statuses[paid]`, `statuses[dispute]` |
| 41 restructuring, 42 insan | `transfers[restructuring]`, `transfers[human]` (`ask_first`) |
| 45 konuşmak istemiyor | `statuses[refused]` / doğrulama öncesi `close_id_declined` |
| 46–47 kapanış tablosu, veda | `closing.*` |

Brief B'nin 11 kuralı `multi_product.rules`'a girer ve şunları açar: `notes_enabled`, `first_ask_multi`, ürün başına bant ve deneme (kod zaten ürün başına hesaplar). Kapanış: hepsi `paid` ise `paid`; değilse `get_account` sırasına göre ilk `paid` olmayan durum (`decide_close`).

## LLM çıkarımı ile altın spec (10 Ekim, Brief A)
Takvim, bantlar, denemeler, floor ve ifade şablonları, callback penceresi, kapanış eşlemesi ve onay soruları **birebir aynı** çıktı.

Farklar ve yapılan düzeltmeler:
- `success_sentence`'e "Your promise is recorded." eklemişti. Bu tekrar yaratıyordu; prompt'a ve alan açıklamasına "sistem zaten söyler" notu eklendi.
- Veda cümlesi `{title} {last_name}` içeriyordu. `closing_speech` artık çağrı değişkenleriyle dolduruluyor.
