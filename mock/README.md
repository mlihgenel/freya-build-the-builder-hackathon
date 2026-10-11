# Bank mock (final)

Final formatı (11 Eki): mock'u biz yazıp Cloudflare Workers'ta host ediyoruz; sonuçlar açıklanana kadar açık kalmalı.

- `src/index.js`: yedi tool + kayıt defteri (`GET <base>/ledger/<customer_id>`), müşteri başına Durable Object.
- `src/config.js`: sözleşmeye özgü değerler (yol öneki, outcome/reason tablosu, not sebepleri, kuyruklar, alan adları).
- `customers.json`: test müşterileri (`identity`, `products`, isteğe bağlı `faults`: ilk N çağrı 500). Şu anki içerik kitin
  pratik vakalarından, iskeleti denemek için; finalde zip'teki test müşterileriyle değiştirilir.

```bash
npx wrangler dev            # yerel deneme: http://localhost:8787/v1
npx wrangler login          # bir kez (tarayıcı)
npx wrangler deploy         # → https://yz50-bank-mock.<hesap>.workers.dev
```
