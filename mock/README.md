# Bank mock (final)

Final formatı: mock'u biz yazıp Cloudflare Workers'ta host ediyoruz; sonuçlar açıklanana kadar açık kalmalı.

- `data/test-customers.json`: vaka paketindeki `test-environment/test-customers.json`, değiştirilmeden.
- `src/index.js`: her servis için o müşterinin (ve kartın, haftanın) kayıtlı cevabını HTTP koduyla döndürür.
  Servis yoldan tanınır; müşteri/kart/hafta gövde, sorgu ya da başlıktan okunur.

```bash
npx wrangler dev            # yerel deneme: http://localhost:8787
npx wrangler login          # bir kez (tarayıcı)
npx wrangler deploy         # → https://yz50-bank-mock.<hesap>.workers.dev
```
