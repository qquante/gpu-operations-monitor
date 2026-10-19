const $ = (id) => document.getElementById(id);

let configData = null;

function card(label, value, hint = "") {
  return `<article><span>${label}</span><strong>${value || "-"}</strong><em>${hint}</em></article>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtTime(ts) {
  if (!ts) return "-";
  return new Date(Number(ts) * 1000).toLocaleTimeString();
}

function fmtDate(ts) {
  if (!ts) return "-";
  return new Date(Number(ts) * 1000).toLocaleString();
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `$${Number(value).toFixed(4)}`;
}

function row(item, index) {
  return `
    <tr>
      <td>${index}</td>
      <td>${item.gpu || "-"}</td>
      <td>${item.machine_id || "-"}</td>
      <td>${item.host_id || "-"}</td>
      <td>${item.ask_id || "-"}</td>
      <td>${item.instance_id || "-"}</td>
      <td>${item.reason || "-"}</td>
      <td><button class="action-button quiet" data-remove-blacklist="${index}">Remover</button></td>
    </tr>
  `;
}

function fixedCostRow(item) {
  return `
    <tr>
      <td>${item.enabled ? "ON" : "OFF"}</td>
      <td>${escapeHtml(item.worker_name || "-")}</td>
      <td>${escapeHtml(item.provider || "-")}</td>
      <td>${money(item.cost_usd_hr)}</td>
      <td>${escapeHtml(item.note || "-")}</td>
      <td>${fmtDate(item.updated_at)}</td>
      <td>
        <button class="action-button quiet" data-edit-fixed-cost="${escapeHtml(item.worker_name)}">Editar</button>
        <button class="action-button danger" data-remove-fixed-cost="${escapeHtml(item.worker_name)}">Remover</button>
      </td>
    </tr>
  `;
}

function triggerRow(item) {
  return `
    <tr>
      <td>${item.enabled ? "ON" : "OFF"}</td>
      <td>${escapeHtml(item.name || "-")}</td>
      <td>${escapeHtml(item.gpu_match || "-")}</td>
      <td>${item.gpu_count || 1}</td>
      <td>$${Number(item.max_price_usd_hr || 0).toFixed(2)}</td>
      <td>${item.recent_matches || 0}</td>
      <td>${fmtTime(item.last_attempt_at)}</td>
      <td>${escapeHtml(item.last_status || "-")}</td>
      <td>
        <button class="action-button quiet" data-edit-trigger="${escapeHtml(item.id)}">Editar</button>
        <button class="action-button danger" data-remove-trigger="${escapeHtml(item.id)}">Remover</button>
      </td>
    </tr>
  `;
}

function triggerPayload() {
  return {
    enabled: $("triggerEnabled").checked,
    name: $("triggerName").value.trim() || "Comprar H100 SXM",
    gpu_match: $("triggerGpu").value.trim() || "H100 SXM",
    gpu_count: Number($("triggerGpuCount").value || 1),
    max_price_usd_hr: Number($("triggerMaxPrice").value || 0),
  };
}

function fixedCostPayload() {
  return {
    enabled: $("fixedEnabled").checked,
    worker_name: $("fixedWorkerName").value.trim(),
    provider: $("fixedProvider").value.trim() || "Fixo",
    cost_usd_hr: Number($("fixedCostHr").value || 0),
    note: $("fixedNote").value.trim(),
  };
}

async function loadConfig() {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error(response.statusText);
  const data = await response.json();
  configData = data;
  $("connection").textContent = `Atualizado ${new Date().toLocaleTimeString()}`;
  $("configCards").innerHTML = [
    card("Akoya template", data.vast.akoya_template_hash_id, data.vast.akoya_ready ? "pronto" : "bloqueado"),
    card("AlphaMine template", data.vast.alphamine_template_hash_id, data.vast.alphamine_ready ? "pronto" : "bloqueado"),
    card("Alpha host", data.pools.alphamine_pool_host, `port ${data.pools.alphamine_pool_port}`),
    card("Alpha difficulty", data.pools.alphamine_difficulty, "env ALPHAMINE_DIFFICULTY"),
    card("Disk Vast", `${data.vast.disk_gb} GB`, "proximo aluguel"),
    card("Modo aluguel", data.vast.autorent_mode, `max ativos ${data.vast.max_active_rents}`),
  ].join("");
  const fixedCosts = data.fixed_worker_costs || [];
  $("fixedCostSummary").textContent = `${fixedCosts.length} custos fixos configurados`;
  $("fixedCostRows").innerHTML = fixedCosts.length ? fixedCosts.map(fixedCostRow).join("") : `<tr><td colspan="7">Nenhum custo fixo configurado</td></tr>`;
  const triggers = data.vast_gpu_triggers || [];
  $("triggerSummary").textContent = `${triggers.length} triggers Vast configurados`;
  $("triggerRows").innerHTML = triggers.length ? triggers.map(triggerRow).join("") : `<tr><td colspan="9">Nenhum trigger configurado</td></tr>`;
  $("blacklistSummary").textContent = `${data.blacklist.count} itens bloqueados`;
  $("blacklistRows").innerHTML = (data.blacklist.items || []).map(row).join("");
  bindFixedCosts();
  bindTriggers();
  bindRemove();
}

function bindFixedCosts() {
  document.querySelectorAll("[data-edit-fixed-cost]").forEach((button) => {
    button.addEventListener("click", () => {
      const workerName = button.getAttribute("data-edit-fixed-cost");
      const item = (configData?.fixed_worker_costs || []).find((cost) => cost.worker_name === workerName);
      if (!item) return;
      $("fixedCostForm").dataset.editWorkerName = workerName;
      $("fixedWorkerName").value = item.worker_name || "";
      $("fixedWorkerName").disabled = true;
      $("fixedProvider").value = item.provider || "Fixo";
      $("fixedCostHr").value = item.cost_usd_hr || 0;
      $("fixedEnabled").checked = Boolean(item.enabled);
      $("fixedNote").value = item.note || "";
      $("fixedSaved").textContent = "editando";
    });
  });
  document.querySelectorAll("[data-remove-fixed-cost]").forEach((button) => {
    button.addEventListener("click", async () => {
      const workerName = button.getAttribute("data-remove-fixed-cost");
      const ok = window.confirm(`Remover custo fixo de ${workerName}?`);
      if (!ok) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/config/fixed-worker-costs/${encodeURIComponent(workerName)}`, { method: "DELETE" });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadConfig();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindTriggers() {
  document.querySelectorAll("[data-edit-trigger]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.getAttribute("data-edit-trigger");
      const item = (configData?.vast_gpu_triggers || []).find((trigger) => trigger.id === id);
      if (!item) return;
      $("triggerForm").dataset.editTrigger = id;
      $("triggerEnabled").checked = Boolean(item.enabled);
      $("triggerName").value = item.name || "";
      $("triggerGpu").value = item.gpu_match || "H100 SXM";
      $("triggerGpuCount").value = item.gpu_count || 1;
      $("triggerMaxPrice").value = item.max_price_usd_hr || 3.58;
      $("triggerSaved").textContent = "editando";
    });
  });
  document.querySelectorAll("[data-remove-trigger]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.getAttribute("data-remove-trigger");
      const ok = window.confirm("Remover este trigger Vast?");
      if (!ok) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/config/vast-gpu-triggers/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadConfig();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

function bindRemove() {
  document.querySelectorAll("[data-remove-blacklist]").forEach((button) => {
    button.addEventListener("click", async () => {
      const index = button.getAttribute("data-remove-blacklist");
      const ok = window.confirm("Remover este item da blacklist?");
      if (!ok) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/config/blacklist/${index}`, { method: "DELETE" });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        await loadConfig();
      } catch (error) {
        button.textContent = "Erro";
        button.title = String(error);
        button.classList.add("failed");
      }
    }, { once: true });
  });
}

loadConfig().catch((error) => {
  $("connection").textContent = `Erro: ${error}`;
});

$("fixedCostForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("fixedSaved").textContent = "salvando...";
  const editWorkerName = $("fixedCostForm").dataset.editWorkerName;
  const url = editWorkerName
    ? `/api/config/fixed-worker-costs/${encodeURIComponent(editWorkerName)}`
    : "/api/config/fixed-worker-costs";
  const method = editWorkerName ? "PUT" : "POST";
  try {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fixedCostPayload()),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    $("fixedSaved").textContent = "salvo";
    delete $("fixedCostForm").dataset.editWorkerName;
    $("fixedWorkerName").disabled = false;
    await loadConfig();
  } catch (error) {
    $("fixedSaved").textContent = `erro: ${error}`;
  }
});

$("triggerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("triggerSaved").textContent = "salvando...";
  const editId = $("triggerForm").dataset.editTrigger;
  const url = editId ? `/api/config/vast-gpu-triggers/${encodeURIComponent(editId)}` : "/api/config/vast-gpu-triggers";
  const method = editId ? "PUT" : "POST";
  try {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(triggerPayload()),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    $("triggerSaved").textContent = "salvo";
    delete $("triggerForm").dataset.editTrigger;
    await loadConfig();
  } catch (error) {
    $("triggerSaved").textContent = `erro: ${error}`;
  }
});
