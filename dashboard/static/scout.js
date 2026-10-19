const $ = (id) => document.getElementById(id);
let settingsTimer = null;
const riskLabels = {
  cuda_below_12_9: "cuda<12.9",
  cuda_unknown: "cuda?",
  pcie_unknown: "pcie?",
  pcie_below_rule: "pcie baixo",
  reliability_low: "rel baixa",
  reliability_watch: "rel media",
  network_bad: "rede ruim",
  network_watch: "rede media",
  low_value_gpu: "low-value",
  clore_cache_risk: "cache Clore",
  clore_unverified: "Clore nao verif.",
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

function fmtEta(seconds) {
  if (!seconds) return "-";
  const value = Math.max(0, Number(seconds));
  const m = Math.floor(value / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}

function poolLabel(pool) {
  if (pool === "alphamine") return "AlphaMine";
  if (pool === "akoya") return "Akoya";
  return pool || "-";
}

function providerLabel(provider) {
  if (provider === "clore") return "Clore";
  if (provider === "vastai" || !provider) return "Vast";
  return provider;
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

function testOfferId(item) {
  return item.offer_id || item.server_id || item.ask_id || "-";
}

function testInstanceId(item) {
  return item.order_id || item.instance_id || "-";
}

function dateLabel(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function profitClass(value) {
  if (value === null || value === undefined) return "";
  return Number(value) >= 0 ? "positive" : "negative";
}

function decisionClass(value) {
  if (value === "keep") return "green";
  if (value === "destroy" || value === "blacklist" || value === "failed") return "red";
  if (value === "switch_pool" || value === "no_worker" || value === "offline") return "yellow";
  return "gray";
}

function pct(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${fmtNum(Number(value) * 100, digits)}%`;
}

function queueClass(status) {
  if (status === "queued" || status === "rented") return "green";
  if (status === "renting" || status === "cooldown") return "yellow";
  if (status === "lost" || status === "blocked") return "red";
  return "gray";
}

function shortText(value, fallback = "-") {
  const text = value === null || value === undefined || value === "" ? fallback : String(value);
  return text.length > 80 ? `${text.slice(0, 77)}...` : text;
}

function escapeAttr(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function riskText(risks) {
  if (!risks || !risks.length) return "";
  return risks.map((risk) => riskLabels[risk] || risk).join(", ");
}

function reliabilityLabel(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const number = Number(value);
  const pctValue = number <= 1 ? number * 100 : number;
  return `${fmtNum(pctValue, 1)}%`;
}

function costSpent(test) {
  const elapsed = Number(test.elapsed_s || 0);
  const cost = Number(test.price_usd_hr || 0) * elapsed / 3600;
  return cost;
}

function renderCards(data) {
  const summary = data.summary || {};
  const settings = data.settings || {};
  $("scoutSummary").textContent =
    `${summary.enabled ? "auto ativo" : "auto pausado"} | ` +
    `${summary.active || 0}/${summary.max_parallel_tests || settings.max_parallel_tests || 10} ativos | ` +
    `minimo ${money(summary.min_profit_usd_hr)}/h | ${summary.test_minutes || 30} min por pool`;
  syncSettingInput("maxParallelTests", settings.max_parallel_tests || 10);
  syncSettingInput("minProfitHr", settings.min_profit_usd_hr || 0.2);
  syncSettingInput("testMinutes", Math.round(Number(settings.test_seconds || 1800) / 60));
  syncSettingInput("workerTimeoutMinutes", Math.round(Number(settings.worker_timeout_seconds || 900) / 60));
  syncSettingInput("maxPriceHr", settings.max_price_usd_hr || 3);
  $("scoutCards").innerHTML = `
    <article><span>Auto</span><strong>${summary.enabled ? "ON" : "OFF"}</strong><em>controla novos testes</em></article>
    <article><span>Ativos</span><strong>${summary.active || 0}/${summary.max_parallel_tests || settings.max_parallel_tests || 10}</strong><em>rodando agora</em></article>
    <article><span>Fila Scout</span><strong>${(summary.queue || {}).queued || 0}</strong><em>prontos/retry real</em></article>
    <article><span>Janela</span><strong>${fmtEta(settings.test_seconds || 1800)}</strong><em>por pool</em></article>
    <article><span>Sem worker</span><strong>${fmtEta(settings.worker_timeout_seconds || 600)}</strong><em>troca/destroy</em></article>
    <article><span>Lucro minimo</span><strong>${money(settings.min_profit_usd_hr || 0.2)}/h</strong><em>manter</em></article>
    <article><span>Preco max</span><strong>${money(settings.max_price_usd_hr || 3)}/h</strong><em>entrada Scout</em></article>
    <article><span>Hash minimo</span><strong>${fmtNum((settings.min_hash_ratio || 0.45) * 100, 0)}%</strong><em>do esperado</em></article>
    <article><span>CUDA min</span><strong>12.9+</strong><em>filtro duro</em></article>
    <article><span>PCIe min</span><strong>x8/x16</strong><em>filtro duro</em></article>
    <article><span>A/B Pool</span><strong>${settings.pool_switch_mode || "in_place_ab"}</strong><em>sem perder GPU</em></article>
  `;
}

function syncSettingInput(id, value) {
  const input = $(id);
  if (!input || document.activeElement === input) return;
  input.value = value;
}

async function saveSettings() {
  const payload = {
    max_parallel_tests: Number($("maxParallelTests").value || 10),
    min_profit_usd_hr: Number($("minProfitHr").value || 0.2),
    test_minutes: Number($("testMinutes").value || 30),
    worker_timeout_minutes: Number($("workerTimeoutMinutes").value || 15),
    max_price_usd_hr: Number($("maxPriceHr").value || 3),
  };
  $("settingsSaved").textContent = "salvando...";
  const response = await fetch("/api/scout/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  $("settingsSaved").textContent = response.ok ? "salvo" : "erro ao salvar";
  if (response.ok) await load();
}

function scheduleSettingsSave() {
  clearTimeout(settingsTimer);
  $("settingsSaved").textContent = "alterado";
  settingsTimer = setTimeout(() => {
    saveSettings().catch((error) => {
      $("settingsSaved").textContent = `erro: ${error}`;
    });
  }, 500);
}

function renderActiveRow(test) {
  const ratio = test.latest_hash_ratio === null || test.latest_hash_ratio === undefined
    ? "-"
    : `${fmtNum(Number(test.latest_hash_ratio) * 100, 1)}%`;
  const diagnostics = [
    test.cuda ? `CUDA ${test.cuda}` : "",
    test.pcie ? `PCIe ${test.pcie}` : "",
    test.reliability !== undefined ? `rel ${reliabilityLabel(test.reliability)}` : "",
    riskText(test.risks),
  ].filter(Boolean).join(" | ");
  return `
    <tr>
      <td>${test.test_id || "-"}</td>
      <td>${providerLabel(test.provider)}</td>
      <td>${testOfferId(test)}</td>
      <td>${testInstanceId(test)}</td>
      <td title="${escapeAttr(sourceDetail(test))}">${sourceLabel(test)}${test.source === "auto_clore" ? ` / ${decisionLabel(test.auto_decision || test.opportunity_decision)}` : ""}</td>
      <td>${poolLabel(test.pool_strategy)}</td>
      <td title="${escapeAttr(diagnostics)}">${test.gpu || "-"} x${test.gpu_count || "-"}</td>
      <td>${test.cuda || "-"}</td>
      <td>${test.pcie || "-"}</td>
      <td>${reliabilityLabel(test.reliability)}</td>
      <td>${shortText(riskText(test.risks), "-")}</td>
      <td>${fmtEta(test.remaining_s)}</td>
      <td>${fmtNum(test.latest_hashrate_ths, 2)}</td>
      <td>${fmtNum(test.expected_ths, 2)}</td>
      <td>${ratio}</td>
      <td class="${profitClass(test.latest_profit_usd_hr)}">${money(test.latest_profit_usd_hr)}</td>
      <td>${money(costSpent(test))}</td>
      <td title="${escapeAttr(diagnostics)}">${test.next_action || test.reason || test.decision || "-"}</td>
      <td>
        <button class="action-button danger" data-destroy-test="${test.test_id}">${test.provider === "clore" ? "Cancelar" : "Destroy"}</button>
        <button class="action-button quiet" data-stop-test="${test.test_id}">Parar</button>
      </td>
    </tr>
  `;
}

function renderQueueRow(item) {
  const previous = item.previous_result_summary || {};
  const previousLabel = previous.count
    ? `${previous.quality || "-"} ${money(previous.best_profit_usd_hr)}/h ${pct(previous.best_hash_ratio)}`
    : "-";
  return `
    <tr>
      <td><span class="pill ${queueClass(item.queue_status)}">${item.queue_status || "-"}</span></td>
      <td>${item.ask_id || "-"}</td>
      <td>${item.gpu || "-"}</td>
      <td>${item.gpu_count || "-"}</td>
      <td>${money(item.price_usd_hr)}</td>
      <td class="${profitClass(item.profit_usd_hr)}">${money(item.profit_usd_hr)}</td>
      <td>${fmtNum(item.roi_pct, 1)}%</td>
      <td>${fmtNum(item.priority_score, 1)}</td>
      <td>${item.pcie || "-"}</td>
      <td>${fmtNum(item.net_down_mbps, 0)}/${fmtNum(item.net_up_mbps, 0)}</td>
      <td>${reliabilityLabel(item.reliability)}</td>
      <td>${item.host_id || "-"}</td>
      <td>${item.machine_id || "-"}</td>
      <td>${item.is_new_machine ? "sim" : "nao"}</td>
      <td>${dateLabel(item.machine_first_seen_at || item.first_seen_at)}</td>
      <td>${dateLabel(item.last_seen_at)}</td>
      <td>${item.is_new_machine ? "sniper novo" : "radar/reteste"}</td>
      <td>${item.retest_allowed ? "sim" : "nao"}</td>
      <td>${item.retry_attempts || "-"}</td>
      <td>${dateLabel(item.next_retry_at)}</td>
      <td>${shortText(item.skip_reason || item.retest_reason || previousLabel)}</td>
    </tr>
  `;
}

function renderHistoryRow(item) {
  const allResults = [...(item.prior_results || []), item].filter((result) => result && result.pool_strategy);
  const measuredResults = allResults.filter((result) => result.decision === "pool_measured");
  const results = measuredResults.length ? measuredResults : allResults;
  const poolResult = (pool) => [...results].reverse().find((result) => result.pool_strategy === pool) || {};
  const akoya = poolResult("akoya");
  const alpha = poolResult("alphamine");
  const akoyaProfit = akoya.profit_usd_hr === undefined ? null : Number(akoya.profit_usd_hr);
  const alphaProfit = alpha.profit_usd_hr === undefined ? null : Number(alpha.profit_usd_hr);
  const diff = akoyaProfit === null || alphaProfit === null ? null : alphaProfit - akoyaProfit;
  let bestPool = "-";
  if (akoyaProfit !== null || alphaProfit !== null) {
    bestPool = (alphaProfit ?? -Infinity) > (akoyaProfit ?? -Infinity) ? "AlphaMine" : "Akoya";
  }
  const previous = item.previous_result_summary || {};
  const previousLabel = previous.count
    ? `${previous.quality || "-"} ${money(previous.best_profit_usd_hr)}/h ${pct(previous.best_hash_ratio)}`
    : "-";
  return `
    <tr>
      <td>${dateLabel(item.ended_at)}</td>
      <td>${providerLabel(item.provider)}</td>
      <td>${testOfferId(item)}</td>
      <td>${testInstanceId(item)}</td>
      <td title="${escapeAttr(sourceDetail(item))}">${sourceLabel(item)}${item.source === "auto_clore" ? ` / ${decisionLabel(item.auto_decision || item.opportunity_decision)}` : ""}</td>
      <td>${item.gpu || "-"}</td>
      <td>${item.gpu_count || "-"}</td>
      <td>${item.cuda || "-"}</td>
      <td>${item.pcie || "-"}</td>
      <td>${reliabilityLabel(item.reliability)}</td>
      <td>${shortText(riskText(item.risks), "-")}</td>
      <td>${item.host_id || "-"}</td>
      <td>${item.machine_id || "-"}</td>
      <td>${money(item.price_usd_hr)}</td>
      <td>${fmtNum(akoya.live_ths_avg, 2)}</td>
      <td class="${profitClass(akoya.profit_usd_hr)}">${money(akoya.profit_usd_hr)}</td>
      <td>${pct(akoya.hash_ratio)}</td>
      <td>${fmtNum(alpha.live_ths_avg, 2)}</td>
      <td class="${profitClass(alpha.profit_usd_hr)}">${money(alpha.profit_usd_hr)}</td>
      <td>${pct(alpha.hash_ratio)}</td>
      <td class="${profitClass(diff)}">${money(diff)}</td>
      <td>${bestPool}</td>
      <td><span class="pill ${decisionClass(item.decision)}">${item.decision || "-"}</span></td>
      <td>${item.retest_allowed === undefined ? "-" : item.retest_allowed ? "sim" : "nao"}</td>
      <td>${shortText(item.retest_reason)}</td>
      <td>${previousLabel}</td>
      <td>${shortText(item.improvement_summary)}</td>
      <td>${renderHistoryActions(item)}</td>
    </tr>
  `;
}

function renderHistoryActions(item) {
  const reason = item.reason || "-";
  const nextPool = item.manual_next_pool_strategy;
  if (item.provider !== "clore" || !nextPool || item.decision === "keep") return reason;
  return `
    ${shortText(reason)}
    <button class="action-button" data-scout-provider="clore" data-scout-offer-id="${testOfferId(item)}" data-rent-strategy="${nextPool}">
      Testar ${poolLabel(nextPool)}
    </button>
  `;
}

function bindButtons() {
  ["maxParallelTests", "minProfitHr", "testMinutes", "workerTimeoutMinutes", "maxPriceHr"].forEach((id) => {
    const input = $(id);
    if (input && !input.dataset.bound) {
      input.dataset.bound = "1";
      input.addEventListener("input", scheduleSettingsSave);
      input.addEventListener("change", scheduleSettingsSave);
    }
  });
  $("resumeScout").onclick = async () => {
    await fetch("/api/scout/resume", { method: "POST" });
    await load();
  };
  $("pauseScout").onclick = async () => {
    await fetch("/api/scout/pause", { method: "POST" });
    await load();
  };
  $("clearScoutHistory").onclick = async () => {
    if (!confirm("Resetar Scout do zero? Isso apaga historico/testes anteriores e destrói testes Scout ativos.")) return;
    const button = $("clearScoutHistory");
    button.disabled = true;
    const response = await fetch("/api/scout/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        destroy_active: true,
        destroy_all_active_except_preserved: true,
        preserve_instance_ids: [38283931],
        preserve_ask_ids: [34912849],
        archive_history: true,
        clear_vast_history: true,
        clear_vast_blacklist: true,
      }),
    });
    const body = await response.json().catch(() => ({}));
    $("connection").textContent = response.ok
      ? `Reset: ${body.removed_tests || 0} testes, ${body.removed_history || 0} historicos, ${body.destroyed_active || 0} destroys`
      : "Erro ao resetar Scout";
    button.disabled = false;
    await load();
  };
  $("startForm").onsubmit = async (event) => {
    event.preventDefault();
    const askId = $("askId").value.trim();
    if (!askId) return;
    const provider = $("manualProvider")?.value || "vastai";
    const strategy = $("manualStrategy")?.value || "akoya";
    const response = await fetch("/api/scout/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, offer_id: Number(askId), strategy }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      $("connection").textContent = `Erro: ${body.detail || response.statusText}`;
      return;
    }
    $("askId").value = "";
    await load();
  };
  document.querySelectorAll("[data-scout-provider=\"clore\"][data-scout-offer-id][data-rent-strategy]").forEach((button) => {
    button.onclick = async () => {
      const offerId = button.getAttribute("data-scout-offer-id");
      const strategy = button.getAttribute("data-rent-strategy") || "akoya";
      button.disabled = true;
      const response = await fetch("/api/scout/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "clore", offer_id: Number(offerId), strategy }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        $("connection").textContent = `Erro: ${body.detail || response.statusText}`;
      }
      await load();
    };
  });
  document.querySelectorAll("[data-destroy-test]").forEach((button) => {
    button.onclick = async () => {
      const id = button.getAttribute("data-destroy-test");
      button.disabled = true;
      let response = await fetch(`/api/scout/destroy/${id}`, { method: "POST" });
      if (response.status === 409) {
        const body = await response.json().catch(() => ({}));
        const ok = confirm(`${body.detail || "Teste parece lucrativo."}\n\nDestruir mesmo assim?`);
        if (ok) {
          response = await fetch(`/api/scout/destroy/${id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ force_profitable_destroy: true }),
          });
        }
      }
      await load();
    };
  });
  document.querySelectorAll("[data-stop-test]").forEach((button) => {
    button.onclick = async () => {
      const id = button.getAttribute("data-stop-test");
      button.disabled = true;
      await fetch(`/api/scout/stop/${id}`, { method: "POST" });
      await load();
    };
  });
}

function render(data) {
  renderCards(data);
  const queueCounts = (data.summary || {}).queue || {};
  const radarCounts = (data.summary || {}).radar || {};
  $("queueSummary").textContent =
    `queued ${queueCounts.queued || 0} | renting ${queueCounts.renting || 0} | ` +
    `rented ${queueCounts.rented || 0} | radar blocked ${radarCounts.blocked || 0} | cooldown ${radarCounts.cooldown || 0}`;
  $("queueRows").innerHTML = (data.queue || []).slice(0, 40).map(renderQueueRow).join("");
  $("activeTests").innerHTML = (data.active_tests || []).map(renderActiveRow).join("");
  $("historyRows").innerHTML = (data.history || [])
    .filter((item) => item.decision !== "pool_measured")
    .map(renderHistoryRow)
    .join("");
  $("connection").textContent = `Atualizado ${new Date().toLocaleTimeString()}`;
  bindButtons();
}

async function load() {
  const response = await fetch("/api/scout/state");
  render(await response.json());
}

load().catch((error) => {
  $("connection").textContent = `Erro ao carregar Scout: ${error}`;
});
setInterval(load, 5000);
