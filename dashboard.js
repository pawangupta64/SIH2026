/* KisanMitra AI — dashboard front-end */

const $ = (id) => document.getElementById(id);
const TITLES = {
  home: ["Dashboard", "Live overview of your field"],
  monitoring: ["Field Monitoring", "Every reading sent by your ESP32 board"],
  ai: ["AI Analysis", "Upload a crop photo for an instant health report"],
  analytics: ["Field Analytics", "Averages over the last 7 days"],
  alerts: ["Alerts", "Warnings based on your threshold settings"],
  advisory: ["AI Advisory", "Daily guidance generated from your field data"],
  chat: ["Chatbot", "Ask anything about farming"],
  settings: ["Settings", "Tune when you get alerted"],
  profile: ["My Profile", "Your details"],
};

/* ---------------- navigation ---------------- */
function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $("view-" + name).classList.add("active");
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name)
  );
  const [t, s] = TITLES[name] || ["Dashboard", ""];
  $("viewTitle").textContent = t;
  $("viewSub").textContent = s;
  $("dropdown").classList.remove("open");
  $("sidebar").classList.remove("open");
  if (name === "analytics") loadAnalytics();
  if (name === "monitoring" || name === "alerts") loadReadings();
  if (name === "chat") loadChatHistory();
}

document.querySelectorAll("[data-view]").forEach((btn) =>
  btn.addEventListener("click", () => showView(btn.dataset.view))
);
$("menuBtn").addEventListener("click", () => $("sidebar").classList.toggle("open"));
$("avatarBtn").addEventListener("click", (e) => {
  e.stopPropagation();
  $("dropdown").classList.toggle("open");
});
document.addEventListener("click", () => $("dropdown").classList.remove("open"));

/* ---------------- charts ---------------- */
let liveChart, analyticsChart;

function makeLineChart(canvasId, labels, sets) {
  return new Chart($(canvasId), {
    type: "line",
    data: {
      labels,
      datasets: sets.map((s) => ({
        label: s.label,
        data: s.data,
        borderColor: s.color,
        backgroundColor: s.color + "22",
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
      })),
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" } },
      scales: { y: { beginAtZero: true, grid: { color: "#eceee9" } }, x: { grid: { display: false } } },
    },
  });
}

/* ---------------- readings ---------------- */
async function loadReadings() {
  const res = await fetch("/api/readings?limit=40");
  const { readings, alerts } = await res.json();

  if (readings.length) {
    const last = readings[readings.length - 1];
    $("statTemp").textContent = last.temperature;
    $("statHum").textContent = last.humidity;
    $("statMoist").textContent = last.soil_moisture;
    $("statTime").textContent = new Date(last.created_at).toLocaleString();
  }

  const labels = readings.map((r) => r.time_label);
  const sets = [
    { label: "Temperature (°C)", data: readings.map((r) => r.temperature), color: "#c0392b" },
    { label: "Humidity (%)", data: readings.map((r) => r.humidity), color: "#2d6cdf" },
    { label: "Soil moisture (%)", data: readings.map((r) => r.soil_moisture), color: "#2f7d4f" },
  ];
  if (liveChart) {
    liveChart.data.labels = labels;
    liveChart.data.datasets.forEach((d, i) => (d.data = sets[i].data));
    liveChart.update();
  } else {
    liveChart = makeLineChart("liveChart", labels, sets);
  }

  $("readingRows").innerHTML = readings.length
    ? [...readings].reverse().map((r) =>
        `<tr><td>${new Date(r.created_at).toLocaleString()}</td><td>${r.device_id}</td>
         <td>${r.temperature}</td><td>${r.humidity}</td><td>${r.soil_moisture}</td></tr>`
      ).join("")
    : `<tr><td colspan="5" class="muted">No readings yet.</td></tr>`;

  const html = alerts.map((a) =>
    `<div class="alert ${a.level}"><strong>${a.title} — ${a.value}</strong><span>${a.message}</span></div>`
  ).join("");
  $("alertList").innerHTML = html;
  $("homeAlerts").innerHTML = html;
}

async function loadAnalytics() {
  const res = await fetch("/api/analytics");
  const d = await res.json();
  const sets = [
    { label: "Temperature (°C)", data: d.temperature, color: "#c0392b" },
    { label: "Humidity (%)", data: d.humidity, color: "#2d6cdf" },
    { label: "Soil moisture (%)", data: d.soil_moisture, color: "#2f7d4f" },
  ];
  if (analyticsChart) analyticsChart.destroy();
  analyticsChart = makeLineChart("analyticsChart", d.labels, sets);

  const avg = (a) => (a.length ? (a.reduce((x, y) => x + y, 0) / a.length).toFixed(1) : "–");
  $("statCount").textContent = d.total_readings;
  $("avgTemp").textContent = avg(d.temperature);
  $("avgHum").textContent = avg(d.humidity);
  $("avgMoist").textContent = avg(d.soil_moisture);
}

$("refreshBtn").addEventListener("click", loadReadings);
$("simulateBtn").addEventListener("click", async () => {
  await fetch("/api/simulate", { method: "POST" });
  loadReadings();
});

/* ---------------- AI image analysis ---------------- */
$("pickBtn").addEventListener("click", () => $("imageInput").click());
$("imageInput").addEventListener("change", () => {
  const file = $("imageInput").files[0];
  if (!file) return;
  const img = $("preview");
  img.src = URL.createObjectURL(file);
  img.hidden = false;
  $("analyseBtn").disabled = false;
});

$("analyseForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("imageInput").files[0];
  if (!file) return;
  const box = $("analyseResult");
  box.innerHTML = `<div class="result-card muted">Analysing your image…</div>`;
  $("analyseBtn").disabled = true;

  const fd = new FormData();
  fd.append("image", file);
  try {
    const res = await fetch("/api/analyse", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Analysis failed.");

    if (!data.is_crop) {
      box.innerHTML = `<div class="result-card">
        <span class="badge bad">Cannot be analysed</span>
        <p>This image cannot be analysed. Please upload a photo of a crop, leaf, plant or field.</p></div>`;
      return;
    }
    const badge = /health/i.test(data.health_status) || data.health_status === "Healthy" ? "" :
      (data.health_status || "").toLowerCase().includes("severe") ? "bad" : "warn";
    box.innerHTML = `<div class="result-card">
      <span class="badge ${badge}">${data.health_status || "Result"}</span>
      <h3 style="margin-top:10px">${data.crop_name || "Crop"} · confidence ${data.confidence || "–"}</h3>
      <p>${data.summary || ""}</p>
      ${data.issues?.length ? `<h4>Issues spotted</h4><ul class="bullet-list">${data.issues.map((i) => `<li>${i}</li>`).join("")}</ul>` : ""}
      ${data.recommendations?.length ? `<h4>What to do</h4><ul class="bullet-list">${data.recommendations.map((i) => `<li>${i}</li>`).join("")}</ul>` : ""}
    </div>`;
  } catch (err) {
    box.innerHTML = `<div class="result-card" style="color:#c0392b">${err.message}</div>`;
  } finally {
    $("analyseBtn").disabled = false;
  }
});

/* ---------------- advisory ---------------- */
$("advisoryBtn").addEventListener("click", async () => {
  $("advisoryList").innerHTML = `<li class="muted">Thinking…</li>`;
  const res = await fetch("/api/advisory");
  const data = await res.json();
  $("advisoryList").innerHTML = res.ok
    ? data.points.map((p) => `<li>${p}</li>`).join("")
    : `<li style="color:#c0392b">${data.error}</li>`;
});

/* ---------------- chatbot ---------------- */
function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = "bubble " + (role === "user" ? "user" : "bot");
  div.textContent = text;
  $("chatLog").appendChild(div);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
  return div;
}

let historyLoaded = false;
async function loadChatHistory() {
  if (historyLoaded) return;
  historyLoaded = true;
  const res = await fetch("/api/chat/history");
  const { messages } = await res.json();
  messages.forEach((m) => addBubble(m.role, m.content));
}

$("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("chatInput").value.trim();
  if (!text) return;
  addBubble("user", text);
  $("chatInput").value = "";
  const pending = addBubble("bot", "Typing…");
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    pending.textContent = res.ok ? data.reply : data.error;
  } catch {
    pending.textContent = "Could not reach the server.";
  }
});

/* ---------------- settings & profile ---------------- */
$("saveSettings").addEventListener("click", async () => {
  const body = {};
  ["temp_min", "temp_max", "humidity_min", "humidity_max", "moisture_min", "moisture_max"]
    .forEach((k) => (body[k] = $(k).value));
  await fetch("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  $("settingsNote").textContent = "Saved ✓";
  setTimeout(() => ($("settingsNote").textContent = ""), 2000);
  loadReadings();
});

$("saveProfile").addEventListener("click", async () => {
  const body = {};
  ["name", "phone", "farm_name", "location", "crop"].forEach((k) => (body[k] = $("p_" + k).value));
  await fetch("/api/profile", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  $("profileNote").textContent = "Saved ✓";
  setTimeout(() => ($("profileNote").textContent = ""), 2000);
});

/* ---------------- start ---------------- */
loadReadings();
setInterval(loadReadings, 30000); // auto-refresh every 30 seconds
