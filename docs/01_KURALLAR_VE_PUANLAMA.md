# 01: Kurallar ve puanlama

Kaynaklar: `kit/README.md` (kit v3), https://www.freyavoice.ai/hackathon ve kickoff maili (10 Ekim 2026).

## Görev
- Builder bir brief'i (bir ya da daha fazla .md dosyası) ve brief'in tool API'sini (`openapi.json`) okur.
- Freya'da bir **workflow** oluşturur. Workflow, telefon agent'ının kendisi.
- Puanlanan şey sadece bu telefon agent'ı. Agent, gecikmiş ödemesi olan müşteriyi arar: kimliği doğrular, borcu söyler, ödeme sözü almaya çalışır ve çağrıyı doğru sonuçla kapatır.

## Puanlama
- 2 gizli brief × 30 müşteri = 60 vaka. Her vaka **3 kez** çalışır ve ancak **üçü de** geçerse sayılır.
- Final skoru = geçen vaka / 60. Kısmi puan yok.
- Bir çalışmanın geçmesi için **hepsi** doğru olmalı:
  1. **Ledger** (`kit/tools/score.py`): `(outcome, reason)`, promise'ler `(product_id, amount, date)`, notlar `(product_id, reason)`, callback'ler `(date, time)` ve transfer kuyrukları beklenenle birebir aynı.
     - Son tool çağrısı `close_call` olmalı.
     - Kimlik doğrulanmadan `get_account` ya da `create_promise` çağrılmamış olmalı.
     - Ulaşılamayan müşteri vakalarında (`not_reached` ve benzeri) `verify_identity` ve `get_account` hiç çağrılmamış olmalı.
  2. **Policy** ve 3. **dürüstlük**: Gemini hakem transcript'i vakanın `checks` listesine göre okur.
- Eşitlik bozma sırası: geçen vakalardaki toplam promise tutarı → daha kısa toplam build süresi → daha erken teslim.

## Final
- Gizli brief'ler **Paz 17:00 UTC (20:00 TR)**'de açılır, teslim **20:00 UTC (23:00 TR)**'de kapanır.
- Brief'lerden biri temiz bir spesifikasyon. Diğeri ham banka materyali: mail, poliçe alıntısı, onu değiştiren bir memo ve kod listesi.
- Her brief kendi `openapi.json`'u ile gelir. **7 tool'un adları aynı kalır**, alanlar ve izin verilen değerler değişebilir.
- Değişebilecekler: sayılar ve limitler, kimlik soruları, outcome tablosu, takvim.
- Müşterilerin en fazla 3 ürünü olabilir. Müşteriler parçalı konuşur, söylediğini düzeltir, konudan sapar, karşı soru sorar ve tutarı ya da tarihi yazıyla söyler.
- Testler birden fazla takvim gününde (`now`) ve 3'er kez yapılır.

## Kurallar → builder'daki karşılığı

| # | Kural | Karşılığı |
|---|---|---|
| R1 | Tek komut, brief girdi, agent çıktı, elle adım yok | `uv run build-agent <brief…> --tools <openapi.json>` |
| R2 | Brief başına en fazla 30 dk, self-test dahil | Hedef ≤ 10 dk. Self-test opsiyonel ve 20. dakikada kesilir |
| R3 | `AGENT_LLM` (`kit/freya.py`) değiştirilemez | `kit/` hiç değiştirilmez; `kitapi.py` onu import eder |
| R4 | Agent sadece bankanın tool API'sini çağırabilir. Code ve hook serbest | URL'ler `openapi.servers` + path'ten okunur |
| R5 | En fazla 200 workflow | `kitapi.save(slot)` aynı workflow'u günceller |
| R6 | Brief açıldıktan sonra sadece bug fix | `docs/BUGFIX_LOG.md`, `tests/test_no_hardcoded_brief.py` |
| R7 | Trace: başlangıç/bitiş, model çağrıları (model + amaç), Freya ID'leri, self-test'ler, key yok | `src/fbb/trace.py` |
| R8 | Teslim: `freya.export_workflow` dosyası, repo, commit, komut, trace | `exports/`, `traces/`, `docs/09_TESLIM.md` |
| R9 | Müşteri konuşma tarzları, birden fazla `now` günü | Tarihler çağrı sırasında code node'da hesaplanır, cevaplar normalize edilir |
| R10 | En fazla 3 ürün, `get_account` sırasıyla | Ürünler kodda tutulur, kayıt sırası ürün sırasıdır |
| R11 | Platform yoklanmaz, yük testi yapılmaz | Sadece belgelenmiş API'ler; deneyler kendi workflow'umuzla |
| R12 | `promise` ve `paid` outcome'larında `reason` alanı **gönderilmez** | `close_call` pre-hook'u `reason`'ı siler |

## Kurallar dışında kalan ama önemli olanlar
- Workflow güncellemesi sonrası **publish** şart (`freya.save_workflow` bunu yapar). Publish edilmezse simülasyon eski versiyonu çalıştırır.
- Workspace'te aynı anda tek simülasyon çalışabilir. 10 vaka 3–11 dk sürer.
- Agent ~10 sn'den uzun susarsa müşteri telefonu kapatır (`customer-ended-call`).
