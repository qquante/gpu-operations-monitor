# SafeTrade Books Browser

Coletor local para o book `PRL/USDT` da SafeTrade usando Chrome visivel com perfil persistente.

Ele existe porque a API publica da SafeTrade pode responder `403` com Cloudflare quando chamada direto pelo backend. O coletor abre a propria pagina da SafeTrade, voce resolve Cloudflare/login uma vez, e o script chama os endpoints publicos de dentro da sessao do navegador. Cookies e `cf_clearance` ficam apenas no perfil do Chrome.

## Install

Do repo root:

```powershell
python -m pip install -r scripts\spheron_sniper_requirements.txt
python -m playwright install chromium
```

O script prefere Google Chrome instalado; Chromium do Playwright fica como fallback.

## First Run

```powershell
python scripts\safetrade_books_browser.py --watch
```

Na primeira execucao, uma janela do Chrome abre em:

```text
https://safetrade.com/exchange/PRL-USDT?type=basic
```

Resolva Cloudflare/login nessa janela. O script espera ate `SAFETRADE_LOGIN_WAIT_SECONDS` segundos, padrao `60`, e passa a salvar o cache em:

```text
data\safetrade_books_cache.json
```

O dashboard em `http://localhost:8091/books` le esse cache e mostra SafeTrade como `book_real_browser` enquanto o cache estiver fresco.

## Manual Chrome Mode

Se a Cloudflare nao aceitar o Chrome aberto pelo Playwright, use seu Chrome normal:

1. Abra `https://safetrade.com/exchange/PRL-USDT?type=basic`.
2. Resolva a verificacao de humano manualmente.
3. Abra DevTools > Console.
4. Cole este snippet:

```js
(() => {
  const market = "prlusdt";
  const localUrl = "http://localhost:8091/api/safetrade/browser-cache";
  const readJson = async (path) => {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { Accept: "application/json, text/plain, */*" },
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  };
  const push = async () => {
    const [depth, ticker, trades] = await Promise.all([
      readJson(`/api/v2/trade/public/markets/${market}/depth?limit=100`),
      readJson(`/api/v2/trade/public/tickers/${market}`).catch((error) => ({ error: String(error) })),
      readJson(`/api/v2/trade/public/markets/${market}/trades?limit=80`).catch(() => null),
    ]);
    const payload = {
      market,
      bids: Array.isArray(depth.bids) ? depth.bids : [],
      asks: Array.isArray(depth.asks) ? depth.asks : [],
      sequence: depth.sequence ?? null,
      ticker,
      trades,
    };
    const saved = await fetch(localUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((response) => response.json());
    console.log("[SafeTrade PRL book]", saved);
  };
  clearInterval(window.__safeTradePrlBookInterval);
  push().catch(console.error);
  window.__safeTradePrlBookInterval = setInterval(() => push().catch(console.error), 5000);
})();
```

Para parar:

```js
clearInterval(window.__safeTradePrlBookInterval);
```

## Tampermonkey Mode

Este e o modo mais pratico para manter rodando no Chrome normal:

1. Instale Tampermonkey no Chrome.
2. Abra `http://localhost:8091/static/safetrade_tampermonkey.user.js`.
3. Tampermonkey deve oferecer instalar o userscript.
4. Abra `https://safetrade.com/exchange/PRL-USDT?type=basic`.
5. Resolva Cloudflare manualmente.
6. Deixe a aba `SafeTrade Bridge` aberta.

O userscript busca apenas `/depth?limit=100` a cada 15s e usa backoff ate 120s quando a SafeTrade retorna `403`, para reduzir chamadas e evitar derrubar a sessao.

No console da SafeTrade:

```js
safeTradePrlBookBridge.stop()
safeTradePrlBookBridge.start()
```

## Commands

Salvar um book e sair:

```powershell
python scripts\safetrade_books_browser.py --once
```

Manter atualizando:

```powershell
python scripts\safetrade_books_browser.py --watch
```

Ver status do cache:

```powershell
python scripts\safetrade_books_browser.py --status
```

## Env Vars

```text
SAFETRADE_BROWSER_PROFILE_DIR=%LOCALAPPDATA%\SafeTradeBooks\ChromeProfile
SAFETRADE_BOOK_CACHE_PATH=data\safetrade_books_cache.json
SAFETRADE_BOOK_POLL_SECONDS=5
SAFETRADE_LOGIN_WAIT_SECONDS=60
SAFETRADE_MARKET_ID=prlusdt
SAFETRADE_BOOK_CACHE_TTL_SECONDS=30
```

O script nao imprime nem salva cookies em arquivo do repo. O arquivo de cache contem apenas `ts`, `source`, `market`, `bids`, `asks`, `ticker`, `trades` e erros publicos de coleta.
