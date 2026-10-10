# 10: Test rehberi (ekip için)

Bu dosya, repoyu yeni çeken bir takım arkadaşının builder'ı kurup Freya'da test etmesi, sonuçları okuması ve düzeltme yapması için adım adım yol gösterir. Mimarinin ayrıntıları `03_MIMARI.md` ve `05_GRAF_TASARIMI.md`'de.

---

## 1. Ne yapıyoruz, kısaca

```
brief.md + openapi.json ──(Claude)──► out/<slot>.spec.json ──(Python)──► Freya workflow ──► telefon agent'ı
                                                                         │
                       kit/tools/run_cases.py: pratik müşteriler (Gemini) + banka ledger'ı + hakem ──► PASS/FAIL
```

- **Builder**: brief'i okur ve Freya'da bir workflow (agent) kurar.
- **Test**: kitin pratik müşterileri bu agent'ı simülasyonla arar. Her vaka iki yerden kontrol edilir:
  - bankanın kayıtları (ledger)
  - hakem modelinin transcript'i okuması
- **Final puanı**: her vaka 3 kez çalışır ve ancak 3'ü de geçerse sayılır. Bu yüzden tek bir yeşil tur kanıt değildir.

---

## 2. Kurulum (repoyu ilk kez çeken kişi)

```bash
git clone <repo> && cd <repo>
uv sync                                  # Python 3.12 ortamı, bağımlılıklar
cp env.example .env                      # sonra .env'yi doldur (aşağıya bak)
uv run pytest                            # 50'ye yakın test, hepsi yeşil olmalı
```

`.env` içinde doldurulacaklar:

| Değişken | Ne | Nereden |
|---|---|---|
| `FREYA_API_KEY` | takımın Freya key'i (`fak_…`) | **Kurallar takım başına tek key istiyor.** Mevcut key'i güvenli bir kanaldan iste. Yeni key açma, git'e ve sohbete yazma |
| `FREYA_BANK_TEAM_KEY` | takımın banka şifresi (≥16 karakter) | **Takımdaki herkes aynısını kullanır.** Bankanın pratik oturumları ve ledger'ı bu şifreyle ayrılıyor |
| `FREYA_API_URL` | `https://staging-app.freyavoice.ai` | değiştirme |
| `BUILDER_MODEL` | `claude-opus-5-5` | değiştirme |

**Claude:** Builder'ın LLM adımı (`--spec` vermeden yapılan tam build) Claude'u `claude-agent-sdk` ile kullanır. Bunun için:
- makinede Claude Code girişi olmalı (`claude` komutu çalışıyorsa tamam)
- ya da `.env`'de `ANTHROPIC_API_KEY` olmalı

Sadece hazır spec ile (`--spec`) test edecek biri için Claude gerekmez.

**Python sertifika hatası (macOS):** `CERTIFICATE_VERIFY_FAILED` görürsen bir şey yapmana gerek yok; builder `certifi`'yi otomatik kullanıyor. Kitin scriptlerini doğrudan `python3` ile çalıştırırken görürsen `uv run` ile çalıştır.

> Bu klasörün dışında aktif bir Python venv'in varsa `uv` komutlarının başına `env -u VIRTUAL_ENV` ekle. `make` hedefleri bunu zaten yapıyor.

---

## 3. Ortak workspace kuralları (önemli)

Hepimiz **aynı Freya workspace'ini** kullanıyoruz:

1. **Aynı anda tek simülasyon çalışabilir.** İkinci `fbb cases` birincinin bitmesini bekler. Simülasyon başlatmadan önce takımda haber ver.
2. **Kendi slot adını kullan.** Slot, workflow'un bizdeki adı. `--slot dev-a` başkasının agent'ının üzerine yazar.
   - Kişisel bir önek kullan: `--slot ali-a`, `--slot ali-b`.
   - `.freya-agents.json` (slot → workflow eşlemesi) her makinede yereldir ve git'e girmez.
3. **Workspace en fazla 200 workflow tutar.** Her yeni slot yeni bir workflow demek; slot adlarını boş yere çoğaltma.
4. **Freya panelinde agent'ları elle düzenleme.** Kural: agent'lar sadece builder ile kurulur.
5. **Kredi:** workspace'te $100 var.
   - Bir simülasyon çağrısı $0.01–0.15 tutuyor; 10 vakalık tur yaklaşık $0.5–1.5.
   - Chat denemesi çağrı başına yaklaşık $0.02–0.15.

---

## 4. Test katmanları ve komutlar

Ucuzdan pahalıya doğru sıralı. Bir değişikliği önce alt katmanda doğrula.

### L0: birim testleri (ücretsiz, saniyeler)
```bash
make test lint          # uv run pytest + ruff
```
Tarih hesapları, cevap normalizasyonu, kayıt döngüsü, kapanış kararı, graf kontrolleri ve "src'de brief değeri yok" testi burada.

### L1: yerel build (Freya'ya dokunmaz)
```bash
make local-a            # altın spec (tests/fixtures/spec_a.json) → out/brief-a.workflow.json + lint
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json --slot ali-a --no-deploy
                        # ↑ Claude ile spec çıkarımı (~2 dk, ~$1), Freya'ya göndermez
```
Çıktılar: `out/<slot>.spec.json` (Claude'un brief'ten çıkardığı kurallar) ve `out/<slot>.workflow.json`.

### L2: Freya'ya kur (saniyeler)
```bash
# hızlı: elle yazılmış altın spec ile (LLM yok). Graf/prompt değişikliklerini denemek için.
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json --spec tests/fixtures/spec_a.json --slot ali-a
uv run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools kit/tools/openapi.json --spec tests/fixtures/spec_ab.json --slot ali-b

# tam: finaldeki gibi (Claude + Freya). Spec çıkarımını da test eder.
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json --slot ali-a-llm
```
- Çıktının sonunda `workflow_id`, `agent_id`, `export` yolu ve trace yolu yazar.
- Aynı slotla tekrar çalıştırmak aynı agent'ı günceller ve yeni sürüm olarak yayınlar.

### L3: chat smoke (tek tur, simülasyon kuyruğuna girmez)
```bash
uv run fbb chat ali-a "Hello?" --case PUB-01           # yeni çağrı, PUB-01 müşterisinin değişkenleriyle
uv run fbb chat ali-a "Yes, speaking." --call-id <önceki çıktıdaki callId>
```
- Açılışın, kimlik sorusunun ve ilk turların çalıştığını hızlıca görmek için kullanılır.
- Uzun bir kayıt zincirinde chat **502** dönebilir, ama çağrı arka planda tamamlanır. `fbb call <callId>` ile kontrol et.

### L4: simülasyon (asıl ölçüm, 1–11 dk)
```bash
uv run fbb cases ali-a --brief A                       # Brief A'nın 10 vakası, 1 kez
uv run fbb cases ali-b --brief B                       # Brief B'nin 3 vakası
uv run fbb cases ali-a --brief A --only PUB-04,PUB-07  # sadece belirli vakalar
uv run fbb cases ali-a --brief A --reps 3              # pass^3: her vaka 3 kez, ancak 3/3 ise geçer
uv run fbb cases ali-a --brief A --style pieces        # müşteri konuşma tarzı (aşağıda)
```

| `--style` | Müşteri ne yapıyor |
|---|---|
| `pieces` | numarayı ve tarihi iki parça halinde verir |
| `corrects` | yanlış söyleyip hemen düzeltir ("21'i, pardon 20'si") |
| `talkative` | konudan sapar, ilgisiz tarihler söyler |
| `asks_back` | cevap vermeden önce soru sorar |
| `in_words` | tutarı ve tarihi yazıyla söyler |

Final müşterileri böyle konuşuyor. Her stili ayrı dene.

---

## 5. Sonuçları okumak

### `fbb cases` çıktısı
```
PASS PUB-01 easy   Happy path     | verify > verify > get_account > promise > close_call
FAIL PUB-12 hard   Multi-product  | verify > verify > verify > get_account
       - outcome (None, None), expected ('promise', None)        ← ledger farkı
       - conversation: ...                                         ← hakemin gerekçesi
slowest agent turn per call: median 27 s ...                       ← model yavaşsa uyarı
10 / 10 passed ...
sonuç dosyası: /…/results/run-<agent>-<zaman>.json
```

### Bir turun özeti ve başarısız çağrılar
```bash
uv run fbb report results/run-<agent>-<zaman>.json      # PASS/FAIL listesi + her başarısız vakanın call_id'si ve sebepleri
```

### Bir çağrıyı baştan sona görmek (en önemli araç)
```bash
uv run fbb call <call_id>          # konuşma + girilen node'lar + tool çağrıları + hatalar, saniye damgalı
uv run fbb call <call_id> --all    # route kararları dahil
```

Satır biçimleri:
- `USER:` ve `ASSISTANT:` konuşmanın kendisi
- `> node` workflow'un girdiği adım
- `* tool {...}` tool çağrısı ve argümanları
- `= {...}` bankanın cevabı
- `!!` hata. Özellikle **`snekbox`** hataları platformun kod servisinin çöktüğü anlamına gelir; bu bizim hatamız değil, bkz. §8.

### Freya paneli
staging-app.freyavoice.ai → çağrı kayıtları. Simülasyon çağrıları "Simülasyon", chat denemeleri "Web Arayanı" olarak görünür. Duygu ve tema sütunları sadece web çağrılarında dolu; simülasyon sonucunu panelden değil `fbb report`'tan oku.

---

## 6. İyileştirme döngüsü

1. **Başarısız çağrının transcript'ini oku** (`fbb call`). Transcript okunmadan hiçbir şey değiştirilmez.
2. **Sebebi sınıflandır:**

| Sebep | Belirti | Nerede düzeltilir |
|---|---|---|
| Agent yanlış konuştu ya da yanlış karar verdi | hakem gerekçesi, transcript | `src/fbb/workflow/texts.py` (prompt'lar) |
| Kural hesabı yanlış (tarih, tutar, deadline, kapanış) | yanlış tarih veya outcome, birim testi yakalamıyor | `src/fbb/runtime/*.py` + önce bir **test** yaz |
| Akış ya da route hatası | `> node` sırası beklenmedik, döngü | `src/fbb/workflow/graph.py` |
| Spec yanlış (Claude brief'i yanlış okudu) | `out/<slot>.spec.json` brief'le uyuşmuyor | `src/fbb/ingest/prompts/*.md` (**genel** talimat), `spec.py` alan açıklamaları |
| Platform sorunu | `!! HATA: snekbox…`, 502, "model was busy" | bizim kodumuzda değil. Not al, sonra tekrar dene |
| Hakem hatalı | transcript doğru ama FAIL | not al; aynı vakayı tekrar çalıştır (hakem de rastgele) |

3. `make test lint` → aynı slotla yeniden kur (`build-agent … --slot ali-a`).
4. Önce sadece o vakayı çalıştır (`--only PUB-xx`), sonra bütün brief'i, sonra `--reps 3`.
5. Kalıcı bir ders çıkardıysan `docs/02` (platform) ya da `docs/05` (graf) dosyasına bir satır ekle.

**Altın kurallar:**
- `src/` altına brief'ten **hiçbir değer yazılmaz**: tatil, tutar, isim, outcome adı, cümle. Bunlar spec'ten gelir. `tests/test_no_hardcoded_brief.py` bunu yakalar.
- `kit/` klasörü **hiç değiştirilmez** (organizatörün kiti, `AGENT_LLM` dahil).
- Bir şey bir kez düştü diye değiştirilmez. Önce tekrar ediyor mu bak: bu skor pass^3.
- Gizli brief'ler açıldıktan sonra (Paz 20:00 TR) sadece bug fix yapılır ve her değişiklik `docs/BUGFIX_LOG.md`'ye yazılır.

---

## 7. Dosyalar nerede

| Yol | Ne | Git'e girer mi |
|---|---|---|
| `out/` | spec ve workflow çıktıları | hayır |
| `results/run-*.json` | simülasyon sonuçları (`fbb report` ile oku) | hayır |
| `traces/` | build trace'leri. Finalde teslim edilecekler buradan seçilir | evet (sadece teslim edilecekler) |
| `exports/` | Freya'dan export edilen workflow. Finalde teslim edilir | evet |
| `.freya-agents.json` | slot → workflow/agent ID (makineye özel) | hayır |
| `kit/results/log.jsonl` | kitin kendi tuttuğu tur kaydı | hayır |

---

## 8. Bilinen sorunlar

| Sorun | Ne yapılır |
|---|---|
| **Mock'a erişilemiyor** (`freya-bank-mock.freyavoice.workers.dev:443` bağlantı reddi; 10 Eki 20:20, bazı TR ağlarında `*.workers.dev` engelli). `fbb cases`, `fbb chat --case` ve `score.py` çalışmaz | VPN ya da başka bir ağ. Freya'nın kendisi mock'a erişiyor; sadece bizim pratik oturumu açmamız ve ledger okumamız engelli |
| `FREYA_SIM_CONCURRENCY` yükseltmek | 10'da koşu 3–4 kat hızlandı ama agent turları 30 sn'ye kadar yavaşladı (müşteri kapatma riski, ölçüm bozulur). Varsayılan 5'te kal |
| **Kod servisi (snekbox) kesintisi.** Freya staging'de code node'ları ve hook'lar çalışmıyor: `Failed to reach snekbox …` (10 Eki ~17:20 TR'den beri) | Agent kilitlenmez; korumalı olarak sabit vedayla kapanır, ama iş yapamaz. Organizatöre bildirildi. Servis düzelince bir chat smoke ile kontrol et, sonra simülasyon çalıştır |
| Chat 502 | Uzun kayıt zincirinde normal; `fbb call` ile sonuca bak |
| "the phone agent was slow" uyarısı | Model o an yoğun. Aynı agent başka bir turda hızlıysa skor düşük ölçülmüştür, tekrar çalıştır |
| `CERTIFICATE_VERIFY_FAILED` | `uv run` ile çalıştır (builder certifi kullanır) |

---

## 9. Şu ana kadarki sonuçlar

| Zaman (10 Eki) | Slot | Ne | Sonuç | Not |
|---|---|---|---|---|
| 17:13 | dev-a (v1) | Brief A, 10 vaka × 1 | **10/10** | kayıt zinciri uzun (en yavaş tur ~27–38 sn) |
| 17:19 | dev-b (v1) | Brief B, 3 vaka × 1 | 0/3 | kod servisi kesintisi → kayıt döngüsü kilitlendi. Konuşmalar doğruydu; bir "yarın" tarih hatası bulundu |
| 17:28 | dev-b (v2) | Brief B, 3 vaka × 1 | 0/3 | kod servisi tamamen kapalı; koruma çağrıyı temiz kapattı |
| 17:45 | dev-b (v3) | Brief B, 3 vaka × 1 | **3/3** | kod servisi düzelmişti. Risk: PUB-11'de her ürün ayrı onaylandı (brief tek ortak onay istiyor); prompt'ta düzeltildi (v4) |
| 18:12 | mert-a (HEAD 8c400d6) | PUB-09 × 1 | 1/1 | |
| 20:30 | mert-a, mert-b (review düzeltmeleri) | L2: dryRun + kayıt + geri okuma | 0 fark | 43 node, ≈300/305 KB; lifecycle pre-hook korunmuş |
| 20:36 | mert-a-llm | Brief A, LLM çıkarımı, `--no-deploy` | spec geçerli, lint 0 | 2 dk 18 sn, $1.82; `agent_role` amacı içeriyordu → prompt + lint uyarısı |
| 20:41 | mert-a (review) | Brief A, `--reps 3` | **9/10 pass³** (29/30) | en yavaş tur medyanı 2 sn (önce 12–24), kapatma 0. PUB-05 2/3: destek ekibi iki kez teklif edildi |
| 20:45 | mert-b (review) | Brief B, `--reps 3` | 2/3 | PUB-12 0/3: yanlış telefondan sonra DOB soruldu → `id_q` yazılmıyordu (bug, düzeltildi + test) |
| 20:49 | mert-b (id_q düzeltmesi) | Brief B, `--reps 3` | 2/3 | PUB-12 1/3: kimlik doğru; ikna sayımı: ürün başına "bugün" tekrar soruldu / late bandında 2. deneme atlandı → negotiate'e genel ikna kuralları |
| 20:53 | mert-b (ikna kuralları) | Brief B, `--reps 3` | **3/3 pass³** | |
| 20:56 | mert-a (ikna kuralları) | Brief A, `--reps 3` | **9/10 pass³** | PUB-05 3/3; PUB-06 2/3: floor önce "bugün" için teklif edildi, 1. deneme atlandı (tek düşüş, prompt değişmedi). Bir koşuda en yavaş tur 15,9 sn |
| 21:08–21:47 | mert-b (A+B spec, 13 vaka) | 5 stil × 1 | pieces 8/13, in_words 6/13, asks_back 10/13, corrects 10/13, talkative 9/13 | Ölçüm hatası: A vakaları notları açık agent'ta koşuldu (PUB-05/08 add_note düşüşleri geçersiz). Gerçek hatalar: rakam rakam yıl okunmuyordu ve eksik cevapta agent bekliyordu ("one moment" döngüsü), iki parça yıl birleşmiyordu, 2. soruda ret açıklamasından sonra DOB soruluyordu → düzeltildi + test |
| 22:01 | mert-a / mert-b | in_words A / B | **9/10**, **3/3** | A: PUB-06 (floor iki kez teklif) |
| 22:11 | mert-a | pieces A | 8/10 | PUB-01: "19"+"88"+"1988" → 2095 okundu (bug, düzeltildi + test); PUB-06 |
| 22:18 | mert-b | pieces B (iki koşu) | 1/3, 2/3 | PUB-13: "30." ve "Twenty" ilk parçaları kullanıldı (model) → parça kuralı güçlendirildi; PUB-12 ikna sayımı |
| 22:25 | mert-a / mert-b (paralellik 10) | pieces A / B | **9/10**, 2/3 | PUB-01 ve PUB-13 düzeldi. Paralellik 10'da bir turda 30 sn sessizlik → koşularda varsayılan 5 kullanılmalı |
| 22:30 | mert-a (tekrar teklif kuralı) | PUB-06 pieces × 3 | 2/3 | floor tekrar teklifi azaldı, bitmedi |
| 22:53 | mert-b | PUB-12 pieces × 3 | — | Freya 503 "API key validation is temporarily unavailable"; koşmadı |
| 20:31 | mert-a | chat smoke (elle değişkenler, sahte customer_id) | akış doğru | parçalı DOB birleşti; HTTP hatasında `id_fix → reask` "could not check" dedi; submit exec 0,2–0,7 sn |

17:45 koşusundan sonra yapılan düzeltmeler:
- kayıt zinciri 6 adımdan 2'ye indi
- her code node'una kesinti koruması eklendi
- kod zaman sınırı 30 sn'ye çıktı
- "yarın" tarih kuralı eklendi

20:30 sürümündeki düzeltmeler (review): bkz. `11_REVIEW.md` §F.

Sıradaki ölçüm (mock erişimi gerekli): `fbb cases mert-a --brief A --reps 3`, `fbb cases mert-b --brief B --reps 3`, ardından `--style pieces|in_words|asks_back|corrects|talkative`. Hedef: medyan en yavaş tur < 10 sn, A ≥ 9/10 ve B 3/3 pass^3.
