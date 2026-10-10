# 05: Workflow grafı

Kod: `src/fbb/workflow/graph.py`. Brief A, tek ürünlü ve notları kapalı bir Brief B gibi işlenir.

**Model sadece konuşur ve üç tool çağırır:**
- `submit_answer(answer)`: müşterinin güvenlik cevabı
- `submit_results(results)`: müzakerenin sonucu
- `propose_callback(date, time)`: üçüncü kişinin verdiği geri arama zamanı

Bu üçü code_exec tool'larıdır; bankaya hiçbir şey yazmazlar, sadece doğrulayıp bayrak koyarlar. Bankaya yazan bütün çağrıları engine yapar (api_request node'ları). Kararlar code node'larında verilir. Route'lar sadece string bayraklara bakar.

## Akış

```
opener (tts açılış + onay sorusu; tool-call transition'lar)
 ├─ identity_check (code: id_init) → ask_identity (tts {{id_say}}; submit_answer)
 │     id_ready=yes → verify_answer (api: verify_identity) → id_result (code: id_after)
 │         id_state=verified → fetch_account (api: get_account, data.products→products)
 │                              → prep_account (code) → negotiate (tts {{debt_statement}} {{first_ask}}; submit_results)
 │         id_state=failed   → close_id_failed
 │         diğer             → ask_identity (yeni {{id_say}} söylenir)
 │     transition_to_close_id_declined / transition_to_transfer_human
 ├─ third_party (code: prep_callback) → third_party_talk (propose_callback)
 │     cb_state=ok → book_callback (api: schedule_callback) → close_callback
 │     cb_state=invalid → cb_fix → third_party_retry      cb_state=gave_up → close_no_callback
 ├─ close_wrong_number / close_deceased / close_unclear / close_id_declined
negotiate / negotiate_fix
 ├─ commit=ready   → rec_pick ⇄ record_promise (api: create_promise) → rec_after   (kuyruk boşalana kadar)
 │                   → note_pick ⇄ record_note (api: add_note) → note_after         (notlar kapalıysa atlanır)
 │                   → close_final
 ├─ commit=invalid → commit_fix → negotiate_fix (llm: "kaydedilmedi: {{commit_msg}}")
 └─ transition_to_transfer_<id> → transfer_<id> (code) → do_transfer (api: transfer_to_agent) → close_transfer
her close_* (code: set_close) → end_main (end_call, spoken {{closing_speech}})
çağrı bitince: close_call (lifecycle end_of_call; pre-hook outcome/reason'ı durumdan hesaplar)
```

## Değişken sözleşmesi

| Değişken | Yazan | Okuyan | Değerler |
|---|---|---|---|
| `id_q`, `id_say`, `id_state`, `id_ready`, `id_field`, `id_answer`, `id_msg` | `id_init`, `id_take_answer`, `id_after` | `ask_identity` tts, `verify_answer` gövdesi, route | `id_state`: asking / verified / failed |
| `id_r_ok/verified/all/left/hint` | `verify_answer` mapping | `id_after` | metin |
| `products` | `fetch_account` mapping | `prep_account` | liste |
| `debt_statement`, `first_ask`, `product_facts`, `day_table`, `today_iso`, `today_spoken`, `plans_json` | `prep_account` | `negotiate` metni, doğrulama | metin |
| `commit`, `commit_msg`, `rec_queue`, `statuses_json` | `take_results` | route, kayıt döngüsü | ready / invalid |
| `rec_pid/amount/date`, `rec_state`, `rec_r_ok`, `rec_try`, `recorded_json`, `failed_json`, `promises_ok` | `rec_pick`, `rec_after` | `record_promise` gövdesi, kapanış | go / done |
| `note_pid/reason`, `note_state`, `note_i` | `note_pick`, `note_after` | `record_note` | go / done |
| `cb_facts`, `cb_days`, `cb_state`, `cb_msg`, `cb_date`, `cb_time`, `cb_bad` | `prep_callback`, `take_callback` | `third_party_talk`, `book_callback` | ok / invalid / gave_up |
| `transfer_queue`, `transfer_say` | `transfer_<id>` | `do_transfer`, kapanış | kuyruk |
| `close_outcome`, `close_reason`, `closing_speech` | `set_close` | `end_main`, `close_call` | outcome tablosu |

## Neden böyle

| Tasarım seçimi | Sorun | Kaynak |
|---|---|---|
| Kimlik cümleleri sabit tts | Agent tool sonucundan sonra susmasın | kit tools-and-code.md "Tool results and the next turn" |
| Promise'leri engine kaydeder; ilk hata tekrar denenir, ikinci hatada `service_error` | PUB-10 | Brief A kural 37 |
| Not ve kapanış kodla yazılır | Model gereksiz not eklemesin (B kural 10), outcome doğru olsun | |
| `close_call` lifecycle tool'u | Her zaman son çağrı ve tam bir kez | score.py: `calls[-1] == close_call` |
| system prompt aramanın amacından söz etmez | PUB-02'de akraba "payment" kelimesini duymasın | |
| Robot/scam cevapları system prompt'ta, global node yok | Geri dönüşte sessizlik ya da tekrar riski | |

## Pratik vakaların graf üzerindeki izi

| Vaka | Yol | Beklenen ledger |
|---|---|---|
| PUB-01 | opener → kimlik (2 soru) → negotiate (bugün, tam tutar) → submit `p1:X:bugün` → kayıt → close_final | promise |
| PUB-02 | opener → third_party → propose_callback(yarın 11:00) → book → close_callback | not_reached/callback, verify yok |
| PUB-03 | kimlik: 3 yanlış → `id_state=failed` → close_id_failed ("app or branch") | not_verified/failed |
| PUB-04 | 6 Kasım > deadline → model deadline'ı önerir (23 Eki) → kabul | promise 23 Eki |
| PUB-05 | iş kaybı → sempati + destek teklifi → ret → `p1:hardship` | no_promise/hardship |
| PUB-06 | "çok fazla" → floor + kalan borç uyarısı → Cuma 16 Eki | promise floor |
| PUB-07 | belirsiz → kesin gün sorulur → 26 Eki tatil → 27 Eki önerilir | promise 27 Eki |
| PUB-08 | "ödedim" → cümle → `p1:paid` | paid |
| PUB-09 | daha düşük taksit isteği → transfer_restructuring | transferred/restructuring |
| PUB-10 | create_promise önce 500 → engine tekrar dener → ok | tek promise |
| PUB-11 | 3 ürün, Cuma → `p1;p2;p3` → 3 kayıt | 3 promise |
| PUB-12 | p1 yarın, p2/p3 ret (p2 late: 2 deneme, p3 early: 1 deneme) → 1 kayıt + 2 not | promise + 2 refused notu |
| PUB-13 | tek tarih 30 Eki, kredinin deadline'ı 23 Eki → read-back iki tarihi söyler | 2 promise |
