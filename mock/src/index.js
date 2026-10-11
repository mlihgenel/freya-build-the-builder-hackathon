// Freya Bank mock (final): yedi tool + kayıt defteri. Müşteri başına durum bir Durable Object'te (tutarlı, kalıcı).
// Davranış kitin mock'unda gözlenene göre (docs/02); sözleşmeye özgü değerler config.js ve customers.json'da.
import { CONFIG } from "./config.js";
import CUSTOMERS from "../customers.json";

const TOOLS = ["verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
  "transfer_to_agent", "close_call"];
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json", "access-control-allow-origin": "*" } });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, "");
    const base = CONFIG.basePath;
    if (req.method === "GET" && (path === "" || path === base)) return json({ ok: true, service: "bank-mock" });
    // kayıt defteri: GET <base>/ledger/<customer_id>  (ve kitteki gibi <base>/practice/ledger/<id>)
    const m = path.match(new RegExp(`^${base}(?:/practice)?/ledger/([^/]+)$`));
    if (req.method === "GET" && m) return stub(env, m[1]).fetch(new Request("https://do/ledger"));
    // pratik oturumu: POST <base>/practice/sessions {case} → test müşterisinin yeni bir kopyası
    if (req.method === "POST" && path === `${base}/practice/sessions`) {
      const body = await req.json().catch(() => ({}));
      const c = CUSTOMERS[body.case || body.customer || ""];
      if (!c) return json({ ok: false, error: "unknown case" }, 404);
      const id = `${body.case}-${crypto.randomUUID().slice(0, 8)}`;
      await stub(env, id).fetch(new Request("https://do/init", { method: "POST", body: JSON.stringify(c) }));
      return json({ ok: true, variables: { ...(c.variables || {}), customer_id: id } });
    }
    const tool = TOOLS.find((t) => path === `${base}/${t}`);
    if (!tool || req.method !== "POST") return json({ ok: false, error: "not found" }, 404);
    const body = await req.json().catch(() => null);
    if (!body) return json({ ok: false, error: "body must be JSON" }, 400);
    const cid = String(body[CONFIG.fields.customer] || "");
    if (!cid) return json({ ok: false, error: "customer_id is required" }, 400);
    return stub(env, cid).fetch(new Request(`https://do/${tool}`, { method: "POST", body: JSON.stringify(body) }));
  },
};

function stub(env, cid) { return env.LEDGER.get(env.LEDGER.idFromName(cid)); }

export class Ledger {
  constructor(state) { this.state = state; }

  async load(cid) {
    let s = await this.state.storage.get("s");
    if (!s) {
      // doğrudan test müşterisi kimliğiyle gelen çağrı (organizatörün müşterileri): kaydı ilk çağrıda kur
      const c = CUSTOMERS[cid] || Object.values(CUSTOMERS).find((x) => x.customer_id === cid);
      if (!c) return null;
      s = fresh(c);
    }
    return s;
  }

  async fetch(req) {
    const url = new URL(req.url);
    const op = url.pathname.slice(1);
    if (op === "init") {
      await this.state.storage.put("s", fresh(await req.json()));
      return json({ ok: true });
    }
    if (op === "ledger") {
      const s = await this.state.storage.get("s");
      if (!s) return json({ ok: false, error: "unknown customer_id" }, 404);
      const { outcome, reason, promises, notes, callbacks, transfers, calls } = s;
      return json({ outcome, reason, promises, notes, callbacks, transfers, calls });
    }
    const body = await req.json();
    const cid = String(body[CONFIG.fields.customer]);
    const s = await this.load(cid);
    if (!s) return json({ ok: false, error: "unknown customer_id" }, 404);
    const [result, status] = handle(op, body, s);
    s.calls.push({ tool: op, args: body, result, at: new Date().toISOString() });
    await this.state.storage.put("s", s);
    return json(result, status);
  }
}

function fresh(c) {
  return { customer: c, verified: {}, wrong: 0, faults: { ...(c.faults || {}) }, outcome: null, reason: null,
    closed: false, promises: [], notes: [], callbacks: [], transfers: [], calls: [] };
}

function allVerified(s) {
  return Object.keys(s.customer.identity || {}).every((f) => s.verified[f]);
}

function isDate(v) { return /^\d{4}-\d{2}-\d{2}$/.test(v) && !isNaN(Date.parse(v)); }

function fault(s, op) {
  // customers.json: "faults": {"create_promise": 1} → ilk N çağrı 500 döner, hiçbir şey kaydedilmez
  if (s.faults[op] > 0) { s.faults[op] -= 1; return true; }
  return false;
}

function handle(op, b, s) {
  const F = CONFIG.fields;
  if (fault(s, op)) return [{ ok: false, error: "service unavailable" }, 500];
  if (op === "verify_identity") {
    const field = String(b[F.field] || ""), answer = String(b[F.answer] ?? "").trim();
    const ids = s.customer.identity || {};
    if (!(field in ids)) return [{ ok: false, error: `unknown field; use one of ${Object.keys(ids).join(", ")}` }, 200];
    if (s.wrong >= CONFIG.maxWrong) return [{ ok: true, verified: false, wrong_answers_left: 0, all_verified: false }, 200];
    if (CONFIG.dateFields.includes(field) && !isDate(answer))
      return [{ ok: false, error: "answer is not a date. Send it as YYYY-MM-DD." }, 200];
    const want = String(ids[field]);
    const norm = (x) => x.replace(/\s+/g, "").toUpperCase();
    if (norm(answer) === norm(want)) {
      s.verified[field] = true;
      return [{ ok: true, verified: true, wrong_answers_left: CONFIG.maxWrong - s.wrong, all_verified: allVerified(s) }, 200];
    }
    if (CONFIG.swapHint && CONFIG.dateFields.includes(field)) {
      const [y, m, d] = answer.split("-");
      if (`${y}-${d}-${m}` === want) return [{ ok: true, verified: false, wrong_answers_left: CONFIG.maxWrong - s.wrong,
        all_verified: false, hint: CONFIG.swapHint }, 200];
    }
    s.wrong += 1;
    return [{ ok: true, verified: false, wrong_answers_left: CONFIG.maxWrong - s.wrong, all_verified: false }, 200];
  }
  if (s.closed && op !== "close_call") return [{ ok: false, error: "the call is already closed" }, 200];
  if (op === "get_account") {
    if (!allVerified(s)) return [{ ok: false, error: "identity not verified" }, 200];
    return [{ ok: true, products: (s.customer.products || []).map((p, i) => ({ product_id: `p${i + 1}`, ...p })) }, 200];
  }
  const pids = (s.customer.products || []).map((_, i) => `p${i + 1}`);
  if (op === "create_promise") {
    if (!allVerified(s)) return [{ ok: false, error: "identity not verified" }, 200];
    const pid = String(b[F.product]), amount = Number(b[F.amount]), date = String(b[F.date] || "");
    if (!pids.includes(pid)) return [{ ok: false, error: "unknown product_id" }, 200];
    if (!(amount > 0) || !isDate(date)) return [{ ok: false, error: "amount must be a number and date YYYY-MM-DD" }, 200];
    if (s.promises.some((p) => p.product_id === pid)) return [{ ok: false, error: "one promise per product" }, 200];
    s.promises.push({ product_id: pid, amount, date });
    return [{ ok: true, promise_id: `pr${s.promises.length}` }, 200];
  }
  if (op === "add_note") {
    const pid = String(b[F.product] || ""), reason = String(b[F.reason] || "");
    if (!CONFIG.noteReasons.includes(reason)) return [{ ok: false, error: `reason must be one of ${CONFIG.noteReasons.join(", ")}` }, 200];
    s.notes.push({ product_id: pid, reason, text: b.text || "" });
    return [{ ok: true }, 200];
  }
  if (op === "schedule_callback") {
    const date = String(b[F.date] || ""), time = String(b[F.time] || "");
    if (!isDate(date) || !/^\d{2}:\d{2}$/.test(time)) return [{ ok: false, error: "date YYYY-MM-DD and time HH:MM" }, 200];
    s.callbacks.push({ date, time });
    return [{ ok: true }, 200];
  }
  if (op === "transfer_to_agent") {
    const queue = String(b[F.queue] || "");
    if (!CONFIG.queues.includes(queue)) return [{ ok: false, error: `queue must be one of ${CONFIG.queues.join(", ")}` }, 200];
    s.transfers.push({ queue });
    return [{ ok: true }, 200];
  }
  if (op === "close_call") {
    if (s.closed) return [{ ok: false, error: "the call is already closed" }, 200];
    const outcome = String(b[F.outcome] || ""), reason = b[F.reason] == null ? null : String(b[F.reason]);
    const allowed = CONFIG.outcomes[outcome];
    if (!allowed) return [{ ok: false, error: `outcome must be one of ${Object.keys(CONFIG.outcomes).join(", ")}` }, 200];
    if (allowed.length && !allowed.includes(reason)) return [{ ok: false, error: `this outcome needs one of these reasons: ${allowed.join(", ")}` }, 200];
    if (!allowed.length && reason) return [{ ok: false, error: "this outcome takes no reason" }, 200];
    s.closed = true; s.outcome = outcome; s.reason = allowed.length ? reason : null;
    return [{ ok: true }, 200];
  }
  return [{ ok: false, error: "not found" }, 404];
}
