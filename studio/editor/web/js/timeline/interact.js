import { snapTime } from './snap.js';
import { GUTTER } from './render.js';
import { fmtShift, frame, el } from '../util.js';

export const PRE = { whoosh: 0.15, riser: 1.2, swipe: 0.1 };
const F = 1 / 30;

export function attachInteract(store, tl) {
  const ov = tl.overlay;
  let drag = null;
  const tip = el('div', { class: 'dragtip', hidden: true }), line = el('div', { class: 'snapline', hidden: true });
  ov.append(tip, line);
  const showSnap = (t, text) => { const x = GUTTER + tl.x(t); line.hidden = false; line.style.left = x + 'px'; tip.hidden = false; tip.style.left = x + 'px'; tip.textContent = text; };
  const hideSnap = () => { line.hidden = true; tip.hidden = true; };
  const edgesExcept = (ids) => { const out = []; for (const c of store.project.clips) if (!ids.includes(c.id) && (c.track === 'v1' || c.track === 'text')) out.push(c.start, c.start + c.dur); return out; };
  const snapOpts = (e, ids) => ({ words: store.words, edges: edgesExcept(ids), playhead: store.t, pps: store.ui.pps, disabled: e.metaKey });

  tl.body.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('.tg')) return;
    const ce = e.target.closest('.cl'), t = tl.tAt(e.clientX);
    if (!ce) { drag = { type: 'marquee', x0: e.clientX, y0: e.clientY, t0: t }; tl.body.setPointerCapture(e.pointerId); return; }
    const c = store.clip(ce.dataset.id); if (!c) return;
    const edge = e.target.closest('.edge');
    if (edge && c.track === 'v1') {
      const v1 = store.track('v1'), i = v1.findIndex((x) => x.id === c.id);
      const left = edge.classList.contains('l') ? v1[i - 1] : c, right = edge.classList.contains('l') ? c : v1[i + 1];
      if (!left || !right) return;
      drag = { type: 'cut', left, right, t0: right.start, ripple: e.altKey, target: left };
    } else if (edge && c.track !== 'voice') {
      drag = { type: 'trim', c, side: edge.classList.contains('l') ? 'l' : 'r' };
    } else {
      if (!store.sel.has(c.id) || e.metaKey || e.shiftKey) store.select([c.id], e.metaKey || e.shiftKey ? 'toggle' : 'set');
      drag = { type: 'maybe-move', c, x0: e.clientX, dt: t - c.start };
    }
    tl.body.setPointerCapture(e.pointerId);
  });

  tl.body.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const t = tl.tAt(e.clientX);
    if (drag.type === 'cut') {
      const lo = drag.left.start + F, hi = drag.right.start + drag.right.dur - F;
      const s = snapTime(Math.min(hi, Math.max(lo, t)), snapOpts(e, [drag.left.id, drag.right.id]));
      drag.t = frame(Math.min(hi, Math.max(lo, s.t))); drag.snap = s;
      const L = tl.clipEl(drag.left.id), R = tl.clipEl(drag.right.id);
      if (L) L.style.width = Math.max(2, (drag.t - drag.left.start) * store.ui.pps - 1) + 'px';
      if (R && !e.altKey) { R.style.left = tl.x(drag.t) + 'px'; R.style.width = Math.max(2, (drag.right.start + drag.right.dur - drag.t) * store.ui.pps - 1) + 'px'; }
      drag.ripple = e.altKey;
      showSnap(drag.t, `${s.kind === 'word' ? '«' + s.label + '» · ' : ''}${fmtShift(drag.t - drag.t0)}${e.altKey ? ' · пауза в голос' : ''}`);
    } else if (drag.type === 'maybe-move' && (drag.c.track !== 'voice' || drag.c.kind === 'audio') && Math.abs(e.clientX - drag.x0) > 4) {   // реплику голоса тоже можно сдвинуть (под губы), паузы — нет
      drag.type = 'move'; drag.ghost = tl.clipEl(drag.c.id);
    } else if (drag.type === 'move') {
      const c = drag.c, pre = c.track.startsWith('sfx') ? (PRE[c.tag] || 0) : 0;
      if (c.track === 'v1') { const over = document.elementFromPoint(e.clientX, e.clientY)?.closest('.cl.v1'); drag.over = over && over.dataset.id !== c.id ? over.dataset.id : null; tl.body.querySelectorAll('.cl.v1.drop').forEach((n) => n.classList.remove('drop')); if (drag.over) tl.clipEl(drag.over)?.classList.add('drop'); return; }
      const s = c.track === 'voice' ? { t: t - drag.dt, kind: null } : snapTime(t - drag.dt + pre, snapOpts(e, [c.id]));
      drag.start = Math.max(0, frame(s.t - pre)); drag.snap = s;
      if (c.track === 'voice') {       // голос: без прилипания и не внахлёст с соседними репликами
        const vs = store.track('voice').filter((x) => x.id !== c.id);
        const prev = vs.filter((x) => x.start < c.start).pop(), next = vs.find((x) => x.start > c.start);
        const lo = prev ? prev.start + prev.dur : 0, hi = next ? next.start - c.dur : Infinity;
        drag.start = frame(Math.min(hi, Math.max(lo, drag.start)));
      }
      drag.lane = c.track === 'voice' ? 'voice' : tl.laneAt(e.clientY);
      if (drag.ghost) drag.ghost.style.left = tl.x(drag.start) + 'px';
      showSnap(drag.start + pre, `${s.kind === 'word' ? '«' + s.label + '» · ' : ''}${fmtShift(drag.start - c.start)}`);
    } else if (drag.type === 'trim') {
      const s = snapTime(t, snapOpts(e, [drag.c.id])); drag.t = frame(s.t);
      showSnap(drag.t, s.kind === 'word' ? `«${s.label}»` : '');
    } else if (drag.type === 'marquee') {
      let m = ov.querySelector('.marquee'); if (!m) ov.append(m = el('div', { class: 'marquee' }));
      const R = tl.root.getBoundingClientRect();
      Object.assign(m.style, { left: Math.min(drag.x0, e.clientX) - R.left + 'px', top: Math.min(drag.y0, e.clientY) - R.top + 'px', width: Math.abs(e.clientX - drag.x0) + 'px', height: Math.abs(e.clientY - drag.y0) + 'px' });
      drag.t1 = t; drag.y1 = e.clientY;
    }
  });

  tl.body.addEventListener('pointerup', async (e) => {
    const d = drag; drag = null; hideSnap();
    ov.querySelector('.marquee')?.remove();
    tl.body.querySelectorAll('.cl.drop').forEach((n) => n.classList.remove('drop'));
    if (!d) return;
    try {
      if (d.type === 'cut' && d.t != null && Math.abs(d.t - d.t0) > 1e-6) {
        if (d.ripple) await store.dispatch([{ op: 'ripple', id: d.left.id, delta: frame(d.t - d.t0) }], { label: 'пауза' });
        else await store.dispatch([{ op: 'move_cut', left: d.left.id, right: d.right.id, t: d.t, anchor: d.snap && d.snap.kind === 'word' ? { word: d.snap.ref, lead: 0.12 } : null }], { label: 'склейка' });
      } else if (d.type === 'move' && d.c.track === 'v1' && d.over) {
        if (e.altKey) { const src = d.c; const f = {}; for (const k of ['kind', 'src', 'in', 'speed', 'reverse', 'fit', 'text', 'volume_db', 'mute', 'motion', 'transition']) f[k] = src[k] ?? null; await store.dispatch([{ op: 'set', id: d.over, fields: f }], { label: 'копия кадра' }); }
        else await store.dispatch([{ op: 'swap', a: d.c.id, b: d.over }], { label: 'обмен кадров' });
      } else if (d.type === 'move' && d.start != null) {
        const lane = d.lane && d.lane !== d.c.track && store.project.tracks.find((x) => x.id === d.lane)?.kind === store.project.tracks.find((x) => x.id === d.c.track)?.kind ? d.lane : undefined;
        const pre = d.c.track.startsWith('sfx') ? (PRE[d.c.tag] || 0) : 0;
        const anchor = d.snap && d.snap.kind === 'word' ? { word: d.snap.ref, lead: 0.12, ...(pre ? { pre } : {}) } : null;   // start = слово − lead − pre
        await store.dispatch([{ op: 'move', id: d.c.id, start: d.start, track: lane, anchor }], { label: 'перемещение' });
      } else if (d.type === 'trim' && d.t != null) {
        const c = d.c, end = c.start + c.dur;
        const fields = d.side === 'r' ? { dur: Math.max(F, d.t - c.start) } : { start: Math.min(d.t, end - F), dur: Math.max(F, end - d.t), ...(c.in != null ? { in: Math.max(0, c.in + (d.t - c.start)) } : {}) };
        await store.dispatch([{ op: 'set', id: c.id, fields }], { label: 'длина' });
      } else if (d.type === 'marquee' && d.t1 != null) {
        const a = Math.min(d.t0, d.t1), b = Math.max(d.t0, d.t1), top = Math.min(d.y0, d.y1), bot = Math.max(d.y0, d.y1);
        const ids = [];
        for (const [tr, lane] of tl.lanes) { const r = lane.getBoundingClientRect(); if (r.bottom < top || r.top > bot) continue; for (const c of store.track(tr)) if (c.start < b && c.start + c.dur > a) ids.push(c.id); }
        store.select(ids, e.metaKey ? 'add' : 'set');
      } else if (d.type === 'maybe-move') {
        store.setTime(tl.tAt(e.clientX));
      } else if (d.type === 'marquee') { store.select([]); store.setTime(tl.tAt(e.clientX)); }
    } catch (err) { /* ошибка уже показана через store 'error' */ }
    tl.render();
  });

  // красная линия: схватить (за линию или «шапку» на линейке) и тянуть — перемотка
  const clampT = (t) => Math.max(0, Math.min(store.duration(), t));
  const scrub = (e) => {
    e.preventDefault(); e.stopPropagation();
    tl.ph.classList.add('drag'); document.body.classList.add('scrubbing');
    const mv = (ev) => store.setTime(clampT(tl.tAt(ev.clientX)));
    const up = () => { tl.ph.classList.remove('drag'); document.body.classList.remove('scrubbing'); removeEventListener('pointermove', mv); removeEventListener('pointerup', up); };
    addEventListener('pointermove', mv); addEventListener('pointerup', up);
  };
  tl.ph.addEventListener('pointerdown', (e) => { if (e.button === 0) scrub(e); });

  // линейка: клик — перейти, протянуть — выделить отрезок и все клипы в нём на всех дорожках (как рамкой);
  // клик рядом с красной линией (±7 px) — схватить её
  tl.ruler.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    if (Math.abs(tl.x(store.t) - (tl.tAt(e.clientX) - store.ui.scroll) * store.ui.pps) <= 7) return scrub(e);
    const t0 = clampT(tl.tAt(e.clientX)); store.setTime(t0); store.setRange(null);
    let last = '';
    const base = e.metaKey ? [...store.sel] : [];              // с ⌘ — добавить к уже выделенному
    const mv = (ev) => {
      const t1 = tl.tAt(ev.clientX); if (Math.abs(t1 - t0) * store.ui.pps <= 4) return;
      const a = Math.min(t0, t1), b = Math.max(t0, t1);
      store.setRange([a, b]);
      const ids = store.project.clips.filter((c) => c.start < b - 1e-6 && c.start + c.dur > a + 1e-6).map((c) => c.id);
      const key = ids.join('|'); if (key !== last) { last = key; store.select([...new Set([...base, ...ids])]); }
    };
    const up = () => { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); };
    addEventListener('pointermove', mv); addEventListener('pointerup', up);
  });
  // клик по рамке правки — открыть её
  ov.addEventListener('click', (e) => { const r = e.target.closest('.rng b')?.parentElement; if (r) store.emit('openComment', r.dataset.comment); });
  // колесо: ⌘/Ctrl или жест — масштаб вокруг курсора, иначе прокрутка
  tl.root.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) tl.zoomAround(tl.tAt(e.clientX), Math.exp(-e.deltaY * 0.01));
    else store.setUi({ scroll: Math.max(0, store.ui.scroll + (e.deltaX || e.deltaY) / store.ui.pps) });
  }, { passive: false });
  // двойной клик по надписи — правка текста на месте
  tl.body.addEventListener('dblclick', (e) => {
    const ce = e.target.closest('.cl.text'); if (!ce) return;
    const c = store.clip(ce.dataset.id), sp = ce.firstChild;
    sp.contentEditable = 'true'; sp.style.pointerEvents = 'auto'; sp.focus();
    const done = async () => { sp.contentEditable = 'false'; sp.style.pointerEvents = ''; const text = sp.textContent.trim(); if (text && text !== c.text) await store.dispatch([{ op: 'set', id: c.id, fields: { text, words: store.kineticFor ? store.kineticFor(c, text) : c.words } }], { label: 'текст' }); };
    sp.addEventListener('blur', done, { once: true });
    sp.addEventListener('keydown', (k) => { if (k.key === 'Enter') { k.preventDefault(); sp.blur(); } });
  });

  // приём из панелей и Finder
  tl.body.addEventListener('dragover', (e) => { e.preventDefault(); const t = tl.tAt(e.clientX); const s = snapTime(t, { words: store.words, pps: store.ui.pps }); showSnap(s.t, s.kind === 'word' ? `«${s.label}»` : ''); });
  tl.body.addEventListener('dragleave', hideSnap);
  tl.body.addEventListener('drop', async (e) => {
    e.preventDefault(); hideSnap();
    const t = tl.tAt(e.clientX), lane = tl.laneAt(e.clientY), onClip = document.elementFromPoint(e.clientX, e.clientY)?.closest('.cl.v1');
    const raw = e.dataTransfer.getData('application/x-nick-asset');
    if (raw) {
      const a = JSON.parse(raw);
      if (a.type === 'sfx') {
        const pre = PRE[a.name] || 0, s = snapTime(t + pre, { words: store.words, pps: store.ui.pps });
        const track = lane === 'sfx2' ? 'sfx2' : 'sfx1';
        await store.dispatch([{ op: 'add', clip: { track, tag: a.name, src: a.src, start: Math.max(0, frame(s.t - pre)), dur: a.dur, volume_db: -9, ...(s.kind === 'word' ? { anchor: { word: s.ref, lead: 0.12, pre } } : {}) } }], { label: 'эффект' });
      } else if (a.type === 'music') api.openMusicChooser(a, t, e.clientX, e.clientY);
      else if (a.type === 'media' && onClip) await store.dispatch([{ op: 'set', id: onClip.dataset.id, fields: { src: a.src, kind: a.kind, in: a.kind === 'video' ? 0 : null } }], { label: 'замена картинки' });
      return;
    }
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f && onClip) {
      const c = store.clip(onClip.dataset.id);
      const up = await store.api.postRaw(`/api/upload?project=${store.pid}&shot=${encodeURIComponent(c.shot || c.id)}`, f, f.type || 'application/octet-stream', { 'X-Filename': encodeURIComponent(f.name) });
      await store.dispatch([{ op: 'set', id: c.id, fields: { src: up.src, kind: up.kind, in: up.kind === 'video' ? 0 : null } }], { label: 'новый файл' });
    }
  });

  const api = {
    async splitAtPlayhead() {
      const t = store.t;
      const target = [...store.sel].map((id) => store.clip(id)).find((c) => c && c.start < t && t < c.start + c.dur) || store.clipAt('v1', t);
      if (target) await store.dispatch([{ op: 'split', id: target.id, t }], { label: 'разрез' });
    },
    async removeSelected() {
      const ids = [...store.sel].filter((id) => { const c = store.clip(id); return c && c.track !== 'voice'; });
      if (ids.length) await store.dispatch(ids.map((id) => ({ op: 'remove', id })), { label: 'удаление' });
    },
    openMusicChooser(a, t, x, y) {
      const total = store.duration(), cur = store.clipAt('v1', t), chapter = cur && cur.chapter;
      const ch = store.track('v1').filter((c) => c.chapter === chapter);
      const modes = [
        ['на весь выпуск', 0, total],
        ['на эту главу', ch.length ? ch[0].start : t, ch.length ? ch[ch.length - 1].start + ch[ch.length - 1].dur : total],
        ...(store.range ? [['на выделенный отрезок', store.range[0], store.range[1]]] : []),
        ['отсюда до конца', t, total],
      ];
      store.emit('menu', { x, y, items: modes.map(([label, a0, b0]) => ({ label, run: () => store.dispatch([{ op: 'add', replace: true, clip: { track: 'music', src: a.src, start: frame(a0), dur: frame(b0 - a0), loop: true, fade_in: 0.5, fade_out: 0.8, volume_db: -17 } }], { label: 'музыка' }) })) });
    },
  };
  return api;
}
