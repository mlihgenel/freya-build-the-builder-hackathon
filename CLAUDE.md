# CLAUDE.md

Freya × YC "Build the Builder" (10–11 Ekim 2026) için yazılan builder. Builder, brief (.md) ve `openapi.json`'dan bir Freya workflow'u, yani bir telefon agent'ı üretir.

Puan: 3 tekrarın üçünde de geçen vaka / 60. Geçmek için ledger kontrolü (`kit/tools/score.py`) ve Gemini hakemi birlikte geçmeli.

## Önce oku
- `docs/00_INDEX.md`: harita
- `docs/01_KURALLAR_VE_PUANLAMA.md`: kesin kurallar (R1–R12)
- `docs/05_GRAF_TASARIMI.md`: graf ve değişken sözleşmesi
- `docs/02_FREYA_PLATFORM_GERCEKLERI.md`: platform davranışları ve deney sonuçları

## Komutlar
- `uv run pytest`: yeşil kalmalı
- `uv run ruff check src tests`
- `uv run build-agent <brief.md…> --tools <openapi.json> [--no-deploy] [--spec f.json] [--selftest cases:A]`
- `uv run fbb cases <agent_id> --brief A [--reps 3] [--style pieces]`
- `uv run fbb chat <slot> "Hello?" --case PUB-01`
- Bu klasörün dışında aktif bir venv varsa komutların başına `env -u VIRTUAL_ENV` ekleyin.

## Kurallar
- `kit/` organizatörün kiti, **asla değiştirme**. Özellikle `freya.py` içindeki `AGENT_LLM`.
- `kit/.claude/skills/build-phone-agent` kitin örnek builder'ına ait. Onu kullanma. Bizim builder'ımız `src/fbb`, mimarisi `docs/03` ve `docs/05`'te.
- Proje durumu ve sıradaki adımlar `docs/00_INDEX.md` ("Durum") ile `docs/07_RUNBOOK_FINAL.md`'deki faz tablosunda. Her önemli adımdan sonra ikisini de güncelle.
- `src/` altında **hiçbir brief değeri olmaz**: tatil tarihi, tutar, isim, outcome adı, cümle. Hepsi spec'ten gelir. `tests/test_no_hardcoded_brief.py` bunu denetler. A/B değerleri sadece `tests/` altında durur.
- Gizli brief'ler açıldıktan sonra (Paz 17:00 UTC) sadece bug fix yapılır. Her değişiklik `docs/BUGFIX_LOG.md`'ye yazılır.
- `src/fbb/runtime/` Freya içinde çalışır:
  - sadece `datetime`, `json`, `re` kullanılabilir
  - iki süslü parantez yan yana yazılmaz
  - hata fırlatılmaz
  - route'lar string bayraklarla kurulur
- Aynı spec her zaman aynı workflow'u üretir (`test_deterministic`).
- Workflow sadece `kitapi.save(slot)` ile kaydedilir (200 workflow sınırı var).
- Key'ler `.env`'de durur (`env.sh` de okunur). Trace'ler redaction'dan geçer.
- Davranış değişikliği `fbb cases --reps 3` ile ölçülür. Her başarısızlığın transcript'i okunmadan prompt değiştirilmez.
- Git işlemlerini kullanıcı yapar.
