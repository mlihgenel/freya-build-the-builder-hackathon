# 07: Runbook

## Cumartesi → Pazar planı

| Faz | İş | Çıkış kriteri | Durum |
|---|---|---|---|
| F0a | iskelet, uv, kit kopyası | `make test` yeşil | ✅ |
| F1 | runtime + testler | tarih ve normalizasyon testleri yeşil | ✅ |
| F2 | spec + openapi + altın fixture'lar | şema testleri yeşil | ✅ |
| F3a | graf + lint + yerel akış testleri | lint temiz | ✅ |
| F5a | LLM çıkarımı (Claude SDK) | Brief A spec'i altın spec'e çok yakın | ✅ |
| F0b | Freya key'leri → deneyler F-01…F-11 | `02`'deki tablo dolu | 🟡 F-01,03–06,08 ✅; F-10 kısmen; F-09/F-11 mock erişimi bekliyor |
| F3b | Brief A simülasyonu | A tek çalışmada ≥ 9/10, iki kez | ✅ `--reps 3` 10/10 pass³, iki ayrı koşuda (11 Eki 00:15, next_offer sürümü, altın spec) |
| R1 | Review düzeltmeleri (`11_REVIEW.md` C.1–C.6) | testler yeşil, L1/L2 temiz | ✅ kod + test (10 Eki 20:35); L4 ölçümü bekliyor |
| F4 | Brief B | 13/13 bir kez, `--reps 3` ile ≥ 11/13 | ✅ public 3 vaka `--reps 3` 3/3 pass³ (11 Eki 00:10) |
| F6 | varyant provası (C/D/E), G-01 cevap alanı eşlemesi | çökme yok, ≥ %80 | 🟡 (13 Faz 5'e bağlı) G-01 ✅, varyant openapi birim testi ✅ (`test_variant_openapi_does_not_crash`); ham materyal provası C (LLM, `--no-deploy`) ✅ lint 0; simülasyon provası yok |
| F7 | stiller + 3 tekrar | bilinmeyen sebeple 3/3 altında vaka yok | 🟡 5 stil × A/B ölçüldü, düzeltmelerden sonra talkative A 10/10 · B 3/3, düşen vakalar hedefli 3/3 (11 Eki 05:00, `14_RAPOR_11EKIM.md`). pieces/in_words/asks_back/corrects son sürümle bütün brief olarak koşulmadı (13 Adım 6) |
| F5b | LLM spec'iyle uçtan uca (finaldeki zincir) | A ≥ 9/10, B 3/3 pass³; çıkarımlar arası puan farkı yok | ✅ A 10/10, B 3/3; 3 çıkarım 0 fark (11 Eki 01:45) |
| F8 | teslim provası: temiz kopyadan 2 brief art arda | tek komut, brief başına ≤ 10 dk | ✅ 11 Eki 10:34: temiz klon, A+B 109 sn / $1.00, lint 0, geri okuma 0 fark, export + trace doğru (13 §6.2) |
| F9 | dondurma provası: son commit'le slotlar, Claude spec'iyle A ve B `--reps 3` | A ≥ 9/10, B 3/3 | ✅ 11 Eki 17:15: B 3/3 pass³ (altın ve Claude spec'i); A-LLM 7/10 → düşüşlerin 1'i platform, 1'i zamanlama yarışı, 1'i düzeltildi (PUB-08 3/3, A-LLM ×1 10/10) (`13` Faz 7) |
| — | **Özellik dondurma: Pazar 18:00 TR — DONDURULDU 11 Eki ~17:30** | | |

## Final penceresi (Pazar 20:00–23:00 TR)

1. **19:30** Hazırlık:
   - `git status` temiz olmalı.
   - `make test lint secrets-check freeze-check` yeşil olmalı.
   - `env.sh` yüklü olmalı.
   - Claude girişi `claude` CLI ile kontrol edilmeli.
   - Workspace'te çalışan bir simülasyon olmamalı: `GET /api/v2/simulations?limit=5`; `running` kalmış varsa
     `POST /api/v2/simulations/<id>/cancel` (02, 11 Eki).
   - Platform sağlık kontrolü: kimlikli bir GET birkaç saniyede dönmeli (11 Eki'de dakikalarca 504 verdi).
2. **20:00** Brief'ler açılır. Dosyalar `final/<ad>/` altına indirilir; brief ve openapi'nin içine hiçbir şey yazılmaz.
3. **20:05** Önce temiz spesifikasyon olan brief:
   ```bash
   uv run build-agent final/<x>/brief.md --tools final/<x>/openapi.json --slot final-<x>
   ```
   Kontrol: trace'te `lint 0`, `cross_check` boş, `unmapped` mantıklı, export yazılmış. `warnings`'te "workflow büyük"
   uyarısı build'i durdurmaz (dryRun 1,2 MB'ı kabul etti).
   Aynı anda ikinci bir çıkarım (deploy yok, ~2 dk, ~$0.5) ve karşılaştırma:
   ```bash
   uv run build-agent final/<x>/brief.md --tools final/<x>/openapi.json --slot chk-<x> --no-deploy
   uv run fbb specdiff out/chk-<x>.spec.json out/final-<x>.spec.json
   ```
   PUAN farkı varsa iki değerden hangisinin brief'e uyduğuna bakılır. 11 Eki 18:36 provasında (Brief E ve G) görülen
   ve **zararsız** çıkan fark türleri:
   - Tarihli memo iki çıkarımda ters yönden yazılmış: biri "ana değer X, şu tarihe kadar Y", öteki "ana değer Y, şu
     tarihten itibaren X". Anlam aynıysa ikisi de doğrudur.
   - `tool_fields` eşlemesinin birinde boş olması: builder eksik eşlemeyi kendisi tamamlıyor. Şüphede iki spec'ten
     üretilen gövdeyi karşılaştır (`out/<slot>.workflow.json` içinde ilgili `pre_actions` gövdesi).
   - `closing.hangup_unverified` / `hangup_verified`: brief tanımlamıyorsa (`unmapped`'te not vardır) karar değil.
   Süre (prova): iki brief için asıl build + kontrol çıkarımı aynı anda **~2,5 dk**, ~$3,3. Asıl spec yanlışsa genel bir prompt düzeltmesi
   yapılıp build tekrarlanır (BUGFIX_LOG). 11 Eki provası: C ve D'de iki çıkarım 0 PUAN farkı.
4. **20:15** Ham materyal brief'i: bütün dosyalar sırayla verilir (mail, poliçe, memo, kod listesi; ilgili sırayla).
5. **20:30** Gözle kontrol:
   - `out/<slot>.spec.json`: tatiller, bantlar, kimlik soruları, outcome tablosu brief'le aynı mı?
   - Hata varsa sadece **genel** bir bug fix yapılır ve `BUGFIX_LOG.md`'ye yazılır. Brief'ten değer **yazılmaz**.
   - Builder yeniden çalıştırılır.
6. **21:00** Chat smoke (workspace'te **çalışan simülasyon yokken**: 11 Eki 18:40'ta simülasyon çalışırken chat bilinen
   sağlam agent'ta da 504 verdi; o durumda tek vakalık simülasyon `fbb cases final-<x> --only PUB-02` kullanılır):
   ```bash
   uv run fbb chat final-<x> "Hello?" --case PUB-01
   ```
   İlk turların (kimlik soruları, hata yolunda dürüst cümle) çalıştığı görülmeli. **Not:** chat'te açılış tts'i
   söylenmez, ilk cevabı model üretir ve cümle atlayabilir (02). Açılışın birebir söylendiğini görmek için tek vakalık
   bir simülasyon (`fbb cases final-<x> --only PUB-02`) transcript'ine bakılır; ledger'ın düşmesi beklenir (kodlar farklı).
7. **21:30** `exports/` + `traces/` → kullanıcı commit ve push yapar → commit hash → form gönderilir (bkz. 09).
8. **22:30** Son güvenli teslim anı.

## Acil durumlar
| Durum | Ne yapılır |
|---|---|
| Claude girişi ya da kotası sorun çıkarırsa | `ANTHROPIC_API_KEY` ile tekrar dene; `BUILDER_MODEL=claude-sonnet-5-5` |
| Lint hatası (beklenmeyen tablo ya da alan) | Hata genel bir bug ise düzelt ve kaydet. Spec alanı eksikse prompt'u genel olarak düzelt |
| Freya 5xx ya da `1010` | Tekrar dene. `User-Agent`'ı `freya.py` ayarlıyor |
| Mock'a erişilemiyor (timeout, DNS) | VPN aç; olmazsa DNS 1.1.1.1; olmazsa telefondan hotspot. Kontrol: `curl -s -o /dev/null -w '%{http_code}' https://freya-bank-mock.freyavoice.workers.dev/v1/practice/sessions` (401 = erişim var) |
| Deploy sırasında Freya 5xx / zaman aşımı (11 Eki'de sık) | Çıkarım tekrarlanmaz: build spec'i deploy'dan önce yazar. `uv run build-agent final/<x>/brief.md --tools final/<x>/openapi.json --spec out/final-<x>.spec.json --slot final-<x>` (saniyeler, LLM yok). Teslimde iki trace birlikte verilir: çıkarımlı olan + deploy eden. BUGFIX_LOG'a "platform kesintisi, kod değişmedi" yazılır |
| Smoke ölçümünde kit "the phone agent was slow" diyor | Düşüşler büyük olasılıkla platform sessizliği (müşteri kapatır). `fbb cases … --rerun-if-slow 1` yavaş koşuyu atıp 5 dk sonra tekrarlar (organizatörün yöntemi). Ajan düzeltilmez |
| Simülasyon / chat 504 veriyor, takılıyor | Simülasyon çökmüş olmayabilir (02). `fbb` koşucusu GET'leri ~5 dk tekrar dener, 10 dk'yı aşan simülasyonu iptal eder. Hiçbir müşteride tool çağrısı yoksa ya da "no verdict" geliyorsa bu kesintidir: ajan **düzeltilmez**, beklenir |
| Platform workflow'un bir kısmını sildiyse | Trace'teki `freya_readback` farkına bak, `02`'yi güncelle |
