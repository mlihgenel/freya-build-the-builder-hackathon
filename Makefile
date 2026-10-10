UV = env -u VIRTUAL_ENV uv
TOOLS = kit/tools/openapi.json

.PHONY: setup test lint build-a build-b local-a local-b secrets-check freeze-check

setup:          ## bağımlılıklar
	$(UV) sync

test:           ## ağsız birim testleri
	$(UV) run pytest

lint:
	$(UV) run ruff check src tests

local-a:        ## Brief A: altın spec ile yerel workflow (LLM ve Freya yok)
	$(UV) run build-agent kit/briefs/brief-a.md --tools $(TOOLS) --spec tests/fixtures/spec_a.json --no-deploy

local-b:
	$(UV) run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools $(TOOLS) --spec tests/fixtures/spec_ab.json --no-deploy

build-a:        ## Brief A: tam build (Claude + Freya)
	$(UV) run build-agent kit/briefs/brief-a.md --tools $(TOOLS)

build-b:
	$(UV) run build-agent kit/briefs/brief-a.md kit/briefs/brief-b.md --tools $(TOOLS)

secrets-check:  ## teslim edilecek dosyalarda key benzeri metin var mı
	@! grep -rnE 'fak_[A-Za-z0-9_-]{12,}|sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}' src tests docs exports traces README.md CLAUDE.md 2>/dev/null || (echo "olası key bulundu" && exit 1)
	@echo "key bulunmadı"

freeze-check:   ## src/ içinde brief değeri var mı
	$(UV) run pytest tests/test_no_hardcoded_brief.py
