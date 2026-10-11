"""PolicySpec: brief'in yapısal hali. Bütün değerler brief'ten ve openapi'den gelir; kodda brief değeri yoktur.

LLM (ingest/extract.py) bu şemayı doldurur, pydantic doğrular, `cross_check` openapi ile tutarlılığı kontrol eder.
`to_runtime` spec'i Freya code node'larının kullandığı `RT` sözlüğüne çevirir.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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


CALLBACK_DAY = r"^(today|next_business_day|business_days:\d+)$"
AMOUNT_RULE = r"^(full|floor|percent:\d+(\.\d+)?|fixed:\d+(\.\d+)?)$"
DEADLINE_RULE = r"^(business_days:\d+|calendar_days:\d+|end_of_month|date:\d{4}-\d{2}-\d{2})$"
_FLOOR_ONE = r"(field:[A-Za-z_][\w]*|percent:\d+(\.\d+)?|fixed:\d+(\.\d+)?)"
FLOOR_RULE = rf"^({_FLOOR_ONE}|(max|min):{_FLOOR_ONE}(,{_FLOOR_ONE})+)$"


class HourWindow(Strict):
    start: str = Field(..., description="HH:MM")
    end: str = Field(..., description="HH:MM")


class Callback(Strict):
    days: list[str] = Field(default_factory=lambda: ["today", "next_business_day"],
                            description="'today' (only if today is a business day) | 'next_business_day' | "
                            "'business_days:N' (each of the next N business days)")
    start: str = Field(..., description="HH:MM")
    end: str = Field(..., description="HH:MM")
    hours_by_weekday: dict[str, HourWindow] = Field(
        default_factory=dict, description="Saat aralığı güne göre değişiyorsa: '0'..'6' (Pazartesi=0) → {start, end}")
    inclusive: bool = True
    after_now: bool = True
    retries: int = Field(1, description="Pencere dışı teklifte kaç kez daha sorulur")

    @field_validator("days")
    @classmethod
    def _days(cls, v):
        for d in v:
            if not re.match(CALLBACK_DAY, d):
                raise ValueError(f"desteklenmeyen callback günü: {d}")
        return v


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
    field: str = Field(..., description="verify_identity 'field' enum değeri; tool soru başına ayrı gövde alanı "
                       "istiyorsa o alanın adı")
    ask: str = Field(..., description="Soruyu soran cümle")
    answer_type: str = Field(..., description="'date' | 'digits:N' | 'year' | 'postcode' | 'alnum' | 'text'")
    example: str = Field("", description="Tool API'nin beklediği biçimde örnek bir değer (ör. 'SW1A 1AA'), varsa")


class Identity(Strict):
    questions: list[IdentityQuestion]
    verify_mode: Literal["each", "all_at_once"] = Field(
        "each", description="each: her cevap ayrı verify çağrısı; all_at_once: tool bütün cevapları tek çağrıda istiyor")
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
    deadline_rule: str = Field("", description="deadline_bd yerine: 'business_days:N' | 'calendar_days:N' (o günden "
                               "geç olmayan son iş günü) | 'end_of_month' (ayın son iş günü) | 'date:YYYY-MM-DD'")
    attempts: int

    @field_validator("deadline_rule")
    @classmethod
    def _rule(cls, v):
        if v and not re.match(DEADLINE_RULE, v):
            raise ValueError(f"desteklenmeyen deadline kuralı: {v}")
        return v


class Attempt(Strict):
    n: int
    amount: str = Field(..., description="'full' | 'floor' | 'percent:N' (borcun yüzdesi) | 'fixed:X'")
    date: str = Field(..., description="'end_of_week' | 'deadline' | 'today' | 'next_business_day' | 'business_days:N'")
    bands: list[str] = Field(default_factory=list, description="Boşsa her bantta geçerli")

    @field_validator("amount")
    @classmethod
    def _amount(cls, v):
        if not re.match(AMOUNT_RULE, v):
            raise ValueError(f"desteklenmeyen tutar kuralı: {v}")
        return v


class Disclosure(Strict):
    debt_intro: str = Field(..., description="Doğrulamadan sonra aramanın amacını söyleyen cümle")
    debt_sentence: str = Field(..., description="Ürün başına cümle; {product} {past_due} {days_late} ve get_account alanları")
    product_wording: dict[str, str] = Field(..., description="Ürün tipi → ifade şablonu, ör. '<ürün adı> ending {<alan>}'")
    floor_field: dict[str, str] = Field(..., description="Ürün tipi → get_account'taki floor alanı")
    floor_rule: dict[str, str] = Field(
        default_factory=dict, description="floor_field yerine: ürün tipi → 'field:<alan>' | 'percent:N' (past_due'nun "
        "yüzdesi) | 'fixed:X' | 'max:<k1>,<k2>' / 'min:<k1>,<k2>' (büyüğü/küçüğü). '*' anahtarı bütün tipler için")

    @field_validator("floor_rule")
    @classmethod
    def _floor(cls, v):
        for k, rule in v.items():
            if not re.match(FLOOR_RULE, rule):
                raise ValueError(f"desteklenmeyen floor kuralı {k}: {rule}")
        return v


class Calendar(Strict):
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], description="İş günleri, Pazartesi=0")
    holidays: list[str] = Field(default_factory=list, description="YYYY-MM-DD")


class Negotiation(Strict):
    first_ask_single: str
    first_ask_multi: str = ""
    attempts: list[Attempt]
    rules: list[str] = Field(..., description="Müzakere kuralları, kısa emir cümleleri (tarih, tutar, ikna, ret tanımı)")
    forbidden_offers: list[str] = Field(default_factory=list)
    hardship_status: str = Field("", description="Brief zorlukta (hastalık, ölüm, işsizlik…) bir transfer teklifi "
                                 "istiyorsa, teklif reddedilince ürünlerin alacağı durum (statuses[].id); yoksa boş")
    floor_note: str = Field("", description="Floor (ya da borçtan düşük bir tutar) ilk kez teklif edilirken brief'in "
                            "söylenmesini istediği cümle, ör. kalan borcun gecikmiş kalacağı; yoksa boş")


class Confirmation(Strict):
    confirm_question: str
    rules: list[str] = Field(default_factory=list)
    change_after_record_sentence: str = ""


class Recording(Strict):
    mode: Literal["batch", "per_product"] = Field(
        "batch", description="batch: bütün ürünler tek onaydan sonra kaydedilir; per_product: brief her ürünün "
        "onaylanınca hemen kaydedilmesini istiyorsa")
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


class CustomerCallback(Strict):
    enabled: bool = False
    trigger: str = Field("", description="Müşteri ne derse geri arama teklif edilir (ör. 'şu an konuşamam')")
    ask: str = Field("", description="Müşteriye ne zaman aranmak istediğini soran cümle")
    outcome: OutcomeRef = Field(default_factory=lambda: OutcomeRef(outcome="", reason=""))
    stages: list[Literal["pre_identity", "post_verify"]] = Field(default_factory=lambda: ["post_verify"])
    window: Callback | None = Field(None, description="Boşsa third_party.callback penceresi kullanılır")


class ResponseFields(Strict):
    """Tool cevaplarındaki alan adları (openapi cevap şemasından). Rol adıyla aynıysa varsayılan kalır."""
    ok: str = "ok"
    verified: str = "verified"
    all_verified: str = "all_verified"
    wrong_answers_left: str = "wrong_answers_left"
    hint: str = "hint"
    products: str = "products"
    product_id: str = "product_id"
    product_type: str = "type"
    past_due: str = "past_due"
    days_late: str = "days_late"


class Override(Strict):
    """Bir memo'nun belli bir tarihten itibaren (ya da tarihe kadar) değiştirdiği değerler."""
    effective_from: str = Field("", description="YYYY-MM-DD; bu günden itibaren geçerli (boşsa baştan)")
    effective_until: str = Field("", description="YYYY-MM-DD; bu gün dahil geçerli (boşsa süresiz)")
    note: str = Field("", description="Hangi belge, ne değişiyor")
    bands: list[Band] | None = None
    holidays_add: list[str] = Field(default_factory=list)
    holidays_remove: list[str] = Field(default_factory=list)
    weekdays: list[int] | None = None
    callback: Callback | None = None
    floor_rule: dict[str, str] | None = None
    attempts: list[Attempt] | None = None


class Locale(Strict):
    """Kodun ürettiği cümlelerin dili. Brief İngilizce değilse hepsi brief'in dilinde yazılır."""
    weekday_names: list[str] = Field(default_factory=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                                              "Saturday", "Sunday"])
    month_names: list[str] = Field(default_factory=lambda: [
        "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
        "November", "December"])
    one_moment: str = "One moment, please."
    could_not_check: str = "Sorry, I could not check that answer."
    ask_year: str = "Thank you. And the year, please?"
    ask_day_month: str = "Thank you. And the day and the month, please?"
    ask_rest: str = "Thank you. And the rest, please?"
    readback_intro: str = "Let me read that back."
    readback_item: str = Field("{amount} on {date} for your {product}",
                               description="{amount} {date} {product} şablonu")
    promise_recorded: str = Field("Your promise to pay {amount} on {date} for your {product} is recorded.",
                                  description="Başarılı kayıttan sonra; {amount} {date} {product}")
    moved_deadline: str = Field("The latest date I can record for your {product} is {date}.",
                                description="Tarih deadline'a çekildiğinde")
    moved_business_day: str = Field("{asked} is not a business day, so for your {product} the date is {date}.",
                                    description="Tarih sonraki iş gününe kaydırıldığında")
    capped_amount: str = Field("The past-due amount of your {product} is {amount}.",
                               description="Tutar borçtan fazlaysa")
    below_floor: str = Field("I cannot accept less than {amount} for your {product}. Could you pay {amount}?",
                             description="Tutar floor'un altındaysa")
    past_date: str = Field("That date has already passed. Could you pay by {date}?",
                           description="Tarih geçmişteyse")
    continue_with: str = Field("Let us continue with your {product}.", description="per_product modunda")
    offer: str = Field("Could you pay {amount} for your {product} on {date}?",
                       description="Kodun yaptığı ikna teklifi; {amount} {date} {product}")

    @field_validator("weekday_names")
    @classmethod
    def _wd(cls, v):
        if len(v) != 7:
            raise ValueError("7 gün adı gerekli")
        return v

    @field_validator("month_names")
    @classmethod
    def _mn(cls, v):
        if len(v) != 12:
            raise ValueError("12 ay adı gerekli")
        return v


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
    tool_constants: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Tool'un zorunlu ama yukarıdaki rollere uymayan alanları: tool → {alan: "
        "sabit değer} (ör. para birimi). Değer brief'ten ya da openapi'den")
    response_fields: ResponseFields = Field(default_factory=ResponseFields,
                                            description="Tool cevaplarındaki alan adları rol adlarından farklıysa")
    customer_callback: CustomerCallback = Field(default_factory=CustomerCallback,
                                                description="Doğrulanmış/ulaşılmış müşteri sonra aranmak isterse")
    overrides: list[Override] = Field(default_factory=list,
                                      description="Belli bir tarihten itibaren geçerli değişiklikler (memo)")
    locale: Locale = Field(default_factory=Locale)
    general_rules: list[str] = Field(default_factory=list, description="Her adımda geçerli kurallar")
    unmapped: list[str] = Field(default_factory=list, description="Yukarıdaki alanlara sığmayan kurallar")

    @model_validator(mode="after")
    def _bands_ok(self):
        spans = sorted((b.min, b.max) for b in self.bands)
        for (_, a1), (b0, _) in zip(spans, spans[1:], strict=False):
            if b0 <= a1:
                raise ValueError(f"bantlar çakışıyor: {spans}")
        return self


def _schema_props(cat: ToolCatalog, tool: str) -> dict:
    t = cat.tools.get(tool)
    return t.response if t else {}


def _item_props(cat: ToolCatalog, products_field: str) -> dict:
    node = _schema_props(cat, "get_account").get(products_field, {})
    return (node.get("items") or {}).get("properties", {}) if node.get("type") == "array" else {}


def _pick(props: dict, kinds: tuple[str, ...], words: tuple[str, ...], avoid: tuple[str, ...] = ()) -> str:
    """Cevap şemasında rolüne en çok benzeyen alanı bulur (alan adı değişmişse)."""
    for name, p in props.items():
        low = name.lower()
        if p.get("type", "string") in kinds and any(w in low for w in words) and not any(a in low for a in avoid):
            return name
    return ""


def resolve_response_fields(spec: PolicySpec, cat: ToolCatalog) -> list[str]:
    """Spec'teki cevap alanı adları openapi'de yoksa en yakın alanı seçer. Değişiklik notlarını döner.

    Cevap şeması hiç yoksa (ör. sadece 200 açıklaması) hiçbir şey değiştirilmez."""
    rf = spec.response_fields
    notes: list[str] = []
    verify = _schema_props(cat, "verify_identity")
    account = _schema_props(cat, "get_account")
    rules = [
        ("ok", verify, ("boolean",), ("ok", "success"), ()),
        ("all_verified", verify, ("boolean",), ("all", "complete", "fully"), ()),
        ("verified", verify, ("boolean",), ("verif", "correct", "match", "pass"), ("all", "complete", "fully")),
        ("wrong_answers_left", verify, ("integer", "number"), ("left", "remaining", "attempt"), ()),
        ("hint", verify, ("string",), ("hint",), ()),
        ("products", account, ("array",), ("product", "account", "item", "debt"), ()),
    ]
    for role, props, kinds, words, avoid in rules:
        cur = getattr(rf, role)
        if not props or cur in props:
            continue
        found = _pick(props, kinds, words, avoid)
        if found:
            setattr(rf, role, found)
            notes.append(f"cevap alanı {role}: '{cur}' yok, '{found}' kullanıldı")
    items = _item_props(cat, rf.products)
    for role, kinds, words, avoid in [
        ("product_id", ("string", "integer"), ("id",), ()),
        ("product_type", ("string",), ("type", "kind", "category"), ()),
        ("past_due", ("number", "integer"), ("due", "overdue", "arrear", "owed", "balance"), ("min", "instal", "day")),
        ("days_late", ("integer", "number"), ("day",), ()),
    ]:
        cur = getattr(rf, role)
        if not items or cur in items:
            continue
        found = _pick(items, kinds, words, avoid)
        if found:
            setattr(rf, role, found)
            notes.append(f"ürün alanı {role}: '{cur}' yok, '{found}' kullanıldı")
    return notes


def cross_check(spec: PolicySpec, cat: ToolCatalog) -> list[str]:
    """Spec'teki enum değerlerinin ve alan adlarının openapi ile uyumunu kontrol eder. Hata listesi döner."""
    errs: list[str] = []

    def need(tool: str, field: str, value: str, what: str):
        allowed = cat.enum(tool, field)
        if allowed and value not in allowed:
            errs.append(f"{what}: '{value}' {tool}.{field} enum'unda yok ({allowed})")

    rf = spec.response_fields
    verify_fields = cat.tools["verify_identity"].fields if cat.has("verify_identity") else {}
    for q in spec.identity.questions:
        role_field = spec.tool_fields.get("verify_identity", {}).get("field", "field")
        if role_field in verify_fields:
            need("verify_identity", role_field, q.field, "kimlik sorusu")
        elif verify_fields and q.field not in verify_fields:
            errs.append(f"kimlik sorusu: '{q.field}' verify_identity'de ne 'field' enum'u ne de gövde alanı")
    for t in spec.transfers:
        need("transfer_to_agent", spec.tool_fields.get("transfer_to_agent", {}).get("queue", "queue"), t.queue,
             "transfer kuyruğu")
    if spec.multi_product.notes_enabled:
        for s in spec.statuses:
            need("add_note", spec.tool_fields.get("add_note", {}).get("reason", "reason"), s.id, "not sebebi")
    c = spec.closing
    outs = [c.promise_outcome, c.paid_outcome, c.no_promise_outcome, c.transfer_outcome, c.hangup_verified.outcome,
            c.hangup_unverified.outcome, spec.opening.unclear.outcome, spec.identity.fail_outcome.outcome,
            spec.identity.decline_outcome.outcome, spec.third_party.callback_outcome.outcome,
            spec.third_party.no_callback_outcome.outcome, spec.third_party.wrong_number_outcome.outcome,
            spec.third_party.deceased_outcome.outcome]
    if spec.customer_callback.enabled:
        outs.append(spec.customer_callback.outcome.outcome)
    for o in outs:
        need("close_call", spec.tool_fields.get("close_call", {}).get("outcome", "outcome"), o, "outcome")
    for ptype in spec.disclosure.product_wording:
        need("get_account", f"{rf.products}[].{rf.product_type}", ptype, "ürün tipi")
    items = _item_props(cat, rf.products)
    if items:
        for ptype, fname in spec.disclosure.floor_field.items():
            if fname and fname not in items:
                errs.append(f"floor alanı: '{fname}' ({ptype}) get_account ürünlerinde yok")
        for ptype, rule in spec.disclosure.floor_rule.items():
            for part in re.sub(r"^(max|min):", "", rule).split(","):
                if part.startswith("field:") and part[6:] not in items:
                    errs.append(f"floor kuralı: '{part}' ({ptype}) get_account ürünlerinde yok")
        for role in ("product_id", "product_type", "past_due", "days_late"):
            if getattr(rf, role) not in items:
                errs.append(f"cevap alanı {role}: '{getattr(rf, role)}' get_account ürünlerinde yok")
    hs = spec.negotiation.hardship_status
    if hs and hs not in [st.id for st in spec.statuses]:
        errs.append(f"negotiation.hardship_status: '{hs}' statuses içinde yok")
    for tool, consts in spec.tool_constants.items():
        if not cat.has(tool):
            errs.append(f"tool_constants: bilinmeyen tool {tool}")
            continue
        for fname, value in consts.items():
            if fname not in cat.tools[tool].fields:
                errs.append(f"tool_constants: {tool}.{fname} openapi'de yok")
            else:
                need(tool, fname, value, f"sabit {tool}.{fname}")
    return errs


def _floor_rules(spec: PolicySpec) -> dict[str, str]:
    rules = {t: "field:" + f for t, f in spec.disclosure.floor_field.items() if f}
    rules.update(spec.disclosure.floor_rule)
    return rules


def to_runtime(spec: PolicySpec) -> dict:
    """Spec → Freya code node'larının kullandığı RT sözlüğü."""
    c = spec.closing
    status_reasons = [s.id for s in spec.statuses]
    if spec.recording.failure_status not in status_reasons:
        status_reasons.append(spec.recording.failure_status)
    cc = spec.customer_callback
    return {
        "now_var": spec.call_variables.now,
        "cal": {"weekdays": spec.calendar.weekdays, "holidays": sorted(spec.calendar.holidays)},
        "bands": [b.model_dump() for b in spec.bands],
        "floor_rule": _floor_rules(spec),
        "product_wording": spec.disclosure.product_wording,
        "debt_intro": spec.disclosure.debt_intro,
        "debt_sentence": spec.disclosure.debt_sentence,
        "first_ask_single": spec.negotiation.first_ask_single,
        "first_ask_multi": spec.negotiation.first_ask_multi or spec.negotiation.first_ask_single,
        "floor_note": spec.negotiation.floor_note,
        "hardship_status": spec.negotiation.hardship_status,
        "refused_status": next((st.id for st in spec.statuses if st.persuade),
                               spec.statuses[0].id if spec.statuses else "refused"),
        "attempts": [a.model_dump() for a in spec.negotiation.attempts],
        "money": spec.money.model_dump(),
        "callback": spec.third_party.callback.model_dump(),
        "customer_callback": (cc.window or spec.third_party.callback).model_dump(),
        "status_reasons": status_reasons,
        "identity": {
            "questions": [q.model_dump() for q in spec.identity.questions],
            "numeric_date_order": spec.identity.numeric_date_order,
            "max_wrong_total": spec.identity.max_wrong_total,
            "decline_close_after": spec.identity.decline_close_after,
            "decline_explain": spec.identity.decline_explain,
            "retry_wrong_sentence": spec.identity.retry_wrong_sentence,
            "swap_hint": spec.identity.swap_hint,
            "swap_instruction": spec.identity.swap_instruction,
            "verify_mode": spec.identity.verify_mode,
        },
        "recording": spec.recording.model_dump(),
        "confirm_question": spec.confirmation.confirm_question,
        "notes_enabled": spec.multi_product.notes_enabled,
        "goodbye": c.goodbye_sentence,
        "call_vars": spec.call_variables.all,
        "fields": spec.response_fields.model_dump(),
        "locale": spec.locale.model_dump(),
        "overrides": [o.model_dump(exclude_none=True) for o in spec.overrides],
        "closing": {
            "promise_outcome": c.promise_outcome, "paid_outcome": c.paid_outcome,
            "no_promise_outcome": c.no_promise_outcome, "transfer_outcome": c.transfer_outcome,
            "paid_status": c.paid_status, "transfer_reasons": c.transfer_reasons,
            "status_to_reason": c.status_to_reason, "no_reason_outcomes": c.no_reason_outcomes,
            "hangup_verified": [c.hangup_verified.outcome, c.hangup_verified.reason],
            "hangup_unverified": [c.hangup_unverified.outcome, c.hangup_unverified.reason],
        },
    }
