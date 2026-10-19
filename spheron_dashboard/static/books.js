const booksUrl = "/api/books";

const fmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });
const compact = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function num(value, digits = 4) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toLocaleString("pt-BR", { maximumFractionDigits: digits });
}

function usd(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: digits,
  });
}

function metric(label, value) {
  return `<div class="metric"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

function badge(value, cls = "") {
  return `<span class="badge ${cls}">${text(value)}</span>`;
}

function statusClass(status) {
  if (status === "book_real" || status === "book_real_browser" || status === "book_real_http") return "ok";
  if (status === "book_stale_browser" || status === "fallback_sem_book" || status === "dex_liquidity_sem_book") return "warn";
  if (status === "erro") return "fail";
  return "";
}

function marketLink(row) {
  if (!row.url) return text(row.exchange);
  return `<a href="${row.url}" target="_blank" rel="noreferrer">${text(row.exchange)}</a>`;
}

function quoteLines(row) {
  const quotes = row.sell_quotes || {};
  const lines = Object.entries(quotes)
    .map(([amount, quote]) => {
      if (!quote) return `<div class="muted">${amount} PRL: sem book</div>`;
      const state = quote.complete ? "" : " parcial";
      const fee = quote.quote_out_after_fee
        ? ` <span class="muted">liq. ${usd(quote.quote_out_after_fee, 4)}</span>`
        : "";
      return `<div>${amount} PRL -> ${usd(quote.quote_out, 4)}${fee} <span class="muted">@ ${num(quote.avg_sell_price, 6)}${state}</span></div>`;
    });
  return lines.length ? lines.join("") : `<span class="muted">DEX: use quote de swap</span>`;
}

function depthLine(label, value) {
  if (!value) return `<div class="muted">${label}: -</div>`;
  return `<div>${label}: ${num(value.base, 2)} PRL <span class="muted">${usd(value.quote, 2)}</span></div>`;
}

function render(data) {
  const markets = data.markets || [];
  const realBooks = markets.filter((row) => ["book_real", "book_real_browser", "book_real_http"].includes(row.book_status));
  const dexRows = markets.filter((row) => row.kind === "dex_pool");
  const fallbackRows = markets.filter((row) => row.book_status && row.book_status !== "book_real" && row.kind !== "dex_pool");

  document.querySelector("#refreshStatus").textContent = `atualizado ${new Date(data.ts * 1000).toLocaleTimeString()}`;
  document.querySelector("#bookMetrics").innerHTML = [
    metric("books reais", realBooks.length),
    metric("DEX pools", dexRows.length),
    metric("fallbacks", fallbackRows.length),
    metric("quantidades", (data.amounts_prl || []).join(", ")),
    metric("melhor Ourbit", (() => {
      const row = markets.find((item) => item.exchange === "Ourbit");
      return row ? `${usd(row.best_bid, 4)} bid` : "-";
    })()),
  ].join("");
  document.querySelector("#notes").textContent = (data.notes || []).join(" ");

  document.querySelector("#marketCount").textContent = `${markets.length} mercados`;
  document.querySelector("#markets").innerHTML = markets
    .map((row) => `<tr>
      <td>${marketLink(row)}<div class="muted">${text(row.asset)}</div></td>
      <td class="mono">${text(row.pair)}</td>
      <td>${badge(row.book_status, statusClass(row.book_status))}<div class="muted">${text(row.kind)}</div></td>
      <td>${num(row.best_bid, 6)} / ${num(row.best_ask, 6)}<div class="muted">spread ${num(row.spread_pct, 3)}%</div></td>
      <td>${num(row.last, 6)}</td>
      <td>${row.quote_volume_24h ? usd(row.quote_volume_24h, 0) : "-"}</td>
      <td>${row.liquidity_usd ? usd(row.liquidity_usd, 0) : "-"}<div class="muted">${row.txns_24h ? `${row.txns_24h} tx 24h` : ""}</div></td>
      <td>${quoteLines(row)}</td>
      <td>
        ${depthLine("2%", row.sell_depth_2pct)}
        ${depthLine("5%", row.sell_depth_5pct)}
        ${depthLine("10%", row.sell_depth_10pct)}
      </td>
      <td class="muted">${text(row.note || row.relation)}</td>
    </tr>`)
    .join("");
}

async function refresh() {
  const form = document.querySelector("#bookForm");
  const params = new URLSearchParams({
    amounts: form.elements.amounts.value,
  });
  const response = await fetch(`${booksUrl}?${params.toString()}`);
  if (!response.ok) throw new Error(`books ${response.status}`);
  render(await response.json());
}

document.querySelector("#bookForm").addEventListener("submit", (event) => {
  event.preventDefault();
  refresh().catch((error) => {
    document.querySelector("#refreshStatus").textContent = error.message;
  });
});

refresh().catch((error) => {
  document.querySelector("#refreshStatus").textContent = error.message;
});

setInterval(() => refresh().catch((error) => {
  document.querySelector("#refreshStatus").textContent = error.message;
}), 15000);
