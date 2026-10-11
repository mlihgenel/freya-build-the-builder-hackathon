# 15 — Final devir notu (11 Ekim 2026, 21:15 TR)

Bu not, Claude limiti dolarsa işe başka bir araçla (Codex ya da elle) kaldığı yerden devam edebilmek için yazıldı.
Teslim **23:00 TR (20:00 UTC)**, e-posta ile: yavuz@freyavoice.ai.

## 1. Durum

| Parça | Durum |
|---|---|
| Vaka klasörü | `final/` (paketin tamamı, sadece girdi; builder kodu vakaya özgü hiçbir şey içermez) |
| Mock (Cloudflare Worker) | **Yayında**: `https://yz50-bank-mock.kirgilmert.workers.dev`, sürüm `39e61cf8`. Kod `mock/src/index.js`, veri `mock/data/test-customers.json` (= `final/test-environment/test-customers.json`) |
| Mock doğrulaması | Canlı adreste 617/617 test cevabı birebir (gövde + HTTP kodu, 12 sn gecikmeli cevap dahil); kayıt yoksa sözleşme bölüm 4'teki kodlar (102/120/121/107, diğerleri 400 `INVALID_ARGUMENTS_ERROR`) |
| Builder | Genel yol + ajan modu hazır (aşağıda). Final build **henüz başarılı çalışmadı**: `final-try1` tek seferlik yazımda takıldı, `final-try2` Melih'in makinesinde Claude limitine çarptı |
| `submission.json` | Takım "Horozlar", üyeler, repo, run_command, mock_url dolu. **Eksik:** `commit` (yer tutucu), `workflow` dosyası henüz üretilmedi |
| Testler | `uv run pytest` yeşil, `uv run ruff check src tests` temiz |

## 2. Builder nasıl çalışıyor (final için)

Komut (repo kökünden):

```
python3 builder/build.py final https://yz50-bank-mock.kirgilmert.workers.dev 2>&1 | tee traces/final.log
```

`builder/build.py` gerekirse kendini `uv run` altında yeniden başlatır ve `src/fbb/build.py`'yi `slot=final` ile çağırır.
Akış:

1. `src/fbb/ingest/sources.py`: klasördeki md/txt/docx/xlsx/pdf/json dosyalarını okur (çok büyük veri dosyalarını kısaltır).
2. Tahsilat formatı (yedi tahsilat tool'u) yoksa **genel yol** (`src/fbb/generic.py`):
   - Claude, belgelerden API'yi OpenAPI olarak çıkarır (~1–2 dk).
   - Taban adres mock adresiyle değiştirilir (`/voice/v1` yolu korunur).
3. **Ajan modu** (`src/fbb/refine.py` + `refine_knowledge.md`):
   - Claude (Agent SDK, Read/Write/Edit/Bash araçlarıyla) workflow'u `out/final-refine/workflow.json`'a yazar.
   - `uv run python -m fbb.agent_tools check|save|chat|call|end` ile kontrol eder, Freya'ya kaydeder ve mock'a karşı chat ile test edip düzeltir.
   - Kararlarını `out/final-refine/DECISIONS.md`'ye yazar.
   - Build'in 25. dakikasında kesilir.
   - Her başarılı kayıt `out/final-refine/last_saved.json`'a da yazılır. Son dosya geçmezse ya da ajan hata verirse (ör. Claude limiti) bu son başarılı kayıt kullanılır.
4. Ajan hiçbir geçerli workflow bırakmadıysa ve build'in ilk 12 dakikasındaysak tek seferlik yazım devreye girer (lint + dryRun, 2 düzeltme turu). Daha geçse build hata verir; tek seferlik yazım ~16 dk sürebildiği için başlatılırsa 30 dk sınırı aşılır.
5. Kayıt (`kitapi.save("final")`), geri okuma ve export: **`exports/final.workflow.json`**. Trace: `traces/final-<zaman>.txt/.jsonl` ve tee ile `traces/final.log`.

Süre: brief başına en fazla 30 dk (kural R2). Ajan 25. dakikada durur, kayıt ve export ~1 dk sürer.

## 3. Kalan işler, sırasıyla

1. **Final build'i bir kez, tek makineden çalıştır** (yukarıdaki komut). Aynı anda ikinci bir build çalışmasın; ikisi de `final` slot'una kaydeder. Bu adım Freya kredisi (chat testleri) ve Claude kotası harcar.
2. **Çıktıyı kontrol et:**
   - `traces/final.log` sonunda `build bitti` satırı var mı?
   - `exports/final.workflow.json` oluştu mu?
   - `out/final-refine/DECISIONS.md` okunur mu?
   - İsteğe bağlı kısa chat smoke (kredi harcar): `uv run python -m fbb.agent_tools chat final "Merhaba" --vars '{"customerNumber":"90000001","now":"2026-10-12T10:30:00+03:00"}'`
3. **Workflow'u teslim yoluna koy.** `submission.json` `exports/final.workflow.json` gösteriyor; o dosyayı aynen kullan. (Brief örnekte `submission/final.workflow.json` yazıyor; istenirse kopyalanıp alan güncellenir. Kopya elle düzenleme sayılmaz, içerik değişmez.)
4. **Commit ve push:**
   - Trace, export ve `submission.json` (`.gitignore`'da `!traces/final*` ve `!exports/final*` istisnaları var).
   - `submission.json`'daki `commit` = **build'i çalıştırdığın commit**. Build'den önce `git rev-parse HEAD` ile al. Trace/export commit'i ondan sonra gelir; o commit'in hash'ini yazma.
5. **E-posta** (23:00'ten önce) → yavuz@freyavoice.ai. Ekler: `submission.json`, `exports/final.workflow.json`, `traces/final.log`.
6. **Mock'u sonuçlar açıklanana kadar açık tut.** Worker'a dokunma; Cloudflare panelinde Workers & Pages → yz50-bank-mock → Metrics'ten istekler izlenebilir.

## 4. Claude limiti dolarsa ne olur, Codex ne yapabilir

- Builder'ın bütün LLM çağrıları `claude-agent-sdk` üzerinden **Claude**'a gider (`src/fbb/llm.py`, `src/fbb/refine.py`). Builder'da OpenAI/Codex desteği yok. Build'i Codex başlatsa bile LLM adımları yine Claude limitine takılır.
- Limit build sırasında dolarsa:
  - Ajan modundaysa son başarılı kayıt (`last_saved.json`) kullanılır ve build kayıt/export ile biter. Trace'te `agentic_error` ve `son başarılı kaydı kullanılıyor` satırları görünür.
  - Hiç kayıt yoksa ve süre erkense tek seferlik yazım dener; o da limitliyse build başarısız olur.
- Claude'suz devam yolları:
  1. `.env`'ye `ANTHROPIC_API_KEY=...` eklemek. SDK makinedeki girişi değil anahtarı kullanır; abonelik limitinden bağımsızdır ama ücretlidir.
  2. Build'i Claude limiti dolu olmayan diğer ekip üyesinin makinesinde çalıştırmak.
- **Codex'in güvenle yapabileceği işler** (LLM gerektirmez): bölüm 3'teki 2–6. adımlar, mock kontrolü (bölüm 5), `submission.json` düzenleme, commit/push, e-posta taslağı.
- **Codex'in yapmaması gerekenler:**
  - Üretilen workflow'u elle düzeltmek (yasak).
  - `src/` altına vakaya özgü değer yazmak (yasak; organizatör commit'i bu gözle okuyacak).
  - `kit/` altını değiştirmek.

## 5. Mock'u kontrol etmek / yeniden yayınlamak

- Sağlık: `curl https://yz50-bank-mock.kirgilmert.workers.dev/health` → `{"ok":true,"customers":34}`
- Tek çağrı:

  ```
  curl -s -X POST -H 'content-type: application/json' https://yz50-bank-mock.kirgilmert.workers.dev/voice/v1/cards.list -d '{"data":{"customerNo":"90000001"},"call":{"ani":"x","lang":"tr"}}'
  ```

- Yerel deneme: `cd mock && npx -y wrangler@4.149.0 dev --port 8791`
- Yeniden yayın (sadece kod değişirse; adres aynı kalır): `cd mock && npx -y wrangler@4.149.0 deploy`. Wrangler bu makinede kirgilmert hesabıyla girişli.
- Ücret: Workers Free planı (günde 100 bin istek), ücret yok. Mock'a giden istekler Freya kredisi harcamaz. Freya kredisini chat ve simülasyonlar harcar.
- 12 sn gecikmeli tek cevap (müşteri 94907600, `cards.balance`) Cloudflare'de sorun değil; bekleme CPU süresine sayılmaz, canlıda doğrulandı. Agent tarafında tool'un `config.timeoutMs` değeri 12 sn'den büyük olmalı. Builder bilgisine genel kural olarak eklendi; build sonrası export'ta kontrol et:

  ```
  grep -o '"timeoutMs": *[0-9]*' exports/final.workflow.json
  ```

## 6. Kurallar (hatırlatma)

- Workflow sadece builder'dan çıkar; elle düzenleme yok.
- Builder düzeltmeleri vakadan bağımsız olur ve her biri `docs/BUGFIX_LOG.md`'ye yazılır.
- Commit ve PR'lara Claude yazar ya da ortak yazar satırı eklenmez.
