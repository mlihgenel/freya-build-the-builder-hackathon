# 14: Final hazırlık raporu (11 Ekim 2026, 02:15–05:05 TR)

Bu rapor, Kardo'nun `next_offer` commit'lerini (`2644e60`'a kadar) çektikten sonra yapılan inceleme, testler ve düzeltmeleri anlatır. Plan ve kutular `13_FINAL_HAZIRLIK.md`'de, ham sonuç tablosu `10_TEST_REHBERI.md` §9'da.

## 1. Özet

| Ölçüt | Başlangıç (pull sonrası) | Şimdi |
|---|---|---|
| Brief A, `--reps 3` | 10/10 (Kardo, altın spec) | **10/10** (son sürüm, iki ayrı koşu) |
| Brief B, `--reps 3` | 3/3 | **3/3** (son sürüm, iki ayrı koşu) |
| Farklı günler (3 gün × 13 vaka) | hiç test edilmemişti | **38/39** (tek düşüş tarihten bağımsız, sonra düzeldi) |
| talkative stili, A / B | 7/10 / 2/3 (ilk tur) | **10/10 / 3/3** |
| asks_back stili, A / B | 8/10 / 2/3 (ilk tur) | düşen vakalar 3/3, B 3/3 |
| PUB-05 (hardship), stiller | birçok stilde düşüyordu | 4 stilde **4/4** |
| `per_product` kayıt modu | fiilen toplu kayıt yapıyordu | ürün başına kayıt, canlı prova 2/2 |
| Ret turunda en yavaş tur (B) | medyan 10 sn | medyan 2–4 sn |
| Birim testleri | 93 | **130** (hepsi yeşil), ruff temiz |

## 2. Yapılan değişiklikler

### 2.1 Pull incelemesinde bulunan eksikler
1. **Önceki anlaşmalar kayboluyordu.** Bir ürün `next_offer` ile anlaşıldıktan sonra başka bir üründe dispute/paid gelirse model bütün listeyi yeniden yazmak zorundaydı; unutursa öneri reddediliyordu. Düzeltme: `merge_offer_results`, modelin listesinde olmayan ürünleri `next_offer` sonuçlarından tamamlar (`test_propose_results_keeps_offers_already_agreed`).
2. **Ret turunda ~10 sn sessizlik.** Her ret turunda arka arkaya 3 code node (tool kaydı, `offer_step`, `commit_fix`) çalışıyordu. `offer_step` bayrağı kendisi temizleyip doğrudan teklif cümlesine gidiyor (`offer_go`); medyan 10 sn → 2 sn (`test_offer_goes_straight_to_speech`).
3. **Read-back reddinden sonra ikna denemesi yapılmıyordu.** Model sadece bir ürün kabul edilmişken `agreed_all` dedi; müşteri itiraz edince teklif durumu "bitti" kaldı. `readback_reset` son `next_offer`'ı geri alıyor (`offers_prev`); `agreed_all` açıklaması netleşti (`test_readback_rejection_reopens_offers`).

### 2.2 Farklı günler (Faz 4)
- **`fbb days <slot> --now <gün> [--brief] [--only] [--style] [--reps]`** (`src/fbb/days.py`): kitin `persona_for`, `run_simulation`, `score_ledger` fonksiyonlarıyla aynı zincir; sadece `now` ve o güne göre yazılmış senaryo/beklenti/checks değişir.
- **`tests/fixtures/days.json`**: 3 gün × 13 vaka. Beklentiler brief kurallarından elle hesaplandı ve builder kodunu kullanmayan bağımsız bir takvimle kontrol edildi; her satırda dayandığı kural (`why`) yazılı.
  - Cuma 16 Ekim: "yarın" Cumartesi → Pazartesi; bu Cuma = bugün → ilk teklif gelecek Cuma.
  - Cuma 23 Ekim: Pazartesi 26 tatil → callback ve "yarın" Salı'ya; 11 Kasım tatili.
  - Çarşamba 23 Aralık: haftanın son iş günü Perşembe (25 tatil); 25 Aralık ve 1 Ocak'ı ödeme günü olarak söylemek.
- **`tests/test_days.py`** (26 test): fixture'ların tutarlılığı (iş günü, deadline içi) ve builder runtime'ının aynı deadline, ilk teklif, kaydırma, callback günü ve takvim etiketlerini üretmesi. Kod düzeltmesi gerekmedi.

### 2.3 Konuşma stilleri (Faz 2)
Her düşüşün transcript'i okundu; düzeltmelerin hepsi genel, brief değeri içermiyor ve testli.

| Sorun (stil) | Kök neden | Düzeltme |
|---|---|---|
| "It is 1…" doğrulamaya gitti (asks_back) | ay içermeyen tek sayı okunamaz sayılıyordu | eksik cevap sayılır, sistem kalanını sorar (`test_lone_number_is_partial_date`) |
| DOB/telefon sorusu "iki-üç kez soruldu" (asks_back) | geri soruya cevapta ve ret açıklamasında soru tekrarlanıyordu; hakem her tekrarı ayrı soru sayıyor | açıklama ve geri soru cevabında soru tekrarlanmaz |
| Kimlik tur sınırı doldu, "declined" (talkative) | `max_node_turns` 12 | 30 |
| "You tell me" ret sayıldı, floor iki kez (asks_back) | model belirsiz cevabı `refused` bildirdi | `next_offer` açıklaması: soru/belirsiz cevap ret değildir |
| Kesik mesajda yanlış tarih (corrects) | "on the twenty-fourth," düzeltmeden önce kullanıldı | kesik mesajda `next_offer` çağrılmaz |
| Konuşkan müşterinin her parçasına cevap, "Can you pay today?" ×8 (talkative) | simüle müşterinin mesajları yarıda kesilip baştan başlıyor | mesajda cevap varsa önce cevap işlenir; yoksa kısa, değişen bir dinleme cevabı; soru/teklif tekrarı yok |
| "Go on." ×10 döngüsü, müşteri kapattı (talkative, ara sürüm) | ilk kesik-mesaj kuralı tek bir cümle öneriyordu ve tam cümlelere de uygulandı | değişen cevaplar, sadece gerçekten kesik mesajda |
| Destek ekibi iki kez teklif edildi (PUB-05, birçok stil) | model teklifi tekrar ediyordu | teklifi model brief kuralıyla bir kez yapar; ret `next_offer(result='hardship')` ile gelince açık ürünler `negotiation.hardship_status` ile hemen biter (`test_hardship_*`) |

Denenip geri alınan: hardship teklifini kodun tts ile söylemesi. Model teklifi zaten kendisi yaptığı için çift teklif oluştu.

### 2.4 Kod yolları (Faz 3)
- **3.1 `per_product` + `next_offer`:** kabul edilen ürün kaydedilmeden sıradaki ürüne geçiliyordu. Şimdi kabul → o ürün (ve bekleyen durumlar) hemen read-back ve kayıt → "kaydedildi" + sıradaki ürünün ilk teklifi tek cümlede (`next_offer_say`). Propose edilenler `offers_json.proposed`'da tutuluyor (çift öneri yok). Testler: `test_per_product_with_next_offer`, `test_per_product_last_product_agreed_after_refusals`.
- **3.3** (dispute/paid + `next_offer`): 2.1/1 ile kapandı.

### 2.5 Spec ve çıkarım
- `negotiation.hardship_status` (yeni alan): brief zorlukta transfer teklifi istiyorsa, teklif reddedilince ürünlerin alacağı durum. `cross_check` geçerli bir `statuses` id'si olduğunu denetler; `specdiff` PUAN alanı sayar; `extract.md` nasıl doldurulacağını anlatır.
- Altın spec'ler (`spec_a.json`, `spec_ab.json`): `hardship_status: "hardship"`.

## 3. Test sonuçları (kronolojik)

| Zaman | Ne | Sonuç |
|---|---|---|
| 02:22 | pull sonrası B ×1; pieces PUB-01, PUB-06 | 3/3 (ret turu medyanı 10 sn); 2/2 |
| 02:26–02:28 | ret turu ve read-back düzeltmeleri, B ×1 | 2/3 → 3/3, medyan 2 sn |
| 02:48–02:55 | `fbb days`, 3 gün × A/B | A 10/10, 10/10, 9/10; B 3/3 ×3 |
| 02:58 | PUB-05 transfer-bir-kez kuralı: `--reps 3`, corrects, talkative | 3/3, 1/1, 1/1 |
| 03:00–03:45 | 5 stil × A/B ×1 (eski sürüm) | pieces 8/10·3/3, in_words 10/10·3/3, asks_back 8/10·2/3, corrects 10/10·2/3, talkative 7/10·2/3 |
| 03:50–04:20 | düzeltmelerden sonra: talkative, asks_back | talkative A 8/10 · B 3/3; asks_back A 8/10 · B 3/3 |
| 04:05–04:15 | hedefli PUB-03/05/07: talkative, asks_back, pieces | 1/3, 3/3, 3/3 |
| 04:15–04:25 | aynı sürüm A / B `--reps 3` | **10/10**, **3/3** |
| 04:30–04:55 | son sürüm: talkative A/B, PUB-05 × 4 stil, A/B `--reps 3` | **10/10**, **3/3**, **4/4**, **10/10**, **3/3** (hiç düşüş yok) |
| 05:00 | son sürüm A ×1, B ×1; `mert-pp` (per_product) PUB-12, PUB-13 | 10/10, 3/3, 2/2 |

Gecikme: son koşularda en yavaş tur medyanı 1–4 sn, en kötü 7 sn civarı; müşterinin kapattığı başarısız çağrı (sim kaynaklı bir tane hariç) yok.

## 4. Kalan işler ve eksikler

**Ölçülmeyenler**
- pieces, in_words, asks_back ve corrects stilleri son sürümle **bütün brief olarak** yeniden koşulmadı; sadece düşen vakalar hedefli ölçüldü. Stil koşuları tek tekrarlık (pass³ değil).
- Farklı günler stillerle birleştirilmedi (`fbb days --style …` hazır).
- Müşteri callback'i (Faz 3.2), teklif sırasında transfer (3.4) ve kod servisi kesintisi (3.6) canlıda denenmedi; sadece birim testi var.

**Planda kalanlar (`13_FINAL_HAZIRLIK.md`)**
- Faz 5: uydurma Brief D (per_product, müşteri callback'i, farklı outcome tablosu, posta kodu) + Brief C/D deploy ve chat provası.
- Faz 6: builder modeli kararı, temiz klondan teslim provası, final makinesinde mock erişimi (VPN), kredi durumu.
- Faz 7: dondurma (Paz 18:00 TR), son `--reps 3`.

**Bilinen riskler**
- **Simülasyon kaynaklı:** konuşkan müşterinin mesajları yarıda kesilip baştan başlıyor; bir koşuda müşteri hiçbir şey söylemeden kapattı (pieces PUB-09). Bunlar bizim kontrolümüzde değil; agent'ın tepkisi iyileştirildi.
- **Eşzamanlı mesaj yarışı:** müşteri kod çalışırken art arda iki cevap verirse ilki doğrulanmadan kaybolabiliyor (asks_back PUB-03, bir kez görüldü). Platform davranışı.
- **Tutar tipi:** create_promise'e tutar metin olarak gidiyor (`"amount": "300.0"`); mock kabul ediyor, başka bir mock reddedebilir.
- **Model sınıflandırmaları:** `next_offer`'ın `agreed`/`refused`/`hardship` seçimi hâlâ modelde; kalan düşüşlerin çoğu bu sınıftan. Read-back ve kod tarafı denetimler hatanın etkisini sınırlıyor ama sıfırlamıyor.
- **İkili çıkarım** (spec tutarlılığı için iki çıkarım + `specdiff`) yapılmadı.
- Varsayılan paralellik (5) dışında ölçüm yapılmamalı: 10'da agent turları 30 sn'ye kadar yavaşladı.

## 5. Tekrar üretmek

```bash
make test lint
uv run build-agent kit/briefs/brief-a.md --tools kit/tools/openapi.json --spec tests/fixtures/spec_a.json --slot <ad>-a
uv run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools kit/tools/openapi.json --spec tests/fixtures/spec_ab.json --slot <ad>-b
uv run fbb cases <ad>-a --brief A --reps 3
uv run fbb cases <ad>-b --brief B --reps 3
for d in 2026-10-16T11:00 2026-10-23T11:00 2026-12-23T11:00; do uv run fbb days <ad>-a --now $d --brief A; uv run fbb days <ad>-b --now $d --brief B; done
for st in pieces in_words asks_back corrects talkative; do uv run fbb cases <ad>-a --brief A --style $st; uv run fbb cases <ad>-b --brief B --style $st; done
```

Brief A vakaları A agent'ında, B vakaları A+B agent'ında koşulur. Mock bazı TR ağlarından erişilemiyor (VPN).

## 6. Değişen dosyalar
- **Yeni:** `src/fbb/days.py`, `tests/test_days.py`, `tests/fixtures/days.json`, `docs/14_RAPOR_11EKIM.md`
- **Kod:** `src/fbb/runtime/flow.py`, `src/fbb/runtime/normalize.py`, `src/fbb/spec.py`, `src/fbb/specdiff.py`, `src/fbb/workflow/graph.py`, `src/fbb/workflow/texts.py`, `src/fbb/ingest/prompts/extract.md`, `src/fbb/cli.py`, `.gitignore`
- **Test:** `tests/test_graph.py`, `tests/test_runtime.py`, `tests/test_spec.py`, `tests/fixtures/spec_a.json`, `tests/fixtures/spec_ab.json`
- **Doküman:** `docs/00_INDEX.md`, `docs/10_TEST_REHBERI.md`, `docs/13_FINAL_HAZIRLIK.md`
