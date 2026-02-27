/**
 * SDN-IoT Dashboard v2 - with DPI Routing Log
 * Fetches from API Gateway every 3 seconds
 */

const API_BASE = 'http://localhost:8000';
const REFRESH = 3000;

const el = id => document.getElementById(id);

// -- Connection Status --------------------------------------------------------
function setConnected(ok) {
  el('conn-dot').className = 'status-dot ' + (ok ? 'online' : 'offline');
  el('conn-text').textContent = ok ? 'Connected' : 'Disconnected';
}

// -- Number animation ---------------------------------------------------------
function animateNumber(id, newVal) {
  const node = el(id);
  if (!node) return;
  node.style.transform = 'scale(1.15)';
  node.textContent = newVal;
  setTimeout(() => { node.style.transform = 'scale(1)'; }, 200);
}

// -- Latency bar --------------------------------------------------------------
function setLatencyBar(barId, valueId, ms, maxMs = 80) {
  const pct = Math.min((ms / maxMs) * 100, 100);
  el(barId).style.width = pct + '%';
  el(valueId).textContent = ms + 'ms';
}

// -- Traffic class badge ------------------------------------------------------
function classBadge(tc) {
  const map = {
    EMERGENCY: ['', 'badge-emergency'],
    CRITICAL: ['', 'badge-critical'],
    ANALYTICS: ['', 'badge-analytics'],
    BULK: ['', 'badge-bulk'],
  };
  const [icon, cls] = map[tc] || ['', ''];
  return `<span class="badge ${cls}">${tc}</span>`;
}

// -- Routing log item ---------------------------------------------------------
function routingItem(ev) {
  const time = new Date(ev.timestamp).toLocaleTimeString();
  const destLabel = ev.destination === 'FOG' ? 'FOG' : 'CLOUD';
  return `
      <div class="feed-item routing-item">
        <div class="feed-item-header">
          <span>${classBadge(ev.traffic_class)}</span>
          <span class="feed-item-time">${time}</span>
        </div>
        <div class="feed-item-body">
          FROM -> ${ev.source_ip} | TO -> <strong>${destLabel}</strong> |
          Sensor: ${ev.sensor_id} |
          Conf: ${(ev.confidence * 100).toFixed(0)}%
        </div>
        <div class="feed-item-reason">${ev.reason}</div>
      </div>`;
}

// -- Alert item ---------------------------------------------------------------
function alertItem(a) {
  const time = new Date(a.received_at).toLocaleTimeString();
  const cls = a.severity === 'HIGH' ? 'critical' : '';
  return `
      <div class="feed-item ${cls}">
        <div class="feed-item-header">
          <span class="feed-item-title">ALERT: ${a.status}</span>
          <span class="feed-item-time">${time}</span>
        </div>
        <div class="feed-item-body">
          Smoke: ${a.smoke_level}% | ${a.action_taken}
        </div>
      </div>`;
}

// -- Analytics item -----------------------------------------------------------
function analyticsItem(r) {
  const time = new Date(r.received_at).toLocaleTimeString();
  return `
      <div class="feed-item analytics">
        <div class="feed-item-header">
          <span class="feed-item-title">BATCH #${r.id}</span>
          <span class="feed-item-time">${time}</span>
        </div>
        <div class="feed-item-body">
          ${r.batch_size} pts | ${((r.payload_size_bytes || 0) / 1024).toFixed(1)}KB | ${r.processing_time_ms}ms
        </div>
      </div>`;
}

// -- Donut chart for routing split --------------------------------------------
function updateDonut(fog, cloud) {
  const total = fog + cloud;
  const fogPct = total ? Math.round(fog / total * 100) : 0;
  const cloudPct = total ? Math.round(cloud / total * 100) : 0;
  el('donut-fog').textContent = fogPct + '%';
  el('donut-cloud').textContent = cloudPct + '%';
  el('donut-total').textContent = total + ' pkts';

  // CSS conic-gradient donut
  el('donut-ring').style.background =
    `conic-gradient(var(--accent-fog) 0% ${fogPct}%, var(--accent-cloud) ${fogPct}% 100%)`;
}

// -- Main update --------------------------------------------------------------
async function refresh() {
  try {
    const res = await fetch(`${API_BASE}/dashboard`);
    const data = await res.json();
    setConnected(true);

    const s = data.summary || {};

    // Fog stats
    animateNumber('fog-alerts', s.fog_alerts_total || 0);
    animateNumber('fog-critical', s.fog_critical_count || 0);
    el('fog-latency').textContent = (s.fog_avg_latency_ms || 0) + 'ms';

    // Cloud stats
    animateNumber('cloud-batches', s.cloud_batches_total || 0);
    animateNumber('cloud-points', s.cloud_data_points || 0);
    el('cloud-latency').textContent = (s.cloud_avg_latency_ms || 0) + 'ms';

    // SDN stats
    animateNumber('sdn-total', s.sdn_total_packets || 0);
    animateNumber('sdn-fog', s.sdn_fog_routed || 0);
    animateNumber('sdn-cloud', s.sdn_cloud_routed || 0);
    animateNumber('sdn-emergency', s.sdn_emergency_count || 0);
    animateNumber('sdn-critical', s.sdn_critical_count || 0);
    animateNumber('sdn-analytics', s.sdn_analytics_count || 0);

    // Latency bars
    setLatencyBar('fog-bar', 'fog-bar-val', s.fog_avg_latency_ms || 0);
    setLatencyBar('cloud-bar', 'cloud-bar-val', s.cloud_avg_latency_ms || 0);

    // Donut
    updateDonut(s.sdn_fog_routed || 0, s.sdn_cloud_routed || 0);

    // Routing log
    const routing = (data.recent_routing || []).slice().reverse();
    el('routing-feed').innerHTML = routing.length
      ? routing.map(routingItem).join('')
      : '<div class="feed-empty">Waiting for traffic...</div>';

    // Alerts feed
    const alerts = (data.recent_alerts || []).slice().reverse();
    el('alerts-feed').innerHTML = alerts.length
      ? alerts.map(alertItem).join('')
      : '<div class="feed-empty">No alerts yet</div>';

    // Analytics feed
    const recs = (data.recent_analytics || []).slice().reverse();
    el('analytics-feed').innerHTML = recs.length
      ? recs.map(analyticsItem).join('')
      : '<div class="feed-empty">No analytics yet</div>';

    el('last-update').textContent = new Date().toLocaleTimeString();

  } catch {
    setConnected(false);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  refresh();
  setInterval(refresh, REFRESH);
});
