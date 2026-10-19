const statusEl = document.querySelector("#status");
const logEl = document.querySelector("#log");

function setStatus(text) {
  statusEl.textContent = text;
}

function appendLog(data) {
  const now = new Date().toLocaleTimeString();
  logEl.textContent = `[${now}] ${JSON.stringify(data)}`;
}

window.addEventListener("message", async (event) => {
  if (event.origin !== "https://safetrade.com" && event.origin !== "https://safe.trade") {
    return;
  }
  const payload = event.data && event.data.type === "safetrade-prl-book" ? event.data.payload : null;
  if (!payload) {
    return;
  }
  try {
    const response = await fetch("/api/safetrade/browser-cache", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const saved = await response.json();
    if (!response.ok) {
      throw new Error(saved.detail || `HTTP ${response.status}`);
    }
    setStatus(`Recebido: ${saved.bids} bids / ${saved.asks} asks`);
    appendLog(saved);
  } catch (error) {
    setStatus(`Erro: ${error.message}`);
    appendLog({ error: error.message });
  }
});
