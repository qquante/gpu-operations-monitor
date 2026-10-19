const $ = (id) => document.getElementById(id);

const labels = {
  green: "ALUGAR",
  yellow: "MARGEM",
  alert: "RISCO",
  red: "NAO",
  gray: "SEM CALC",
};

const riskLabels = {
  low_value_gpu: "low-value",
  cuda_below_12_9: "cuda<12.9",
  cuda_unknown: "cuda?",
  pcie_unknown: "pcie?",
  pcie_below_rule: "pcie baixo",
  reliability_low: "rel baixa",
  reliability_watch: "rel media",
  network_bad: "rede ruim",
  network_watch: "rede media",
  price_usd_missing: "preco?",
  clore_cache_risk: "verificar Clore",
  clore_unverified: "revalida no clique",
  worker_offline: "offline",
  cost_fixed_config: "custo fixo",
  cost_hardcoded: "custo hardcoded",
  cost_from_archived_action: "custo salvo",
  clore_action: "custo Clore",
  cost_not_configured: "sem custo",
  gpu_count_mismatch: "qtd placas",
  hashrate_below_rented_gpus: "hash baixo p/ placas",
  insufficient_vcpu: "vcpu insuf.",
  insufficient_ram: "ram insuf.",
  insufficient_storage: "disk insuf.",
};

const providerLabels = {
  all: "Todos",
  vastai: "Vast.ai",
  clore: "Clore",
  runpod: "RunPod",
  tensordock: "TensorDock",
};

const opportunityUi = {
  provider: "all",
  decision: "all",
  gpu: "all",
  sort: "profit_desc",
  sortKey: "profit_usd_hr",
  sortDir: "desc",
  search: "",
  allItems: [],
};
let decisionControlsReady = false;

const actionLabels = {
  ready: "pronto",
  verify: "verificar",
  blocked: "bloqueado",
  renting: "alugando",
  rented: "alugado",
  active: "ativo",
  waiting_worker: "aguardando worker",
  waiting_market: "aguardando Vast",
  watching: "watch",
  worker_offline: "worker offline",
  instance_error: "erro host",
  failed: "falhou",
  cancelled: "cancelado",
  archived: "arquivado",
};

const presetSorts = {
  profit_desc: ["profit_usd_hr", "desc"],
  roi_desc: ["roi_pct", "desc"],
  cost_asc: ["price_usd_hr", "asc"],
  hash_desc: ["hashrate_ths", "desc"],
};

const sortLabels = {
  decision: "Decisao",
  platform: "Plataforma",
  id: "ID",
  gpu: "GPU",
  gpu_count: "Qtd",
  pool: "Pool",
  hashrate_ths: "TH/s",
  history_seen: "Ja pegou?",
  history_count: "Pegas",
  history_avg_ths: "TH/s real med.",
  revenue_usd_hr: "Receita/h",
  revenue_usd_day: "Receita/dia",
  price_usd_hr: "Custo/h",
  max_safe_price_usd_hr: "Teto/h",
  cost_usd_day: "Custo/dia",
  profit_usd_hr: "Lucro/h",
  profit_usd_day: "Lucro/dia",
  roi_pct: "ROI",
  reliability: "Rel.",
  country: "Pais",
};

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

function reliabilityLabel(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const number = Number(value);
  const pctValue = number <= 1 ? number * 100 : number;
  return `${fmtNum(pctValue, 1)}%`;
}

function dateLabel(ts) {
  if (!ts) return "-";
  return new Date(Number(ts) * 1000).toLocaleString();
}

function ageLabel(source) {
  if (!source || source.age_s === null) return "sem dados";
  return source.fallback ? `${source.age_s}s cache` : `${source.age_s}s`;
}

function renderSources(status) {
  $("sources").innerHTML = Object.entries(status)
    .map(([key, value]) => {
      const name = key.replace("monitor:", "");
      const cls = value.ok ? "ok" : "bad";
      return `<span class="source ${cls}">${name} ${ageLabel(value)}</span>`;
    })
    .join("");
}

function renderNetwork(network) {
  const priceSource = network.fallback
    ? `${network.price_source || "-"} cache ${fmtEta(network.fallback_age_s)}`
    : (network.price_source || "-");
  $("network").innerHTML = `
    <article><span>PRL</span><strong>${money(network.prl_price_usd)}</strong><em>${priceSource}</em></article>
    <article><span>Rede</span><strong>${fmtNum(network.network_hashrate_ehs, 2)} EH/s</strong><em>${fmtNum(network.network_hashrate_ths, 0)} TH/s</em></article>
    <article><span>Difficulty</span><strong>${fmtNum(network.difficulty, 0)}</strong><em>height ${network.best_block_height || "-"}</em></article>
    <article><span>Blocos/dia</span><strong>${fmtNum(network.blocks_per_day, 1)}</strong><em>reward ${fmtNum(network.reward_per_block, 2)} PRL</em></article>
    <article><span>Akoya $/TH/dia</span><strong>${money(network.usd_per_th_per_day?.akoya)}</strong><em>base conservadora</em></article>
    <article><span>Alpha $/TH/dia</span><strong>${money(network.usd_per_th_per_day?.alphamine)}</strong><em>5% + dev fee</em></article>
  `;
}

function renderOperation(operation) {
  $("operationStatus").textContent = operation.ok ? "online" : "sem dados";
  $("operationStatus").className = operation.ok ? "pill green" : "pill red";
  const totals = operation.online_totals || {};
  const providerTotals = operation.provider_totals || {};
  $("operation").innerHTML = `
    <article><span>Workers</span><strong>${operation.online_worker_count}/${operation.worker_count}</strong></article>
    <article><span>Hash real</span><strong>${fmtNum(operation.total_hashrate_ths, 2)} TH/s</strong></article>
    <article><span>Todos lucro/dia</span><strong class="${profitClass(totals.online_profit_usd_day)}">${money(totals.online_profit_usd_day)}</strong><em>${money(totals.online_profit_usd_hr)}/h</em></article>
    <article><span>PRL/dia bruto</span><strong>${fmtNum(totals.online_gross_prl_day, 4)} PRL</strong><em>antes do custo</em></article>
    <article><span>PRL/dia liquido</span><strong class="${profitClass(totals.online_net_prl_day)}">${fmtNum(totals.online_net_prl_day, 4)} PRL</strong><em>depois do custo</em></article>
    <article><span>Custo GPUs</span><strong>${money(totals.online_cost_usd_hr)}/h</strong><em>${money(totals.online_cost_usd_day)}/dia</em></article>
    ${renderProviderTotalsCard("Vast", providerTotals.vastai)}
    ${renderProviderTotalsCard("Clore", providerTotals.clore)}
    <article><span>Saldo pendente</span><strong>${fmtNum(operation.pending_balance_prl, 4)} PRL</strong></article>
    <article><span>Stale 24h</span><strong>${pct(operation.stale_rate24h_pct)}</strong></article>
  `;
  const workers = operation.workers || [];
  const onlineProfit = workers.filter((worker) => worker.is_connected && Number(worker.profit_usd_hr || 0) >= 0);
  const onlineLoss = workers.filter((worker) => worker.is_connected && Number(worker.profit_usd_hr || 0) < 0);
  const sections = [
    renderWorkerSection("Online lucrativo", onlineProfit),
    renderWorkerSection("Online sem lucro", onlineLoss),
  ].join("");
  $("workers").innerHTML = sections || `<tr><td colspan="20">Nenhum worker online.</td></tr>`;
}

function renderProviderTotalsCard(label, totals = {}) {
  return `
    <article>
      <span>${label} online</span>
      <strong class="${profitClass(totals.online_profit_usd_day)}">${money(totals.online_profit_usd_day)}/dia</strong>
      <em>${totals.online_worker_count || 0} workers | ${fmtNum(totals.total_hashrate_ths, 1)} TH/s | rec ${money(totals.online_revenue_usd_hr)}/h | custo ${money(totals.online_cost_usd_hr)}/h</em>
    </article>
  `;
}

function renderWorkerSection(label, rows) {
  if (!rows.length) return "";
  return `
    <tr class="section-row"><td colspan="20">${label}</td></tr>
    ${rows.map(renderWorkerRow).join("")}
  `;
}

function renderVastControl(vast) {
  const counts = vast.counts || {};
  $("vastSummary").textContent =
    `modo ${vast.mode || "-"} | ativos ${vast.active_count || 0} | ` +
    `alugados ${counts.rented || 0}, minerando ${counts.active || 0}, falhas ${counts.failed || 0} | ` +
    `blacklist ${window.lastBlacklistCount || 0} | disk ${fmtNum(vast.default_disk_gb, 0)} GB`;
  $("vastControl").innerHTML = `
    <article><span>Ativos locais</span><strong>${vast.active_count || 0}</strong><em>sincronizado com Vast</em></article>
    <article><span>Minerando</span><strong>${counts.active || 0}</strong><em>worker online</em></article>
    <article><span>Alugadas</span><strong>${counts.rented || 0}</strong><em>aguardando/rodando</em></article>
    <article><span>Falhas</span><strong>${counts.failed || 0}</strong><em>historico local</em></article>
    <article><span>Arquivadas</span><strong>${counts.archived || 0}</strong><em>nao contam limite</em></article>
    <article><span>Disk proximo aluguel</span><strong>${fmtNum(vast.default_disk_gb, 0)} GB</strong><em>VAST_INSTANCE_DISK_GB</em></article>
  `;
  $("vastActions").innerHTML = (vast.items || []).slice(0, 12).map(renderVastActionRow).join("");
  renderAkoyaUpdates(vast.pool_updates || vast.akoya_updates || []);
}

function renderCloreControl(clore) {
  const counts = clore.counts || {};
  const wallets = clore.wallets || {};
  const currencyOrder = clore.currency_order || [];
  const coinLabel = currencyOrder.join(", ") || "-";
  $("cloreSummary").textContent =
    `modo ${clore.mode || "-"} | alugadas ${counts.rented || 0}, minerando ${counts.active || 0}, falhas ${counts.failed || 0}, blacklist ${counts.blacklisted || 0} | moedas ${coinLabel}`;
  $("cloreControl").innerHTML = `
    <article><span>Configurado</span><strong>${clore.configured ? "sim" : "nao"}</strong><em>CLORE_API_KEY</em></article>
    <article><span>Saldo CLORE</span><strong>${fmtNum(wallets.clore_balance, 4)}</strong><em>CLORE-Blockchain</em></article>
    <article><span>Saldo USD</span><strong>${money(wallets.usd_balance)}</strong><em>USD-Blockchain</em></article>
    <article><span>Minerando</span><strong>${counts.active || 0}</strong><em>worker online</em></article>
    <article><span>Alugadas</span><strong>${counts.rented || 0}</strong><em>orders abertas</em></article>
    <article><span>Falhas</span><strong>${counts.failed || 0}</strong><em>historico local</em></article>
    <article><span>Blacklist</span><strong>${counts.blacklisted || 0}</strong><em>Scout Clore</em></article>
    <article><span>Watch</span><strong>${counts.watching || 0}</strong><em>realugar se voltar</em></article>
    <article><span>Canceladas</span><strong>${counts.cancelled || 0}</strong><em>cancel_order</em></article>
    <article><span>Moedas</span><strong>${currencyOrder[0] || "-"}</strong><em>${coinLabel}</em></article>
  `;
  $("cloreActions").innerHTML = (clore.items || []).slice(0, 18).map(renderCloreActionRow).join("") || `
    <tr><td colspan="15">Sem tentativas Clore registradas.</td></tr>
  `;
}

function renderCloreActionRow(action) {
  const state = actionLabels[action.runtime_state] || actionLabels[action.state] || action.state || "-";
  const pillClass =
    action.runtime_state === "active" ? "green" :
    action.state === "blacklisted" ? "red" :
    action.state === "failed" ? "red" :
    action.state === "watching" ? "yellow" :
    action.state === "renting" ? "yellow" :
    action.state === "rented" ? "alert" :
    action.state === "cancelled" ? "gray" : "gray";
  const deploy = action.clore_online === true ? "order online" : (action.clore_online === false ? "order offline" : "");
  const detail = [action.error, action.reason, action.order_sync_error, deploy].filter(Boolean).join(" | ") || "-";
  return `
    <tr>
      <td>${action.server_id || "-"}</td>
      <td>${action.order_id || "-"}</td>
      <td>${fmtEta(action.clore_order_mrl_seconds)}</td>
      <td>${fmtEta(action.clore_order_time_left_seconds)}</td>
      <td>${dateLabel(action.clore_order_expires_at)}</td>
      <td><span class="pill ${pillClass}">${state}</span></td>
      <td>${action.worker_name || "-"}</td>
      <td>${poolLabel(action.pool_strategy)}</td>
      <td>${action.gpu || "-"} x${action.gpu_count || "-"}</td>
      <td>${money(action.price_usd_hr)}</td>
      <td>${action.currency || "-"}</td>
      <td>${fmtNum(action.worker_hashrate_ths, 2)}</td>
      <td>${shortText(action.image, 42)}</td>
      <td>${shortText(detail, 160)}</td>
      <td>${renderCloreRowActions(action)}</td>
    </tr>
  `;
}

function renderCloreRowActions(action) {
  if (!action.server_id || !["renting", "rented"].includes(action.state)) return "-";
  return `<button class="action-button danger" data-clore-cancel-server-id="${action.server_id}" data-worker-name="${action.worker_name || action.server_id}" data-order-id="${action.order_id || ""}">Cancelar</button>`;
}

function renderAkoyaUpdates(rows) {
  const improved = rows.filter((row) => row.status === "melhorou" || Number(row.delta_hashrate_ths || 0) > 0).length;
  $("akoyaUpdatesSummary").textContent = rows.length
    ? `${rows.length} comparativos | ${improved} melhoraram`
    : "nenhum comparativo de pool registrado ainda";
  $("akoyaUpdates").innerHTML = rows.length ? rows.map(renderAkoyaUpdateRow).join("") : `
    <tr><td colspan="14">Sem trocas ou atualizacoes manuais ainda.</td></tr>
  `;
}

function renderAkoyaUpdateRow(row) {
  const deltaClass = Number(row.delta_hashrate_ths || 0) >= 0 ? "positive" : "negative";
  const profitDeltaClass = Number(row.delta_profit_usd_hr || 0) >= 0 ? "positive" : "negative";
  const status = row.status || (row.worker_connected ? "online" : "aguardando");
  const statusClass = row.status_class || (row.worker_connected ? "green" : "yellow");
  return `
    <tr>
      <td>${row.ask_id || "-"}</td>
      <td>${row.instance_id || "-"}</td>
      <td>${row.worker_name || "-"}</td>
      <td>${row.gpu || "-"} x${row.gpu_count || "-"}</td>
      <td>${poolLabel(row.from_pool)}</td>
      <td>${poolLabel(row.current_pool || row.to_pool)}</td>
      <td>${fmtNum(row.before_hashrate_ths, 2)}</td>
      <td>${fmtNum(row.current_hashrate_ths, 2)}</td>
      <td class="${deltaClass}">${fmtNum(row.delta_hashrate_ths, 2)}</td>
      <td class="${deltaClass}">${pct(row.delta_pct)}</td>
      <td>${money(row.before_profit_usd_hr)}</td>
      <td>${money(row.current_profit_usd_hr)}</td>
      <td class="${profitDeltaClass}">${money(row.delta_profit_usd_hr)}</td>
      <td>${dateLabel(row.updated_at)}</td>
      <td>${shortText(row.target_image, 48)}</td>
      <td><span class="pill ${statusClass}">${status}</span></td>
    </tr>
  `;
}

function renderVastActionRow(action) {
  const state = actionLabels[action.runtime_state] || actionLabels[action.state] || action.state || "-";
  const pillClass =
    action.runtime_state === "instance_error" ? "red" :
    action.runtime_state === "active" ? "green" :
    action.state === "failed" ? "red" :
    action.state === "renting" ? "yellow" :
    action.state === "rented" ? "alert" : "gray";
  return `
    <tr>
      <td>${action.ask_id || "-"}</td>
      <td>${action.instance_id || "-"}</td>
      <td><span class="pill ${pillClass}">${state}</span></td>
      <td>${action.worker_name || "-"}</td>
      <td>${poolLabel(action.pool_strategy)}</td>
      <td>${action.gpu || "-"} x${action.gpu_count || "-"}</td>
      <td>${money(action.price_usd_hr)}</td>
      <td>${money(action.max_safe_price_usd_hr)}</td>
      <td>${fmtNum(action.worker_hashrate_ths, 2)}</td>
      <td>${action.error || action.reason || "-"}</td>
      <td>${renderVastRowActions(action)}</td>
    </tr>
  `;
}

function renderVastRowActions(action) {
  if (action.state === "archived") return "-";
  if (!action.ask_id) return "-";
  const recycle = action.instance_id
    ? `<button class="action-button" data-vast-recycle-ask-id="${action.ask_id}" data-worker-name="${action.worker_name || action.ask_id}" data-instance-id="${action.instance_id}">Recycle</button>`
    : "";
  return `
    ${recycle}
    <button class="action-button danger" data-blacklist-ask-id="${action.ask_id}">Blacklist</button>
    <button class="action-button quiet" data-archive-ask-id="${action.ask_id}">Arquivar</button>
  `;
}

function fmtEta(seconds) {
  if (!seconds) return "-";
  const m = Math.floor(seconds / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}

function renderWorkerRow(worker) {
  const status = worker.is_connected ? "online" : "offline";
  return `
    <tr>
      <td>${worker.worker_name}</td>
      <td>${poolLabel(worker.pool)}</td>
      <td>${providerLabel(worker.provider)}</td>
      <td>${workerOfferId(worker)}</td>
      <td>${workerInstanceId(worker)}</td>
      <td>${renderWorkerGpu(worker)}</td>
      <td><span class="pill ${worker.is_connected ? "green" : "red"}">${status}</span></td>
      <td>${fmtNum(worker.hashrate_ths, 2)}</td>
      <td>${fmtNum(worker.hashrate_live_ths, 2)}</td>
      <td>${fmtNum(worker.hashrate_1h_ths, 2)}</td>
      <td>${fmtNum(worker.hashrate_24h_ths, 2)}</td>
      <td>${fmtNum(worker.difficulty, 0)}</td>
      <td>${money(worker.revenue_usd_hr)}</td>
      <td>${money(worker.revenue_usd_day)}</td>
      <td>${money(worker.cost_usd_hr)}</td>
      <td>${money(worker.cost_usd_day)}</td>
      <td class="${profitClass(worker.profit_usd_hr)}">${money(worker.profit_usd_hr)}</td>
      <td class="${profitClass(worker.profit_usd_day)}">${money(worker.profit_usd_day)}</td>
      <td>${renderRisks(worker.risks)}</td>
      <td>${renderWorkerActions(worker)}</td>
    </tr>
  `;
}

function providerLabel(provider) {
  if (provider === "Vast.ai" || provider === "vastai") return "Vast";
  if (provider === "Clore" || provider === "clore") return "Clore";
  return provider || "-";
}

function workerOfferId(worker) {
  if (worker.server_id) return worker.server_id;
  if (worker.ask_id) return worker.ask_id;
  return "-";
}

function workerInstanceId(worker) {
  if (worker.clore_order_id) return worker.clore_order_id;
  if (worker.vast_instance_id) return worker.vast_instance_id;
  return "-";
}

function renderWorkerActions(worker) {
  if (worker.clore_order_id || worker.server_id) {
    const serverId = worker.server_id;
    return `<button class="action-button danger" data-clore-cancel-server-id="${serverId}" data-worker-name="${worker.worker_name}" data-order-id="${worker.clore_order_id || ""}">Cancelar Clore</button>`;
  }
  if (!worker.vast_instance_id || !worker.ask_id) return "-";
  const updateAkoya = worker.pool === "akoya"
    ? `<button class="action-button" data-worker-update-akoya-ask-id="${worker.ask_id}" data-worker-name="${worker.worker_name}" data-instance-id="${worker.vast_instance_id}">Atualizar Akoya</button>`
    : "";
  const targetPool = worker.pool === "akoya" ? "alphamine" : worker.pool === "alphamine" ? "akoya" : "";
  const switchPool = targetPool
    ? `<button class="action-button" data-worker-switch-pool-ask-id="${worker.ask_id}" data-worker-name="${worker.worker_name}" data-instance-id="${worker.vast_instance_id}" data-target-pool="${targetPool}">Trocar para ${poolLabel(targetPool)}</button>`
    : "";
  return `
    ${updateAkoya}
    ${switchPool}
    <button class="action-button" data-vast-recycle-ask-id="${worker.ask_id}" data-worker-name="${worker.worker_name}" data-instance-id="${worker.vast_instance_id}">Recycle</button>
    <button class="action-button danger" data-worker-destroy-ask-id="${worker.ask_id}" data-worker-name="${worker.worker_name}" data-instance-id="${worker.vast_instance_id}">Destroy</button>
    <button class="action-button quiet" data-blacklist-ask-id="${worker.ask_id}">BL+Destroy</button>
  `;
}

function renderWorkerGpu(worker) {
  const akoyaCount = worker.akoya_gpu_count ?? worker.gpu_count;
  const poolCount = worker.pool_gpu_count ?? worker.gpu_count;
  const rentedCount = worker.rented_gpu_count;
  const suffix = worker.gpu_suffix ? ` ${worker.gpu_suffix}` : "";
  if (rentedCount && rentedCount !== poolCount) {
    return `${worker.gpu}${suffix} ${poolLabel(worker.pool)} x${poolCount} / Placas x${rentedCount}`;
  }
  return `${worker.gpu}${suffix} x${poolCount}`;
}

function poolLabel(pool) {
  if (pool === "alphamine") return "AlphaMine";
  if (pool === "akoya") return "Akoya";
  return pool || "-";
}

function profitClass(value) {
  if (value === null || value === undefined) return "";
  return Number(value) >= 0 ? "positive" : "negative";
}

function shortText(value, max = 90) {
  const text = String(value || "-");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function renderSnipers(snipers) {
  const counts = snipers.counts || {};
  const items = snipers.items || [];
  $("snipersSummary").textContent =
    `${counts.total || 0} maquinas novas | fila ${counts.queued || 0}, testando ${counts.testing || 0}, aprovadas ${counts.approved || 0}, encerradas ${counts.failed || 0}`;
  $("snipersCards").innerHTML = `
    <article><span>Novas</span><strong>${counts.total || 0}</strong><em>hardware nunca visto</em></article>
    <article><span>Na fila</span><strong>${counts.queued || 0}</strong><em>prontas p/ pegar</em></article>
    <article><span>Testando</span><strong>${counts.testing || 0}</strong><em>A/B em andamento</em></article>
    <article><span>Aprovados</span><strong>${counts.approved || 0}</strong><em>pool final selado</em></article>
    <article><span>Encerrados</span><strong>${counts.failed || 0}</strong><em>destroy/blacklist/lost</em></article>
  `;
  $("snipersRows").innerHTML = items.slice(0, 30).map(renderSniperRow).join("");
}

function renderSniperRow(item) {
  return `
    <tr>
      <td>${item.ask_id || "-"}</td>
      <td>${item.instance_id || "-"}</td>
      <td><span class="pill ${item.status_class || "gray"}">${item.status || "-"}</span></td>
      <td>${item.gpu || "-"} x${item.gpu_count || "-"}</td>
      <td>${item.host_id || "-"}</td>
      <td>${item.machine_id || "-"}</td>
      <td>${poolLabel(item.pool_current)}</td>
      <td>${money(item.price_usd_hr)}</td>
      <td class="${profitClass(item.akoya_profit_usd_hr)}">${money(item.akoya_profit_usd_hr)}</td>
      <td class="${profitClass(item.alphamine_profit_usd_hr)}">${money(item.alphamine_profit_usd_hr)}</td>
      <td>${poolLabel(item.best_pool)}</td>
      <td>${fmtNum(item.current_hashrate_ths, 2)}</td>
      <td class="${profitClass(item.current_profit_usd_hr)}">${money(item.current_profit_usd_hr)}</td>
      <td>${dateLabel(item.machine_first_seen_at || item.marketplace_first_seen_at)}</td>
      <td>${dateLabel(item.sniped_at)}</td>
      <td>${dateLabel(item.last_seen_at || item.updated_at)}</td>
      <td>${item.decision || "-"}</td>
      <td>${shortText(item.reason)}</td>
    </tr>
  `;
}

function renderSummary(summary) {
  const c = summary.counts || {};
  $("summary").textContent =
    `${summary.total_opportunities || 0} oportunidades disponiveis | ` +
    `${c.green || 0} verdes, ${c.yellow || 0} amarelas, ${c.alert || 0} alertas, ${c.red || 0} vermelhas, ${c.gray || 0} sem calculo`;
}

function platformLabel(platform) {
  return providerLabels[platform] || platform || "-";
}

function renderDecisionControls(items) {
  const providers = ["all", ...Array.from(new Set(items.map((item) => item.platform))).sort()];
  const decisions = ["all", "green", "yellow", "alert", "red", "gray"];
  $("providerFilters").innerHTML = providers.map((provider) => {
    const active = opportunityUi.provider === provider ? "active" : "";
    const count = provider === "all" ? items.length : items.filter((item) => item.platform === provider).length;
    return `<button class="${active}" data-provider-filter="${provider}">${platformLabel(provider)} <em>${count}</em></button>`;
  }).join("");
  $("decisionFilters").innerHTML = decisions.map((decision) => {
    const active = opportunityUi.decision === decision ? "active" : "";
    const label = decision === "all" ? "Todas" : labels[decision] || decision;
    const count = decision === "all" ? items.length : items.filter((item) => item.decision === decision).length;
    return `<button class="${active}" data-decision-filter="${decision}">${label} <em>${count}</em></button>`;
  }).join("");
  $("opportunitySort").value = opportunityUi.sort;
  const gpuOptions = ["all", ...Array.from(new Set(items.map((item) => item.gpu).filter(Boolean))).sort()];
  $("gpuFilter").innerHTML = gpuOptions.map((gpu) => {
    const label = gpu === "all" ? "Todas" : gpu;
    const count = gpu === "all" ? items.length : items.filter((item) => item.gpu === gpu).length;
    const selected = opportunityUi.gpu === gpu ? "selected" : "";
    return `<option value="${gpu}" ${selected}>${label} (${count})</option>`;
  }).join("");
  $("opportunitySearch").value = opportunityUi.search;
}

function filteredOpportunities() {
  const needle = opportunityUi.search.trim().toLowerCase();
  const filtered = opportunityUi.allItems.filter((item) => {
    if (opportunityUi.provider !== "all" && item.platform !== opportunityUi.provider) return false;
    if (opportunityUi.decision !== "all" && item.decision !== opportunityUi.decision) return false;
    if (opportunityUi.gpu !== "all" && item.gpu !== opportunityUi.gpu) return false;
    if (!needle) return true;
    return [
      item.id,
      item.platform,
      item.gpu,
      item.gpu_raw,
      item.pool,
      item.country,
      item.worker_name_preview,
      item.history_last_decision,
      item.history_last_pool,
      ...(item.risks || []),
    ].join(" ").toLowerCase().includes(needle);
  });
  const num = (value, fallback = -999999) =>
    value === null || value === undefined || Number.isNaN(Number(value)) ? fallback : Number(value);
  const text = (value) => String(value ?? "").toLowerCase();
  const key = opportunityUi.sortKey || "profit_usd_hr";
  const dir = opportunityUi.sortDir === "asc" ? 1 : -1;
  filtered.sort((a, b) => {
    const numeric = [
      "gpu_count",
      "hashrate_ths",
      "history_seen",
      "history_count",
      "history_avg_ths",
      "history_best_ths",
      "revenue_usd_hr",
      "revenue_usd_day",
      "price_usd_hr",
      "max_safe_price_usd_hr",
      "cost_usd_day",
      "profit_usd_hr",
      "profit_usd_day",
      "roi_pct",
      "reliability",
    ].includes(key);
    if (key === "decision") {
      const diff = decisionOrder(a.decision) - decisionOrder(b.decision);
      if (diff !== 0) return diff * dir;
    } else if (numeric) {
      const fallback = opportunityUi.sortDir === "asc" ? 999999 : -999999;
      const diff = num(a[key], fallback) - num(b[key], fallback);
      if (diff !== 0) return diff * dir;
    } else {
      const diff = text(a[key]).localeCompare(text(b[key]));
      if (diff !== 0) return diff * dir;
    }
    return num(b.profit_usd_hr) - num(a.profit_usd_hr);
  });
  return filtered;
}

function decisionOrder(value) {
  return { green: 0, yellow: 1, alert: 2, red: 3, gray: 4 }[value] ?? 9;
}

function renderDecisionCalcCards(items) {
  const visible = filteredOpportunities();
  const best = visible.find((item) => item.profit_usd_hr !== null && item.profit_usd_hr !== undefined);
  const green = visible.filter((item) => item.decision === "green").length;
  const yellow = visible.filter((item) => item.decision === "yellow").length;
  const totalProfitDay = visible
    .filter((item) => Number(item.profit_usd_day) > 0)
    .reduce((sum, item) => sum + Number(item.profit_usd_day || 0), 0);
  $("decisionCalcCards").innerHTML = `
    <article><span>Visiveis</span><strong>${visible.length}/${items.length}</strong><em>${platformLabel(opportunityUi.provider)}</em></article>
    <article><span>Verdes / margem</span><strong>${green}/${yellow}</strong><em>apos filtros</em></article>
    <article><span>Melhor lucro/h</span><strong class="${profitClass(best?.profit_usd_hr)}">${money(best?.profit_usd_hr)}</strong><em>${best ? `${platformLabel(best.platform)} ${best.gpu} x${best.gpu_count}` : "-"}</em></article>
    <article><span>Ordenacao</span><strong>${sortLabels[opportunityUi.sortKey] || opportunityUi.sortKey}</strong><em>${opportunityUi.sortDir === "asc" ? "menor para maior" : "maior para menor"}</em></article>
    <article><span>Soma lucro/dia positivo</span><strong class="positive">${money(totalProfitDay)}</strong><em>visivel, nao deduplicado</em></article>
    <article><span>Formula</span><strong>TH/s * $/TH/d / 24 - custo/h</strong><em>pool decide taxa</em></article>
  `;
}

function renderOpportunities(items) {
  opportunityUi.allItems = items;
  if (opportunityUi.provider !== "all" && !items.some((item) => item.platform === opportunityUi.provider)) {
    opportunityUi.provider = "all";
  }
  if (opportunityUi.gpu !== "all" && !items.some((item) => item.gpu === opportunityUi.gpu)) {
    opportunityUi.gpu = "all";
  }
  renderDecisionControls(items);
  renderDecisionCalcCards(items);
  $("opportunities").innerHTML = filteredOpportunities().map(renderOpportunityRow).join("");
  renderSortHeaders();
}

function renderSortHeaders() {
  document.querySelectorAll("[data-sort-key]").forEach((th) => {
    const key = th.getAttribute("data-sort-key");
    const label = sortLabels[key] || th.textContent.replace(/[ ↑↓]$/, "");
    const marker = key === opportunityUi.sortKey ? (opportunityUi.sortDir === "asc" ? " ↑" : " ↓") : "";
    th.textContent = `${label}${marker}`;
    th.classList.toggle("sortable-active", key === opportunityUi.sortKey);
  });
}

function renderGpuSummary(items) {
  $("gpuSummary").innerHTML = items.map(renderGpuSummaryRow).join("");
}

function renderGpuSummaryRow(item) {
  return `
    <tr>
      <td>${item.gpu}</td>
      <td>${item.total}</td>
      <td class="positive">${item.green || 0}</td>
      <td>${item.yellow || 0}</td>
      <td>${item.alert || 0}</td>
      <td>${money(item.min_cost_usd_hr)}</td>
      <td>${money(item.max_cost_profit_usd_hr_per_gpu)}</td>
      <td>${money(item.max_green_cost_usd_hr_per_gpu)}</td>
      <td>${money(item.max_cost_profit_usd_day_per_gpu)}</td>
      <td class="${profitClass(item.best_profit_usd_hr)}">${money(item.best_profit_usd_hr)}</td>
      <td class="${profitClass(item.best_profit_usd_day)}">${money(item.best_profit_usd_day)}</td>
      <td>${pct(item.best_roi_pct)}</td>
      <td>${renderBestOffer(item)}</td>
      <td>${renderBestSearch(item)}</td>
      <td>${item.best_pool || "-"}</td>
      <td>${fmtNum(item.best_hashrate_ths, 1)}</td>
    </tr>
  `;
}

function renderOpportunityRow(item) {
  return `
    <tr class="row-${item.decision}">
      <td><span class="pill ${item.decision}">${labels[item.decision] || item.decision}</span></td>
      <td>${item.platform}</td>
      <td>${item.id}</td>
      <td>${renderAction(item)}</td>
      <td>${renderLink(item)}</td>
      <td>${renderSearchLink(item)}</td>
      <td>${item.gpu}</td>
      <td>${item.gpu_count}</td>
      <td>${item.pool}</td>
      <td>${fmtNum(item.hashrate_ths, 1)}</td>
      <td>${renderHistorySeen(item)}</td>
      <td>${item.history_count || "-"}</td>
      <td title="${historyTitle(item)}">${fmtNum(item.history_avg_ths, 1)}</td>
      <td>${money(item.revenue_usd_hr)}</td>
      <td>${money(item.revenue_usd_day)}</td>
      <td>${money(item.price_usd_hr)}</td>
      <td>${money(item.max_safe_price_usd_hr)}</td>
      <td>${money(item.cost_usd_day)}</td>
      <td class="${profitClass(item.profit_usd_hr)}">${money(item.profit_usd_hr)}</td>
      <td class="${profitClass(item.profit_usd_day)}">${money(item.profit_usd_day)}</td>
      <td>${pct(item.roi_pct)}</td>
      <td title="${item.calc_formula || ""}">${renderCalc(item)}</td>
      <td>${item.worker_name_preview || "-"}</td>
      <td>${item.cuda || "-"}</td>
      <td>${item.pcie || "-"}</td>
      <td>${reliabilityLabel(item.reliability)}</td>
      <td>${item.country || "-"}</td>
      <td>${renderRisks(item.risks)}</td>
    </tr>
  `;
}

function historyTitle(item) {
  if (!item.history_seen) return "sem historico salvo";
  const parts = [
    `pegas ${item.history_count || 0}`,
    `ativas ${item.history_active_count || 0}`,
    `media ${fmtNum(item.history_avg_ths, 1)} TH/s`,
    `melhor ${fmtNum(item.history_best_ths, 1)} TH/s`,
  ];
  if (item.history_best_profit_usd_hr !== null && item.history_best_profit_usd_hr !== undefined) {
    parts.push(`melhor lucro ${money(item.history_best_profit_usd_hr)}/h`);
  }
  if (item.history_last_decision) parts.push(`ult ${item.history_last_decision}`);
  if (item.history_last_at) parts.push(dateLabel(item.history_last_at));
  return parts.join(" | ");
}

function renderHistorySeen(item) {
  const seen = Boolean(item.history_seen);
  const cls = seen ? "yellow" : "gray";
  return `<span class="pill ${cls}" title="${historyTitle(item)}">${seen ? "sim" : "nao"}</span>`;
}

function renderAction(item) {
  const options = item.rent_options || {};
  if ((item.platform === "vastai" || item.platform === "clore") && (options.akoya || options.alphamine)) {
    return ["akoya", "alphamine"].map((strategy) => {
      const option = options[strategy] || { state: "blocked", reason: "sem opcao" };
      const state = option.state || "blocked";
      const reason = option.reason || "";
      const text = item.platform === "clore"
        ? (strategy === "alphamine" ? "Testar AlphaMine via Scout" : "Testar Akoya via Scout")
        : (strategy === "alphamine" ? "Alugar AlphaMine" : "Alugar Akoya");
      if (state === "ready") {
        const attr = item.platform === "clore"
          ? `data-scout-provider="clore" data-scout-offer-id="${item.id}"`
          : `data-ask-id="${item.id}"`;
        return `<button class="action-button" ${attr} data-rent-strategy="${strategy}" title="${reason}">${text}</button>`;
      }
      const cls = state === "rented" ? "green" : state === "failed" ? "red" : state === "renting" ? "yellow" : "gray";
      return `<span class="pill ${cls}" title="${reason}">${strategy === "alphamine" ? "Alpha" : "Akoya"} ${actionLabels[state] || state}</span>`;
    }).join(" ");
  }
  const state = item.action_state || "blocked";
  const label = actionLabels[state] || state;
  const reason = item.action_reason || "";
  const cls = state === "rented" ? "green" : state === "failed" ? "red" : state === "renting" ? "yellow" : "gray";
  const providerNote = item.platform === "runpod" || item.platform === "tensordock" ? "monitorado, aluguel manual/API ainda nao ligado ao Scout" : reason;
  return `<span class="pill ${cls}" title="${providerNote}">${label}</span>`;
}

function renderLink(item) {
  if (!item.rental_url) return "-";
  const label =
    item.platform === "vastai" ? "Vast ask" :
    item.platform === "runpod" ? "RunPod" :
    item.platform === "tensordock" ? "TensorDock" :
    "Clore";
  return `<a class="rent-link" href="${item.rental_url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}

function renderSearchLink(item) {
  if (!item.search_url) return "-";
  const label =
    item.platform === "clore" ? "Busca Clore" :
    item.platform === "runpod" ? "Busca RunPod" :
    item.platform === "tensordock" ? "Busca TensorDock" :
    "Busca Vast";
  return `<a class="rent-link search-link" href="${item.search_url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}

function renderBestOffer(item) {
  if (!item.best_id) return "-";
  if (!item.best_url) return `${item.best_platform} ${item.best_id}`;
  const label =
    item.best_platform === "vastai" ? "Vast ask" :
    item.best_platform === "runpod" ? "RunPod" :
    item.best_platform === "tensordock" ? "TensorDock" :
    "Clore";
  return `<a class="rent-link" href="${item.best_url}" target="_blank" rel="noopener noreferrer">${label} ${item.best_id}</a>`;
}

function renderBestSearch(item) {
  if (!item.best_search_url) return "-";
  const label =
    item.best_platform === "clore" ? "Busca Clore" :
    item.best_platform === "runpod" ? "Busca RunPod" :
    item.best_platform === "tensordock" ? "Busca TensorDock" :
    "Busca Vast";
  return `<a class="rent-link search-link" href="${item.best_search_url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}

function renderCalc(item) {
  if (!item.calc_formula || item.calc_formula === "aguardando preco/rede") return item.calc_formula || "-";
  return `
    <span class="calc-line">${fmtNum(item.hashrate_ths, 1)} TH/s</span>
    <span class="calc-muted">${money(item.revenue_usd_hr)} - ${money(item.price_usd_hr)}</span>
  `;
}

function renderRisks(risks) {
  if (!risks || !risks.length) return "";
  return risks.map((risk) => `<span class="risk">${riskLabels[risk] || risk}</span>`).join(" ");
}

function renderCloreAuto(state) {
  const button = $("cloreAutoToggle");
  const status = $("cloreAutoStatus");
  if (!button || !status) return;
  const scout = state.scout || {};
  const enabled = Boolean(scout.clore_auto_enabled);
  const queue = Object.values(scout.clore_auto_queue || {}).filter((item) => item && typeof item === "object");
  const counts = queue.reduce((acc, item) => {
    const key = item.queue_status || "blocked";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const active = (counts.renting || 0) + (counts.rented || 0);
  const settings = scout.settings || {};
  button.textContent = `AUTOMATICO CLORE ${enabled ? "ON" : "OFF"}`;
  button.classList.toggle("quiet", !enabled);
  button.title = enabled
    ? "Auto Clore ligado: pega candidatos ALUGAR bons e manda para o Scout"
    : "Auto Clore desligado";
  status.textContent = `fila ${counts.queued || 0} | ativos ${active} | cooldown ${counts.cooldown || 0} | min ${money(settings.min_profit_usd_hr)} | max ${money(settings.max_price_usd_hr)}/h`;
  button.onclick = async () => {
    if (!enabled) {
      const ok = window.confirm(
        "Ativar AUTOMATICO CLORE?\n\n" +
        "Ele vai alugar sozinho apenas Clore ALUGAR com CUDA 12.9+, PCIe x8/x16, sem rel/rede ruim, dentro do lucro minimo e preco maximo do Scout."
      );
      if (!ok) return;
    }
    button.disabled = true;
    button.textContent = enabled ? "DESLIGANDO..." : "LIGANDO...";
    try {
      const response = await fetch(enabled ? "/api/scout/clore-auto/pause" : "/api/scout/clore-auto/resume", { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || response.statusText);
      }
      await loadInitial();
    } catch (error) {
      button.textContent = "FALHOU";
      button.title = String(error);
      button.classList.add("failed");
    } finally {
      button.disabled = false;
    }
  };
}

function render(state) {
  window.lastBlacklistCount = state.vast_blacklist?.count || 0;
  renderSources(state.source_status || {});
  renderNetwork(state.network || {});
  renderVastControl(state.vast_actions || { items: [], counts: {} });
  renderCloreControl(state.clore_actions || { items: [], counts: {} });
  renderSnipers(state.snipers || { items: [], counts: {} });
  renderOperation(state.operation || { workers: [] });
  renderSummary(state.summary || {});
  renderCloreAuto(state);
  renderOpportunities(state.opportunities || []);
  renderGpuSummary(state.gpu_summary || []);
  $("connection").textContent = `Atualizado ${new Date((state.generated_at || Date.now() / 1000) * 1000).toLocaleTimeString()}`;
  bindRentButtons();
  bindArchiveButtons();
  bindBlacklistButtons();
  bindWorkerUpdateAkoyaButtons();
  bindWorkerSwitchPoolButtons();
  bindVastRecycleButtons();
  bindWorkerDestroyButtons();
  bindCloreCancelButtons();
}

function initDecisionControls() {
  if (decisionControlsReady) return;
  decisionControlsReady = true;
  document.addEventListener("click", (event) => {
    const providerButton = event.target.closest("[data-provider-filter]");
    if (providerButton) {
      opportunityUi.provider = providerButton.getAttribute("data-provider-filter") || "all";
      renderOpportunities(opportunityUi.allItems);
      return;
    }
    const decisionButton = event.target.closest("[data-decision-filter]");
    if (decisionButton) {
      opportunityUi.decision = decisionButton.getAttribute("data-decision-filter") || "all";
      renderOpportunities(opportunityUi.allItems);
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target && event.target.id === "opportunitySort") {
      opportunityUi.sort = event.target.value;
      const [key, dir] = presetSorts[opportunityUi.sort] || ["profit_usd_hr", "desc"];
      opportunityUi.sortKey = key;
      opportunityUi.sortDir = dir;
      renderOpportunities(opportunityUi.allItems);
    }
    if (event.target && event.target.id === "gpuFilter") {
      opportunityUi.gpu = event.target.value || "all";
      renderOpportunities(opportunityUi.allItems);
    }
  });
  document.addEventListener("click", (event) => {
    const header = event.target.closest("[data-sort-key]");
    if (!header) return;
    const key = header.getAttribute("data-sort-key");
    if (!key) return;
    if (opportunityUi.sortKey === key) {
      opportunityUi.sortDir = opportunityUi.sortDir === "asc" ? "desc" : "asc";
    } else {
      opportunityUi.sortKey = key;
      opportunityUi.sortDir = ["price_usd_hr", "cost_usd_day"].includes(key) ? "asc" : "desc";
    }
    opportunityUi.sort = "custom";
    renderOpportunities(opportunityUi.allItems);
  });
  document.addEventListener("input", (event) => {
    if (event.target && event.target.id === "opportunitySearch") {
      opportunityUi.search = event.target.value;
      renderDecisionCalcCards(opportunityUi.allItems);
      $("opportunities").innerHTML = filteredOpportunities().map(renderOpportunityRow).join("");
    }
  });
}

function bindRentButtons() {
  document.querySelectorAll("[data-ask-id][data-rent-strategy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-ask-id");
      const strategy = button.getAttribute("data-rent-strategy") || "akoya";
      button.disabled = true;
      button.textContent = "Alugando...";
      try {
        const response = await fetch(`/api/vast/rent/${askId}/${strategy}`, { method: "POST" });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Falhou";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
  document.querySelectorAll("[data-scout-provider=\"clore\"][data-scout-offer-id][data-rent-strategy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const serverId = button.getAttribute("data-scout-offer-id");
      const strategy = button.getAttribute("data-rent-strategy") || "akoya";
      const ok = window.confirm(
        `Testar Clore server ${serverId} em ${poolLabel(strategy)} pelo Scout?\n\n` +
        `O dashboard vai revalidar, criar uma ordem on-demand e cancelar se nao houver worker/hash/lucro.`
      );
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Iniciando...";
      try {
        const response = await fetch("/api/scout/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider: "clore", offer_id: Number(serverId), strategy }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Falhou";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindCloreCancelButtons() {
  document.querySelectorAll("[data-clore-cancel-server-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const serverId = button.getAttribute("data-clore-cancel-server-id");
      const orderId = button.getAttribute("data-order-id") || "-";
      const workerName = button.getAttribute("data-worker-name") || serverId;
      const ok = window.confirm(`Cancelar ordem Clore ${orderId} (${workerName})? Isso encerra a ordem na Clore.`);
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Cancelando...";
      try {
        const response = await fetch(`/api/clore/actions/${serverId}/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "Cancelamento manual pela Operacao Pools" }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindArchiveButtons() {
  document.querySelectorAll("[data-archive-ask-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-archive-ask-id");
      button.disabled = true;
      try {
        const response = await fetch(`/api/vast/actions/${askId}/archive`, { method: "POST" });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindBlacklistButtons() {
  document.querySelectorAll("[data-blacklist-ask-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-blacklist-ask-id");
      const ok = window.confirm("Blacklist vai destruir a instancia na Vast e ocultar ofertas futuras desse host/maquina. Continuar?");
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Destroy...";
      try {
        const response = await fetch(`/api/vast/actions/${askId}/blacklist`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "Host com erro CDI/GPU ruim" }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindWorkerDestroyButtons() {
  document.querySelectorAll("[data-worker-destroy-ask-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-worker-destroy-ask-id");
      const instanceId = button.getAttribute("data-instance-id");
      const workerName = button.getAttribute("data-worker-name") || askId;
      const ok = window.confirm(`Destroy Vast instance ${instanceId} (${workerName})? Isso encerra a GPU agora, sem blacklist.`);
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Destroy...";
      try {
        const response = await fetch(`/api/vast/actions/${askId}/destroy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "Destroy manual pela Operacao Pools" }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindWorkerUpdateAkoyaButtons() {
  document.querySelectorAll("[data-worker-update-akoya-ask-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-worker-update-akoya-ask-id");
      const instanceId = button.getAttribute("data-instance-id");
      const workerName = button.getAttribute("data-worker-name") || askId;
      const ok = window.confirm(`Atualizar imagem Akoya e reciclar Vast instance ${instanceId} (${workerName})? A GPU pode ficar offline por alguns minutos.`);
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Atualizando...";
      try {
        const response = await fetch(`/api/vast/actions/${askId}/update-akoya`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "Atualizacao manual Akoya Miner pelo dashboard" }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindVastRecycleButtons() {
  document.querySelectorAll("[data-vast-recycle-ask-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-vast-recycle-ask-id");
      const instanceId = button.getAttribute("data-instance-id");
      const workerName = button.getAttribute("data-worker-name") || askId;
      const ok = window.confirm(
        `Reciclar Vast instance ${instanceId} (${workerName}) sem trocar imagem/template?\n\n` +
        `Se continuar offline, o dashboard tenta novamente a cada 3 min.`
      );
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Recycle...";
      try {
        const response = await fetch(`/api/vast/actions/${askId}/recycle`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "Recycle manual pela Operacao Pools" }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindWorkerSwitchPoolButtons() {
  document.querySelectorAll("[data-worker-switch-pool-ask-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const askId = button.getAttribute("data-worker-switch-pool-ask-id");
      const instanceId = button.getAttribute("data-instance-id");
      const workerName = button.getAttribute("data-worker-name") || askId;
      const targetPool = button.getAttribute("data-target-pool") || "";
      const ok = window.confirm(
        `Trocar ${workerName} para ${poolLabel(targetPool)} via Vast update_template + recycle?\n\n` +
        `Instance ${instanceId} sera preservada. Nao vai destruir nem liberar a VPS. ` +
        `O miner pode ficar offline por alguns minutos.`
      );
      if (!ok) return;
      button.disabled = true;
      button.textContent = "Trocando...";
      try {
        const response = await fetch(`/api/vast/actions/${askId}/switch-pool`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_pool: targetPool,
            reason: `Troca manual para ${poolLabel(targetPool)} pelo dashboard`,
          }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadInitial();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

async function loadInitial() {
  const response = await fetch("/api/state");
  render(await response.json());
}

function connectWs() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws`);
  ws.onopen = () => {
    $("connection").textContent = "WebSocket conectado";
  };
  ws.onmessage = (event) => {
    render(JSON.parse(event.data));
  };
  ws.onclose = () => {
    $("connection").textContent = "WebSocket desconectado, tentando reconectar...";
    setTimeout(connectWs, 2000);
  };
}

initDecisionControls();
loadInitial().catch((error) => {
  $("connection").textContent = `Erro ao carregar estado: ${error}`;
});
connectWs();
