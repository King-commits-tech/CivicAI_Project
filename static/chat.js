// ================= CivicAI chat + voice + GPS / area picker + AI brain panel =================
// base.html se aate hain: esc(), api(), toast()

const box = document.getElementById('messages');
const input = document.getElementById('input');
const brain = document.getElementById('brainBody');
const LOCATION_STAGES = ['need_location', 'need_duration', 'confirm'];

let voiceLang = 'en-IN';
let speakOn = false;
let busy = false;
let stage = 'idle';        // server ka batata hai: idle / need_category / need_location / need_duration / confirm
let pendingGeo = null;     // complaint likhne se PEHLE dabaya gaya GPS - agle message ke saath jayega
let LOC_STATE = null;      // {lat, lng, source, accuracy} - brain panel me map card dikhane ke liye

// Dropdown ke liye areas (area ka center). Seed data ke same areas.
const AREAS = [
  ['Vijay Nagar', 22.7533, 75.8937], ['Palasia', 22.7244, 75.8839], ['Rajwada', 22.7195, 75.8537],
  ['Bhawarkua', 22.6990, 75.8650], ['Khajrana', 22.7305, 75.8988], ['Sudama Nagar', 22.6980, 75.8340],
  ['Rajendra Nagar', 22.6840, 75.8290], ['Nipania', 22.7710, 75.9140], ['AB Road', 22.7420, 75.8890],
  ['Scheme 54', 22.7580, 75.8970], ['Bengali Square', 22.7280, 75.9090], ['MG Road', 22.7190, 75.8580],
  ['Musakhedi', 22.7120, 75.9010], ['Malharganj', 22.7270, 75.8420], ['Tilak Nagar', 22.7290, 75.8820],
  ['Banganga', 22.7680, 75.8450], ['Saket Nagar', 22.7380, 75.9020], ['Annapurna', 22.6990, 75.8410],
  ['Geeta Bhawan', 22.7190, 75.8810], ['Chhoti Gwaltoli', 22.7130, 75.8690], ['Pipliyahana', 22.7100, 75.9080],
  ['Rau', 22.6390, 75.8050], ['Mhow', 22.5540, 75.7640], ['Silicon City', 22.6210, 75.8020],
  ['Navlakha', 22.7010, 75.8740], ['Super Corridor', 22.7950, 75.8120], ['Khandwa Road', 22.6890, 75.8790],
];

function scrollDown() { box.scrollTop = box.scrollHeight; }

function addMsg(html, who) {
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  d.innerHTML = html;
  box.appendChild(d); scrollDown();
  return d;
}

function typing() {
  return addMsg('<span class="typing"><i></i><i></i><i></i></span>', 'bot');
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------------------------------------------------------------- voice out (bot bolta hai)
function speak(html) {
  if (!speakOn || !window.speechSynthesis) return;
  const tmp = document.createElement('div'); tmp.innerHTML = html;
  const text = tmp.textContent.replace(/[\u{1F300}-\u{1FAFF}☀-➿]/gu, '');
  const u = new SpeechSynthesisUtterance(text);
  u.lang = /[ऀ-ॿ]/.test(text) ? 'hi-IN' : 'en-IN';
  speechSynthesis.speak(u);
}

// ---------------------------------------------------------------- sending messages
async function send(text) {
  text = (text || '').trim();
  if (!text || busy) return;
  busy = true;
  document.getElementById('examples').style.display = 'none';
  clearInteractive();
  addMsg(esc(text), 'user');
  input.value = '';

  const body = {message: text};
  if (pendingGeo) {                       // pehle dabaya hua GPS isi message ke saath jata hai
    body.coordinates = pendingGeo.coordinates;
    body.location_type = pendingGeo.type;
    pendingGeo = null;
  }

  const t = typing();
  try {
    const [r] = await Promise.all([api('/api/chat', body), sleep(650)]);
    t.remove();
    await render(r);
  } catch (e) { t.remove(); addMsg('⚠️ ' + esc(e.message), 'bot'); }
  busy = false;
  input.focus();
}

// Location bhejna (GPS ya dropdown) jab complaint chal rahi ho
async function sendLocation(userLabel, message, coords, type) {
  if (busy) return;
  busy = true;
  clearInteractive();
  addMsg(esc(userLabel), 'user');
  const t = typing();
  try {
    const [r] = await Promise.all([
      api('/api/chat', {message: message, coordinates: coords, location_type: type}), sleep(500)]);
    t.remove();
    await render(r);
  } catch (e) { t.remove(); addMsg('⚠️ ' + esc(e.message), 'bot'); }
  busy = false;
}

function clearInteractive() {
  box.querySelectorAll('.chips, .loc-picker').forEach(c => c.remove());
}

// ---------------------------------------------------------------- render server reply
async function render(r) {
  stage = r.stage || 'idle';
  if (r.analysis) showBrain(r.analysis);
  for (const m of r.messages) {
    addMsg(m, 'bot'); speak(m);
    await sleep(350);
  }
  if (r.done && r.done.lat != null && r.done.lng != null) {
    addMsg('📍 Location saved with your complaint — <a href="https://www.google.com/maps?q=' + r.done.lat + ',' + r.done.lng +
      '" target="_blank" rel="noopener">view on map</a>', 'bot');
    LOC_STATE = null;
  }
  if (r.card) showCard(r.card);
  if (r.chips && r.chips.length) showChips(r.chips);
  if (r.location_picker) showPicker();
}

function showChips(chips) {
  const w = document.createElement('div'); w.className = 'chips';
  chips.forEach(c => {
    const b = document.createElement('button'); b.textContent = c;
    b.onclick = () => {
      w.remove();
      if (c.startsWith('Open tracking: ')) { location.href = '/track/' + c.split(': ')[1]; return; }
      send(c);
    };
    w.appendChild(b);
  });
  box.appendChild(w); scrollDown();
}

// ---------------------------------------------------------------- location picker (📍 + area dropdown)
function showPicker() {
  box.querySelectorAll('.loc-picker').forEach(c => c.remove());
  const w = document.createElement('div'); w.className = 'loc-picker';
  w.innerHTML = '<button type="button" class="lp-gps">📍 My location</button>' +
    '<select class="lp-area"><option value="">— or choose an area —</option>' +
    AREAS.map(a => '<option value="' + esc(a[0]) + '">' + esc(a[0]) + '</option>').join('') + '</select>' +
    '<button type="button" class="lp-use">Use area</button>';
  w.querySelector('.lp-gps').onclick = captureAndSendLiveLocation;
  w.querySelector('.lp-use').onclick = () => {
    const name = w.querySelector('.lp-area').value;
    if (!name) { toast('Please choose an area first'); return; }
    const a = AREAS.find(x => x[0] === name);
    setLoc({lat: a[1], lng: a[2], source: 'dropdown'});
    sendLocation('🗺️ ' + name, name, {lat: a[1], lng: a[2]}, 'dropdown');
  };
  box.appendChild(w); scrollDown();
}

// ---------------------------------------------------------------- GPS button (chat.html ka 📍 MAP)
function captureAndSendLiveLocation() {
  const gpsBtn = document.getElementById('gpsBtn');
  if (!navigator.geolocation) { toast('This browser does not support GPS. Please choose an area instead.'); return; }
  if (gpsBtn) { gpsBtn.style.opacity = '0.6'; }
  navigator.geolocation.getCurrentPosition(pos => {
    if (gpsBtn) { gpsBtn.style.opacity = '1'; gpsBtn.classList.add('active-gps'); }
    const c = {
      lat: Number(pos.coords.latitude.toFixed(5)),
      lng: Number(pos.coords.longitude.toFixed(5)),
      accuracy: Math.round(pos.coords.accuracy || 0),
    };
    setLoc({lat: c.lat, lng: c.lng, source: 'gps', accuracy: c.accuracy});
    if (LOCATION_STAGES.includes(stage)) {
      // complaint chal rahi hai -> seedha location bhej do (message khali, server "Pinned location" naam rakhta hai)
      sendLocation('📍 Live location shared', '', c, 'Live GPS');
    } else {
      // abhi complaint shuru nahi hui -> GPS yaad rakho, agle message ke saath bhejenge
      pendingGeo = {coordinates: c, type: 'Live GPS'};
      document.getElementById('examples').style.display = 'none';
      addMsg('📍 Location mil gayi (±' + c.accuracy + ' m). Ab apni problem likhein ya bolein — main isi jagah ke saath darj kar dunga.', 'bot');
    }
  }, err => {
    if (gpsBtn) { gpsBtn.style.opacity = '1'; }
    const why = err && err.code === 1 ? 'Location permission denied. Please allow location access or choose an area.'
      : 'Could not get your location. Please choose an area instead.';
    toast(why);
  }, {enableHighAccuracy: true, timeout: 12000, maximumAge: 0});
}

// ---------------------------------------------------------------- summary card
function showCard(c) {
  if (c.lat != null && c.lng != null) setLoc({lat: c.lat, lng: c.lng, source: c.loc_source || 'dropdown'});
  const src = {gps: '📡 Live GPS', dropdown: '🗺️ Area from list', typed: '⌨️ Typed address'}[c.loc_source] || '⌨️ Typed address';
  const d = document.createElement('div'); d.className = 'summary-card';
  d.innerHTML = `<div class="top" style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); font-weight: bold;">📝 Complaint Summary</div>
    <table>
      <tr><td>Problem</td><td>${esc(c.description)}</td></tr>
      <tr><td>Location</td><td>📍 ${esc(c.location)}<div class="small muted">${src}${c.map_link ? ' · <a href="' + esc(c.map_link) + '" target="_blank" rel="noopener">open map</a>' : ''}</div></td></tr>
      <tr><td>AI category</td><td>${esc(c.category)} → <span style="color:#2a5298;"><b>${esc(c.subtype)}</b></span></td></tr>
      <tr><td>Department</td><td>🏢 ${esc(c.department)}</td></tr>
      <tr><td>Priority</td><td><span class="badge p-${esc(c.priority)}" style="padding: 4px 8px; border-radius: 6px; font-weight: bold;">${esc(c.priority)}</span> severity ${c.severity}/100</td></tr>
      <tr><td>Deadline</td><td>⏱️ within <b>${c.deadline_hours} hours</b></td></tr>
      ${c.duration ? `<tr><td>Issue duration</td><td>~${c.duration} hours</td></tr>` : ''}
    </table>
    <div class="acts" style="margin-top: 12px; display: flex; gap: 8px;"><button class="btn green" id="submitBtn" style="border-radius: 8px; font-weight: bold; background-color: #28a745;">✅ Submit</button>
      <button class="btn ghost" id="editBtn" style="border-radius: 8px;">✏️ Add detail</button>
      <button class="btn ghost" id="cancelBtn" style="border-radius: 8px;">✖</button></div>`;
  box.appendChild(d); scrollDown();

  d.querySelector('#submitBtn').onclick = async (e) => {
    e.target.disabled = true; e.target.textContent = 'Submitting…';
    try {
      const r = await api('/api/submit', {});
      d.querySelector('.acts').remove();
      box.querySelectorAll('.loc-picker').forEach(p => p.remove());
      markPipeline(8);
      const gpsBtn = document.getElementById('gpsBtn');
      if (gpsBtn) gpsBtn.classList.remove('active-gps');
      await render(r);
      confetti();
    } catch (err) { toast(err.message); e.target.disabled = false; e.target.textContent = '✅ Submit'; }
  };
  d.querySelector('#editBtn').onclick = () => {
    d.querySelector('.acts').remove();
    addMsg('Sure — type any extra detail and I will update the analysis. ✏️', 'bot'); input.focus();
  };
  d.querySelector('#cancelBtn').onclick = () => { d.querySelector('.acts').remove(); send('cancel'); };
}

// ---------------------------------------------------------------- AI brain panel
function ring(score, color) {
  const r = 34, c = 2 * Math.PI * r, off = c * (1 - score / 100);
  return `<svg width="90" height="90" viewBox="0 0 90 90"><circle cx="45" cy="45" r="${r}" stroke="#1c2d42" stroke-width="9" fill="none"/>
    <circle cx="45" cy="45" r="${r}" stroke="${color}" stroke-width="9" fill="none" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c}"
      transform="rotate(-90 45 45)" style="transition:stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1)" data-off="${off}"/>
    <text x="45" y="51" text-anchor="middle" fill="#fff" font-size="20" font-weight="800">${score}</text></svg>`;
}

const PRI_COLOR = {Critical: '#ff4d6a', High: '#ff8a3d', Medium: '#f5c030', Low: '#3dd68c'};
const STEPS = ['Language detected', 'Category classified (ML)', 'Sub-type identified', 'Location extracted', 'Duration understood',
  'Duplicate / repeat check', 'Severity scored', 'Department & deadline assigned', 'Ticket created'];

function markPipeline(n) {
  document.querySelectorAll('#pipe div').forEach((d, i) => d.classList.toggle('on', i <= n));
}

function showBrain(a) {
  const loc = a.location ? '📍 ' + esc(a.location) : '<span style="color:#ff8a3d; font-weight: bold;">missing → will ask you</span>';
  const dur = a.duration_hours != null
    ? `~${a.duration_hours} h ${a.duration_text ? '(“' + esc(a.duration_text) + '”)' : ''}`
    : '<span style="color:#718096">not mentioned</span>';
  const sim = a.similar_open.length
    ? `${a.similar_open.length} similar open complaint(s) in this area → priority boosted<br>` +
      a.similar_open.map(s => `<span class="kw" style="background:#2d3748; color:#fc8181;">${esc(s.id)} · ${s.similarity}% match</span>`).join('')
    : 'No open duplicates found in this area';
  const rep = a.similar_resolved.length
    ? `<div style="color:#ffb86b; margin-top:6px; font-weight: bold; animation: pulseGlow 2s infinite;">⚠️ Problem re-appeared after ${esc(a.similar_resolved[0].id)} was marked resolved</div>`
    : '';

  brain.innerHTML = `
    <div class="blk" style="margin-bottom: 16px;"><h5>Processing pipeline</h5><div class="pipeline" id="pipe">${STEPS.map(s => `<div>${s}</div>`).join('')}</div></div>
    <div class="blk" style="margin-bottom: 16px;"><h5>1 · Language</h5><div class="big" style="color: #63b3ed; font-weight: bold;">${esc(a.language_name)}</div></div>
    <div class="blk" style="margin-bottom: 16px;"><h5>2 · Classification (TF-IDF + keywords)</h5>
      ${a.top3.map(t => `<div class="row" style="margin-top: 4px;"><span>${esc(t.category)}</span><b>${t.prob}%</b></div><div class="bar" style="background: rgba(255,255,255,0.1); height: 6px; border-radius: 4px; overflow: hidden;"><i style="width:0; background: #63b3ed; display: block; height: 100%; transition: width 0.8s ease;" data-w="${t.prob}"></i></div>`).join('')}
      <div class="small" style="color:#a0aec0; margin-top: 8px;">Words that decided it:</div>
      <div style="display:flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;">
        ${(a.keywords.length ? a.keywords : ['(none)']).map(k => `<span class="kw" style="font-size: 11px; padding: 2px 6px;">${esc(k)}</span>`).join('')}
      </div>
    </div>
    <div class="blk" style="margin-bottom: 16px;"><h5>3 · Extracted details</h5>
      <div class="row"><span>Sub-type</span><b style="color:#48bb78">${esc(a.subtype)}</b></div>
      <div class="row"><span>Location</span><b>${loc}</b></div>
      <div class="row"><span>Duration</span><b>${dur}</b></div>
    </div>
    <div class="blk" style="margin-bottom: 16px;"><h5>4 · Duplicate / repeat check</h5><div class="small" style="color:#cbd5e0;">${sim}</div>${rep}</div>
    <div class="blk" style="margin-bottom: 16px;"><h5>5 · Severity score (0-100)</h5>
      <div class="gauge" style="display: flex; align-items: center; gap: 16px;">${ring(a.severity, PRI_COLOR[a.priority])}
        <div><div class="big" style="color:${PRI_COLOR[a.priority]}; font-weight: bold; font-size: 20px;">${esc(a.priority)}</div><div class="small" style="color:#a0aec0">Deadline: ${a.deadline_hours} h</div></div></div>
      ${a.breakdown.map(b => `<div class="row small" style="margin-top:8px;"><span>${esc(b.factor)}</span><b>${b.points}/${b.max}</b></div>
        <div class="bar" style="background: rgba(255,255,255,0.1); height: 4px; border-radius: 2px; overflow: hidden;"><i style="width:0; background: ${PRI_COLOR[a.priority]}; display: block; height: 100%; transition: width 0.8s ease;" data-w="${100 * b.points / b.max}"></i></div><div class="small" style="color:#a0aec0; margin-top:2px; font-size: 11px;">${esc(b.detail)}</div>`).join('')}
    </div>
    <div class="blk" style="margin-bottom: 4px;"><h5>6 · Routed to</h5><div class="big" style="color: #48bb78; font-weight: bold;">🏢 ${esc(a.department)}</div><div class="small" style="color:#a0aec0">Officer in charge: ${esc(a.officer)}</div></div>`;

  updateMapCard();

  requestAnimationFrame(() => setTimeout(() => {
    brain.querySelectorAll('.bar i').forEach(i => i.style.width = i.dataset.w + '%');
    brain.querySelectorAll('circle[data-off]').forEach(c => c.style.strokeDashoffset = c.dataset.off);
  }, 50));

  // pipeline ke steps ek-ek karke tick hote hain (location mila to 7 tak, nahi to 2 tak)
  const last = a.location ? 7 : 2;
  let i = -1;
  (function step() {
    i++;
    markPipeline(i);
    if (i < last) setTimeout(step, 140);
  })();
}

// ---------------------------------------------------------------- geo-tag map card (brain panel)
function setLoc(loc) {
  LOC_STATE = loc;
  updateMapCard();
}

function updateMapCard() {
  const old = brain.querySelector('.map-card-wrapper');
  if (old) old.remove();
  if (!LOC_STATE) return;
  const empty = brain.querySelector('.empty');
  if (empty) empty.remove();
  const l = LOC_STATE;
  const label = {gps: '📡 Live GPS', dropdown: '🗺️ Area from list', typed: '⌨️ Typed address'}[l.source] || '📍 Pinned';
  const wrap = document.createElement('div');
  wrap.className = 'map-card-wrapper';
  wrap.innerHTML = `<h5 style="margin:0; font-size:11.5px; letter-spacing:.08em; text-transform:uppercase; color:#8d95c7;">Geo-tag</h5>
    <div class="row" style="margin-top:6px;"><span>${label}</span><b>${Number(l.lat).toFixed(5)}, ${Number(l.lng).toFixed(5)}</b></div>
    ${l.accuracy ? `<div class="small" style="color:#a0aec0;">accuracy about ±${l.accuracy} m</div>` : ''}
    <div class="map-frame-sim"><div class="map-radar-pin"></div></div>
    <a class="small" style="color:#63b3ed; display:inline-block; margin-top:8px;" target="_blank" rel="noopener"
       href="https://www.google.com/maps?q=${l.lat},${l.lng}">🗺️ Open in Google Maps</a>`;
  brain.appendChild(wrap);
}

// ---------------------------------------------------------------- confetti after submit
function confetti() {
  const colors = ['#3b4bd8', '#f28c28', '#14995b', '#d7263d', '#7c4dff', '#0ea5e9', '#e7a008'];
  for (let n = 0; n < 60; n++) {
    const p = document.createElement('i');
    p.style.cssText = 'position:fixed;top:-12px;left:' + (Math.random() * 100) + 'vw;width:8px;height:12px;z-index:200;pointer-events:none;' +
      'background:' + colors[n % colors.length] + ';opacity:.95;transition:top 2.2s ease-in, transform 2.2s ease-in, opacity 2.2s;';
    document.body.appendChild(p);
    requestAnimationFrame(() => {
      p.style.top = '105vh';
      p.style.transform = 'translateX(' + ((Math.random() - .5) * 240) + 'px) rotate(' + (Math.random() * 720) + 'deg)';
      p.style.opacity = '0';
    });
    setTimeout(() => p.remove(), 2400);
  }
}

// ---------------------------------------------------------------- wiring: form, examples, language, speaker, mic
document.getElementById('composer').addEventListener('submit', e => { e.preventDefault(); send(input.value); });

document.querySelectorAll('#examples button').forEach(b => b.onclick = () => send(b.textContent));

document.querySelectorAll('.lang-toggle button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.lang-toggle button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  voiceLang = b.dataset.l;
});

document.getElementById('speakBtn').onclick = (e) => {
  speakOn = !speakOn;
  e.currentTarget.textContent = speakOn ? '🔊' : '🔇';
  if (!speakOn && window.speechSynthesis) speechSynthesis.cancel();
  toast(speakOn ? '🔊 Bot will read replies aloud' : '🔇 Voice replies off');
};

(function setupMic() {
  const mic = document.getElementById('mic');
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, listening = false;

  mic.onclick = () => {
    if (!SR) { toast('Voice input works in Google Chrome or Microsoft Edge. You can type instead.'); return; }
    if (listening && rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = voiceLang;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onstart = () => { listening = true; mic.classList.add('rec'); input.placeholder = '🎤 Listening… speak now / अब बोलिए'; };
    rec.onresult = ev => {
      let txt = '';
      for (let i = 0; i < ev.results.length; i++) txt += ev.results[i][0].transcript;
      input.value = txt;
      if (ev.results[ev.results.length - 1].isFinal) { send(txt); }
    };
    rec.onerror = ev => {
      if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') toast('Microphone permission denied.');
      else if (ev.error !== 'no-speech' && ev.error !== 'aborted') toast('Voice error: ' + ev.error);
    };
    rec.onend = () => {
      listening = false; mic.classList.remove('rec');
      input.placeholder = 'Apni samasya likhein ya MIC par click karke bolein...';
    };
    try { rec.start(); } catch (e) { /* already started */ }
  };
})();

// ---------------------------------------------------------------- start: bot greeting
(async function init() {
  try {
    const r = await api('/api/chat', {message: ''});
    await render(r);
  } catch (e) { addMsg('⚠️ ' + esc(e.message), 'bot'); }
})();