const $ = (id) => document.getElementById(id);

let lastPrimeState = { now: [], akoya21_radar: [], gpu_universe: [], gpu_sections: [], reevaluate: [], real_history: [], queue: [] };

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `$${fmtNum(value, 2)}`;
}

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${fmtNum(value, 1)}%`;
}

function dateLabel(ts) {
  if (!ts) return "-";
  return new Date(Number(ts) * 1000).toLocaleString();
}

function poolLabel(pool) {
  if (pool === "alphamine") return "AlphaMine";
  if (pool === "akoya") return "Akoya";
  return pool || "-";
}

function statusClass(value) {
  if (value === "ready" || value === "started" || value === "active") return "green";
  if (value === "waiting" || value === "renting" || value === "no_offer" || value === "manual") return "yellow";
  if (value === "blocked" || value === "failed") return "red";
  return "gray";
}

function profitClass(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value) >= 0 ? "positive" : "negative";
}

function sourceLabel(source) {
  if (source === "real_scout") return "real Scout";
  if (source === "akoya_2_1_benchmark") return "Akoya 2.1";
  if (source === "shared_database") return "database";
  return source || "-";
}

function shortText(value, max = 72) {
  const text = value === null || value === undefined || value === "" ? "-" : String(value);
  return text.length > max ? `${text.slice(0, max - 3)}...` : text;
}

function noRows(colspan, label) {
  return `<tr><td colspan="${colspan}">${label}</td></tr>`;
}

function riskText(row) {
  return (row.risks || []).length ? (row.risks || []).join(", ") : "-";
}

function networkText(row) {
  const down = row.net_down_mbps;
  const up = row.net_up_mbps;
  if ((down === null || down === undefined || down === "") && (up === null || up === undefined || up === "")) return "-";
  return `${fmtNum(down, 0)}/${fmtNum(up, 0)} Mbps`;
}

function statusPill(row) {
  return `<span class="pill ${statusClass(row.status || row.action_status)}" title="${row.status_reason || ""}">${shortText(row.status_reason || row.status || row.action_status, 34)}</span>`;
}

function actionCell(row) {
  if (row.status === "active") return `<span class="pill green">Ja alugada</span>`;
  if (!row.ask_id) return "-";
  return `<button class="action-button" data-prime-ask="${row.ask_id}">${row.action_label || "Testar/Alugar via Scout"}</button>`;
}

function renderSummary(data) {
  const summary = data.summary || {};
  $("summaryCards").innerHTML = `
    <article><span>Ofertas Vast</span><strong>${summary.vast_offers || 0}</strong><em>atuais</em></article>
    <article><span>Prontas</span><strong>${summary.ready || 0}</strong><em>acao manual</em></article>
    <article><span>Ativas</span><strong>${summary.active || 0}</strong><em>ja alugadas</em></article>
    <article><span>Akoya 2.1 lucro</span><strong>${summary.akoya21_profitable || 0}</strong><em>simuladas positivas</em></article>
    <article><span>Melhor score</span><strong>${fmtNum(summary.best_prime_score, 2)}</strong><em>${summary.best_gpu || "-"}</em></article>
    <article><span>Melhor lucro/h</span><strong>${money(summary.best_profit_usd_hr)}</strong><em>Akoya 2.1/real</em></article>
    <article><span>Fila</span><strong>${summary.queue_waiting || 0}</strong><em>Results waiting</em></article>
  `;
}

function renderNowRow(row) {
  return `
    <tr>
      <td>${fmtNum(row.prime_score, 2)}</td>
      <td>${row.ask_id || "-"}</td>
      <td>${row.gpu || "-"} x${row.gpu_count || "-"}</td>
      <td>${row.host_id || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${money(row.price_usd_hr)}</td>
      <td>${fmtNum(row.akoya21_hashrate_ths, 2)}</td>
      <td class="${profitClass(row.akoya21_profit_usd_hr)}">${money(row.akoya21_profit_usd_hr)}</td>
      <td>${row.history_hits || 0} hits ${money(row.best_real_profit_usd_hr)}</td>
      <td>${sourceLabel(row.hash_source)} / ${row.confidence || "-"}</td>
      <td>${statusPill(row)}</td>
      <td>${actionCell(row)}</td>
    </tr>
  `;
}

function renderRadarRow(row) {
  return `
    <tr>
      <td>${row.gpu || "-"} x${row.gpu_count || "-"}</td>
      <td>${row.ask_id || "-"}</td>
      <td>${money(row.price_usd_hr)}</td>
      <td>${fmtNum(row.akoya21_hashrate_ths, 2)}</td>
      <td class="${profitClass(row.akoya21_profit_usd_hr)}">${money(row.akoya21_profit_usd_hr)}</td>
      <td>${pct(row.roi_pct)}</td>
      <td>${row.confidence || "-"}</td>
      <td>${shortText(riskText(row), 54)}</td>
      <td>${statusPill(row)}</td>
      <td>${actionCell(row)}</td>
    </tr>
  `;
}

function renderReevaluateRow(row) {
  return `
    <tr>
      <td>${row.gpu || "-"} x${row.gpu_count || "-"}</td>
      <td>${row.ask_id || "-"}</td>
      <td>${money(row.price_usd_hr)}</td>
      <td class="${profitClass(row.current_profit_usd_hr)}">${money(row.current_profit_usd_hr)}</td>
      <td class="${profitClass(row.akoya21_profit_usd_hr)}">${money(row.akoya21_profit_usd_hr)}</td>
      <td>${sourceLabel(row.hash_source)}</td>
      <td>${poolLabel(row.gpu_best_pool)} ${money(row.gpu_best_profit_usd_hr)}</td>
      <td>${statusPill(row)}</td>
      <td>${actionCell(row)}</td>
    </tr>
  `;
}

function renderGpuUniverseRow(row) {
  const status = row.current_offers ? (row.best_current_status && row.best_current_status !== "no_offer" ? row.best_current_status : "manual") : "no_offer";
  const label = status === "no_offer" ? "Sem oferta" : status === "manual" ? "Manual" : status;
  const action = row.best_current_ask
    ? `<button class="action-button" data-prime-ask="${row.best_current_ask}">Testar manual</button>`
    : "-";
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${fmtNum(row.akoya21_ths, 2)}</td>
      <td>${row.current_offers || 0}</td>
      <td>${row.best_current_ask || "-"}</td>
      <td>${money(row.best_current_price_usd_hr)}</td>
      <td class="${profitClass(row.best_current_profit_usd_hr)}">${money(row.best_current_profit_usd_hr)}</td>
      <td class="${profitClass(row.best_history_profit_usd_hr)}">${money(row.best_history_profit_usd_hr)}</td>
      <td>${poolLabel(row.best_history_pool)}</td>
      <td>${row.history_samples || 0}</td>
      <td><span class="pill ${statusClass(status)}">${label}</span></td>
      <td>${action}</td>
    </tr>
  `;
}

function renderGpuOfferRow(row) {
  return `
    <tr>
      <td>${row.ask_id || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.host_id || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${money(row.price_usd_hr)}</td>
      <td>${fmtNum(row.akoya21_hashrate_ths, 2)}</td>
      <td class="${profitClass(row.akoya21_profit_usd_hr)}">${money(row.akoya21_profit_usd_hr)}</td>
      <td>${row.pcie || "-"}</td>
      <td>${row.cuda || "-"}</td>
      <td>${networkText(row)}</td>
      <td>${row.reliability || "-"}</td>
      <td>${sourceLabel(row.hash_source)} / ${row.confidence || "-"}</td>
      <td>${shortText(riskText(row), 48)}</td>
      <td>${statusPill(row)}</td>
      <td>${actionCell(row)}</td>
    </tr>
  `;
}

function renderGpuSection(section) {
  const offers = section.offers || [];
  const rows = offers.length ? offers.map(renderGpuOfferRow).join("") : noRows(15, "Sem oferta Vast atual para esta GPU.");
  return `
    <div class="gpu-section">
      <div class="gpu-section-head">
        <div>
          <h3>${section.gpu || "-"}</h3>
          <p>Hash 2.1 ${fmtNum(section.akoya21_ths, 2)} TH/s · ${section.current_offers || 0} ofertas · melhor ask ${section.best_offer_ask || "-"}</p>
        </div>
        <div class="gpu-section-metrics">
          <span>Lucro oferta: <strong class="${profitClass(section.best_offer_profit_usd_hr)}">${money(section.best_offer_profit_usd_hr)}</strong></span>
          <span>Historico: <strong class="${profitClass(section.best_history_profit_usd_hr)}">${money(section.best_history_profit_usd_hr)}</strong> ${poolLabel(section.best_history_pool)}</span>
          <span>Amostras: <strong>${section.history_samples || 0}</strong></span>
        </div>
      </div>
      <div class="table-wrap gpu-offers">
        <table>
          <thead>
            <tr>
              <th>Ask</th>
              <th>Qtd</th>
              <th>Host</th>
              <th>Machine</th>
              <th>Preco/h</th>
              <th>Hash 2.1</th>
              <th>Lucro/h</th>
              <th>PCIe</th>
              <th>CUDA</th>
              <th>Rede down/up</th>
              <th>Reliability</th>
              <th>Fonte</th>
              <th>Riscos</th>
              <th>Status</th>
              <th>Acao</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderHistoryRow(row) {
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${row.host_id || "-"}</td>
      <td>${row.count || 0}</td>
      <td>${poolLabel(row.preferred_pool || row.best_pool)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td><span class="pill ${statusClass(row.action_status)}">${row.action_status || "-"}</span></td>
    </tr>
  `;
}

function renderHostRow(row) {
  return `
    <tr>
      <td>${row.host_id || "-"}</td>
      <td>${(row.gpus || []).join(", ") || "-"}</td>
      <td>${row.machines_count || 0}</td>
      <td>${row.hits || 0}</td>
      <td>${poolLabel(row.best_pool)}</td>
      <td class="${profitClass(row.avg_profit_usd_hr)}">${money(row.avg_profit_usd_hr)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${row.current_offers_count || 0}</td>
      <td><span class="pill ${statusClass(row.action_status)}">${row.action_status || "-"}</span></td>
    </tr>
  `;
}

function renderQueueRow(row) {
  return `
    <tr>
      <td><span class="pill ${statusClass(row.status)}">${row.status || "-"}</span></td>
      <td>${row.kind || "-"}</td>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${row.host_id || "-"}</td>
      <td>${dateLabel(row.next_retry_at)}</td>
      <td>${shortText(row.last_error, 90)}</td>
    </tr>
  `;
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || response.statusText);
  return body;
}

async function rentPrimeOffer(askId, button) {
  const sectionOffers = (lastPrimeState.gpu_sections || []).flatMap((section) => section.offers || []);
  const row = (lastPrimeState.now || []).find((item) => String(item.ask_id) === String(askId))
    || (lastPrimeState.akoya21_radar || []).find((item) => String(item.ask_id) === String(askId))
    || (lastPrimeState.gpu_universe || []).find((item) => String(item.best_current_ask) === String(askId))
    || sectionOffers.find((item) => String(item.ask_id) === String(askId))
    || {};
  const ok = window.confirm(`Enviar ask ${askId} para teste/aluguel via Scout?`);
  if (!ok) return;
  button.disabled = true;
  button.textContent = "Enviando...";
  await postJson("/api/results/rent/offer", {
    ask_id: askId,
    gpu: row.gpu,
    gpu_count: row.gpu_count || row.best_current_gpu_count,
    machine_id: row.machine_id || row.best_current_machine_id,
    host_id: row.host_id || row.best_current_host_id,
    pcie: row.pcie || row.best_current_pcie,
    cuda: row.cuda || row.best_current_cuda,
    reliability: row.reliability || row.best_current_reliability,
    net_up_mbps: row.net_up_mbps || row.best_current_net_up_mbps,
    net_down_mbps: row.net_down_mbps || row.best_current_net_down_mbps,
    price_usd_hr: row.price_usd_hr || row.best_current_price_usd_hr,
    profit_usd_hr: row.akoya21_profit_usd_hr || row.best_current_profit_usd_hr,
    preferred_pool: "akoya",
  });
  await load();
}

function bindActions() {
  document.querySelectorAll("[data-prime-ask]").forEach((button) => {
    button.onclick = async () => {
      try {
        await rentPrimeOffer(button.getAttribute("data-prime-ask"), button);
      } catch (error) {
        $("connection").textContent = `Erro PRIME: ${error.message || error}`;
        button.disabled = false;
        button.textContent = "Testar/Alugar via Scout";
      }
    };
  });
}

function render(data) {
  lastPrimeState = data || {};
  renderSummary(data || {});
  $("nowRows").innerHTML = (data.now || []).length ? (data.now || []).map(renderNowRow).join("") : noRows(12, "Nenhuma oferta Vast atual.");
  $("radarRows").innerHTML = (data.akoya21_radar || []).length ? (data.akoya21_radar || []).map(renderRadarRow).join("") : noRows(10, "Nenhum candidato Akoya 2.1 agora.");
  $("gpuUniverseRows").innerHTML = (data.gpu_universe || []).length ? (data.gpu_universe || []).map(renderGpuUniverseRow).join("") : noRows(11, "Sem GPUs mapeadas.");
  $("gpuSections").innerHTML = (data.gpu_sections || []).length ? (data.gpu_sections || []).map(renderGpuSection).join("") : `<p class="empty-state">Sem secoes por GPU.</p>`;
  $("reevaluateRows").innerHTML = (data.reevaluate || []).length ? (data.reevaluate || []).map(renderReevaluateRow).join("") : noRows(9, "Nada para reavaliar agora.");
  $("historyRows").innerHTML = (data.real_history || []).length ? (data.real_history || []).map(renderHistoryRow).join("") : noRows(8, "Sem historico real.");
  const hosts = (data.premium_hosts || {}).hosts || [];
  $("hostRows").innerHTML = hosts.length ? hosts.map(renderHostRow).join("") : noRows(9, "Sem hosts premium.");
  $("queueRows").innerHTML = (data.queue || []).length ? (data.queue || []).map(renderQueueRow).join("") : noRows(8, "Fila vazia.");
  $("connection").textContent = `Atualizado ${new Date((data.updated_at || Date.now() / 1000) * 1000).toLocaleTimeString()}`;
  bindActions();
}

async function load() {
  const response = await fetch("/api/prime/state");
  if (!response.ok) throw new Error(response.statusText);
  render(await response.json());
}

load().catch((error) => {
  $("connection").textContent = `Erro ao carregar PRIME: ${error.message || error}`;
});
setInterval(() => {
  load().catch((error) => {
    $("connection").textContent = `Erro ao atualizar PRIME: ${error.message || error}`;
  });
}, 5000);
