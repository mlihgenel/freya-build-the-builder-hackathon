"""Graf adımlarının code node'larında ve model tool'larında çalışan akış mantığı (docs/05_GRAF_TASARIMI.md).

Her fonksiyon `vars`'ı okur/yazar. Route'lar string bayraklara bakar (boolean'a değil):
id_go: <cevabın geldiği node adı> | '' | fail      id_decl: close | explain_q<i> | ''
commit: confirm | go_<adım> | invalid | invalid_say | offer_in | propose_in | ''   offer_go: say | ''
offer_pending / propose_pending: '1' | ''  (model aynı turda iki tool çağırırsa ikisi de işlenir: önce durumlar)
next_step: record | note | more | end_r | end_nr     cb_state: ok | invalid | gave_up | ''
Bir node'dan çıkışı sağlayan bayrak, o node'a geri dönülmeden önce bir kod adımında temizlenir; yoksa bayrak
eski değeriyle tekrar tetiklenir.
"""
import json
import re


def truthy(x):
    return str(x).strip().lower() in ("true", "1", "yes")


def first_set(vars, names):
    for n in names:
        v = vars.get(n)
        if v is not None and str(v) != "" and "{" not in str(v):
            return v
    return None


def tool_arg(vars, tool, name, literal=""):
    """Modelin bir code_exec tool'una verdiği argümanı bulur (platformun koyduğu yer kesin değil).

    `literal`: koddaki ARG_<ad> şablonunun çözülmüş hali; emit.py sonuna '~' koyar (tırnak/ters bölü güvenliği)."""
    literal = str(literal or "")
    if literal.endswith("~"):
        literal = literal[:-1]
    if literal and "{" not in literal:
        return literal
    v = first_set(vars, [name, tool + "_args." + name, "code_exec_args." + name])
    if v is not None:
        return str(v)
    for key in (tool + "_args", "code_exec_args"):
        d = vars.get(key)
        if isinstance(d, dict) and d.get(name) is not None:
            return str(d.get(name))
    return ""


# --- kimlik -----------------------------------------------------------------------------------------------

def id_reset_result(vars):
    for k in ("id_r_ok", "id_r_verified", "id_r_all", "id_r_left", "id_r_hint"):
        vars[k] = ""


def id_take_answer(vars, RT, raw, idx, node, swap=False):
    """submit_answer: cevabı normalize et. Eksikse (parçalı söylenmiş) sakla ve gönderme; tamamsa doğrulamaya yolla.

    Parçalar birleştirilir: '12' + '34' → '1234', '14 March' + '1988' → 1988-03-14. `swap`: gün/ay ipucundan sonra
    müşteri sadece ayı söylerse gün önceki cevaptan alınır."""
    ident = RT["identity"]
    qs = ident["questions"]
    idx = min(max(int(idx), 0), len(qs) - 1)
    q = qs[idx]
    vars["id_q"] = str(idx)
    vars["id_decl"] = ""
    id_reset_result(vars)
    tries = as_int(vars.get("id_tries")) + 1
    vars["id_tries"] = str(tries)
    if tries > len(qs) + as_int(ident.get("max_wrong_total") or 3) + 6:
        vars["id_go"] = "fail"
        return
    prev = str(vars.get("id_partial") or "") if vars.get("id_partial_q") == str(idx) else ""
    swapped_from = str(vars.get("id_last_" + str(idx)) or "") if swap else ""
    value, status = combine_answer(q, raw, prev, ident.get("numeric_date_order", "DMY"), swapped_from)
    if status == "partial":
        vars["id_partial"] = str(value)
        vars["id_partial_q"] = str(idx)
        vars["id_go"] = "partial"
        vars["id_say"] = missing_part_question(q, value, ident.get("numeric_date_order", "DMY"), RT)
        vars["id_msg"] = ("Only part of the answer was given so far (" + str(value) + "). The system asked for the "
                          "missing part; nothing was checked yet.")
        return
    vars["id_partial"] = ""
    vars["id_partial_q"] = ""
    vars["id_answer"] = str(value)
    vars["id_ans_" + str(idx)] = str(value)
    vars["id_last_" + str(idx)] = str(value)
    vars["id_msg"] = ""
    vars["id_go"] = node + ":" + str(idx)


def missing_part_question(q, value, order, RT):
    """Parçalı cevapta eksik kısmı soran sabit cümle (model beklemesin, sistem sorsun)."""
    loc = RT.get("locale") or dict()
    if q.get("answer_type") == "date":
        y, m, d = date_parts(value, order)
        if y is None and m is not None and d is not None:
            return loc.get("ask_year", "")
        if y is not None and (m is None or d is None):
            return loc.get("ask_day_month", "")
    return loc.get("ask_rest", "")


def id_decline(vars, RT, idx=None):
    """Müşteri soruya cevap vermedi ya da aramanın amacını sordu. Sınırdan önce açıklama, sınırda kapanış.

    idx: retin geldiği soru (reask'te None: o anki soru zaten id_q'da)."""
    if idx is not None:
        vars["id_q"] = str(idx)
    n = as_int(vars.get("decl_n")) + 1
    vars["decl_n"] = str(n)
    limit = as_int(RT["identity"].get("decline_close_after") or 2)
    vars["id_decl"] = "close" if n >= limit else "explain"


def id_fix(vars, RT):
    """Mutlu yol dışındaki her kimlik sonucu: tekrar sorulacak sabit cümleyi (id_say) hazırlar.

    Sırası: ret açıklaması → gün/ay ipucu (yanlış sayılmaz) → yanlış cevap → okunamayan cevap ya da servis hatası.
    Bayraklar (id_go, id_decl) burada temizlenir; tekrar soran node'a eski bayrakla dönülmez."""
    ident = RT["identity"]
    qs = ident["questions"]
    idx = min(as_int(vars.get("id_q")), len(qs) - 1)
    loc = RT.get("locale") or dict()
    if vars.get("id_go") == "partial":
        vars["id_go"] = ""
        return
    vars["id_go"] = ""
    vars["id_swap"] = ""
    vars["id_partial"] = ""
    if vars.get("id_decl") == "explain":
        vars["id_decl"] = ""
        # soru tekrar edilmez: hakem her tekrarı ayrı bir soru sayıyor; müşteri açıklamadan sonra cevabı veriyor
        vars["id_say"] = ident.get("decline_explain", "") or qs[idx]["ask"]
        return
    hint = first_set(vars, ["id_r_hint"])
    if hint and ident.get("swap_hint") and str(hint) == ident["swap_hint"]:
        vars["id_swap"] = "1"
        vars["id_say"] = ident.get("swap_instruction") or qs[idx]["ask"]
        return
    verified = first_set(vars, ["id_r_verified"])
    if verified is not None and str(verified).strip().lower() == "false":
        if ident.get("verify_mode") == "all_at_once":
            idx = 0
            vars["id_q"] = "0"
        vars["id_say"] = (ident.get("retry_wrong_sentence", "") + " " + qs[idx]["ask"]).strip()
        return
    vars["id_say"] = (loc.get("could_not_check", "") + " " + qs[idx]["ask"]).strip()


# --- müzakere sonucu --------------------------------------------------------------------------------------

def propose_results(vars, RT, raw):
    """propose_results: doğrula ve düzelt. Promise varsa read-back'e, yoksa doğrudan not/kapanışa.

    Modelin listesinde olmayan ürünler check_offer_answer'da zaten bitmişse (offers_json) oradan tamamlanır: model bir
    üründe dispute/paid görünce önceki anlaşmaları tekrar yazmak zorunda kalmaz."""
    raw = merge_offer_results(vars, raw)
    state, msg, customer = validate_results(vars, raw, RT)
    vars["commit_msg"] = msg
    vars["commit_say"] = customer
    if state in ("invalid", "invalid_say"):
        vars["commit"] = state
        vars["fix_prompt"] = ("Your propose_results call was not accepted: " + msg + ". Fix the entries and call "
                              "propose_results again now. Do not tell the customer anything about recording.")
        return
    vars["rec_try"] = "0"
    if state == "confirm":
        rec_pick(vars, RT)
        vars["commit"] = "confirm"
        return
    next_step(vars, RT)
    vars["commit"] = "go_" + vars["next_step"]


def propose_step(vars, RT):
    """propose_step code node'u. Aynı turda check_offer_answer da çağrıldıysa (offer_pending) önce bu durumlar işlenir, sonra
    teklif cevabı offer_step'te (commit = offer_in)."""
    raw = vars.get("propose_args", "")
    vars["propose_pending"] = ""
    vars["offer_go"] = ""
    if fold_statuses(vars, RT, raw):
        return
    vars["offer_pending"] = ""
    propose_results(vars, RT, raw)


def fold_statuses(vars, RT, raw):
    """Teklifler sürerken modelin bildirdiği durumlar (ör. 'p3:dispute', hiç promise yok) teklif durumuna
    (offers_json) işlenir: o ürünler teklif sırasında atlanır, açık ürünlere teklif sürer. Hepsi bittiyse sonuçlar
    propose_results'a gider. Promise içeren ya da hatalı girdi normal doğrulamaya bırakılır (False)."""
    try:
        plans = json.loads(vars.get("plans_json") or "[]")
        state = json.loads(vars.get("offers_json") or "null") or dict(cur=0, items=dict(), results=[])
    except Exception:
        return False
    cur = int(state.get("cur", 0))
    entries = parse_results(raw)
    ids = [p["product_id"] for p in plans]
    settled = settled_ids(vars)
    done = [r.split(":", 1)[0] for r in state.get("results") or []] + settled
    reasons = RT.get("status_reasons", [])
    cur = next_open(state, plans, cur, settled)
    if not plans or cur >= len(plans) or not entries:
        return False
    listed = [e["product_id"] for e in entries]
    if any(e["kind"] not in reasons or e["product_id"] not in ids or e["product_id"] in done for e in entries) \
            or len(set(listed)) != len(listed):
        return False
    old = ids[cur]
    state.setdefault("results", [])
    for e in entries:
        state["results"].append(e["product_id"] + ":" + e["kind"])
    cur = next_open(state, plans, cur, settled)
    state["cur"] = cur
    offer = vars.get("offer_pending") == "1"
    if cur >= len(plans):
        vars["offer_pending"] = ""
        vars["offers_json"] = json.dumps(state)
        propose_results(vars, RT, unproposed(state))
        return True
    if offer and plans[cur]["product_id"] == old:
        vars["offers_json"] = json.dumps(state)
        vars["commit"] = "offer_in"
        return True
    vars["offer_pending"] = ""
    plan = plans[cur]
    if plan["product_id"] != old:
        st = state["items"].get(plan["product_id"]) or dict(n=0, low=False)
        st["n"] = max(int(st.get("n", 0)), 1)
        state["items"][plan["product_id"]] = st
        text, amt, when = offer_sentence(plan, st["n"], st.get("low"), st)
        vars["offers_json"] = json.dumps(state)
        vars["commit"] = ""
        vars["offer_go"] = "say"
        vars["commit_say"] = (plan.get("continue_say", "") + " " + text).strip()
        vars["commit_msg"] = ("Noted: " + "; ".join(listed) + ". The system just proposed for " + plan["product_id"]
                              + " (" + plan.get("wording", plan["product_id"]) + "): " + str(amt) + " on " + when
                              + ". It is now the current product.")
        return True
    vars["offers_json"] = json.dumps(state)
    vars["commit"] = "invalid"
    vars["commit_msg"] = "Noted: " + "; ".join(listed) + ". The current product is still " + old + "."
    vars["fix_prompt"] = ("Noted: " + "; ".join(listed) + ". The current product is still " + old + " ("
                          + plan.get("wording", old) + "). Reply briefly to what the customer said and ask only "
                          "whether the system's last proposal for it works. Do not propose anything new.")
    return True


def next_open(state, plans, cur, settled=()):
    """cur'dan başlayarak sonucu henüz belli olmayan ilk ürünün sırası (durumu önceden bildirilenler ve `settled`:
    per_product'ta kaydedilmiş ya da durumu kesinleşmiş ürünler atlanır)."""
    done = [r.split(":", 1)[0] for r in state.get("results") or []] + list(settled)
    while cur < len(plans) and plans[cur]["product_id"] in done:
        cur += 1
    return cur


def merge_offer_results(vars, raw):
    try:
        state = json.loads(vars.get("offers_json") or "null") or dict()
    except Exception:
        state = dict()
    finished = settled_ids(vars) if (vars.get("recorded_json") or "[]") != "[]" else []
    done = [r for r in state.get("results") or [] if r.split(":", 1)[0] not in finished]
    listed = [e["product_id"] for e in parse_results(raw)]
    extra = [r for r in done if r.split(":", 1)[0] not in listed]
    return "; ".join([x for x in [str(raw or "").strip()] + extra if x])


def readback_reset(vars, RT):
    """Müşteri read-back'i onaylamadı: hiçbir şey kaydedilmedi, müzakereye dönülür."""
    vars["commit"] = ""
    vars["rec_queue"] = "[]"
    # son check_offer_answer'ı geri al: read-back'e götüren cevap yanlış anlaşılmış olabilir (ör. 'agreed_all' sadece bir
    # ürün için söylenmişti); teklif sırası ve deneme sayıları kaldığı yerden sürer
    if vars.get("offers_prev") is not None and str(vars.get("offers_json") or ""):
        vars["offers_json"] = vars.get("offers_prev") or ""
    vars["fix_prompt"] = ("The customer did not confirm the read-back; nothing was recorded. Reply to what they just "
                          "said. Then call check_offer_answer again for the current product with what they really said "
                          "(only 'agreed' for the products they agreed to; 'refused' for a flat no), or "
                          "propose_results when a product ends with another status.")


def commit_reset(vars):
    vars["fix_kind"] = "say" if vars.get("commit") == "invalid_say" else "model"
    vars["commit"] = ""


# --- ikna teklifleri: sayım ve cümle kodda --------------------------------------------------------------

def offer_sentence(plan, k, low, st):
    """Planın k. denemesi (1'den başlar) için teklif cümlesi (prep_account'ta hazırlanır). low: müşteri tam tutarı
    çok buldu → floor."""
    att = plan["attempts"][k - 1]
    amount, text = (att["low"], att["say_low"]) if low else (att["amount"], att["say"])
    note = plan.get("floor_note", "")
    if note and amount < plan["past_due"] - 0.005 and not st.get("noted"):
        st["noted"] = True
        text = text + " " + note
    return text, amount, att["date"]


def unproposed(state):
    """check_offer_answer sonuçlarından henüz propose edilmemiş olanlar (per_product modunda bir kısmı önceden kaydedildi)."""
    said = state.get("proposed") or []
    rest = [r for r in state.get("results") or [] if r not in said]
    state["proposed"] = said + rest
    return "; ".join(rest)


def check_offer_answer(vars, RT, answer, amount="", date=""):
    """check_offer_answer: müşterinin ŞU ANKİ ürüne cevabı: 'refused' (düz ret / cevap yok), 'too_much' (tam tutar fazla) ya
    da 'agreed' (amount + date).

    Ürün sırası ve deneme sayısı kodda (offers_json: cur = şu anki ürünün sırası). İlk soru (bugün, tam tutar) her
    ürün için 0. teklif sayılır. 'too_much' tutarı floor'a indirir ve tarihi korur (ilk sorudan sonra 1. denemenin
    tarihi). Denemeler bitince ürün ikna durumuyla (refused) kapanır. Ürün bitince sıradaki ürünün 1. teklifi
    söylenir; hepsi bitince sonuç propose_results'a verilir (read-back ya da kapanış). Her yol bir geçişle biter."""
    try:
        plans = json.loads(vars.get("plans_json") or "[]")
    except Exception:
        plans = []
    vars["offer_go"] = ""
    vars["offer_pending"] = ""
    vars["offers_prev"] = vars.get("offers_json") or ""
    state = json.loads(vars.get("offers_json") or "null") or dict(cur=0, items=dict(), results=[])
    cur = next_open(state, plans, int(state.get("cur", 0)))
    open_ids = [p["product_id"] for p in plans[cur:]
                if p["product_id"] not in [r.split(":", 1)[0] for r in state.get("results") or []]]
    if not plans or cur >= len(plans):
        vars["commit"] = "invalid"
        vars["commit_msg"] = "check_offer_answer: no product is open; call propose_results."
        vars["fix_prompt"] = "Every product is settled. Call propose_results now. Do not propose anything."
        return
    plan = plans[cur]
    pid = plan["product_id"]
    st = state["items"].get(pid) or dict(n=0, low=False)
    answer = str(answer or "").strip().lower()
    lead = ""
    done = ""
    if answer.startswith("agree") and ("all" in answer or "both" in answer):
        # Müşteri kalan bütün ürünler için tek bir gün söyledi: her ürün tam tutarıyla o güne; deadline'ı aşan ürünü
        # doğrulama kendi deadline'ına çeker ve read-back'te söyler.
        try:
            when = to_date(str(date).strip()[:10])
        except Exception:
            when = None
        if when is None:
            vars["commit"] = "invalid"
            vars["commit_msg"] = "check_offer_answer: 'agreed_all' needs agreed_date (YYYY-MM-DD)."
            vars["fix_prompt"] = ("Your check_offer_answer call was not accepted: " + vars["commit_msg"] + " Call it again "
                                  "now. Do not tell the customer anything about recording.")
            return
        today, _ = parse_now(vars.get(RT.get("now_var", "now")))
        kind, _, _, note = adjust_promise(plan, plan["past_due"], when, today, effective_rt(RT, today))
        if kind == "say":
            vars["commit"] = "invalid_say"
            vars["commit_say"] = note
            vars["commit_msg"] = "NOT ACCEPTED, the customer was told: " + note
            return
        for rest in plans[cur:]:
            if rest["product_id"] in open_ids:
                state["results"].append(rest["product_id"] + ":" + str(rest["past_due"]) + ":" + when.isoformat())
        state["cur"] = len(plans)
        vars["propose_args"] = unproposed(state)
        vars["offers_json"] = json.dumps(state)
        vars["commit"] = "propose_in"
        return
    if answer.startswith("agree"):
        try:
            when = to_date(str(date).strip()[:10])
            value = normalize_amount(re.sub(r"[^0-9a-zA-Z.,\- ]", "", str(amount)).replace(",", ""))
        except Exception:
            when, value = None, None
        if when is None or value is None:
            vars["commit"] = "invalid"
            vars["commit_msg"] = "check_offer_answer: 'agreed' needs agreed_amount (a number) and agreed_date (YYYY-MM-DD)."
            vars["fix_prompt"] = ("Your check_offer_answer call was not accepted: " + vars["commit_msg"] + " Call it again "
                                  "now. Do not tell the customer anything about recording.")
            return
        today, _ = parse_now(vars.get(RT.get("now_var", "now")))
        kind, _, _, note = adjust_promise(plan, value, when, today, effective_rt(RT, today))
        if kind == "say":
            vars["commit"] = "invalid_say"
            vars["commit_say"] = note
            vars["commit_msg"] = "NOT ACCEPTED, the customer was told: " + note
            return
        done = pid + ":" + str(value) + ":" + when.isoformat()
    elif answer.startswith("hardship") and RT.get("hardship_status"):
        # Zorluk: sempati ve destek teklifini model (brief kuralıyla) BİR kez yapar; müşteri reddedince kalan bütün
        # ürünler ikna denemesi olmadan zorluk durumuyla biter. Teklif burada tekrar söylenmez.
        for rest in plans[cur:]:
            if rest["product_id"] in open_ids:
                state["results"].append(rest["product_id"] + ":" + RT["hardship_status"])
        state["cur"] = len(plans)
        vars["propose_args"] = unproposed(state)
        vars["offers_json"] = json.dumps(state)
        vars["commit"] = "propose_in"
        return
    elif answer.startswith("too") and not st.get("low") and plan.get("floor") \
            and plan["floor"] < plan["past_due"] - 0.005:
        st["low"] = True
        st["n"] = max(int(st.get("n", 0)), 1)
    else:
        st["n"] = int(st.get("n", 0)) + 1
        if st["n"] > len(plan["attempts"]):
            done = pid + ":" + str(RT.get("refused_status") or "refused")
    state["items"][pid] = st
    if done:
        state["results"].append(done)
        cur = next_open(state, plans, cur + 1)
        state["cur"] = cur
        per_product = (RT.get("recording") or dict()).get("mode") == "per_product"
        if per_product and done.count(":") >= 2:
            # her ürün onaylanınca kaydedilir: bu promise (ve bekleyen durumlar) şimdi read-back'e; kayıttan sonra
            # sıradaki ürünün ilk teklifi 'kaydedildi' cümlesiyle birlikte söylenir (next_step → negotiate_more)
            nxt = ""
            if cur < len(plans):
                plan = plans[cur]
                st = state["items"].get(plan["product_id"]) or dict(n=0, low=False)
                st["n"] = 1
                state["items"][plan["product_id"]] = st
                text, _, _ = offer_sentence(plan, 1, st.get("low"), st)
                nxt = (plan.get("continue_say", "") + " " + text).strip()
            vars["check_offer_answer_say"] = nxt
            vars["propose_args"] = unproposed(state)
            vars["offers_json"] = json.dumps(state)
            vars["commit"] = "propose_in"
            return
        if cur >= len(plans):
            vars["propose_args"] = unproposed(state)
            vars["offers_json"] = json.dumps(state)
            vars["commit"] = "propose_in"
            return
        plan = plans[cur]
        pid = plan["product_id"]
        st = state["items"].get(pid) or dict(n=0, low=False)
        st["n"] = 1
        state["items"][pid] = st
        lead = plan.get("continue_say", "")
    text, amt, when = offer_sentence(plan, st["n"], st.get("low"), st)
    vars["offers_json"] = json.dumps(state)
    # bayrak burada temizlenir ve offer_step doğrudan teklif cümlesine gider (commit_fix adımı yok: her code
    # node'u yük altında 2-4 sn; ret turu 3 adımla ~10 sn sessizlik yapıyordu)
    vars["commit"] = ""
    vars["offer_go"] = "say"
    vars["commit_say"] = (lead + " " + text).strip()
    vars["commit_msg"] = ("The system just proposed for " + pid + " (" + plan.get("wording", pid) + "): " + str(amt)
                          + " on " + when + ". It is now the current product.")


# --- geri arama -------------------------------------------------------------------------------------------

def take_callback(vars, RT, date_text, time_text):
    ok, why = check_callback(vars, date_text, time_text, RT)
    if ok:
        vars["cb_date"] = to_date(date_text).isoformat()
        vars["cb_time"] = str(time_text).strip()[:5].rjust(5, "0")
        vars["cb_state"] = "ok"
        return
    if not re.match(r"^\s*\d{1,2}:\d{2}", str(time_text or "")):
        # sadece gün söylendi: gün geçerliyse yalnız saat sorulur (tekrar sayılmaz); gün geçersizse (ör. Cumartesi)
        # bu, kuralın tek 'başka bir zaman' sorusudur. Model günü kendisi eleyip saat sormaz (hakem: iki kez sordu).
        try:
            when = to_date(date_text).isoformat()
        except Exception:
            when = ""
        if when and when in [d for d in str(vars.get("cb_days", "")).split(",") if d]:
            vars["cb_state"] = "need_time"
            vars["cb_msg"] = "the day " + when + " is fine; the time is missing"
            vars["cb_say"] = "What time on that day would suit you?"
            return
        if when:
            why = "the day is outside the allowed days (" + str(vars.get("cb_days", "")).replace(",", ", ") + ")"
    n = as_int(vars.get("cb_bad")) + 1
    vars["cb_bad"] = str(n)
    vars["cb_msg"] = why
    # tts: model 'kurdum' diye uyduramaz (SC-05, 11 Eki: reddedilen 20:00 için "I've scheduled a callback" dedi)
    vars["cb_say"] = ("I am sorry, I cannot book that time. Could you give me another time, "
                      + (vars.get("cb_window_say") or "within our calling hours") + "?")
    key = "customer_callback" if vars.get("cb_kind") == "customer" else "callback"
    vars["cb_state"] = "gave_up" if n > as_int(RT.get(key, dict()).get("retries", 1)) else "invalid"


# --- kayıt ve not kuyrukları ------------------------------------------------------------------------------

def rec_pick(vars, RT):
    queue = json.loads(vars.get("rec_queue") or "[]")
    vars["rec_r_ok"] = ""
    if not queue:
        vars["rec_state"] = "done"
        return
    head = queue[0]
    vars["rec_pid"] = head["product_id"]
    vars["rec_amount"] = head["amount"]
    vars["rec_date"] = head["date"]
    vars["rec_state"] = "go"


def rec_after(vars, RT):
    queue = json.loads(vars.get("rec_queue") or "[]")
    if not queue:
        vars["rec_state"] = "done"
        return
    if ok_true(first_set(vars, ["rec_r_ok"])):
        recorded = json.loads(vars.get("recorded_json") or "[]")
        recorded.append(queue.pop(0))
        vars["recorded_json"] = json.dumps(recorded)
        vars["promises_ok"] = str(len(recorded))
        vars["rec_try"] = "0"
    else:
        tries = as_int(vars.get("rec_try")) + 1
        vars["rec_try"] = str(tries)
        if tries > as_int(RT["recording"].get("retries", 1)):
            failed = queue.pop(0)
            statuses = json.loads(vars.get("statuses_json") or "[]")
            statuses.append({"product_id": failed["product_id"], "reason": RT["recording"]["failure_status"]})
            vars["statuses_json"] = json.dumps(statuses)
            fails = json.loads(vars.get("failed_json") or "[]")
            fails.append(failed)
            vars["failed_json"] = json.dumps(fails)
            vars["rec_try"] = "0"
    vars["rec_queue"] = json.dumps(queue)
    mark_close(vars, RT)


def note_pick(vars, RT):
    vars["note_r_ok"] = ""
    if not RT.get("notes_enabled") or vars.get("transfer_queue"):
        vars["note_state"] = "done"
        return
    statuses = json.loads(vars.get("statuses_json") or "[]")
    done = as_int(vars.get("note_i"))
    if done >= len(statuses):
        vars["note_state"] = "done"
        return
    vars["note_pid"] = statuses[done]["product_id"]
    vars["note_reason"] = statuses[done]["reason"]
    vars["note_state"] = "go"


def note_after(vars, RT):
    ok = ok_true(first_set(vars, ["note_r_ok"]))
    tries = as_int(vars.get("note_try")) + 1
    if ok or tries > as_int(RT["recording"].get("retries", 1)):
        vars["note_i"] = str(as_int(vars.get("note_i")) + 1)
        vars["note_try"] = "0"
    else:
        vars["note_try"] = str(tries)


def unsettled_plans(vars):
    try:
        plans = json.loads(vars.get("plans_json") or "[]")
    except Exception:
        plans = []
    done = settled_ids(vars)
    return [p for p in plans if p["product_id"] not in done]


def announce(vars, RT):
    """Daha önce söylenmemiş kayıt sonuçlarının cümleleri (başarılı kayıt, başarısız kayıt)."""
    try:
        plans = dict((p["product_id"], p) for p in json.loads(vars.get("plans_json") or "[]"))
    except Exception:
        plans = dict()
    said = json.loads(vars.get("announced_json") or "[]")
    parts = []
    new_ok = False
    for r in json.loads(vars.get("recorded_json") or "[]"):
        if "r:" + r["product_id"] in said:
            continue
        said.append("r:" + r["product_id"])
        p = plans.get(r["product_id"], dict())
        parts.append(say(RT, "promise_recorded", {"amount": fmt_money(r["amount"], RT), "date": spoken_date(r["date"], RT),
                                                  "product": p.get("wording") or r["product_id"]}))
        new_ok = True
    if new_ok:
        parts.append(RT["recording"]["success_sentence"])
    names = []
    for f in json.loads(vars.get("failed_json") or "[]"):
        if "f:" + f["product_id"] in said:
            continue
        said.append("f:" + f["product_id"])
        names.append(plans.get(f["product_id"], dict()).get("wording", ""))
    if names:
        parts.append(RT["recording"]["failure_sentence"] + (" (" + ", ".join(n for n in names if n) + ")"
                                                            if any(names) and len(plans) > 1 else ""))
    vars["announced_json"] = json.dumps(said)
    return parts


def closing_speech(vars, RT, extra):
    parts = [extra] if extra else []
    parts += announce(vars, RT)
    goodbye = RT.get("goodbye", "")
    if vars.get("anonymous_goodbye") == "yes":
        goodbye = without_placeholders(goodbye)
    parts.append(goodbye)
    values = dict((k, vars.get(k, "")) for k in RT.get("call_vars", []))
    return fill(" ".join(x.strip() for x in parts if x and x.strip()), values)


def set_close(vars, RT, outcome, reason, speech):
    if outcome:
        vars["close_fixed_outcome"] = outcome
        vars["close_fixed_reason"] = reason
    mark_close(vars, RT)
    vars["closing_speech"] = closing_speech(vars, RT, speech)


def set_close_default(vars, RT, outcome, reason):
    """Erken yazılan kapanış: müşteri telefonu kapatırsa yedek close_call bunu kullanır."""
    vars["close_fixed_outcome"] = outcome
    vars["close_fixed_reason"] = reason
    mark_close(vars, RT)


def next_step(vars, RT):
    """Kayıt/not döngüsünün tek adımı: sıradaki işi seç; iş kalmadıysa kapanışı hazırla.

    Dönüşte vars['next_step']: 'record' | 'more' (per_product: sıradaki ürüne dön) | 'note' | 'end_r' | 'end_nr'.
    Her code node'u yük altında birkaç saniye sürdüğü için seçim, sonuç işleme ve kapanış tek node'da yapılır."""
    rec_pick(vars, RT)
    if vars.get("rec_state") == "go":
        vars["next_step"] = "record"
        return
    if (RT.get("recording") or dict()).get("mode") == "per_product":
        rest = unsettled_plans(vars)
        if rest:
            parts = announce(vars, RT)
            nxt = str(vars.get("check_offer_answer_say") or "")
            vars["check_offer_answer_say"] = ""
            parts.append(nxt or say(RT, "continue_with", {"product": rest[0].get("wording") or rest[0]["product_id"]}))
            values = dict((k, vars.get(k, "")) for k in RT.get("call_vars", []))
            vars["progress_say"] = fill(" ".join(x.strip() for x in parts if x and x.strip()), values)
            vars["next_step"] = "more"
            return
    note_pick(vars, RT)
    if vars.get("note_state") == "go":
        vars["next_step"] = "note"
        return
    set_close(vars, RT, "", "", "")
    vars["next_step"] = "end_r" if vars.get("close_kind") == "reason" else "end_nr"


def after_record_step(vars, RT):
    vars["commit"] = ""
    rec_after(vars, RT)
    next_step(vars, RT)


def after_note_step(vars, RT):
    note_after(vars, RT)
    next_step(vars, RT)


def without_placeholders(text):
    """'Thank you for your time, {title} {last_name}. Goodbye.' → 'Thank you for your time. Goodbye.'"""
    out = re.sub(r",?\s*(\{[a-zA-Z_]+\}\s*)+", "", str(text or ""))
    return re.sub(r"\s+([.!?,])", r"\1", out).strip()
