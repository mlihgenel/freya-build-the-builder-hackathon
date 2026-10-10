"""Ortak test verileri. Brief A/B değerleri SADECE testlerde durur, `src/` altında asla."""
import json
from pathlib import Path

import pytest

from fbb.runtime.emit import bundle_namespace
from fbb.spec import Locale

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"

# Brief A'nın çalışma zamanı sabitleri (elle, brief'ten okunarak yazıldı).
RT_A = {
    "now_var": "now",
    "cal": {"weekdays": [0, 1, 2, 3, 4],
            "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]},
    "bands": [{"name": "early", "min": 1, "max": 7, "deadline_bd": 12, "deadline_rule": "", "attempts": 1},
              {"name": "late", "min": 8, "max": 45, "deadline_bd": 7, "deadline_rule": "", "attempts": 2}],
    "floor_rule": {"credit_card": "field:minimum_payment", "personal_loan": "field:instalment_amount",
                   "car_loan": "field:instalment_amount"},
    "product_wording": {"credit_card": "credit card ending {card_last4}", "personal_loan": "personal loan",
                        "car_loan": "car loan"},
    "debt_intro": "I am calling from the collections team about a late payment.",
    "debt_sentence": "Your {product} has a past-due amount of {past_due} and is {days_late} days late.",
    "first_ask_single": "Can you make this payment today?",
    "first_ask_multi": "Can you pay all of them today?",
    "attempts": [{"n": 1, "amount": "full", "date": "end_of_week", "bands": []},
                 {"n": 2, "amount": "floor", "date": "deadline", "bands": ["late"]}],
    "money": {"prefix": "", "suffix": "", "always_decimals": False},
    "callback": {"days": ["today", "next_business_day"], "start": "10:00", "end": "19:00", "hours_by_weekday": {},
                 "inclusive": True, "after_now": True, "retries": 1},
    "confirm_question": "Do you confirm?",
    "recording": {"mode": "batch", "retries": 1, "success_sentence": "You will receive a text message confirming this "
                  "promise.", "failure_sentence": "I am sorry, I could not record your promise.",
                  "failure_status": "service_error"},
    "status_reasons": ["refused", "hardship", "dispute", "paid", "service_error"],
    "closing": {
        "promise_outcome": "promise", "paid_outcome": "paid", "no_promise_outcome": "no_promise",
        "transfer_outcome": "transferred", "paid_status": "paid",
        "transfer_reasons": {"restructuring": "restructuring", "general": "human", "support": "support"},
        "status_to_reason": {},
        "no_reason_outcomes": ["promise", "paid"],
        "hangup_verified": ["no_promise", "refused"],
        "hangup_unverified": ["not_verified", "declined"],
    },
}


RT_A["locale"] = Locale().model_dump()


@pytest.fixture(scope="session")
def rt_a():
    return json.loads(json.dumps(RT_A))


@pytest.fixture(scope="session")
def ns(rt_a):
    return bundle_namespace(rt_a)


@pytest.fixture(scope="session")
def public_cases():
    return {c["id"]: c for c in json.loads((KIT / "public-test-set.json").read_text())}
