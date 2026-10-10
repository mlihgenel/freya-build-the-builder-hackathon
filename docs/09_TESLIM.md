# 09: Teslim

Organizatör teslim adımlarını gizli brief'lerden önce mail ile gönderecek. Bu dosya o maile göre güncellenecek.

## Kitin istedikleri (README "The final", hackathon sayfası)

| Ne | Nerede |
|---|---|
| Her gizli brief için export: `freya.export_workflow(workflow_id, "<brief>.workflow.json")` | `exports/<slot>.workflow.json`. `build-agent` otomatik yazar; tekrar için `uv run export-agent --slot <slot>` |
| Repo URL'si + commit hash | kullanıcının yeni reposu |
| Çalıştırma komutu | `uv run build-agent <brief dosyaları> --tools <openapi.json>` |
| Gizli brief başına bir trace | `traces/<slot>-<zaman>.txt` (+ `.jsonl`) |
| Takım adı | form |

## Trace'in içeriği (kit: "Plain text, no fixed format")
- `start` / `end`: zaman, slot, brief dosyaları, builder modeli
- `model_call`: her Claude çağrısının modeli, amacı ("brief → PolicySpec çıkarımı", "spec denetimi"), süresi ve maliyeti
- `freya_saved`: `workflow_id`, `agent_id`; `freya_readback`, `export`
- `selftest`: varsa simülasyon ID'si ve sonuç
- Key'ler `[GİZLİ]` ile değiştirilmiş olmalı (`make secrets-check`)

## Kontrol listesi (21:30 TR'de başla)
- [ ] `make test lint secrets-check freeze-check` yeşil
- [ ] `exports/` altında iki gizli brief'in dosyası var; `workflow_id`'ler trace'tekilerle aynı
- [ ] Export içinde `tools` (close_call lifecycle) mevcut
- [ ] `traces/` altında her brief için teslim edilecek tek trace seçildi (birden fazla çalıştırma varsa export'u üreten çalıştırmanınki)
- [ ] `BUGFIX_LOG.md` güncel
- [ ] Kullanıcı: commit + push, commit hash'ini al
- [ ] Form: takım adı, repo, hash, komut, workflow dosyaları, trace'ler
