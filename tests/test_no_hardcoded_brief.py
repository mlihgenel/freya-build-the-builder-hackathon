"""src/ altında public brief'lere özgü değer olmamalı (kural R6). Builder her şeyi brief'ten almalı."""
import re

from conftest import ROOT

FORBIDDEN = [
    "2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01",  # Brief A tatilleri
    "Freya Bank", "Daniel", "Reyes", "Almeida", "637.5", "4471", "4821",
    "minimum_payment", "instalment_amount", "card_last4",                  # get_account alan adları spec'ten gelir
    "date_of_birth", "phone_last4",                                         # kimlik alanları openapi/spec'ten gelir
    "restructuring", "no_promise", "not_verified", "not_reached",           # outcome/reason/queue değerleri
    "Do you confirm", "text message", "I am sorry for your loss",
]


def test_src_has_no_brief_values():
    hits = []
    for path in (ROOT / "src").rglob("*"):
        if path.suffix not in (".py", ".md", ".json"):
            continue
        text = path.read_text()
        for word in FORBIDDEN:
            if re.search(r"(?<![\w.])" + re.escape(word) + r"(?![\w])", text):
                hits.append(f"{path.relative_to(ROOT)}: {word}")
    assert hits == [], "src/ içinde brief değeri var:\n" + "\n".join(hits)
