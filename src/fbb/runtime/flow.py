"""Graf adımlarının code node'larında ve model tool'larında çalışan akış mantığı (docs/05_GRAF_TASARIMI.md).

Her fonksiyon `vars`'ı okur/yazar. Route'lar string bayraklara bakar (boolean'a değil):
id_go: <cevabın geldiği node adı> | '' | fail      id_decl: close | explain_q<i> | ''
commit: confirm | go_<adım> | invalid | invalid_say | ''
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
        vars["id_say"] = (ident.get("decline_explain", "") + " " + qs[idx]["ask"]).strip()
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
    """propose_results: doğrula ve düzelt. Promise varsa read-back'e, yoksa doğrudan not/kapanışa."""
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


def readback_reset(vars, RT):
    """Müşteri read-back'i onaylamadı: hiçbir şey kaydedilmedi, müzakereye dönülür."""
    vars["commit"] = ""
    vars["rec_queue"] = "[]"
    vars["fix_prompt"] = ("The customer did not confirm the read-back; nothing was recorded. Reply to what they just "
                          "said and settle it under the rules. When everything is agreed again, call propose_results "
                          "again.")


def commit_reset(vars):
    vars["fix_kind"] = "say" if vars.get("commit") == "invalid_say" else "model"
    vars["commit"] = ""


# --- geri arama -------------------------------------------------------------------------------------------

def take_callback(vars, RT, date_text, time_text):
    ok, why = check_callback(vars, date_text, time_text, RT)
    if ok:
        vars["cb_date"] = to_date(date_text).isoformat()
        vars["cb_time"] = str(time_text).strip()[:5].rjust(5, "0")
        vars["cb_state"] = "ok"
        return
    n = as_int(vars.get("cb_bad")) + 1
    vars["cb_bad"] = str(n)
    vars["cb_msg"] = why
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
            parts.append(say(RT, "continue_with", {"product": rest[0].get("wording") or rest[0]["product_id"]}))
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
