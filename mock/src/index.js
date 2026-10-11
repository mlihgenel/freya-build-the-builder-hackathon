// Bankanın servislerinin mock'u (final). Test müşterileri için test-environment/test-customers.json'daki cevabı
// (HTTP kodu dahil, varsa gecikmesiyle) aynen döndürür. Durumsuz: cevaplar sabit veriden gelir.
//
// Servis yoldan tanınır (entegrasyon belgesinin yolu ya da servis adı, ör. /cards/list, /cards.list); parametreler
// (müşteri numarası, kart numarası, istenen hafta) gövdede, sorgu parametresinde ya da başlıkta aranır.
import DATA from "../data/test-customers.json";

const CUSTOMERS = Object.fromEntries(DATA.customers.map((c) => [String(c.customerNo), c]));

// servis adı → yolda aranacak kelime grupları (hepsi geçmeli); ilk eşleşen kazanır, özel olanlar önce
const ROUTES = [
  ["statement.week.decide", [["week", "decide"]]],
  ["statement.week.change", [["week", "change"], ["week", "update"]]],
  ["statement.week.get", [["week"]]],
  ["statement.pdf.send", [["pdf"], ["statement", "send"], ["statement", "mail"]]],
  ["contact.email.get", [["email"], ["mail"], ["contact"]]],
  ["cards.balance", [["balance"], ["debt"]]],
  ["cards.list", [["card"]]],
];

const PARAMS = {
  customer: ["customerno", "customernumber", "customer_no", "customerid", "custno", "customer"],
  card: ["cardnumber", "cardno", "card_number", "maskedcardnumber", "card", "pan"],
  week: ["newstatementweek", "statementweek", "week", "newweek"],
};

const headers = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*",
  "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,PUT,PATCH,OPTIONS" };
const reply = (body, status) => new Response(JSON.stringify(body), { status, headers });

function service(pathname) {
  const p = decodeURIComponent(pathname).toLowerCase();
  for (const [name, groups] of ROUTES) {
    if (p.includes(name)) return name;
  }
  for (const [name, groups] of ROUTES) {
    if (groups.some((g) => g.every((w) => p.includes(w)))) return name;
  }
  return null;
}

function collect(obj, out) {
  if (!obj || typeof obj !== "object") return;
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === "object") collect(v, out);
    else if (v !== null && v !== undefined && v !== "") out[k.toLowerCase().replace(/[^a-z0-9_]/g, "")] ??= String(v);
  }
}

function pick(vals, names) {
  for (const n of names) if (vals[n] !== undefined) return vals[n];
  return undefined;
}

function digits(x) { return String(x || "").replace(/\D/g, ""); }

// Panelin "Test API Request" düğmesi değişkenleri doldurmadan gönderir ("{{customerNumber}}"): hata yerine ilk test
// müşterisinin (ve ilk kartının, ilk haftasının) kaydı döner (paketteki cloudflare-mock/README.md).
function isTemplate(v) { return typeof v === "string" && (v.startsWith("{{") || v.startsWith("%7B%7B")); }

function byCard(table, card) {
  if (!table || card === undefined) return undefined;
  if (table[card]) return table[card];
  const want = digits(card);
  for (const key of Object.keys(table)) {
    const k = digits(key);
    // maskeli numaralar: baştaki ve sondaki rakamlar tutmalı (ör. 540000******1234 ↔ 5400********1234 ↔ 1234)
    if (want && (k === want || (want.length <= 6 && k.endsWith(want)) ||
        (k.slice(-4) === want.slice(-4) && (want.length <= 4 || k.slice(0, 4) === want.slice(0, 4))))) return table[key];
  }
  return undefined;
}

function error(code, text, status) {
  return reply({ result: { returnCode: code, messageText: text, code, message: text, type: "ERROR" } }, status);
}

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers });
    const url = new URL(req.url);
    if (url.pathname === "/" || url.pathname === "/health") return reply({ ok: true, customers: DATA.customers.length }, 200);
    const svc = service(url.pathname);
    if (!svc) return error("NOT_FOUND", `unknown service path ${url.pathname}`, 404);
    const vals = {};
    collect(Object.fromEntries(url.searchParams), vals);
    if (!["GET", "HEAD"].includes(req.method)) {
      const text = await req.text();
      try { collect(JSON.parse(text || "{}"), vals); } catch { /* gövde JSON değilse yok sayılır */ }
    }
    for (const [k, v] of req.headers) vals[k.toLowerCase().replace(/[^a-z0-9_]/g, "")] ??= v;
    // yolda numara olabilir: /customers/90000001/cards
    const pathNums = url.pathname.split("/").filter((s) => /^\d{6,}$/.test(s));
    const customerNo = pick(vals, PARAMS.customer) ?? pathNums[0];
    const sample = isTemplate(customerNo);
    const c = sample ? DATA.customers[0] : CUSTOMERS[digits(customerNo)] || CUSTOMERS[String(customerNo)];
    if (!c) return error("FB_IVR_CHANNEL_101", "Müşteri bulunamadı.", 404);
    let entry = c.services[svc];
    if (!entry) return error("FB_IVR_CHANNEL_100", "Servis bu müşteri için tanımlı değil.", 404);
    if (!("http" in entry)) {  // kart numarasıyla anahtarlı
      const card = pick(vals, PARAMS.card) ?? pathNums.find((n) => n !== digits(customerNo));
      entry = sample || isTemplate(card) ? Object.values(entry)[0] : byCard(entry, card);
      if (!entry) return error("FB_IVR_CHANNEL_103", "Kart bulunamadı.", 404);
      if (!("http" in entry)) {  // hafta ile anahtarlı (statement.week.decide / change)
        const week = pick(vals, PARAMS.week);
        entry = sample || isTemplate(week) ? Object.values(entry)[0]
          : entry[String(parseInt(week, 10))] ?? entry[String(week)];
        if (!entry) return error("FB_IVR_CHANNEL_104", "Geçersiz hafta.", 400);
      }
    }
    const delay = Number(entry.gecikmeSaniye || entry.delaySeconds || 0);
    if (delay > 0) await new Promise((r) => setTimeout(r, delay * 1000));
    return reply(entry.response ?? entry.yanit ?? {}, Number(entry.http) || 200);
  },
};
