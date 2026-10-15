// ================= CivicAI officer / admin dashboard =================
const IS_ADMIN = ME.role === 'admin';
const COLORS = ['#3b4bd8', '#f28c28', '#14995b', '#d7263d', '#7c4dff', '#0ea5e9', '#e7a008', '#64748b', '#ec4899'];
const PRI = {Critical: '#d7263d', High: '#f06a1d', Medium: '#e7a008', Low: '#2b9a66'};
let DATA = null, NOW = null;

// ---------------------------------------------------- tabs
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('on')); b.classList.add('on');
  document.querySelectorAll('section[id^="t-"]').forEach(s => s.hidden = s.id !== 't-' + b.dataset.t);
});

// ---------------------------------------------------- data
async function loadAll() { await Promise.all([loadList(), loadAnalytics()]); }

async function loadAnalytics() {
  const a = DATA = await api('/api/admin/analytics');
  document.getElementById('clock').textContent = a.clock.slice(0, 16) + (a.offset_hours ? `  (+${a.offset_hours}h)` : '');
  const mine = IS_ADMIN ? null : a.departments.find(d => d.category === ME.department);
  const k = mine ? [
    ['Total', mine.total], ['Pending', mine.pending], ['Overdue', mine.overdue, 'var(--red)'], ['Resolved', mine.resolved, 'var(--green)'],
    ['Escalated', mine.escalated, 'var(--crit)'], ['Score', mine.score == null ? '—' : mine.score + ' ' + mine.grade]
  ] : [
    ['Total', a.total], ['Open', a.open], ['Resolved', a.resolved, 'var(--green)'], ['Escalated', a.escalated, 'var(--crit)'],
    ['CM Helpdesk', a.cm_level, 'var(--crit)'], ['Satisfaction', a.satisfaction + '%']
  ];
  document.getElementById('kpis').innerHTML = k.map(x => `<div class="kpi"><div class="n" style="color:${x[2] || 'inherit'}">${x[1]}</div><div class="l">${x[0]}</div></div>`).join('');
  drawCharts(a); drawDepts(a); drawHot(a); drawModel(a);
}

async function loadList() {
  const p = new URLSearchParams({status: fStatus.value, q: fQ.value});
  const fc = document.getElementById('fCat'); if (fc && fc.value) p.set('category', fc.value);
  const j = await api('/api/admin/complaints?' + p);
  NOW = new Date(j.now.replace(' ', 'T'));
  const tbl = document.getElementById('tbl');
  if (!j.items.length) { tbl.innerHTML = '<tr><td style="padding:30px;text-align:center" class="muted">No complaints for this filter 🎉</td></tr>'; return; }
  tbl.innerHTML = `<tr><th>ID</th><th>Problem</th>${IS_ADMIN ? '<th>Department</th>' : ''}<th>Priority</th><th>Status</th><th>Escalation</th><th>Deadline</th></tr>` +
    j.items.map(c => {
      const left = (new Date(c.deadline.replace(' ', 'T')) - NOW) / 36e5;
      const active = !['Resolved', 'Closed', 'Rejected'].includes(c.status);
      const dl = !active ? '<span class="muted small">—</span>' : left < 0 ? `<span class="over">Overdue ${Math.abs(left).toFixed(0)}h</span>` : `${left.toFixed(0)}h left`;
      return `<tr class="click" onclick='openC("${c.id}")'>
        <td class="mono">${c.id}${c.repeat_flag ? ' <span title="Repeat issue">🔁</span>' : ''}${c.reopen_count ? ' <span title="Reopened">↺</span>' : ''}</td>
        <td>${esc(c.description.slice(0, 64))}${c.description.length > 64 ? '…' : ''}<div class="small muted">📍 ${esc(c.location)} · ${esc(c.subtype)}</div></td>
        ${IS_ADMIN ? `<td class="small">${esc(c.category)}</td>` : ''}
        <td><span class="badge p-${c.priority}">${c.priority}</span><div class="small muted">${c.severity}/100</div></td>
        <td><span class="badge ${sc(c.status)}">${c.status}</span></td>
        <td><span class="lvl" title="Level ${c.escalation_level}">${[1, 2, 3].map(i => `<i class="${c.escalation_level >= i ? 'on' : ''}"></i>`).join('')}</span>
            <div class="small muted">🔔 ${c.reminders_sent}/3${c.extension_used ? ' · ext' : ''}</div></td>
        <td class="small">${dl}</td></tr>`;
    }).join('');
}

// ---------------------------------------------------- drawer
async function openC(id) {
  const j = await api('/api/track/' + id), c = j.complaint;
  const canEdit = !['Closed'].includes(c.status);
  document.getElementById('drawer').innerHTML = `
    <div style="display:flex;align-items:center;gap:10px"><h2 class="mono" style="margin:0">${c.id}</h2>
      <span class="badge ${sc(c.status)}">${c.status}</span><span class="badge p-${c.priority}">${c.priority} · ${c.severity}</span>
      <button class="btn ghost sm" style="margin-left:auto" onclick="closeDrawer()">✖</button></div>
    <p style="font-size:16px">${esc(c.description)}</p>
    ${c.repeat_flag ? `<div class="alert warn">🔁 ${esc(c.repeat_flag)}</div>` : ''}
    ${c.reopen_count ? `<div class="alert danger">↺ Reopened ${c.reopen_count} time(s) by AI after negative citizen feedback.</div>` : ''}
    ${c.escalation_level >= 1 || c.repeat_flag || c.reopen_count ? `<a class="btn red sm" href="/report/${c.id}" target="_blank">📑 Open Accountability Report</a>` : ''}
    <div class="kv" style="margin:16px 0">
      <div>Location</div><div>📍 ${esc(c.location)}</div>
      <div>AI category</div><div>${esc(c.category)} → ${esc(c.subtype)} (${c.confidence}% sure)</div>
      <div>Keywords</div><div>${c.keywords.map(k => `<span class="badge s-Assigned">${esc(k)}</span>`).join(' ')}</div>
      <div>Department</div><div>${esc(c.department)}</div>
      <div>Officer</div><div>${esc(c.officer)}</div>
      <div>Registered</div><div>${c.created_at}</div>
      <div>Deadline</div><div>${c.deadline}</div>
      <div>Escalation</div><div>Level ${c.escalation_level} · reminders ${c.reminders_sent}/3 · extension ${c.extension_used ? 'used' : 'no'}</div>
      ${c.similar_count ? `<div>Linked</div><div>${c.similar_ids.join(', ')}</div>` : ''}
      ${c.rating ? `<div>Citizen rating</div><div>${'★'.repeat(c.rating)} “${esc(c.feedback)}”</div>` : ''}
    </div>
    ${canEdit ? `<div class="card" style="background:var(--bg)"><h3>✍️ Update action</h3>
      <label>New status</label><select id="uStatus"><option>Under Review</option><option>Action Initiated</option><option>Resolved</option><option>Rejected</option></select>
      <label>Official remark (sent to citizen)</label><textarea id="uRem" rows="2" placeholder="e.g. Pipeline repaired, supply restored"></textarea>
      <label>Contractor (optional)</label><input id="uCon" value="${esc(c.contractor || '')}" placeholder="e.g. M/s Sharma Constructions">
      <button class="btn" style="margin-top:12px" onclick="saveC('${c.id}')">Save & notify citizen</button></div>` : ''}
    <h3 style="margin-top:18px">🕒 Audit trail</h3>
    <div class="timeline">${j.history.map(e => `<div class="ev ${/AI/.test(e.actor) ? 'ai' : ''} ${/LEVEL|Escalat|REOPEN|missed/.test(e.action) ? 'esc' : ''}">
      <div class="t">${e.time} · ${esc(e.actor)}</div><div class="a">${esc(e.action)}</div>${e.note ? `<div class="n">${esc(e.note)}</div>` : ''}</div>`).join('')}</div>`;
  document.getElementById('drawer').classList.add('open'); document.getElementById('dbg').classList.add('open');
}
function closeDrawer() { document.getElementById('drawer').classList.remove('open'); document.getElementById('dbg').classList.remove('open'); }
async function saveC(id) {
  try {
    await api('/api/admin/update/' + id, {status: uStatus.value, remarks: uRem.value, contractor: uCon.value});
    toast('✅ Updated — citizen notified by App / SMS / E-mail'); closeDrawer(); loadAll();
  } catch (e) { toast(e.message); }
}

// ---------------------------------------------------- time machine
async function warp(h, reset) {
  const r = await api('/api/admin/timewarp', {hours: h, reset: !!reset});
  toast(reset ? '⟲ Back to real time' : `⏩ Jumped +${h}h — ${r.events} reminder/escalation event(s) fired`);
  loadAll();
}

// ---------------------------------------------------- charts (pure SVG, work offline)
function hbar(obj, colorFn, keepOrder) {
  const e = Object.entries(obj); if (!keepOrder) e.sort((a, b) => b[1] - a[1]); const max = Math.max(1, ...e.map(x => x[1]));
  return e.map(([k, v], i) => `<div style="display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px">
    <div style="width:150px;flex:none">${esc(k)}</div>
    <div style="flex:1;background:var(--bg);border-radius:6px;height:20px"><div style="width:${100 * v / max}%;height:100%;border-radius:6px;background:${colorFn ? colorFn(k, i) : COLORS[i % 9]}"></div></div>
    <b style="width:28px;text-align:right">${v}</b></div>`).join('');
}
function donut(obj) {
  const e = Object.entries(obj); const tot = e.reduce((s, x) => s + x[1], 0) || 1;
  let acc = 0; const R = 60, C = 2 * Math.PI * R;
  const arcs = e.map(([k, v], i) => { const len = C * v / tot; const s = `<circle r="${R}" cx="80" cy="80" fill="none" stroke="${COLORS[i % 9]}" stroke-width="26"
      stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-acc}" transform="rotate(-90 80 80)"/>`; acc += len; return s; }).join('');
  return `<div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap"><svg width="160" height="160">${arcs}
    <text x="80" y="86" text-anchor="middle" font-size="22" font-weight="800">${tot}</text></svg>
    <div>${e.map(([k, v], i) => `<div class="small" style="margin:4px 0"><span style="display:inline-block;width:11px;height:11px;border-radius:3px;background:${COLORS[i % 9]};margin-right:7px"></span>${esc(k)} <b>${v}</b></div>`).join('')}</div></div>`;
}
function line(obj) {
  const e = Object.entries(obj), W = 520, H = 170, P = 26, max = Math.max(1, ...e.map(x => x[1]));
  const pts = e.map(([k, v], i) => [P + i * (W - 2 * P) / (e.length - 1), H - P - (H - 2 * P) * v / max]);
  const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%">
    <path d="${path} L ${pts[pts.length - 1][0]} ${H - P} L ${P} ${H - P} Z" fill="#3b4bd822"/>
    <path d="${path}" fill="none" stroke="#3b4bd8" stroke-width="2.5"/>
    ${pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="#3b4bd8"><title>${e[i][0]}: ${e[i][1]}</title></circle>
      ${i % 2 === 0 ? `<text x="${p[0]}" y="${H - 6}" font-size="10" text-anchor="middle" fill="#8a91a8">${e[i][0]}</text>` : ''}
      <text x="${p[0]}" y="${p[1] - 8}" font-size="10" text-anchor="middle" fill="#4a5270">${e[i][1] || ''}</text>`).join('')}</svg>`;
}
function drawCharts(a) {
  document.getElementById('cCat').innerHTML = hbar(a.by_category);
  document.getElementById('cStatus').innerHTML = donut(a.by_status);
  document.getElementById('cTrend').innerHTML = line(a.trend);
  const pri = {}; ['Critical', 'High', 'Medium', 'Low'].forEach(p => pri[p] = a.by_priority[p] || 0);
  document.getElementById('cPri').innerHTML = hbar(pri, k => PRI[k], true) + '<hr style="border:0;border-top:1px solid var(--line)">' + hbar(a.by_language);
}
function drawDepts(a) {
  document.getElementById('deptTbl').innerHTML = `<tr><th>Department</th><th>Total</th><th>Pending</th><th>Overdue</th><th>Avg resolution</th><th>Escalated</th><th>Reopened</th><th>Rating</th><th>AI score</th></tr>` +
    a.departments.sort((x, y) => (y.score ?? -1) - (x.score ?? -1)).map(d => `<tr>
      <td><b>${esc(d.department)}</b><div class="small muted">${esc(d.officer)}</div></td>
      <td>${d.total}</td><td>${d.pending}</td><td class="${d.overdue ? 'over' : ''}">${d.overdue}</td>
      <td>${d.avg_resolution_h == null ? '—' : d.avg_resolution_h + ' h'}</td><td>${d.escalated}</td><td>${d.reopened}</td>
      <td>${d.avg_rating ? '★ ' + d.avg_rating : '—'}</td>
      <td>${d.score == null ? '—' : `<span class="grade g-${d.grade}">${d.grade}</span> <span class="score">${d.score}</span>`}</td></tr>`).join('');
}
function drawHot(a) {
  document.getElementById('hotList').innerHTML = a.hotspots.length ? a.hotspots.map(h => `<div class="hot"><div class="ic">🔮</div>
    <div><b>${esc(h.location)} — ${esc(h.category)}</b> <span class="badge p-High">${h.count} complaints in 14 days</span>
    <div style="margin-top:4px">AI prediction: <b>${esc(h.prediction)}</b></div><div class="small muted">Highest severity seen: ${h.max_severity}/100</div></div></div>`).join('')
    : '<div class="card muted">No hotspots right now.</div>';
}
function drawModel(a) {
  const m = a.model;
  document.getElementById('modelBox').innerHTML = `
    <div class="card"><h3>🧠 Complaint classifier</h3>
      <div class="kv">
        <div>Algorithm</div><div>TF-IDF (words + character n-grams) → Logistic Regression, blended with a domain keyword lexicon (hybrid AI)</div>
        <div>Library</div><div>scikit-learn</div>
        <div>Languages</div><div>English, Hindi (Devanagari), Hinglish</div>
        <div>Categories</div><div>${m.categories} departments</div>
        <div>Training samples</div><div>${m.train_size} (after augmentation)</div>
        <div>Test sentences</div><div>${m.test_size} never-seen sentences</div>
      </div></div>
    <div class="card"><h3>📊 Accuracy on unseen sentences</h3>
      ${hbar({'Hybrid model (used)': m.test_accuracy, 'Pure ML only': m.ml_only_accuracy,
        'English': m.per_language.en || 0, 'Hindi': m.per_language.hi || 0, 'Hinglish': m.per_language.hinglish || 0}, (k, i) => i === 0 ? '#14995b' : COLORS[i], true)}
      <p class="small muted">Values are % correct. The hybrid design is why accuracy stays high even with a small training set.</p></div>
    <div class="card"><h3>⚖️ Severity model (0-100)</h3>
      <div class="kv"><div>Urgent keywords</div><div>up to 30</div><div>Sentiment intensity</div><div>up to 15</div>
      <div>Repeats in same area</div><div>up to 20</div><div>Duration of issue</div><div>up to 15</div><div>Service criticality</div><div>up to 20</div></div>
      <p class="small muted">≥65 Critical · ≥45 High · ≥25 Medium · else Low. Deadline = department base time × priority factor.</p></div>
    <div class="card"><h3>🚨 Escalation rules</h3>
      <ol class="small" style="padding-left:18px;margin:0">
        <li>Reminders at 50%, 75% and 90% of the deadline</li><li>Deadline missed → one final extension (+50%)</li>
        <li>Still unresolved → <b>Level 1</b>: Main Administrative Office</li><li><b>Level 2</b>: citizen asked to confirm</li>
        <li><b>Level 3</b>: accountability report to CM Helpdesk</li><li>Negative feedback after "resolved" → AI reopens with higher priority</li></ol></div>`;
}

// ---------------------------------------------------- wiring
['fStatus', 'fCat'].forEach(id => { const el = document.getElementById(id); if (el) el.onchange = loadList; });
let qt; document.getElementById('fQ').oninput = () => { clearTimeout(qt); qt = setTimeout(loadList, 300); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
loadAll(); setInterval(loadAll, 20000);
