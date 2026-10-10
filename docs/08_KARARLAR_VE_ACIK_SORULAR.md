# 08: Kararlar ve açık sorular

## Kararlar

| # | Karar | Gerekçe | Alternatif |
|---|---|---|---|
| K-01 | Kod sıfırdan, `yz50-hackathon-v2` klasöründe; kit `kit/` altında olduğu gibi | Kullanıcı kararı; önceden yazılmış kod sorusu (U03) önemsizleşiyor | eski repoyu dönüştürmek |
| K-02 | Hibrit: LLM → PolicySpec, Python → workflow | Aynı spec → aynı workflow; kurallar kodda | Claude'un workflow'u doğrudan yazması (kitteki örnek) |
| K-03 | Builder LLM'i Claude Opus 5.5, claude-agent-sdk ile | Uzun ve ham brief'leri iyi okuyor; structured output; makinedeki giriş | OpenAI |
| K-04 | Model sadece 3 code_exec tool'u çağırır; bankaya yazmaları engine yapar | Sabit model zayıf: susma, olumsuz sonucu görmezden gelme, gereksiz not | modelin bankayı doğrudan çağırması |
| K-05 | Tarihler çağrı sırasında `now`'dan code node'unda hesaplanır | Platform tarihleri gerçek saati kullanıyor; testler birden fazla günde | prompt'ta tarih hesabı |
| K-06 | `close_call` lifecycle (end_of_call) + durumdan hesaplanan pre-hook | Her zaman son çağrı ve tam bir kez; telefon kapansa bile çalışıyor | her yolda node içinde close |
| K-07 | Gizli brief'te simülasyon yok; lint + dryRun + geri okuma + chat smoke | Bilinen vaka yok; eşitlikte build süresi sayılıyor | uzun self-test |
| K-08 | Model talimatları İngilizce, müşteriye söylenen sabit cümleler brief'ten birebir | Agent modeli için en güvenlisi | |

## Yedek planlar (Faz 0 sonuçlarına bağlı)

| Deney olumsuz çıkarsa | Yedek plan |
|---|---|
| F-01 (lifecycle pre-hook `vars`'ı görmüyor) | Baked `{{close_outcome}}`/`{{close_reason}}` zaten var. `set_close` her yolda yazar; pre-hook sadece boş `reason`'ı siler |
| F-02 (telefon kapanınca lifecycle çalışmıyor) | Kapanışı `end_main`'den önce bir api_request node'una taşı |
| F-03 (code_exec tool argümanları ulaşmıyor) | (a) `extraction_schema` ile müşterinin cevabını/teklifini değişkene çek ve `is_set` ile route et; (b) aynı kodu post-hook'lu bir api_call ile çalıştır |
| F-04 (tool sonrası route tetiklenmiyor) | Bayrağı `<tool>_response.*` anahtarlarıyla da kontrol et; sonraki kullanıcı turunda route et |
| F-05 (döngü sorunlu) | Ürün sayısı kadar sabit zincir (en fazla 3 adım) |
| F-08 (boyut sınırı) | `RT`'yi ilk code node'unda bir `vars` değişkenine yaz, snippet'ler oradan okusun; fonksiyon kapanışını küçült |

## Organizatöre açık sorular (taslak e-posta)

> Hi Freya team, a few questions about the final:
> 1. Will the hidden briefs have practice sessions (`/v1/practice/sessions`) or practice cases, and will their tool API be served at a different base URL?
> 2. How much of the workspace credit does a practice simulation or a chat turn use, and can it be topped up if we run out?
> 3. Is calling `close_call` as an `end_of_call` lifecycle tool (as `examples/base-agent.json` does) fine for scoring?
> 4. For the top-10 re-run: will you run our builder with your own keys? Our builder calls Claude through claude-agent-sdk (a Claude login or `ANTHROPIC_API_KEY`).
> Thanks, Ahmet
