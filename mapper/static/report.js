// Behaviour of the report page: tabs, collapsible duty cards, deep links and reviewer decisions.
// `RUN` ({slug, run_id}) is defined by the template right before this script.

// ---- main tabs (Overview / Duty results / Version comparison)
function mainTab(id) {
  document.querySelectorAll('.mtabs button').forEach(b => b.classList.toggle('on', b.dataset.main === id));
  document.querySelectorAll('.mpanel').forEach(p => p.classList.toggle('on', p.id === id));
}
document.querySelectorAll('.mtabs button').forEach(b => b.onclick = () => {
  mainTab(b.dataset.main);
  history.replaceState(null, '', '#' + b.dataset.main);
});

// ---- deep links (#duty-…, #el-…): open the right tab and card, then scroll
function followHash() {
  const id = decodeURIComponent(location.hash.slice(1));
  if (!id) return;
  const el = document.getElementById(id);
  if (!el) return;
  const panel = el.closest('.mpanel');
  if (panel) mainTab(panel.id);
  const card = el.closest('.duty');
  if (card) setCard(card, true);
  if (el === panel) window.scrollTo(0, 0); else el.scrollIntoView();
}
window.addEventListener('hashchange', followHash);

// ---- collapse / expand a duty card
function setCard(card, open) {
  card.classList.toggle('collapsed', !open);
  const b = card.querySelector('.toggle');
  const label = open ? 'Collapse' : 'Expand';
  b.title = label;
  b.setAttribute('aria-label', label);
  b.setAttribute('aria-expanded', open);
}
document.querySelectorAll('.duty .toggle').forEach(b => b.onclick = () => {
  const card = b.closest('.duty');
  setCard(card, card.classList.contains('collapsed'));
});

// ---- sub-tabs inside a duty card (Mapping / Evidence / Missing information / Sources checked)
document.querySelectorAll('.tabs').forEach(t => t.addEventListener('click', ev => {
  const b = ev.target.closest('button');
  if (!b) return;
  const section = t.parentElement;
  t.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
  section.querySelectorAll('.panel').forEach(p => p.classList.toggle('on', p.id === b.dataset.tab));
}));

// ---- reviewer decisions (stored by the local server)
const api = `/api/c/${RUN.slug}/runs/${RUN.run_id}/reviews`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const DECISION_CLASS = {confirmed: 'ok', rejected: 'bad', needs_clarification: 'warn'};

function show(data) {
  Object.entries(data).forEach(([key, d]) => {
    const c = d && d.current;
    if (!c) return;

    // overview table
    const ov = document.querySelector(`.ovrev[data-key="${key}"]`);
    if (ov) ov.innerHTML = `<small><b>${esc(c.label)}</b><br>${esc(c.reviewer)}${c.stale ? '<br><span class="stale">Re-review needed</span>' : ''}</small>`;

    // the "System proposal" label becomes the decision badge
    const pb = document.querySelector(`.proposal[data-key="${key}"]`);
    if (pb) {
      pb.className = 'badge ' + (c.stale ? 'bad' : (DECISION_CLASS[c.decision] || 'muted'));
      pb.textContent = c.stale ? `Re-review needed (was: ${c.label})` : `${c.label} by ${c.reviewer} · ${String(c.at).slice(0, 10)}`;
      pb.title = c.stale ? 'The system proposal changed after this decision' : (c.comment || 'Reviewer decision');
    }

    // the review box: current decision and history
    const box = document.querySelector(`.review[data-key="${key}"]`);
    if (!box) return;
    const stale = c.stale ? ' <span class="stale">Re-review needed – the proposal changed since this decision</span>' : '';
    const cur = box.querySelector('.curtxt');
    cur.innerHTML = `<b>${esc(c.label)}</b> by ${esc(c.reviewer)} on ${esc(c.at)}${c.comment ? ': “' + esc(c.comment) + '”' : ''}${stale}`;
    cur.classList.remove('muted');
    box.querySelector('.histbody').innerHTML = d.history.map(h =>
      `<div>${esc(h.at)} · ${esc(h.reviewer)} · <b>${esc(h.decision)}</b> ${esc(h.comment)} <small>(run ${esc(h.run_id)})</small></div>`).join('');
  });
}

function load() {
  fetch(api).then(r => r.json()).then(show).catch(() => {
    // opened as a file, without the server: reviews are not available
    document.querySelectorAll('.ovrev').forEach(x => x.innerHTML = '<small class="muted">needs the local server</small>');
    document.querySelectorAll('.review .curtxt').forEach(x => x.textContent = 'Reviews need the local server (python3 app.py).');
    document.querySelectorAll('.review button').forEach(b => b.disabled = true);
  });
}

document.querySelectorAll('.review').forEach(box => box.addEventListener('click', ev => {
  const b = ev.target.closest('button[data-d]');
  if (!b) return;
  const name = localStorage.getItem('reviewer') || prompt('Your name (stored with the decision):');
  if (!name) return;
  localStorage.setItem('reviewer', name);
  fetch(api, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({duty_id: box.dataset.duty, element_id: box.dataset.element, decision: b.dataset.d,
                          comment: box.querySelector('textarea').value, reviewer: name}),
  })
    .then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error); return j; }))
    .then(() => { box.querySelector('textarea').value = ''; load(); })
    .catch(err => alert('Could not save: ' + err.message));
}));

load();
followHash();
window.addEventListener('load', () => setTimeout(followHash, 0));
