// ⌘K — поиск по кадрам, словам, звукам/музыке и правкам — задача 16.
import { dialog, toast } from '../ui.js';
import { el, fmtTC, frame } from '../util.js';
import { PRE } from '../timeline/interact.js';

const TAGS = { shot: 'кадр', word: 'слово', sound: 'звук', music: 'музыка', comment: 'правка' };
const MAX = 30;

function collect(store, q) {
  q = q.trim().toLowerCase();
  if (!q) return [];
  const out = [];
  for (const c of store.project.clips) {
    if (c.track !== 'v1') continue;
    if (!`${c.shot || ''} ${c.id}`.toLowerCase().includes(q)) continue;
    out.push({ kind: 'shot', tc: fmtTC(c.start), label: `${c.shot || c.id} · ${c.id}`, clipId: c.id, t: c.start });
  }
  for (const w of store.words || []) {
    const tok = w[2];
    if (!tok || !String(tok).toLowerCase().includes(q)) continue;
    out.push({ kind: 'word', tc: fmtTC(w[0]), label: tok, t: w[0] });
  }
  for (const snd of (store.library.sounds || [])) {
    if (!snd.name.toLowerCase().includes(q)) continue;
    out.push({ kind: 'sound', label: snd.name, asset: snd });
  }
  for (const m of (store.library.music || [])) {
    if (!(m.name || '').toLowerCase().includes(q)) continue;
    out.push({ kind: 'music', label: m.name, asset: m });
  }
  for (const c of (store.review && store.review.comments) || []) {
    if (!(c.text || '').toLowerCase().includes(q)) continue;
    out.push({ kind: 'comment', label: c.text, id: c.id });
  }
  return out.slice(0, MAX);
}

async function activate(store, row, x, y, close) {
  if (row.kind === 'shot' || row.kind === 'word') {
    store.setTime(row.t);
    const clipId = row.clipId || (store.clipAt('v1', row.t) || {}).id;
    if (clipId) store.select([clipId]);
    window.NE.timeline && window.NE.timeline.ensureVisible(row.t);
    close();
  } else if (row.kind === 'sound') {
    const pre = PRE[row.asset.name] || 0, start = Math.max(0, frame(store.t - pre));
    try {
      await store.dispatch([{ op: 'add', clip: { track: 'sfx1', tag: row.asset.name, src: row.asset.src, start, dur: row.asset.dur, volume_db: -9 } }], { label: 'эффект' });
      toast('Эффект добавлен на красную линию', 'ok');
    } catch (e) { /* store уже показала ошибку через 'error' */ }
    close();
  } else if (row.kind === 'music') {
    close();
    window.NE.interact && window.NE.interact.openMusicChooser(row.asset, store.t, x, y);
  } else if (row.kind === 'comment') {
    close();
    store.emit('openComment', row.id);
  }
}

export function openSearch(store) {
  const input = el('input', { class: 'hsearch', type: 'search', placeholder: 'Кадр, слово, звук, музыка или правка…' });
  const list = el('div', { class: 'scroll', style: { maxHeight: '380px' } });
  const body = el('div', {}, input, list);
  let idx = 0, rows = [];

  function paint() {
    list.innerHTML = '';
    if (!rows.length) { list.append(el('div', { class: 'empty' }, input.value.trim() ? 'Ничего не найдено.' : 'Начните вводить запрос.')); return; }
    rows.forEach((r, i) => {
      list.append(el('div', { class: 'srow' + (i === idx ? ' on' : ''), onclick: (e) => activate(store, r, e.clientX, e.clientY, close) },
        el('span', { class: 'tag' }, TAGS[r.kind]), r.tc ? el('span', { class: 'tc' }, r.tc) : null, el('span', { class: 'tx' }, r.label)));
    });
  }
  function refresh() { rows = collect(store, input.value); idx = 0; paint(); }
  input.oninput = refresh;
  input.onkeydown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); if (rows.length) { idx = (idx + 1) % rows.length; paint(); } }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (rows.length) { idx = (idx - 1 + rows.length) % rows.length; paint(); } }
    else if (e.key === 'Enter') { e.preventDefault(); const r = rows[idx]; if (r) { const b = list.children[idx]?.getBoundingClientRect(); activate(store, r, b ? b.right : 0, b ? b.top : 0, close); } }
  };
  refresh();

  const { close } = dialog({ title: 'Поиск', body, ok: 'Закрыть', cancel: null, wide: true });
  setTimeout(() => input.focus(), 0);
  return close;
}
