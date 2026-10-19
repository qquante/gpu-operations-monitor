const $ = (id) => document.getElementById(id);

let lastState = { gpus: [], hardware: [], patterns: [], queue: [], host_watch: {} };

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

function sourceLabel(item) {
  if (item.source_label) return item.source_label;
  if (item.source === "auto_clore") return "Auto Clore";
  if (item.source === "manual_clore") return "Manual Clore";
  if (item.source === "results") return "Results";
  if (item.source === "trigger") return "Trigger";
  return item.source || "-";
}

function decisionLabel(value) {
  return { green: "ALUGAR", yellow: "MARGEM", alert: "RISCO", red: "NAO", gray: "SEM CALC" }[value] || value || "-";
}

function sourceDetail(item) {
  const detail = item.auto_log || (item.source === "auto_clore" ? `Auto Clore: decisao ${decisionLabel(item.auto_decision || item.opportunity_decision)}` : "");
  if (!detail) return sourceLabel(item);
  return `${sourceLabel(item)} | ${detail}`;
}

function profitClass(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value) >= 0 ? "positive" : "negative";
}

function statusClass(value) {
  if (value === "ready" || value === "started" || value === "active") return "green";
  if (value === "waiting" || value === "renting" || value === "no_offer") return "yellow";
  if (value === "blocked" || value === "failed") return "red";
  return "gray";
}

function decisionClass(value) {
  if (value === "keep") return "green";
  if (value === "destroy" || value === "blacklist" || value === "failed") return "red";
  if (value === "no_worker" || value === "zero_hash_5m" || value === "runtime_error" || value === "pool_measured") return "yellow";
  return "gray";
}

function shortText(value, fallback = "-") {
  const text = value === null || value === undefined || value === "" ? fallback : String(value);
  return text.length > 96 ? `${text.slice(0, 93)}...` : text;
}

function escapeAttr(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function noRows(colspan, label) {
  return `<tr><td colspan="${colspan}">${label}</td></tr>`;
}

function offerLabel(offer) {
  if (!offer) return "-";
  const pcie = offer.pcie ? ` ${offer.pcie}` : "";
  return `ask ${offer.ask_id || "-"}${pcie} ${money(offer.price_usd_hr)}/h ${money(offer.profit_usd_hr)}/h`;
}

function actionLabel(status) {
  if (status === "active") return "Ja alugada";
  if (status === "ready") return "Pronta";
  if (status === "waiting") return "Na fila";
  if (status === "renting") return "Alugando";
  if (status === "blocked") return "Bloqueado";
  if (status === "no_offer") return "Sem oferta";
  return status || "-";
}

function renderRentAction(row, kind) {
  if (row.active || row.action_status === "active") {
    return `<span class="pill green">Ja alugada</span>`;
  }
  if (row.queue && row.queue.status === "waiting") {
    return `
      <button class="action-button" data-queue-retry="${row.queue.id}">Retry agora</button>
      <span class="pill yellow">fila</span>
    `;
  }
  const label = row.action_status === "blocked" ? "Alugar manual" : "Alugar";
  return `<button class="action-button" data-rent-kind="${kind}" data-row-id="${row.id}">${label}</button>`;
}

function isAllowlistStatus(row) {
  return String(row.status_reason || row.last_error || "").toLowerCase().includes("fora do allowlist");
}

function statusPill(row) {
  if (isAllowlistStatus(row)) {
    return `<span class="pill yellow">override manual</span>`;
  }
  return `<span class="pill ${statusClass(row.action_status)}">${shortText(row.status_reason || actionLabel(row.action_status), 42)}</span>`;
}

function renderSummary(data) {
  const summary = data.summary || {};
  $("summaryCards").innerHTML = `
    <article><span>Resultados lucrativos</span><strong>${summary.profitable_results || 0}</strong><em>profit > 0</em></article>
    <article><span>GPUs distintas</span><strong>${summary.profitable_gpus || 0}</strong><em>modelos bons</em></article>
    <article><span>Hardwares lucrativos</span><strong>${summary.profitable_hardware || 0}</strong><em>machine/host/GPU</em></article>
    <article><span>Padrões lucrativos</span><strong>${summary.profitable_patterns || 0}</strong><em>GPU/PCIe/host</em></article>
    <article><span>Melhor lucro/h</span><strong>${money(summary.best_profit_usd_hr)}</strong><em>${summary.best_gpu || "-"}</em></article>
    <article><span>Fila Results</span><strong>${summary.queue_waiting || 0}</strong><em>retry 5 min</em></article>
    <article><span>Prox retry</span><strong>${dateLabel(summary.next_retry_at)}</strong><em>quando vencer</em></article>
  `;
}

function renderGpuRow(row) {
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${row.count || 0}</td>
      <td>${row.hardware_count || 0}</td>
      <td>${poolLabel(row.preferred_pool || row.best_pool)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${money(row.max_price_usd_hr)}</td>
      <td>${offerLabel(row.current_offer)}</td>
      <td><span class="pill ${statusClass(row.action_status)}">${actionLabel(row.action_status)}</span></td>
      <td>${renderRentAction(row, "gpu")}</td>
    </tr>
  `;
}

function renderHardwareRow(row) {
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${row.host_id || "-"}</td>
      <td>${row.count || 0}</td>
      <td>${poolLabel(row.preferred_pool || row.best_pool)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${money(row.max_price_usd_hr)}</td>
      <td>${offerLabel(row.current_offer)}</td>
      <td><span class="pill ${statusClass(row.action_status)}">${actionLabel(row.action_status)}</span></td>
      <td>${renderRentAction(row, "hardware")}</td>
    </tr>
  `;
}

function renderPatternRow(row) {
  const priceRange = row.min_price_usd_hr || row.max_seen_price_usd_hr
    ? `${money(row.min_price_usd_hr)} - ${money(row.max_seen_price_usd_hr)}`
    : "-";
  const net = row.net_down_mbps || row.net_up_mbps
    ? `${fmtNum(row.net_down_mbps, 0)}/${fmtNum(row.net_up_mbps, 0)} Mbps`
    : "-";
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.pcie || "-"}</td>
      <td>${row.host_id || "-"}</td>
      <td>${row.machines_count || 0}</td>
      <td>${row.count || 0}</td>
      <td>${poolLabel(row.preferred_pool || row.best_pool)}</td>
      <td class="${profitClass(row.avg_profit_usd_hr)}">${money(row.avg_profit_usd_hr)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${priceRange}</td>
      <td>${net}</td>
      <td>${offerLabel(row.current_offer)}</td>
      <td><span class="pill ${statusClass(row.action_status)}">${actionLabel(row.action_status)}</span></td>
      <td>${renderRentAction(row, "pattern")}</td>
    </tr>
  `;
}

function renderHostIntelRow(row) {
  const priceRange = row.min_price_usd_hr || row.max_seen_price_usd_hr
    ? `${money(row.min_price_usd_hr)} - ${money(row.max_seen_price_usd_hr)}`
    : "-";
  const bestCurrent = row.best_current_h100
    ? `ask ${row.best_current_h100.ask_id} ${money(row.best_current_h100.price_usd_hr)}/h ${money(row.best_current_h100.profit_usd_hr)}/h`
    : "-";
  return `
    <tr>
      <td>${row.host_id || "-"}</td>
      <td>${(row.gpus || []).join(", ") || "-"}</td>
      <td>${row.machines_count || 0}</td>
      <td>${row.hits || 0}</td>
      <td>${poolLabel(row.best_pool)}</td>
      <td class="${profitClass(row.avg_profit_usd_hr)}">${money(row.avg_profit_usd_hr)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${priceRange}</td>
      <td>${row.current_offers_count || 0}</td>
      <td>${row.current_h100_count || 0}</td>
      <td>${bestCurrent}</td>
      <td><span class="pill ${statusClass(row.action_status)}">${actionLabel(row.action_status)}</span></td>
    </tr>
  `;
}

function renderHostOfferRow(row) {
  const net = row.net_down_mbps || row.net_up_mbps
    ? `${fmtNum(row.net_down_mbps, 0)}/${fmtNum(row.net_up_mbps, 0)} Mbps`
    : "-";
  let action = `<span class="pill ${statusClass(row.action_status)}">${actionLabel(row.action_status)}</span>`;
  if ((row.action_status === "ready" && row.eligible) || isAllowlistStatus(row)) {
    action = `<button class="action-button" data-host-offer-ask="${row.ask_id}">${isAllowlistStatus(row) ? "Alugar manual" : "Alugar"}</button>`;
  } else if (row.queue && row.queue.status === "waiting") {
    action = `<button class="action-button" data-queue-retry="${row.queue.id}">Retry agora</button>`;
  }
  return `
    <tr>
      <td>${row.ask_id || "-"}</td>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${money(row.price_usd_hr)}</td>
      <td class="${profitClass(row.profit_usd_hr)}">${money(row.profit_usd_hr)}</td>
      <td>${row.pcie || "-"}</td>
      <td>${net}</td>
      <td>${statusPill(row)}</td>
      <td>${action}</td>
    </tr>
  `;
}

function renderHostIntelOfferRow(row) {
  const net = row.net_down_mbps || row.net_up_mbps
    ? `${fmtNum(row.net_down_mbps, 0)}/${fmtNum(row.net_up_mbps, 0)} Mbps`
    : "-";
  let action = `<span class="pill ${statusClass(row.action_status)}">${actionLabel(row.action_status)}</span>`;
  if ((row.action_status === "ready" && row.eligible) || isAllowlistStatus(row)) {
    action = `<button class="action-button" data-host-offer-ask="${row.ask_id}">${isAllowlistStatus(row) ? "Alugar manual" : "Alugar"}</button>`;
  } else if (row.queue && row.queue.status === "waiting") {
    action = `<button class="action-button" data-queue-retry="${row.queue.id}">Retry agora</button>`;
  }
  return `
    <tr>
      <td>${row.host_id || "-"}</td>
      <td>${row.ask_id || "-"}</td>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${money(row.price_usd_hr)}</td>
      <td class="${profitClass(row.profit_usd_hr)}">${money(row.profit_usd_hr)}</td>
      <td>${row.pcie || "-"}</td>
      <td>${net}</td>
      <td>${statusPill(row)}</td>
      <td>${action}</td>
    </tr>
  `;
}

function renderGroupedHostIntelOffers(rows) {
  if (!rows.length) return noRows(11, "Nenhuma oferta atual nos hosts lucrativos.");
  const grouped = new Map();
  rows.forEach((row) => {
    const host = String(row.host_id || "-");
    if (!grouped.has(host)) grouped.set(host, []);
    grouped.get(host).push(row);
  });
  return Array.from(grouped.entries()).map(([host, items]) => {
    const ready = items.filter((item) => item.action_status === "ready" || isAllowlistStatus(item)).length;
    const title = `
      <tr class="host-group-row">
        <td colspan="11"><strong>Host ${host}</strong> · ${items.length} ofertas atuais · ${ready} acionaveis por clique manual</td>
      </tr>
    `;
    return title + items.map(renderHostIntelOfferRow).join("");
  }).join("");
}

function renderHostHistoryRow(row) {
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${row.gpu_count || "-"}</td>
      <td>${row.machine_id || "-"}</td>
      <td>${row.count || 0}</td>
      <td>${poolLabel(row.best_pool)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${money(row.best_price_usd_hr)}</td>
      <td><span class="pill ${decisionClass(row.last_decision)}">${row.last_decision || "-"}</span></td>
      <td>${dateLabel(row.last_seen_at)}</td>
    </tr>
  `;
}

function renderWorstGpuRow(row) {
  const action = row.blacklisted
    ? `<span class="pill red">blacklist</span>`
    : `<button class="action-button danger" data-blacklist-gpu="${row.gpu}">Blacklist GPU</button>`;
  return `
    <tr>
      <td>${row.gpu || "-"}</td>
      <td>${row.samples || 0}</td>
      <td>${row.bad_samples || 0}</td>
      <td>${row.viable_samples || 0}</td>
      <td>${pct(row.bad_rate_pct)}</td>
      <td class="${profitClass(row.avg_profit_usd_hr)}">${money(row.avg_profit_usd_hr)}</td>
      <td class="${profitClass(row.worst_profit_usd_hr)}">${money(row.worst_profit_usd_hr)}</td>
      <td class="${profitClass(row.best_profit_usd_hr)}">${money(row.best_profit_usd_hr)}</td>
      <td>${dateLabel(row.last_seen_at)}</td>
      <td>${shortText(row.reason)}</td>
      <td>${action}</td>
    </tr>
  `;
}

function renderQueueRow(item) {
  return `
    <tr>
      <td><span class="pill ${statusClass(item.status)}">${item.status || "-"}</span></td>
      <td>${item.kind || "-"}</td>
      <td>${item.gpu || "-"}</td>
      <td>${item.gpu_count || "-"}</td>
      <td>${item.machine_id || "-"}</td>
      <td>${item.host_id || "-"}</td>
      <td>${item.attempts || 0}</td>
      <td>${dateLabel(item.next_retry_at)}</td>
      <td>${shortText(item.last_error)}</td>
      <td>
        <button class="action-button" data-queue-retry="${item.id}">Retry</button>
        <button class="action-button quiet" data-queue-archive="${item.id}">Arquivar</button>
      </td>
    </tr>
  `;
}

function renderHistoryRow(item) {
  return `
    <tr>
      <td>${dateLabel(item.ended_at)}</td>
      <td>${item.ask_id || "-"}</td>
      <td>${item.instance_id || "-"}</td>
      <td title="${escapeAttr(sourceDetail(item))}">${sourceLabel(item)}${item.source === "auto_clore" ? ` / ${decisionLabel(item.auto_decision || item.opportunity_decision)}` : ""}</td>
      <td>${item.gpu || "-"}</td>
      <td>${item.gpu_count || "-"}</td>
      <td>${poolLabel(item.pool_strategy)}</td>
      <td>${money(item.price_usd_hr)}</td>
      <td>${fmtNum(item.live_ths_avg, 2)}</td>
      <td>${item.hash_ratio === null || item.hash_ratio === undefined ? "-" : pct(Number(item.hash_ratio) * 100)}</td>
      <td class="${profitClass(item.profit_usd_hr)}">${money(item.profit_usd_hr)}</td>
      <td><span class="pill ${decisionClass(item.decision)}">${item.decision || "-"}</span></td>
      <td>${shortText(item.reason || item.improvement_summary)}</td>
    </tr>
  `;
}

function findRow(kind, id) {
  const rows = kind === "hardware" ? lastState.hardware || [] : kind === "pattern" ? lastState.patterns || [] : lastState.gpus || [];
  return rows.find((row) => String(row.id) === String(id));
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || response.statusText);
  }
  return body;
}

async function rentRow(kind, id, button) {
  const row = findRow(kind, id);
  if (!row) return;
  const payload = {
    id: row.id,
    gpu: row.gpu,
    gpu_count: row.gpu_count,
    machine_id: row.machine_id,
    host_id: row.host_id,
    pcie: row.pcie,
  };
  button.disabled = true;
  button.textContent = "Enviando...";
  const endpoint = kind === "hardware" ? "/api/results/rent/hardware" : kind === "pattern" ? "/api/results/rent/pattern" : "/api/results/rent/gpu";
  await postJson(endpoint, payload);
  await load();
}

function findHostOffer(askId) {
  const hostIntel = lastState.host_intelligence || {};
  const hostWatch = lastState.host_watch || {};
  const rows = [
    ...(hostIntel.current_offers || []),
    ...(hostWatch.current_offers || []),
  ];
  return rows.find((row) => String(row.ask_id) === String(askId)) || {};
}

async function rentHostOffer(askId, button) {
  const row = findHostOffer(askId);
  button.disabled = true;
  button.textContent = "Enviando...";
  await postJson("/api/results/rent/offer", {
    ask_id: askId,
    gpu: row.gpu,
    gpu_count: row.gpu_count,
    machine_id: row.machine_id,
    host_id: row.host_id,
    pcie: row.pcie,
    cuda: row.cuda,
    reliability: row.reliability,
    net_up_mbps: row.net_up_mbps,
    net_down_mbps: row.net_down_mbps,
    price_usd_hr: row.price_usd_hr,
    profit_usd_hr: row.profit_usd_hr,
  });
  await load();
}

async function retryQueue(id, button) {
  button.disabled = true;
  button.textContent = "Tentando...";
  await postJson(`/api/results/queue/${encodeURIComponent(id)}/retry`);
  await load();
}

async function archiveQueue(id, button) {
  button.disabled = true;
  button.textContent = "Arquivando...";
  await postJson(`/api/results/queue/${encodeURIComponent(id)}/archive`);
  await load();
}

async function blacklistGpu(gpu, button) {
  const ok = confirm(`Bloquear ${gpu} para nao snipar/testar novas ofertas Vast?`);
  if (!ok) return;
  button.disabled = true;
  button.textContent = "Bloqueando...";
  await postJson("/api/results/blacklist/gpu", {
    gpu,
    reason: "Modelo ruim no Results; bloquear sniper/teste",
  });
  await load();
}

function bindActions() {
  document.querySelectorAll("[data-rent-kind]").forEach((button) => {
    button.onclick = async () => {
      try {
        await rentRow(button.getAttribute("data-rent-kind"), button.getAttribute("data-row-id"), button);
      } catch (error) {
        $("connection").textContent = `Erro ao alugar: ${error.message || error}`;
        button.disabled = false;
        button.textContent = "Alugar";
      }
    };
  });
  document.querySelectorAll("[data-queue-retry]").forEach((button) => {
    button.onclick = async () => {
      try {
        await retryQueue(button.getAttribute("data-queue-retry"), button);
      } catch (error) {
        $("connection").textContent = `Erro no retry: ${error.message || error}`;
        button.disabled = false;
        button.textContent = "Retry";
      }
    };
  });
  document.querySelectorAll("[data-host-offer-ask]").forEach((button) => {
    button.onclick = async () => {
      try {
        await rentHostOffer(button.getAttribute("data-host-offer-ask"), button);
      } catch (error) {
        $("connection").textContent = `Erro ao alugar host: ${error.message || error}`;
        button.disabled = false;
        button.textContent = "Alugar";
      }
    };
  });
  document.querySelectorAll("[data-queue-archive]").forEach((button) => {
    button.onclick = async () => {
      try {
        await archiveQueue(button.getAttribute("data-queue-archive"), button);
      } catch (error) {
        $("connection").textContent = `Erro ao arquivar: ${error.message || error}`;
        button.disabled = false;
        button.textContent = "Arquivar";
      }
    };
  });
  document.querySelectorAll("[data-blacklist-gpu]").forEach((button) => {
    button.onclick = async () => {
      try {
        await blacklistGpu(button.getAttribute("data-blacklist-gpu"), button);
      } catch (error) {
        $("connection").textContent = `Erro na blacklist: ${error.message || error}`;
        button.disabled = false;
        button.textContent = "Blacklist GPU";
      }
    };
  });
}

function render(data) {
  lastState = data || {};
  renderSummary(data || {});
  $("gpuRows").innerHTML = (data.gpus || []).length
    ? (data.gpus || []).map(renderGpuRow).join("")
    : noRows(9, "Nenhuma GPU lucrativa ainda.");
  $("hardwareRows").innerHTML = (data.hardware || []).length
    ? (data.hardware || []).map(renderHardwareRow).join("")
    : noRows(11, "Nenhum hardware lucrativo ainda.");
  $("patternRows").innerHTML = (data.patterns || []).length
    ? (data.patterns || []).map(renderPatternRow).join("")
    : noRows(14, "Nenhum padrao lucrativo ainda.");
  const hostIntel = data.host_intelligence || {};
  $("hostIntelRows").innerHTML = (hostIntel.hosts || []).length
    ? (hostIntel.hosts || []).map(renderHostIntelRow).join("")
    : noRows(12, "Nenhum host com lucro acima do minimo ainda.");
  $("hostIntelOfferRows").innerHTML = (hostIntel.current_offers || []).length
    ? renderGroupedHostIntelOffers(hostIntel.current_offers || [])
    : noRows(11, "Nenhuma oferta atual nos hosts lucrativos.");
  const hostWatch = data.host_watch || {};
  $("hostOfferRows").innerHTML = (hostWatch.current_offers || []).length
    ? (hostWatch.current_offers || []).map(renderHostOfferRow).join("")
    : noRows(10, "Nenhuma oferta atual nesse host.");
  $("hostHistoryRows").innerHTML = (hostWatch.history || []).length
    ? (hostWatch.history || []).map(renderHostHistoryRow).join("")
    : noRows(9, "Sem historico desse host ainda.");
  $("worstGpuRows").innerHTML = (data.worst_gpus || []).length
    ? (data.worst_gpus || []).map(renderWorstGpuRow).join("")
    : noRows(11, "Sem modelos ruins suficientes para sugerir blacklist.");
  $("queueRows").innerHTML = (data.queue || []).length
    ? (data.queue || []).map(renderQueueRow).join("")
    : noRows(10, "Fila Results vazia.");
  $("historyRows").innerHTML = (data.recent_results || []).length
    ? (data.recent_results || []).map(renderHistoryRow).join("")
    : noRows(13, "Sem historico do Scout.");
  $("connection").textContent = `Atualizado ${new Date().toLocaleTimeString()}`;
  bindActions();
}

async function load() {
  const response = await fetch("/api/results/state");
  if (!response.ok) throw new Error(response.statusText);
  render(await response.json());
}

load().catch((error) => {
  $("connection").textContent = `Erro ao carregar Results: ${error.message || error}`;
});
setInterval(() => {
  load().catch((error) => {
    $("connection").textContent = `Erro ao atualizar Results: ${error.message || error}`;
  });
}, 5000);
