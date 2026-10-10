"""Graf adımlarının code node'larında çalışan akış mantığı: kimlik döngüsü, kayıt ve not kuyrukları, kapanış.

Her fonksiyon `vars`'ı okur/yazar. Route'lar string bayraklara bakar (boolean'a değil):
id_state: asking | verified | failed      id_ready: yes | ''
commit: ready | invalid | ''              rec_state / note_state: go | done
cb_state: ok | invalid | gave_up | ''
"""
import json


def truthy(x):
    return str(x).strip().lower() in ("true", "1", "yes")


def first_set(vars, names):
    for n in names:
        v = vars.get(n)
        if v is not None and str(v) != "" and "{" not in str(v):
            return v
    return None


def tool_arg(vars, tool, name, literal=""):
    """Modelin bir code_exec tool'una verdiği argümanı bulur (platformun koyduğu yer kesin değil)."""
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


def id_questions(RT):
    return RT["identity"]["questions"]


def id_init(vars, RT):
    vars["id_q"] = "0"
    vars["id_state"] = "asking"
    vars["id_ready"] = ""
    vars["decl_n"] = "0"
    vars["id_say"] = id_questions(RT)[0]["ask"]


def id_take_answer(vars, RT, raw):
    """Model müşterinin cevabını verdi: normalize et; eksikse göndermeden tekrar sor."""
    qs = id_questions(RT)
    q = qs[min(as_int(vars.get("id_q")), len(qs) - 1)]
    value, status = normalize_answer(q["answer_type"], raw, RT["identity"].get("numeric_date_order", "DMY"))
    if status == "partial":
        vars["id_ready"] = ""
        vars["id_msg"] = "Only part of the answer was given (" + str(value) + "). Ask for the rest. NOTHING was checked."
        return
    vars["id_field"] = q["field"]
    vars["id_answer"] = str(value)
    vars["id_ready"] = "yes"
    vars["id_msg"] = "checking"


def id_after(vars, RT):
    """verify_identity sonucunu yorumlar ve bir sonraki sabit cümleyi (id_say) hazırlar."""
    ident = RT["identity"]
    qs = id_questions(RT)
    idx = as_int(vars.get("id_q"))
    vars["id_ready"] = ""
    ok = first_set(vars, ["id_r_ok", "verify_identity_response.data.ok", "verify_response.data.ok"])
    verified = first_set(vars, ["id_r_verified", "verify_identity_response.data.verified", "verify_response.data.verified"])
    all_ok = first_set(vars, ["id_r_all", "verify_identity_response.data.all_verified",
                              "verify_response.data.all_verified"])
    left = first_set(vars, ["id_r_left", "verify_identity_response.data.wrong_answers_left",
                            "verify_response.data.wrong_answers_left"])
    hint = first_set(vars, ["id_r_hint", "verify_identity_response.data.hint", "verify_response.data.hint"])
    ask = qs[min(idx, len(qs) - 1)]["ask"]
    if truthy(all_ok):
        vars["id_state"] = "verified"
        return
    if hint and ident.get("swap_hint") and str(hint) == ident["swap_hint"]:
        vars["id_say"] = ident.get("swap_instruction") or ask
        return
    if truthy(verified):
        idx += 1
        vars["id_q"] = str(idx)
        if idx >= len(qs):
            vars["id_state"] = "verified"
            return
        vars["id_say"] = qs[idx]["ask"]
        return
    if left is not None and as_int(left) <= 0 and str(left).strip() != "":
        vars["id_state"] = "failed"
        return
    if ok is not None and not truthy(ok) and verified is None:
        vars["id_say"] = "Sorry, I did not catch that. " + ask
        return
    vars["id_say"] = (ident.get("retry_wrong_sentence", "") + " " + ask).strip()


def id_reset_result(vars):
    for k in ("id_r_ok", "id_r_verified", "id_r_all", "id_r_left", "id_r_hint"):
        vars[k] = ""


def take_results(vars, RT, raw):
    """submit_results: doğrula; geçerliyse kayıt kuyruğunu kur."""
    ok, msg = validate_results(vars, raw, RT)
    vars["commit_msg"] = msg
    if not ok:
        vars["commit"] = "invalid"
        vars["commit_n"] = str(as_int(vars.get("commit_n")) + 1)


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
    vars["cb_state"] = "gave_up" if n > as_int(RT["callback"].get("retries", 1)) else "invalid"


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
    ok = first_set(vars, ["rec_r_ok"])
    if truthy(ok):
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
    ok = truthy(first_set(vars, ["note_r_ok"]))
    tries = as_int(vars.get("note_try")) + 1
    if ok or tries > 1:
        vars["note_i"] = str(as_int(vars.get("note_i")) + 1)
        vars["note_try"] = "0"
    else:
        vars["note_try"] = str(tries)


def closing_speech(vars, RT, extra):
    parts = []
    if extra:
        parts.append(extra)
    try:
        plans = dict((p["product_id"], p) for p in json.loads(vars.get("plans_json") or "[]"))
    except Exception:
        plans = dict()
    recorded = json.loads(vars.get("recorded_json") or "[]")
    for r in recorded:
        p = plans.get(r["product_id"], dict())
        parts.append("Your promise to pay " + fmt_money(r["amount"], RT) + " on " + spoken_date(r["date"])
                     + (" for your " + p["wording"] if p.get("wording") else "") + " is recorded.")
    if recorded:
        parts.append(RT["recording"]["success_sentence"])
    failed = json.loads(vars.get("failed_json") or "[]")
    if failed:
        names = [plans.get(f["product_id"], dict()).get("wording", "") for f in failed]
        parts.append(RT["recording"]["failure_sentence"] + (" (" + ", ".join(n for n in names if n) + ")"
                                                            if any(names) and len(plans) > 1 else ""))
    parts.append(RT.get("goodbye", ""))
    values = dict((k, vars.get(k, "")) for k in RT.get("call_vars", []))
    return fill(" ".join(x.strip() for x in parts if x and x.strip()), values)


def set_close(vars, RT, outcome, reason, speech):
    if outcome:
        vars["close_outcome"] = outcome
        vars["close_reason"] = reason
    o, r = decide_close(vars, RT)
    vars["close_outcome"] = o
    vars["close_reason"] = r
    vars["closing_speech"] = closing_speech(vars, RT, speech)


def coerce_body(config, types):
    """Bankaya giden gövdede sayı alanlarını sayıya çevirir (baked değerler metin olarak gelir)."""
    body = config.get("body")
    if not isinstance(body, dict):
        return
    for key in list(body):
        val = body[key]
        if isinstance(val, str) and ("{" in val or val.strip() == ""):
            if key in types.get("optional", []):
                body.pop(key)
            continue
        kind = types.get(key, "")
        try:
            if kind == "number":
                body[key] = round(float(val), 2)
            elif kind == "integer":
                body[key] = int(float(val))
        except Exception:
            pass
