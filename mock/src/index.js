// Bankanın servislerinin mock'u (final). Kurallar: sources/documents/2026-10-01-service-contract.md ve
// test-environment/test-customers.md. Test müşterileri için test-customers.json'daki cevabı (HTTP kodu dahil,
// varsa delaySeconds kadar bekleyerek) aynen döndürür. Durumsuz: cevaplar sabit veriden gelir.
//
// Yol: POST <taban>/voice/v1/<servis> (ör. /voice/v1/cards.list). Gövde: {"data": {...}, "call": {...}}.
// Token, başlıklar, call ve aiFlow denetlenmez (test-customers.md).
import DATA from "../data/test-customers.json";

const CUSTOMERS = Object.fromEntries(DATA.customers.map((c) => [String(c.customerNo), c]));
const CARD_SERVICES = new Set(["cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change"]);
const SERVICES = ["cards.list", "cards.balance", "statement.week.get", "statement.week.decide",
  "statement.week.change", "contact.email.get", "statement.pdf.send"];

// Sözleşme bölüm 4: kayıt yoksa servisin 404'ü; 404'ü olmayan serviste 400 INVALID_ARGUMENTS_ERROR.
const NOT_FOUND = {
  "cards.list": ["FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."],
  "cards.balance": ["FB_IVR_CHANNEL_120", "Kart bilgisi bulunamadı."],
  "statement.week.get": ["FB_IVR_CHANNEL_121", "Kart bilgisi bulunamadı."],
  "statement.pdf.send": ["FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"],
};

const HEADERS = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*",
  "access-control-allow-headers": "*", "access-control-allow-methods": "POST, GET, OPTIONS" };
const reply = (body, status) => new Response(JSON.stringify(body), { status, headers: HEADERS });

function guid() { return crypto.randomUUID().replace(/-/g, ""); }

// Hata cevabında data yok, sadece result (sözleşme bölüm 4).
function errorBody(code, text, type, rootCause) {
  const g = guid();
  return { result: { guid: g, returnCode: code, messageText: text, code, message: text, type,
    details: { guid: g, rootCause, errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } };
}

function invalid(text) { return reply(errorBody("INVALID_ARGUMENTS_ERROR", text, "ERROR", "ValidationError"), 400); }

function notFound(svc) {
  const nf = NOT_FOUND[svc];
  return nf ? reply(errorBody(nf[0], nf[1], "WARNING", "BusinessError"), 404) : invalid("record not found");
}

// Panelin "Test API Request" düğmesi değişkenleri doldurmadan gönderir ("{{customerNumber}}"): hata yerine ilk test
// müşterisinin (ve ilk kartının, ilk haftasının) kaydı (paketteki cloudflare-mock/README.md).
function isTemplate(v) { return typeof v === "string" && (v.startsWith("{{") || v.startsWith("%7B%7B")); }

function empty(v) { return v === undefined || v === null || String(v).trim() === ""; }

function digits(x) { return String(x ?? "").replace(/\D/g, ""); }

function service(pathname) {
  const p = decodeURIComponent(pathname).toLowerCase();
  // en uzun ad önce: statement.week.decide, statement.week.get'ten önce denenir
  return [...SERVICES].sort((a, b) => b.length - a.length).find((s) => p.endsWith("/" + s) || p.includes("/" + s + "/"))
    ?? null;
}

// Sözleşme: cardNumber, cards.list'in verdiği maskeli numarayla aynen gelir. Tam eşleşme yoksa (ör. cards.balance'ın
// 5400********1234 biçimi) yalnız TEK aday tutarsa kabul edilir; aynı son 4'e sahip birden çok kart olabilir
// (test-customers.md), o durumda kart bulunamadı sayılır.
function byCard(table, card) {
  if (table[card]) return table[card];
  const want = digits(card);
  if (want.length !== 8 && want.length !== 10) return undefined;
  const hits = Object.keys(table).filter((key) => {
    const k = digits(key);
    return k === want || (want.length === 8 && k.slice(0, 4) === want.slice(0, 4) && k.slice(-4) === want.slice(-4));
  });
  return hits.length === 1 ? table[hits[0]] : undefined;
}

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: HEADERS });
    const url = new URL(req.url);
    if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/health"))
      return reply({ ok: true, customers: DATA.customers.length }, 200);
    const svc = service(url.pathname);
    if (!svc || req.method !== "POST")
      return reply(errorBody("NOT_FOUND", `unknown path ${req.method} ${url.pathname}`, "ERROR", "Routing"), 404);
    let body;
    try { body = JSON.parse((await req.text()) || "{}"); } catch { return invalid("request body must be JSON"); }
    const d = (body && typeof body.data === "object" && body.data) || {};

    let entry;
    if (CARD_SERVICES.has(svc)) {  // sözleşme: istekte yalnız cardNumber var (customerNo gelirse o da kullanılır)
      const card = d.cardNumber;
      if (!isTemplate(card) && empty(card)) return invalid("card number cannot be empty");
      const known = empty(d.customerNo) || isTemplate(d.customerNo) ? null : CUSTOMERS[digits(d.customerNo)];
      if (isTemplate(card)) entry = Object.values(DATA.customers[0].services[svc])[0];
      else if (known && known.services[svc]) entry = byCard(known.services[svc], String(card));
      if (!entry && !isTemplate(card)) {
        const hits = DATA.customers.map((c) => c.services[svc] && byCard(c.services[svc], String(card))).filter(Boolean);
        entry = hits.length === 1 ? hits[0] : undefined;
      }
      if (!entry) return notFound(svc);
      if (!("http" in entry)) {  // hafta ile anahtarlı (statement.week.decide / change)
        const week = d.newStatementWeek;
        if (!isTemplate(week) && empty(week)) return invalid("new statement week cannot be empty");
        entry = isTemplate(week) ? Object.values(entry)[0] : entry[String(parseInt(week, 10))];
        if (!entry) return notFound(svc);
      }
    } else {  // müşteri numarasıyla anahtarlı
      const customerNo = d.customerNo;
      const sample = isTemplate(customerNo);
      if (!sample && empty(customerNo)) return invalid("customer number cannot be empty");
      const c = sample ? DATA.customers[0] : CUSTOMERS[digits(customerNo)];
      if (!c) return notFound(svc);
      entry = c.services[svc];
      if (!entry) return notFound(svc);
    }
    const delay = Number(entry.delaySeconds || 0);
    if (delay > 0) await new Promise((r) => setTimeout(r, delay * 1000));
    return reply(entry.response ?? {}, Number(entry.http) || 200);
  },
};
