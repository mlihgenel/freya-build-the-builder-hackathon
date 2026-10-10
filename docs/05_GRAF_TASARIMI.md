# 05: Workflow grafı

Kod: `src/fbb/workflow/graph.py`. Brief A, tek ürünlü ve notları kapalı bir Brief B gibi işlenir. Brief A ile ~43 node, ~300 KB.

**Model sadece konuşur ve dört code_exec tool'u çağırır:**
- `submit_answer(answer)`: müşterinin güvenlik cevabı (parça parça da olabilir; kod birleştirir)
- `decline_questions()`: müşteri soruya cevap vermiyor ya da aramanın amacını soruyor (sayaç kodda)
- `propose_results(results)`: müzakerenin sonucu; kod doğrular, düzeltir ve read-back cümlesini kendisi üretir
- `propose_callback(date, time)`: geri arama zamanı (üçüncü kişi ya da, brief isterse, müşterinin kendisi)

Bunlar bankaya hiçbir şey yazmaz, sadece doğrulayıp bayrak koyar. Bankaya yazan bütün çağrıları engine yapar
(api_request node'ları). Route'lar string bayraklara ya da cevap alanlarına (`"true"`/`"True"` OR) bakar.

**Gecikme ilkesi:** yük altında her code node'u 2–8 sn. Code node'u sadece hesap gereken yerde var. Kimlik sonucu,
sabit kapanışlar ve transferler kodsuz. Mutlu yolda bir çağrıdaki code exec sayısı: soru başına 1 (submit) + hesap 1
+ öneri 1 + ürün başına kayıt 1.

## Akış

```
opener (tts açılış + onay sorusu; tool-call transition'lar)
 ├─ ask_q0 (tts soru 0; submit_answer, decline_questions)
 │     id_go=ask_q0:0 → verify_q0 (api; ilk girişte tts "One moment") ── mapping: id_r_* ve status_code→id_go
 │         id_r_all=true → fetch_account     id_r_left=0 → close_id_failed     id_r_verified=true → ask_q1 …
 │         gerisi (yanlış, gün/ay ipucu, okunamadı, 500) → id_fix (code) → reask (tts {{id_say}})
 │     id_decl=explain → id_fix (açıklama + soru) → reask      id_decl=close → close_id_declined
 │     id_go=fail (aşırı deneme emniyeti) → close_id_failed
 ├─ third_party (code: erken outcome no_callback + prep_callback) → third_party_talk (propose_callback)
 │     cb_state=ok → third_party_book (api) → ok: close_callback / hata: close_no_callback
 │     cb_state=invalid → third_party_fix → third_party_retry      cb_state=gave_up → close_no_callback
 ├─ close_wrong_number / close_deceased / close_unclear / close_id_declined / transfer_<id> / cust_cb
fetch_account (api, tts "One moment") → prep_account (code; erken outcome = hangup_verified) → negotiate
negotiate / negotiate_fix (llm {{fix_prompt}}) / negotiate_fix_say (tts {{commit_say}}) / negotiate_more (per_product)
 ├─ commit=confirm  → readback (tts {{readback_say}}; routing: evet → record_promise, hayır/değişiklik → readback_reset)
 ├─ commit=go_<adım> (promise yok, sadece durumlar) → record_note / send_close / send_close_nr / negotiate_more
 ├─ commit=invalid|invalid_say → commit_fix (code, bayrağı temizler) → negotiate_fix | negotiate_fix_say
 └─ transition_to_transfer_<id> → transfer_<id> (api, sabit kuyruk) → close_transfer_<id> (sabit kapanış)
record_promise (api, ilk girişte tts "One moment") → rec_step (code) ⇄ … → record_note ⇄ note_step → send_close[_nr]
send_close / send_close_nr: tts {{closing_speech}} + close_call → end_main
sabit kapanışlar (close_unclear, close_id_failed, close_callback, close_transfer_* …): tts sabit veda + sabit
  outcome/reason ile close_call (kodsuz) → end_main
kod servisi hatası (her code node'unun guard'ı): fallback_close[_nr] (o ana kadar yazılmış {{close_outcome}})
çağrı bitince: close_call lifecycle yedeği (pre-hook): close_r_ok varsa URL boşaltılır (istek gitmez); müşteri
  telefonu kapattıysa gövde durumdan kurulur
```

## Değişken sözleşmesi

| Değişken | Yazan | Okuyan | Değerler |
|---|---|---|---|
| `id_go` | `id_take_answer`, verify mapping (`status_code`), `id_fix` | ask/reask route | `<node>:<soru>` / `fail` / `''` |
| `id_decl`, `decl_n` | `id_decline`, `id_take_answer`, `id_fix` | ask/reask route | `explain` / `close` / `''` |
| `id_q`, `id_answer`, `id_ans_<i>`, `id_partial`, `id_partial_q`, `id_last_<i>`, `id_swap`, `id_tries` | `id_take_answer`, `id_fix` | verify gövdesi, reask | metin |
| `id_r_ok/verified/all/left/hint` | verify mapping | verify route, `id_fix` | metin (`"true"`/`"True"`) |
| `id_say`, `id_msg` | `id_fix`, `id_take_answer` | reask tts, ask görevi | metin |
| `products` | `fetch_account` mapping (`data.<response_fields.products>`) | `prep_account` | liste |
| `debt_statement`, `first_ask`, `product_facts`, `day_table`, `today_*`, `tomorrow_*`, `plans_json`, `id_state` | `prep_account` | `negotiate` metni, doğrulama | metin |
| `commit`, `commit_msg`, `commit_say`, `fix_prompt`, `fix_kind`, `readback_say`, `rec_queue`, `statuses_json` | `propose_results`, `commit_reset`, `readback_reset` | route, readback, kayıt döngüsü | confirm / go_* / invalid / invalid_say |
| `rec_pid/amount/date`, `rec_r_ok`, `rec_try`, `recorded_json`, `failed_json`, `promises_ok`, `announced_json`, `progress_say` | `rec_pick`, `rec_after`, `next_step` | `record_promise` gövdesi, kapanış | |
| `note_pid/reason`, `note_r_ok`, `note_i`, `note_try` | `note_pick`, `note_after` | `record_note` | |
| `next_step` | `next_step` | rec_step/note_step route | record / more / note / end_r / end_nr |
| `cb_facts`, `cb_kind`, `cb_days`, `cb_state`, `cb_msg`, `cb_date`, `cb_time`, `cb_bad`, `cb_r_ok` | `prep_callback`, `take_callback` | callback node'ları | ok / invalid / gave_up |
| `transfer_ok_<kuyruk>` | transfer mapping | lifecycle yedeği (`decide_close`) | |
| `close_fixed_outcome/reason` | `set_close`, `set_close_default` | `decide_close` | |
| `close_outcome`, `close_reason`, `close_kind`, `closing_speech`, `close_r_ok` | `mark_close`, `set_close`, close mapping | send/fallback/lifecycle | |

## Neden böyle

| Tasarım seçimi | Sorun | Kaynak |
|---|---|---|
| Kimlik cümleleri sabit tts, sonuç kodsuz route | Agent tool sonucundan sonra susmasın; her code exec 2–8 sn | kit "Tool results and the next turn", review B.4 |
| Bir node'dan çıkış bayrağı, o node'a dönmeden bir kod adımında temizlenir (`id_fix`, `commit_fix`, `readback_reset`, `rec_step`) ya da node'a özgü belirteçtir (`id_go=<node>:<i>`) | Eski bayrak sonraki müşteri mesajında route'u tekrar tetikler | |
| Read-back cümlesini kod üretir, kayıt onaydan sonra başlar | PUB-13 (yanlış tarih onaylatıldı), PUB-10 (read-back'te ürün yok), PUB-07 | review B.3 |
| Geçersiz teklif müşteriye tts ile söylenir | PUB-13 r1: llm on_enter "kaydedildi" dedi (yalan) | review B.2 |
| Promise'leri engine kaydeder; ilk hata tekrar denenir, ikinci hatada `service_error` | PUB-10 | Brief A kural 37 |
| Sabit kapanışlar ve transferler kodsuz | Gecikme ve kod servisi kesintisi | review B.4, B.17 |
| `close_call` normal yolda node içinde, ayrıca lifecycle yedeği | Müşteri kapatınca da son çağrı close_call olsun; normal yolda çift çağrı olmasın | review B.1, F-09 |
| system prompt aramanın amacından söz etmez | PUB-02'de akraba "payment" kelimesini duymasın | |
| Açılışta "recorded" kelimesi yok ("we record this call") | Hakem bunu promise kaydı sandı (PUB-10 r1/r2) | review B.6 |

## Pratik vakaların graf üzerindeki izi

| Vaka | Yol | Beklenen ledger |
|---|---|---|
| PUB-01 | opener → ask_q0 → verify_q0 → ask_q1 → verify_q1 → negotiate (bugün, tam tutar) → propose `p1:X:bugün` → readback → evet → kayıt → send_close_nr | promise |
| PUB-02 | opener → third_party → propose_callback(yarın 11:00) → book → close_callback | not_reached/callback, verify yok |
| PUB-03 | kimlik: yanlış → id_fix → reask … `wrong_answers_left=0` → close_id_failed ("app or branch") | not_verified/failed |
| PUB-04 | 6 Kasım > deadline → model deadline'ı önerir ya da kod read-back'te 23 Eki'ye çeker → kabul | promise 23 Eki |
| PUB-05 | iş kaybı → sempati + destek teklifi → ret → `p1:hardship` | no_promise/hardship |
| PUB-06 | "çok fazla" → floor + kalan borç uyarısı → Cuma 16 Eki | promise floor |
| PUB-07 | belirsiz → kesin gün sorulur → model 26 Eki'yi önerir → kod 27 Eki'ye kaydırır ve read-back'te söyler | promise 27 Eki |
| PUB-08 | "ödedim" → cümle → `p1:paid` | paid |
| PUB-09 | daha düşük taksit isteği → transfer_restructuring | transferred/restructuring |
| PUB-10 | readback onayı → create_promise önce 500 → rec_step tekrar dener → ok | tek promise |
| PUB-11 | 3 ürün, Cuma → `p1;p2;p3` → 3 kayıt | 3 promise |
| PUB-12 | p1 yarın, p2/p3 ret (p2 late: 2 deneme, p3 early: 1 deneme) → 1 kayıt + 2 not | promise + 2 refused notu |
| PUB-13 | tek tarih 30 Eki, kredinin deadline'ı 23 Eki → kod krediyi 23 Eki'ye çeker, read-back iki tarihi söyler | 2 promise |
