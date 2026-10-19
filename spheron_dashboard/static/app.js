const stateUrl = "/api/spheron/state";
const configUrl = "/api/spheron/config";
let currentConfig = null;

const fmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 3 });

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function metric(label, value) {
  return `<div class="metric"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

function badge(value, cls = "") {
  return `<span class="badge ${cls}">${text(value)}</span>`;
}

function groupClass(group) {
  if (group === "DEPLOYED") return "ok";
  if (group === "OFF OK") return "warn";
  if (group === "DEPLOYING") return "warn";
  if (group === "FAILED") return "fail";
  return "";
}

function statusClass(row) {
  if (row.deployment_group) return groupClass(row.deployment_group);
  if (row.terminal) return "fail";
  if (row.akoya_connected && row.akoya_hashrate_ths > 0) return "ok";
  if (row.ssh_status === "running" || row.status === "deploying") return "warn";
  return "";
}

function moneyPair(hour, day) {
  if (hour === null || hour === undefined) return "-";
  return `${money.format(hour || 0)}/h<div class="muted">${money.format(day || 0)}/d</div>`;
}

function moneyTotal(value) {
  return money.format(value || 0);
}

function hours(value) {
  return value ? `${fmt.format(value)}h` : "-";
}

function fillConfig(config) {
  currentConfig = config;
  const form = document.querySelector("#configForm");
  for (const [key, value] of Object.entries(config)) {
    const input = form.elements[key];
    if (input) input.value = value;
  }
  if (form.elements.auto_destroy_bad_enabled) {
    form.elements.auto_destroy_bad_enabled.value = config.auto_destroy_bad_enabled ? "true" : "false";
  }
  if (form.elements.bad_hash_grace_minutes) {
    form.elements.bad_hash_grace_minutes.value = Math.round((config.bad_hash_grace_seconds || 0) / 60);
  }
  const toggle = document.querySelector("#createToggle");
  toggle.textContent = config.create_enabled ? "ligado" : "pausado";
  toggle.className = `toggle ${config.create_enabled ? "on" : "off"}`;
}

function render(data) {
  const summary = data.summary;
  const config = data.config;
  fillConfig(config);
  document.querySelector("#refreshStatus").textContent = `atualizado ${new Date(data.ts * 1000).toLocaleTimeString()}`;
  document.querySelector("#subtitle").textContent = `${config.target_preset} | ${data.config_path}`;
  document.querySelector("#metrics").innerHTML = [
    metric("créditos", summary.credits_balance === null || summary.credits_balance === undefined ? "-" : fmt.format(summary.credits_balance)),
    metric("online alvo", `${summary.online_gpu_count}/${config.desired_online_gpus}`),
    metric("running UI", `${summary.ui_running_cards || 0}/${summary.ui_running_unique || 0}`),
    metric("ativos", `${summary.active_target_count}/${config.global_active_limit}`),
    metric("hashrate", `${fmt.format(summary.total_hashrate_ths)} TH/s`),
    metric("receita", `${money.format(summary.total_revenue_usd_hr)}/h`),
    metric("lucro", `${money.format(summary.total_profit_usd_hr)}/h`),
    metric("custo", `${money.format(summary.total_cost_usd_hr)}/h`),
    metric("lucro dia", `${money.format(summary.total_profit_usd_day)}/d`),
    metric("uso total", moneyTotal(summary.total_usage_usd)),
    metric("ganho total", moneyTotal(summary.total_earned_usd)),
    metric("saldo total", moneyTotal(summary.total_profit_usd)),
    metric("cooldown", summary.cooldown_remaining_seconds ? `${summary.cooldown_remaining_seconds}s` : "0s"),
  ].join("");
  const duplicateText = (summary.ui_duplicate_short_ids || []).length
    ? ` IDs duplicados na UI: ${summary.ui_duplicate_short_ids.map((item) => `${item.short_id} x${item.count}`).join(", ")}.`
    : "";
  document.querySelector("#gapText").textContent =
    `${summary.online_gap} GPUs faltando; ${summary.active_slots_remaining} slots ativos livres; ${summary.wait_reason}.${duplicateText}`;
  document.querySelector("#akoyaText").textContent =
    data.akoya.ok
      ? `${data.akoya.online_worker_count}/${data.akoya.worker_count} workers online, pool ${fmt.format(data.akoya.total_hashrate_ths || 0)} TH/s, Akoya ${money.format((data.pearl && data.pearl.usd_per_th_per_day) || 0)}/TH/dia`
      : "Redis/Akoya indisponível";

  const rows = data.deployments;
  document.querySelector("#tableCount").textContent = `${rows.length} registros`;
  document.querySelector("#deployments").innerHTML = rows
    .map((row) => {
      const akoyaCls = row.akoya_connected && row.akoya_hashrate_ths > 0 ? "ok" : row.deployment_group === "FAILED" ? "fail" : "warn";
      const issueText = row.destroy_reason || row.low_hash_reason || row.failure_reason || row.last_error;
      const issuePrefix = row.destroy_pending ? "DESTROY PENDING: " : row.low_hash_status ? `${row.low_hash_status}: ` : "";
      return `<tr>
        <td class="mono">${text(row.short_id)}</td>
        <td>${badge(row.deployment_group || "-", groupClass(row.deployment_group))}</td>
        <td class="mono">${text(row.worker)}</td>
        <td>${text(row.gpu_count)}x ${text(row.gpu_type)}</td>
        <td>${badge(row.status || row.phase, statusClass(row))}<div class="muted">${text(row.phase)}</div></td>
        <td>${badge(row.ssh_status, row.ssh_status === "succeeded" ? "ok" : row.ssh_status === "failed" ? "fail" : "")}<div class="muted">${text(row.bootstrap_status)}</div></td>
        <td>${badge(row.akoya_connected ? "online" : "offline", akoyaCls)}<div class="muted">${text(row.pool_status)}</div></td>
        <td>${fmt.format(row.akoya_hashrate_ths || 0)}</td>
        <td>${moneyPair(row.revenue_usd_hr, row.revenue_usd_day)}</td>
        <td>${moneyPair(row.cost_usd_hr, row.cost_usd_day)}</td>
        <td>${moneyPair(row.profit_usd_hr, row.profit_usd_day)}</td>
        <td>${hours(row.billed_hours)}</td>
        <td>${moneyTotal(row.total_usage_usd)}</td>
        <td>${moneyTotal(row.earned_usd)}</td>
        <td>${moneyTotal(row.total_profit_usd)}</td>
        <td class="mono">${text(row.ip_address)}</td>
        <td class="muted">${text(issueText ? `${issuePrefix}${issueText}` : "-")}</td>
      </tr>`;
    })
    .join("");
}

async function refresh() {
  const response = await fetch(stateUrl);
  if (!response.ok) throw new Error(`state ${response.status}`);
  render(await response.json());
}

document.querySelector("#createToggle").addEventListener("click", () => {
  if (!currentConfig) return;
  currentConfig.create_enabled = !currentConfig.create_enabled;
  fillConfig(currentConfig);
});

document.querySelector("#configForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    create_enabled: Boolean(currentConfig && currentConfig.create_enabled),
    desired_online_gpus: Number(form.elements.desired_online_gpus.value),
    global_active_limit: Number(form.elements.global_active_limit.value),
    ssh_parallel: Number(form.elements.ssh_parallel.value),
    create_interval_seconds: Number(form.elements.create_interval_seconds.value),
    max_price_usd_hr: Number(form.elements.max_price_usd_hr.value),
    low_credits_threshold: Number(form.elements.low_credits_threshold.value),
    auto_destroy_bad_enabled: form.elements.auto_destroy_bad_enabled.value === "true",
    bad_hash_min_ths: Number(form.elements.bad_hash_min_ths.value),
    bad_hash_grace_seconds: Number(form.elements.bad_hash_grace_minutes.value) * 60,
    bad_hash_samples_required: Number(form.elements.bad_hash_samples_required.value),
  };
  const response = await fetch(configUrl, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`config ${response.status}`);
  render((await response.json()).state);
});

refresh().catch((error) => {
  document.querySelector("#refreshStatus").textContent = error.message;
});
setInterval(() => refresh().catch((error) => {
  document.querySelector("#refreshStatus").textContent = error.message;
}), 5000);
