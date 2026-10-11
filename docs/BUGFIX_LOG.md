# Bug fix kaydı

Gizli brief'ler açıldıktan sonra (Pazar 17:00 UTC) yapılan **her** değişiklik buraya yazılır. Kural: bug düzeltmek serbest; gizli brief'ten kural, değer ya da isim eklemek yasak.

| Zaman (TR) | Dosya | Değişiklik | Neden (genel hata) | Brief'e özgü değer var mı? |
|---|---|---|---|---|
| 11 Eki 19:50 (dondurmadan sonra, brief'ler açılmadan önce) | `src/fbb/ingest/prompts/extract.md`, `audit.md`, `src/fbb/workflow/lint.py` | Açılış cümlesi brief'te birebir (tırnak içinde / "word for word") verilmişse aynen kopyalanır, "recorded" kelimesi dahil; brief sadece "kaydedildiğini söyle" diyorsa "we record this call" kalır. Lint uyarı metni buna göre | 10 Eki'de eklenen genel kural, birebir istenen açılışı değiştiriyordu (prova Brief E: "this call is being recorded" → "we record this call"); hakem birebir açılışı kontrol ederse bütün vakalar düşer. Doğrulama: E yeniden çıkarım birebir, A "We record this call." değişmedi | hayır |
