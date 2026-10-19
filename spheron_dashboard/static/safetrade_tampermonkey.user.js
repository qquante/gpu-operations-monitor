// ==UserScript==
// @name         SafeTrade PRL Book Bridge
// @namespace    http://localhost:8091/
// @version      0.3.1
// @description  Sends SafeTrade PRL/USDT depth from your normal browser session to the local PRL Books dashboard.
// @match        https://safetrade.com/*
// @match        https://safe.trade/*
// @run-at       document-idle
// @noframes
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      localhost
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  "use strict";

  const market = "prlusdt";
  const localUrl = "http://localhost:8091/api/safetrade/browser-cache";
  const baseIntervalMs = 15000;
  const maxIntervalMs = 120000;

  let timer = null;
  let currentIntervalMs = baseIntervalMs;
  const state = {
    running: false,
    lastOkAt: null,
    lastError: null,
    lastSequence: null,
    lastBidCount: 0,
    lastAskCount: 0,
    currentIntervalMs,
  };

  async function readJson(path) {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { Accept: "application/json, text/plain, */*" },
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
  }

  function postLocal(payload) {
    return new Promise((resolve, reject) => {
      if (typeof GM_xmlhttpRequest !== "function") {
        reject(new Error("GM_xmlhttpRequest indisponivel; confira grants do Tampermonkey"));
        return;
      }
      GM_xmlhttpRequest({
        method: "POST",
        url: localUrl,
        headers: { "Content-Type": "application/json" },
        data: JSON.stringify(payload),
        timeout: 10000,
        onload(response) {
          if (response.status >= 200 && response.status < 300) {
            resolve(response.responseText);
          } else {
            reject(new Error(`localhost ${response.status}: ${response.responseText.slice(0, 160)}`));
          }
        },
        onerror(error) {
          reject(new Error(`localhost request failed: ${JSON.stringify(error)}`));
        },
        ontimeout() {
          reject(new Error("localhost request timeout"));
        },
      });
    });
  }

  function scheduleNext() {
    clearTimeout(timer);
    state.currentIntervalMs = currentIntervalMs;
    if (state.running) {
      timer = setTimeout(push, currentIntervalMs);
    }
  }

  async function push() {
    state.running = true;
    try {
      const depth = await readJson(`/api/v2/trade/public/markets/${market}/depth?limit=100`);
      const payload = {
        market,
        bids: Array.isArray(depth.bids) ? depth.bids : [],
        asks: Array.isArray(depth.asks) ? depth.asks : [],
        sequence: depth.sequence ?? null,
        ticker: null,
        trades: null,
      };
      await postLocal(payload);
      currentIntervalMs = baseIntervalMs;
      state.lastOkAt = new Date().toISOString();
      state.lastError = null;
      state.lastSequence = payload.sequence;
      state.lastBidCount = payload.bids.length;
      state.lastAskCount = payload.asks.length;
      console.log("[SafeTrade PRL book] enviado para localhost", {
        bids: payload.bids.length,
        asks: payload.asks.length,
        sequence: payload.sequence,
      });
    } catch (error) {
      currentIntervalMs = Math.min(currentIntervalMs * 2, maxIntervalMs);
      state.lastError = error.message;
      console.warn("[SafeTrade PRL book] aguardando sessao/API liberar", {
        error: error.message,
        retryMs: currentIntervalMs,
      });
    } finally {
      scheduleNext();
    }
  }

  const api = {
    status: state,
    start() {
      currentIntervalMs = baseIntervalMs;
      state.running = true;
      push();
    },
    stop() {
      state.running = false;
      clearTimeout(timer);
      timer = null;
      console.log("[SafeTrade PRL book] parado");
    },
  };

  unsafeWindow.safeTradePrlBookBridge = api;
  window.safeTradePrlBookBridge = api;

  console.log("[SafeTrade PRL book] Tampermonkey carregado", api.status);
  setTimeout(push, 1000);
})();
