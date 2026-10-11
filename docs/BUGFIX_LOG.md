# Bug fix kaydı

Gizli brief'ler açıldıktan sonra (Pazar 17:00 UTC) yapılan **her** değişiklik buraya yazılır. Kural: bug düzeltmek serbest; gizli brief'ten kural, değer ya da isim eklemek yasak.

| Zaman (TR) | Dosya | Değişiklik | Neden (genel hata) | Brief'e özgü değer var mı? |
|---|---|---|---|---|
| 11 Eki 19:50 (dondurmadan sonra, brief'ler açılmadan önce) | `src/fbb/ingest/prompts/extract.md`, `audit.md`, `src/fbb/workflow/lint.py` | Açılış cümlesi brief'te birebir (tırnak içinde / "word for word") verilmişse aynen kopyalanır, "recorded" kelimesi dahil; brief sadece "kaydedildiğini söyle" diyorsa "we record this call" kalır. Lint uyarı metni buna göre | 10 Eki'de eklenen genel kural, birebir istenen açılışı değiştiriyordu (prova Brief E: "this call is being recorded" → "we record this call"); hakem birebir açılışı kontrol ederse bütün vakalar düşer. Doğrulama: E yeniden çıkarım birebir, A "We record this call." değişmedi | hayır |
| 11 Eki 20:05 (final açıldı) | `src/fbb/ingest/sources.py`, `src/fbb/ingest/contract.py`, `src/fbb/build.py`, `builder/build.py`, `pyproject.toml` (pypdf), `.gitignore` | Final formatı (resmi sayfa, 11 Eki): vaka bir belge klasörü (Markdown/Word/PDF/Excel), komut `python3 builder/build.py {case_folder} {mock_url}`. Klasör okuyucu (docx/xlsx zip-XML, pdf pypdf, csv/json/md); tool API klasördeki openapi'den ya da yoksa servis sözleşmesinden (Claude → OpenAPI); sunucu = verilen mock adresi (sözleşmedeki yol korunur); `builder/build.py` sistem python'unda proje ortamına geçer | Builder yeni girdi biçimini okuyamıyordu | hayır |
| 11 Eki 20:07 | `src/fbb/runtime/normalize.py`, `flow.py`, `validate.py` | Türkçe sayı, sıra sayısı ve ay adları (metin Türkçe görünüyorsa İngilizce karşılıklarına çevrilip okunur); ondalık virgül ('637,50', '1.250,75') | Final Türkçe; söylenen tarih/sayılar okunamıyordu | hayır |

