/* Curtailment Brasil — renders charts from window.ONS_DATA (see data.js). */
(function () {
  const D = window.ONS_DATA;
  const COL = { wind: "#4cc9f0", solar: "#ffca3a", accent: "#8ac926" };
  const REASONS = {
    ENE: "Energético (sobreoferta)",
    CNF: "Confiabilidade",
    REL: "Indisp. externa (rede)",
    PAR: "Contrato de conexão",
  };

  if (!D) {
    document.getElementById("kpis").innerHTML =
      '<div class="kpi"><div class="label">Sem dados</div><div class="value">—</div>' +
      '<div class="label">Rode <code>bash scripts/build_data.sh</code></div></div>';
    return;
  }

  Chart.defaults.color = "#9aa7b4";
  Chart.defaults.borderColor = "#2a3340";
  Chart.defaults.font.family = "-apple-system, Segoe UI, Roboto, sans-serif";

  const fmt = (n) => n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  const fmt1 = (n) => n.toLocaleString("pt-BR", { maximumFractionDigits: 1 });

  // ---- KPI cards ----
  const kpis = [
    { cls: "wind", label: "Eólica cortada", val: D.kpi.wind },
    { cls: "solar", label: "Solar cortada", val: D.kpi.solar },
    { cls: "total", label: "Total cortado", val: D.kpi.total },
  ];
  document.getElementById("kpis").innerHTML = kpis
    .map(
      (k) =>
        `<div class="kpi ${k.cls}"><div class="label">${k.label}</div>` +
        `<div class="value">${fmt(k.val)} <small>GWh</small></div></div>`
    )
    .join("");

  document.getElementById("meta").textContent =
    `Período: ${D.range.start} a ${D.range.end} · ${D.monthly.length} meses · ` +
    `gerado em ${D.generated} · unidade: GWh (energia cortada).`;

  // ---- Monthly trend (stacked bars) ----
  new Chart(document.getElementById("chartMonthly"), {
    type: "bar",
    data: {
      labels: D.monthly.map((m) => m.month),
      datasets: [
        { label: "Eólica", data: D.monthly.map((m) => m.wind), backgroundColor: COL.wind, stack: "s" },
        { label: "Solar", data: D.monthly.map((m) => m.solar), backgroundColor: COL.solar, stack: "s" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt1(c.parsed.y)} GWh` } } },
      scales: { x: { stacked: true }, y: { stacked: true, title: { display: true, text: "GWh" } } },
    },
  });

  // ---- By subsystem (horizontal stacked) ----
  new Chart(document.getElementById("chartSubsystem"), {
    type: "bar",
    data: {
      labels: D.subsystem.map((s) => s.name),
      datasets: [
        { label: "Eólica", data: D.subsystem.map((s) => s.wind), backgroundColor: COL.wind, stack: "s" },
        { label: "Solar", data: D.subsystem.map((s) => s.solar), backgroundColor: COL.solar, stack: "s" },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt1(c.parsed.x)} GWh` } } },
      scales: { x: { stacked: true, title: { display: true, text: "GWh" } }, y: { stacked: true } },
    },
  });

  // ---- By reason (doughnut, wind+solar combined) ----
  const reasonTotals = D.reasons.map((r) => ({ code: r.code, total: r.wind + r.solar }));
  new Chart(document.getElementById("chartReasons"), {
    type: "doughnut",
    data: {
      labels: reasonTotals.map((r) => REASONS[r.code] || r.code),
      datasets: [
        {
          data: reasonTotals.map((r) => r.total),
          backgroundColor: ["#8ac926", "#4cc9f0", "#ff595e", "#ffca3a", "#9d4edd"],
          borderColor: "#161b22",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${fmt1(c.parsed)} GWh` } },
      },
    },
  });

  // ---- Top states ----
  new Chart(document.getElementById("chartStates"), {
    type: "bar",
    data: {
      labels: D.states.map((s) => `${s.name} (${s.uf})`),
      datasets: [{ label: "Total cortado", data: D.states.map((s) => s.total), backgroundColor: COL.accent }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${fmt1(c.parsed.x)} GWh` } } },
      scales: { x: { title: { display: true, text: "GWh" } } },
    },
  });
})();
