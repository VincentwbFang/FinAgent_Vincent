const form = document.getElementById("analyze-form");
const runBtn = document.getElementById("run-btn");
const jobBox = document.getElementById("job-box");
const jobLine = document.getElementById("job-line");
const progressFill = document.getElementById("progress-fill");
const resultPanel = document.getElementById("result-panel");
const resultTitle = document.getElementById("result-title");
const narrativeEl = document.getElementById("narrative");
const metricsCards = document.getElementById("metrics-cards");
const jsonBlock = document.getElementById("json-block");
const langButtons = [...document.querySelectorAll(".lang-btn")];

let currentJobId = null;
let currentReport = null;
let currentLang = "en";

function fmtNumber(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    if (Math.abs(value) < 1 && value !== 0) return value.toFixed(4);
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function renderCards(report) {
  metricsCards.innerHTML = "";
  const scenarios = report.scenarios || {};
  const metrics = report.metrics || {};
  const tech = metrics.technical_profile || {};

  const cards = [
    ["Confidence", report.confidence],
    ["Base Case", scenarios.base],
    ["Bull Case", scenarios.bull],
    ["Bear Case", scenarios.bear],
    ["Current Price", metrics.current_price || tech.current_price],
    ["12M Return", tech.ret_12m],
    ["Volatility", metrics.volatility_annualized],
    ["Max Drawdown", metrics.max_drawdown],
  ];

  cards.forEach(([k, v], idx) => {
    const card = document.createElement("div");
    card.className = "card slide-up";
    card.style.animationDelay = `${0.03 * idx}s`;
    card.innerHTML = `<div class="k">${k}</div><div class="v">${fmtNumber(v)}</div>`;
    metricsCards.appendChild(card);
  });
}

async function fetchReadable(jobId, lang) {
  const res = await fetch(`/v1/reports/${jobId}/readable?lang=${lang}`);
  if (!res.ok) throw new Error(`Readable fetch failed: ${res.status}`);
  return res.text();
}

function activateLang(lang) {
  currentLang = lang;
  langButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === lang);
  });
}

async function refreshNarrative() {
  if (!currentJobId) return;
  try {
    const text = await fetchReadable(currentJobId, currentLang);
    narrativeEl.textContent = text;
  } catch (err) {
    narrativeEl.textContent = `Unable to load readable narrative: ${err.message}`;
  }
}

async function pollJob(jobId) {
  while (true) {
    const res = await fetch(`/v1/jobs/${jobId}`);
    if (!res.ok) {
      throw new Error(`Job polling failed: ${res.status}`);
    }

    const job = await res.json();
    jobLine.textContent = `Job ${job.job_id} — ${job.status}`;
    progressFill.style.width = `${job.progress || 0}%`;

    if (job.status === "done") {
      return;
    }

    if (job.status === "failed") {
      throw new Error(job.error || "analysis failed");
    }

    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function fetchReport(jobId) {
  const res = await fetch(`/v1/reports/${jobId}`);
  if (!res.ok) throw new Error(`Report fetch failed: ${res.status}`);
  return res.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  runBtn.disabled = true;
  runBtn.textContent = "Running...";
  resultPanel.classList.add("hidden");
  jobBox.classList.remove("hidden");
  progressFill.style.width = "0%";

  const symbol = document.getElementById("symbol").value.trim().toUpperCase();
  const horizon = Number(document.getElementById("horizon").value || 365);
  const depth = document.getElementById("depth").value;
  const includeMacro = document.getElementById("macro").checked;

  try {
    const payload = {
      symbol,
      horizon_days: horizon,
      depth,
      include_macro: includeMacro,
      valuation_modes: ["dcf", "multiples", "scenarios"],
    };

    const startRes = await fetch("/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!startRes.ok) {
      const txt = await startRes.text();
      throw new Error(`Analyze request failed: ${startRes.status} ${txt}`);
    }

    const startData = await startRes.json();
    currentJobId = startData.job_id;

    await pollJob(currentJobId);
    currentReport = await fetchReport(currentJobId);

    resultTitle.textContent = `${currentReport.symbol} Analysis`;
    jsonBlock.textContent = JSON.stringify(currentReport, null, 2);

    activateLang("en");
    await refreshNarrative();
    renderCards(currentReport);

    resultPanel.classList.remove("hidden");
  } catch (err) {
    resultPanel.classList.remove("hidden");
    narrativeEl.textContent = `Error: ${err.message}`;
    metricsCards.innerHTML = "";
    jsonBlock.textContent = "";
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run Analysis";
  }
});

langButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!currentJobId) return;
    activateLang(btn.dataset.lang);
    await refreshNarrative();
  });
});
