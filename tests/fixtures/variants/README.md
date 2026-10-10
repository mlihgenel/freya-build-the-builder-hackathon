# Varyant provası (uydurma)

Gizli brief'lere benzeyen ama **uydurma** girdiler. Amaç builder'ın kırılmadan çalışıp çalışmadığını görmek. Buradaki hiçbir değer `src/` altına yazılmaz.

| Dosya | Ne değişiyor |
|---|---|
| `brief_c.md` | ham materyal tek dosyada (mail, poliçe, memo, kod listesi). Tarihli memo değişikliği, 3 bant, yüzde floor, farklı callback penceresi, farklı outcome/reason kodları |
| `openapi_c.json` | kimlik alanları `postcode`/`birth_year`, yanıt alanları yeniden adlandırılmış (`amount_due`, `minimum_due`, `identity_confirmed`, `attempts_left`), `create_promise`'e fazladan zorunlu `channel`, farklı enum'lar |

```bash
uv run build-agent tests/fixtures/variants/brief_c.md --tools tests/fixtures/variants/openapi_c.json --slot prova-c --no-deploy
```

## Sonuç: 10 Eki 22:12 (Sonnet, ~47 sn, ~$0.36)

Build **çöktü**: `lint hataları: record_promise: create_promise zorunlu alanı eksik: channel`. Agent oluşmadı.

Spec'in kendisi büyük ölçüde doğru: 3 bant, tatiller (memo'daki dahil), kodlar, callback penceresi, kimlik soruları, cümleler. Sessizce yanlış kalanlar:

| # | Sorun | Etki | Review |
|---|---|---|---|
| 1 | Fazladan zorunlu alan (`channel`) → lint `RuntimeError` | brief'ten 0 puan | P1-10 |
| 2 | Yanıt alanı adları (`amount_due`, `identity_confirmed`, `attempts_left`) spec'te yok, `tool_fields` boş, `cross_check` 0 uyumsuzluk dedi | borç 0, bant yanlış, kimlik hiç geçmez | P1-7, P1-8 |
| 3 | `product_wording`'te `{last4}`; openapi alanı `card_last4`. Şablon alanları openapi'ye karşı kontrol edilmiyor | "credit card ending {last4}" | yeni |
| 4 | Tarihli memo (soft bant 2026-11-02'den itibaren 8, öncesinde 10) → tek değer (8) seçildi | o tarihten önceki günlerde yanlış deadline | P1-12 |
| 5 | Overdraft floor = max(%25 × borç, `minimum_due`) ifade edilemiyor; sadece kural metninde | floor kodda yanlış | P1-11 |
| 6 | Callback "sonraki iki iş günü, aynı gün değil" → sadece `next_business_day` | ikinci gün reddedilir | P1-11 |
| 7 | Posta kodu `answer_type: text`, harf harf söylenen kod birleştirilmiyor | kimlik yanlış sayılır | P1-9 |

## Sonuç: 10 Eki 23:08 (pull sonrası, 0260109; Opus, 92 sn, ~$0.53)

Build **başarılı**: 43 node, lint 0, uyarı 0, spec 0 uyumsuzluk.

| # | Önceki sorun | Şimdi |
|---|---|---|
| 1 | `channel` zorunlu alanı build'i çökertiyordu | ✅ `tool_constants.create_promise.channel = phone_agent`, gövdede |
| 2 | Yeniden adlandırılmış cevap alanları | ✅ `response_fields`: `amount_due`, `identity_confirmed`, `attempts_left` |
| 3 | `{last4}` | ✅ `{card_last4}` |
| 4 | Tarihli memo | ✅ ana bant 10, `overrides` 2026-11-02'den itibaren 8 |
| 5 | Overdraft floor = max(%25, `minimum_due`) | ❌ ifade edilemiyordu → `floor_rule`'a `max:`/`min:` eklendi (23:16). Yeniden koşu: `overdraft: max:percent:25,field:minimum_due` ✅ |
| 6 | "Sonraki iki iş günü" callback | ✅ `business_days:2`, aynı gün yok |
| 7 | Harf harf posta kodu | ✅ `answer_type: postcode` |
