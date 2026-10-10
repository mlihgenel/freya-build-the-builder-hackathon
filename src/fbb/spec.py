"""PolicySpec: brief'in yapısal hali. Bütün değerler brief'ten ve openapi'den gelir; kodda brief değeri yoktur.

LLM (ingest/extract.py) bu şemayı doldurur, pydantic doğrular, `cross_check` openapi ile tutarlılığı kontrol eder.
`to_runtime` spec'i Freya code node'larının kullandığı `RT` sözlüğüne çevirir.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from fbb.ingest.openapi import ToolCatalog


class Strict(BaseModel):
    model_config = {"extra": "forbid"}


class OutcomeRef(Strict):
    outcome: str
    reason: str = ""


class CallVariables(Strict):
    customer_id: str = Field("customer_id", description="Her tool çağrısına giden müşteri kimliği değişkeni")
    now: str = Field("now", description="Şimdiki tarih-saat değişkeni; bütün tarih kuralları bunu kullanır")
    address: str = Field(..., description="Müşteriye hitap şablonu, değişkenler {değişken} biçiminde, ör. '{title} {last_name}'")
    all: list[str] = Field(default_factory=list, description="Brief'in listelediği bütün çağrı değişkenleri")


class Opening(Strict):
    first_sentence: str = Field(..., description="Açılışta birebir söylenecek cümle (kim, hangi kurum, kayıt bildirimi)")
    confirm_question: str = Field(..., description="Kişiyi doğrulama sorusu, {değişken} şablonlu")
    accepted_confirmations: list[str]
    not_confirmations: list[str] = Field(default_factory=list)
    forbidden_before_verification: list[str] = Field(default_factory=list, description="Kimlik doğrulanmadan söylenmeyecek kelimeler")
    max_asks: int = 2
    unclear: OutcomeRef
    robot_answer: str = Field("", description="'Robot musun?' sorusuna cevap")
    scam_answer: str = Field("", description="'Dolandırıcılık mı?' sorusuna cevap")
    unknown_answer: str = Field("", description="Tool'lardan cevaplanamayan soruya cevap")


class Callback(Strict):
    days: list[Literal["today", "next_business_day"]] = Field(default_factory=lambda: ["today", "next_business_day"])
    start: str = Field(..., description="HH:MM")
    end: str = Field(..., description="HH:MM")
    inclusive: bool = True
    after_now: bool = True
    retries: int = Field(1, description="Pencere dışı teklifte kaç kez daha sorulur")


class ThirdParty(Strict):
    say_nothing_beyond_opening: bool = True
    ask_reachability: str = Field(..., description="Müşteriye ne zaman ulaşılabileceğini soran cümle")
    callback: Callback
    callback_outcome: OutcomeRef
    no_callback_outcome: OutcomeRef
    wrong_number_outcome: OutcomeRef
    deceased_outcome: OutcomeRef
    deceased_sentence: str = ""
    rules: list[str] = Field(default_factory=list, description="Üçüncü kişiyle ilgili diğer kurallar, kısa cümleler")


class IdentityQuestion(Strict):
    field: str = Field(..., description="verify_identity 'field' enum değeri")
    ask: str = Field(..., description="Soruyu soran cümle")
    answer_type: str = Field(..., description="'date' | 'digits:N' | 'year' | 'text'")


class Identity(Strict):
    questions: list[IdentityQuestion]
    one_at_a_time: bool = True
    numeric_date_order: Literal["DMY", "MDY", "YMD"] = "DMY"
    max_wrong_total: int = 3
    retry_wrong_sentence: str = Field("", description="Yanlış cevaptan sonra tekrar sorarken söylenecek kısa giriş")
    swap_hint: str = Field("", description="verify_identity'nin gün/ay yer değişimi hint değeri, yoksa boş")
    swap_instruction: str = Field("", description="Hint gelince müşteriye söylenecek cümle")
    fail_sentence: str = Field(..., description="Doğrulama başarısız olunca söylenecek cümle")
    fail_outcome: OutcomeRef
    decline_explain: str = Field(..., description="Cevap vermek istemeyene bir kez söylenecek açıklama")
    decline_outcome: OutcomeRef
    decline_close_after: int = 2
    purpose_question_counts_as_decline: bool = True


class Band(Strict):
    name: str
    min: int
    max: int
    deadline_bd: int = Field(..., description="Bugünden sonraki kaçıncı iş günü son tarih")
    attempts: int


class Attempt(Strict):
    n: int
    amount: Literal["full", "floor"]
    date: str = Field(..., description="'end_of_week' | 'deadline' | 'today' | 'next_business_day' | 'business_days:N'")
    bands: list[str] = Field(default_factory=list, description="Boşsa her bantta geçerli")


class Disclosure(Strict):
    debt_intro: str = Field(..., description="Doğrulamadan sonra aramanın amacını söyleyen cümle")
    debt_sentence: str = Field(..., description="Ürün başına cümle; {product} {past_due} {days_late} ve get_account alanları")
    product_wording: dict[str, str] = Field(..., description="Ürün tipi → ifade şablonu, ör. '<ürün adı> ending {<alan>}'")
    floor_field: dict[str, str] = Field(..., description="Ürün tipi → get_account'taki floor alanı")


class Calendar(Strict):
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], description="İş günleri, Pazartesi=0")
    holidays: list[str] = Field(default_factory=list, description="YYYY-MM-DD")


class Negotiation(Strict):
    first_ask_single: str
    first_ask_multi: str = ""
    attempts: list[Attempt]
    rules: list[str] = Field(..., description="Müzakere kuralları, kısa emir cümleleri (tarih, tutar, ikna, ret tanımı)")
    forbidden_offers: list[str] = Field(default_factory=list)


class Confirmation(Strict):
    confirm_question: str
    rules: list[str] = Field(default_factory=list)
    change_after_record_sentence: str = ""


class Recording(Strict):
    retries: int = 1
    success_sentence: str = Field(..., description="Brief'in başarılı kayıttan sonra şart koştuğu cümle, birebir. "
                                  "Hangi promise'in kaydedildiğini sistem zaten söyler; onu buraya yazma")
    failure_sentence: str = Field(..., description="İki kez başarısız olunca söylenecek cümle")
    failure_status: str = Field("service_error", description="Başarısız ürünün durum/sebep değeri")


class Transfer(Strict):
    id: str = Field(..., description="kısa ad")
    queue: str = Field(..., description="transfer_to_agent queue enum değeri")
    trigger: str = Field(..., description="Ne zaman: müşterinin ne söylediği")
    say: str = Field("", description="Transferden önce söylenecek cümle")
    ask_first: str = Field("", description="Önce bir kez sorulacak soru (ör. insan talebinde 'yardımcı olabilir miyim')")
    stages: list[Literal["pre_identity", "post_verify"]] = Field(default_factory=lambda: ["post_verify"])


class Status(Strict):
    id: str = Field(..., description="add_note reason / kapanış reason değeri, ör. dispute")
    trigger: str = Field(..., description="Müşteri ne söylerse bu durum")
    say: str = Field("", description="O durumda söylenecek cümle")
    persuade: bool = Field(False, description="Bu durumda ikna denemesi yapılır mı")


class MultiProduct(Strict):
    enabled: bool = False
    rules: list[str] = Field(default_factory=list)
    notes_enabled: bool = False
    no_notes_on_transfer: bool = True


class Closing(Strict):
    promise_outcome: str
    paid_outcome: str
    no_promise_outcome: str
    transfer_outcome: str
    paid_status: str = "paid"
    transfer_reasons: dict[str, str] = Field(..., description="queue → kapanış reason")
    status_to_reason: dict[str, str] = Field(default_factory=dict, description="Durum adı farklıysa → kapanış reason")
    no_reason_outcomes: list[str]
    hangup_verified: OutcomeRef
    hangup_unverified: OutcomeRef
    goodbye_sentence: str = Field(..., description="Çağrının son cümlesi: teşekkür ve veda")


class Money(Strict):
    prefix: str = ""
    suffix: str = ""
    always_decimals: bool = False


class PolicySpec(Strict):
    language: str = "English"
    bank_name: str
    agent_role: str = Field(..., description="Agent'ın kim olduğu, tek cümle")
    call_variables: CallVariables
    opening: Opening
    third_party: ThirdParty
    identity: Identity
    disclosure: Disclosure
    calendar: Calendar
    bands: list[Band]
    negotiation: Negotiation
    confirmation: Confirmation
    recording: Recording
    transfers: list[Transfer]
    statuses: list[Status] = Field(..., description="Promise'siz biten ürünlerin durumları (refused, dispute, paid…)")
    multi_product: MultiProduct
    closing: Closing
    money: Money = Field(default_factory=Money)
    tool_fields: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Alan adı farklıysa: tool → {rol: openapi alan adı}. Roller: customer_id, "
        "field, answer, product_id, amount, date, time, reason, queue, outcome")
    general_rules: list[str] = Field(default_factory=list, description="Her adımda geçerli kurallar")
    unmapped: list[str] = Field(default_factory=list, description="Yukarıdaki alanlara sığmayan kurallar")

    @model_validator(mode="after")
    def _bands_ok(self):
        spans = sorted((b.min, b.max) for b in self.bands)
        for (_, a1), (b0, _) in zip(spans, spans[1:], strict=False):
            if b0 <= a1:
                raise ValueError(f"bantlar çakışıyor: {spans}")
        return self


def cross_check(spec: PolicySpec, cat: ToolCatalog) -> list[str]:
    """Spec'teki enum değerlerinin openapi ile uyumunu kontrol eder. Hata listesi döner (boşsa tamam)."""
    errs: list[str] = []

    def need(tool: str, field: str, value: str, what: str):
        allowed = cat.enum(tool, field)
        if allowed and value not in allowed:
            errs.append(f"{what}: '{value}' {tool}.{field} enum'unda yok ({allowed})")

    for q in spec.identity.questions:
        need("verify_identity", "field", q.field, "kimlik sorusu")
    for t in spec.transfers:
        need("transfer_to_agent", "queue", t.queue, "transfer kuyruğu")
    if spec.multi_product.notes_enabled:
        for s in spec.statuses:
            need("add_note", "reason", s.id, "not sebebi")
    c = spec.closing
    outs = [c.promise_outcome, c.paid_outcome, c.no_promise_outcome, c.transfer_outcome, c.hangup_verified.outcome,
            c.hangup_unverified.outcome, spec.opening.unclear.outcome, spec.identity.fail_outcome.outcome,
            spec.identity.decline_outcome.outcome, spec.third_party.callback_outcome.outcome,
            spec.third_party.no_callback_outcome.outcome, spec.third_party.wrong_number_outcome.outcome,
            spec.third_party.deceased_outcome.outcome]
    for o in outs:
        need("close_call", "outcome", o, "outcome")
    for ptype in spec.disclosure.product_wording:
        need("get_account", "products[].type", ptype, "ürün tipi")
    return errs


def to_runtime(spec: PolicySpec) -> dict:
    """Spec → Freya code node'larının kullandığı RT sözlüğü."""
    c = spec.closing
    status_reasons = [s.id for s in spec.statuses]
    if spec.recording.failure_status not in status_reasons:
        status_reasons.append(spec.recording.failure_status)
    return {
        "now_var": spec.call_variables.now,
        "cal": {"weekdays": spec.calendar.weekdays, "holidays": sorted(spec.calendar.holidays)},
        "bands": [b.model_dump() for b in spec.bands],
        "floor_field": spec.disclosure.floor_field,
        "product_wording": spec.disclosure.product_wording,
        "debt_intro": spec.disclosure.debt_intro,
        "debt_sentence": spec.disclosure.debt_sentence,
        "first_ask_single": spec.negotiation.first_ask_single,
        "first_ask_multi": spec.negotiation.first_ask_multi or spec.negotiation.first_ask_single,
        "attempts": [a.model_dump() for a in spec.negotiation.attempts],
        "money": spec.money.model_dump(),
        "callback": spec.third_party.callback.model_dump(),
        "status_reasons": status_reasons,
        "identity": {
            "questions": [q.model_dump() for q in spec.identity.questions],
            "numeric_date_order": spec.identity.numeric_date_order,
            "max_wrong_total": spec.identity.max_wrong_total,
            "swap_hint": spec.identity.swap_hint,
            "swap_instruction": spec.identity.swap_instruction,
            "retry_wrong_sentence": spec.identity.retry_wrong_sentence,
        },
        "recording": spec.recording.model_dump(),
        "notes_enabled": spec.multi_product.notes_enabled,
        "goodbye": c.goodbye_sentence,
        "call_vars": spec.call_variables.all,
        "closing": {
            "promise_outcome": c.promise_outcome, "paid_outcome": c.paid_outcome,
            "no_promise_outcome": c.no_promise_outcome, "transfer_outcome": c.transfer_outcome,
            "paid_status": c.paid_status, "transfer_reasons": c.transfer_reasons,
            "status_to_reason": c.status_to_reason, "no_reason_outcomes": c.no_reason_outcomes,
            "hangup_verified": [c.hangup_verified.outcome, c.hangup_verified.reason],
            "hangup_unverified": [c.hangup_unverified.outcome, c.hangup_unverified.reason],
        },
    }
