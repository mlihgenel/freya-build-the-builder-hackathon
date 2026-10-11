// Sözleşmeye göre değişen her şey burada (final zip'i gelince doldurulur). Kod (index.js) genel kalır.
export const CONFIG = {
  basePath: "/v1",                 // sözleşmedeki yol öneki
  maxWrong: 3,                      // toplam yanlış cevap hakkı
  swapHint: "day_month_swapped",    // gün/ay yer değiştirince dönen ipucu ('' = yok)
  dateFields: ["date_of_birth"],   // YYYY-MM-DD olarak kontrol edilen kimlik alanları
  // close_call: outcome → izin verilen reason'lar ([] = reason almaz)
  outcomes: {
    promise: [], paid: [],
    transferred: ["restructuring", "human", "support"],
    no_promise: ["refused", "hardship", "dispute", "service_error"],
    not_verified: ["failed", "declined"],
    not_reached: ["callback", "no_callback", "wrong_number", "deceased", "unclear"],
  },
  noteReasons: ["refused", "hardship", "dispute", "paid", "service_error"],
  queues: ["restructuring", "general", "support"],
  // istek alanı adları (sözleşme farklı ad kullanırsa)
  fields: { customer: "customer_id", field: "field", answer: "answer", product: "product_id", amount: "amount",
            date: "date", time: "time", reason: "reason", queue: "queue", outcome: "outcome" },
};
