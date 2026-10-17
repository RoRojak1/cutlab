import { fmtTC, thumbURL, el } from '../util.js';
import { drawVoice } from './waveform.js';

export const GUTTER = 164;          // колонка с названиями дорожек; то же число — в timeline.css (--gut)
const NAMES = { v1: 'Кадры', nick: 'Ник', text: 'Надписи', voice: 'Голос', music: 'Музыка', sfx1: 'Эффекты 1', sfx2: 'Эффекты 2' };
// значок дорожки: чтобы с одного взгляда было понятно, что где
const SV = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const TRACK_ICON = {
  v1: SV('<rect x="3.5" y="5.5" width="17" height="13" rx="2.2"/><path d="m4 16 4.4-4.2a1.5 1.5 0 0 1 2 0L15 16.3"/><circle cx="15.3" cy="10" r="1.4"/>'),
  nick: SV('<circle cx="12" cy="8.6" r="3.6"/><path d="M5 19.5c.8-3.5 3.6-5.3 7-5.3s6.2 1.8 7 5.3"/>'),
  text: SV('<path d="M5.5 7.5V5h13v2.5M12 5v14M9 19h6"/>'),
  voice: SV('<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.8 11.5a6.2 6.2 0 0 0 12.4 0M12 17.7v2.8"/>'),
  music: SV('<path d="M9 17.5V6l10-2v11.5"/><circle cx="6.8" cy="17.5" r="2.3"/><circle cx="16.8" cy="15.5" r="2.3"/>'),
  sfx: SV('<path d="M12 3.5 13.9 10 20.5 12l-6.6 2L12 20.5 10.1 14 3.5 12l6.6-2Z"/>'),
};
// вкл/выкл: глаз — для картинки (кадры, Ник, надписи), динамик — для звука
const EYE = SV('<path class="on" d="M2.8 12s3.4-6.2 9.2-6.2 9.2 6.2 9.2 6.2-3.4 6.2-9.2 6.2S2.8 12 2.8 12Z"/><circle class="on" cx="12" cy="12" r="2.7"/><path class="off" d="M4 12s3-5.2 8-5.2 8 5.2 8 5.2-3 5.2-8 5.2S4 12 4 12ZM4.5 19.5l15-15"/>');
const SPK = SV('<path d="M4 9.5h3.2L11.5 6v12l-4.3-3.5H4Z"/><path class="on" d="M15 9.2a4 4 0 0 1 0 5.6M17.6 6.8a7.3 7.3 0 0 1 0 10.4"/><path class="off" d="m15.2 9.5 5 5M20.2 9.5l-5 5"/>');

export class Timeline {
  constructor(store, root) {
    this.s = store; this.root = root; this.lanes = new Map(); this.pool = new Map(); this.q = false; this.GUTTER = GUTTER;
    root.innerHTML = '';
    this.ruler = el('div', { class: 'tl-ruler' }, this.rc = el('canvas'));
    this.body = el('div', { class: 'tl-body' });
    this.words = el('canvas', { class: 'tl-words' });
    // рамки правок и выделение отрезка — в своём слое, обрезанном по области дорожек (не залезают на названия дорожек)
    this.overlay = el('div', { class: 'tl-ov' }, this.ovc = el('div', { class: 'tl-ovc' }), this.ph = el('div', { class: 'ph', 'data-tip': 'Тяните, чтобы перемотать' }));
    root.append(this.ruler, this.body, this.overlay);
    for (const tr of store.project.tracks) {
      const lane = el('div', { class: 'lane' });
      const visual = ['v1', 'nick', 'text'].includes(tr.id);
      const ico = el('span', { class: 'ti' }); ico.innerHTML = TRACK_ICON[tr.id.startsWith('sfx') ? 'sfx' : tr.id] || TRACK_ICON.sfx;
      const off = el('button', { class: 'tg eye', 'data-tg': 'off' }); off.innerHTML = visual ? EYE : SPK;
      const solo = el('button', { class: 'tg solo', 'data-tg': 'solo', 'data-tip': visual ? 'Соло — показывать только эту дорожку' : 'Соло — слушать только эту дорожку' }, 'S');
      const row = el('div', { class: `trk ${tr.kind === 'voice' ? 'voice' : ''}`, 'data-track': tr.id },
        el('div', { class: 'nm' }, ico, el('span', { class: 'tn' }, NAMES[tr.id] || tr.name), off, solo),
        lane);
      if (tr.kind === 'voice') lane.append(this.wave = el('canvas', { class: 'wave' }));
      this.body.append(row);
      this.lanes.set(tr.id, lane);
    }
    this.body.addEventListener('click', (e) => {
      const b = e.target.closest('.tg'); if (!b) return;
      const tr = b.closest('.trk').dataset.track, ui = this.s.ui;
      if (b.dataset.tg === 'off') this.s.setUi({ off: { ...ui.off, [tr]: !ui.off[tr] } });
      else this.s.setUi({ solo: ui.solo === tr ? null : tr });
    });
    for (const ev of ['project', 'sel', 'range', 'ui', 'review', 'words']) store.on(ev, () => this.render());
    // время идёт каждый кадр (игра, перемотка) — двигаем только красную линию, таймлайн целиком не перерисовываем
    store.on('time', () => this.playhead());
    // размеры меряем только при изменении окна: чтение clientWidth каждый кадр заставляло браузер пересчитывать всю страницу
    this._rw = root.clientWidth;
    new ResizeObserver(() => { this._rw = root.clientWidth; this._geo = null; this.render(); }).observe(root);
    this.render();
  }
  get laneW() { return Math.max(100, this._rw - GUTTER - 10); }
  x(t) { return (t - this.s.ui.scroll) * this.s.ui.pps; }
  tAt(clientX) { const r = this.root.getBoundingClientRect(); return this.s.ui.scroll + (clientX - r.left - GUTTER) / this.s.ui.pps; }
  laneAt(clientY) { for (const [id, lane] of this.lanes) { const r = lane.parentElement.getBoundingClientRect(); if (clientY >= r.top && clientY < r.bottom) return id; } return null; }
  clipEl(id) { return this.pool.get(id) || null; }
  zoomAround(t, f) { const ui = this.s.ui, pps = Math.min(600, Math.max(2, ui.pps * f)); const px = (t - ui.scroll) * ui.pps; this.s.setUi({ pps, scroll: Math.max(0, t - px / pps) }); }
  scrollTo(t) { this.s.setUi({ scroll: Math.max(0, t) }); }
  ensureVisible(t) { const w = this.laneW / this.s.ui.pps, sc = this.s.ui.scroll; if (t < sc || t > sc + w * 0.92) this.scrollTo(t - w * 0.25); }
  render() { if (this.q) return; this.q = true; requestAnimationFrame(() => { this.q = false; this._render(); }); }
  playhead() {
    const s = this.s, t0 = s.ui.scroll, t1 = t0 + this.laneW / s.ui.pps;
    const left = (GUTTER + this.x(s.t)) + 'px', disp = s.t >= t0 && s.t <= t1 ? '' : 'none';
    if (this.ph.style.left !== left) this.ph.style.left = left;
    if (this.ph.style.display !== disp) this.ph.style.display = disp;
  }

  _render() {
    const s = this.s, ui = s.ui, t0 = ui.scroll, t1 = t0 + this.laneW / ui.pps, seen = new Set();
    for (const [trId, lane] of this.lanes) {
      lane.parentElement.classList.toggle('off', !!ui.off[trId] || (ui.solo && ui.solo !== trId));
      const offBtn = lane.parentElement.querySelector('[data-tg=off]');
      offBtn.classList.toggle('on', !ui.off[trId]); offBtn.dataset.tip = ui.off[trId] ? 'Включить дорожку' : 'Выключить дорожку';
      lane.parentElement.querySelector('[data-tg=solo]').classList.toggle('on', ui.solo === trId);
      for (const c of s.track(trId)) {
        if (c.start > t1 + 1 || c.start + c.dur < t0 - 1) continue;
        seen.add(c.id);
        let e = this.pool.get(c.id);
        if (!e || e.parentElement !== lane) { e?.remove(); e = this.make(c); lane.append(e); this.pool.set(c.id, e); }
        this.update(e, c);
      }
    }
    for (const [id, e] of this.pool) if (!seen.has(id)) { e.remove(); this.pool.delete(id); }
    const vc = s.track('voice');
    if (this.voiceColor == null) this.voiceColor = getComputedStyle(document.documentElement).getPropertyValue('--c-voice');
    if (this.wave) drawVoice(this.wave, vc, t0, t1, this.voiceColor);
    this.drawRuler(t0, t1);
    this.drawWords(t0, t1);
    this.drawOverlay(t0, t1);
  }
  make(c) {
    const kind = c.track === 'v1' ? 'v1' : c.track.startsWith('sfx') ? 'sfx' : c.kind === 'pause' ? 'pause' : c.track;
    const e = el('div', { class: `cl ${kind}`, 'data-id': c.id }, el('span'), el('div', { class: 'edge l' }), el('div', { class: 'edge r' }));
    if (c.track === 'music') e.append(el('div', { class: 'fade in' }), el('div', { class: 'fade out' }));
    return e;
  }
  update(e, c) {
    const pps = this.s.ui.pps;
    const left = this.x(c.start) + 'px', width = Math.max(2, c.dur * pps - 1) + 'px';
    if (e.style.left !== left) e.style.left = left;
    if (e.style.width !== width) e.style.width = width;
    e.classList.toggle('sel', this.s.sel.has(c.id));
    const label = c.track === 'v1' ? (c.shot || c.id) : c.track === 'text' ? c.text : c.track === 'nick' ? 'Ник' : c.track === 'music' ? (c.src || '').split('/').pop().replace(/\.\w+$/, '') : c.tag || (c.src || '').split('/').pop().replace(/\.\w+$/, '') ;
    const sp = e.firstChild; if (sp.textContent !== (label || '')) sp.textContent = c.track === 'voice' ? '' : (label || '');
    if (c.track === 'v1' && e._src !== (c.src || '')) { e._src = c.src || ''; e.style.backgroundImage = c.src ? `url("${thumbURL(c.src, 160)}")` : ''; }   // обмен/замена картинки
    if (c.track === 'music') { e.querySelector('.fade.in').style.width = (c.fade_in || 0) * pps + 'px'; e.querySelector('.fade.out').style.width = (c.fade_out || 0) * pps + 'px'; }
    e.classList.toggle('missing', !!(this.s.problems && this.s.problems.has(c.id)));
  }
  drawRuler(t0, t1) {
    const cv = this.rc, dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    const nw = Math.round(w * dpr), nh = Math.round(h * dpr);
    if (cv.width !== nw || cv.height !== nh) { cv.width = nw; cv.height = nh; }
    const ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#80848b'; ctx.strokeStyle = '#3a3a40'; ctx.font = '10px ui-monospace, Menlo, monospace';
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
    const step = steps.find((x) => x * this.s.ui.pps >= 70) || 600;
    for (let t = Math.floor(t0 / step) * step; t < t1; t += step) {
      const x = (t - t0) * this.s.ui.pps;
      ctx.beginPath(); ctx.moveTo(x + 0.5, h - 6); ctx.lineTo(x + 0.5, h); ctx.stroke();
      ctx.fillText(fmtTC(t).replace(/\.00$/, ''), x + 3, 12);
    }
  }
  drawWords(t0, t1) {
    const vl = this.lanes.get('voice'); if (!vl) return;
    if (!this._geo) { const r = vl.parentElement.getBoundingClientRect(), R = this.root.getBoundingClientRect(); this._geo = { top: (r.top - R.top - 1) + 'px' }; }
    if (this.words.style.top !== this._geo.top) this.words.style.top = this._geo.top;
    // canvas — replaced element: with only left/right and auto width it does NOT stretch
    // to fill the gap (used width falls back to height × intrinsic aspect ratio), so give
    // it an explicit width matching the lane area or it stays pinned near GUTTER width.
    this.words.style.width = this.laneW + 'px';
    if (!this.words.parentElement) this.root.append(this.words);
    const cv = this.words, dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    const nw = Math.round(w * dpr), nh = Math.round(h * dpr);
    if (cv.width !== nw || cv.height !== nh) { cv.width = nw; cv.height = nh; }
    const ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (this.s.ui.pps < 40) return;
    ctx.font = '9.5px Inter, system-ui'; ctx.fillStyle = '#b8bcc2';
    let lastX = -99;
    for (const [t, , tok] of this.s.words) {
      if (t < t0 || t > t1) continue;
      const x = (t - t0) * this.s.ui.pps;
      if (x < lastX + 4) continue;
      ctx.fillText(tok, x, 10); lastX = x + ctx.measureText(tok).width;
    }
  }
  drawOverlay(t0, t1) {
    const s = this.s;
    this.playhead();
    // рамки правок пересобираем, только если поменялись правки, отрезок или вид
    const key = [t0, s.ui.pps, s.range && s.range.join()].join('|');
    if (this._ovReview === s.review && this._ovKey === key) return;
    this._ovReview = s.review; this._ovKey = key;
    const box = this.ovc; box.querySelectorAll('.rng,.selrng').forEach((n) => n.remove());
    for (const c of (s.review && s.review.comments) || []) {
      if (!c.range || !['new', 'working', 'reopened', 'question'].includes(c.status)) continue;
      const [a, b] = c.range; if (b < t0 || a > t1) continue;
      const d = el('div', { class: `rng ${c.status}`, 'data-comment': c.id, style: { left: this.x(a) + 'px', width: Math.max(4, (b - a) * s.ui.pps) + 'px' } }, el('b', { 'data-tip': 'Открыть правку' }, '💬'));
      box.append(d);
    }
    if (s.range) box.append(el('div', { class: 'selrng', style: { left: this.x(s.range[0]) + 'px', width: (s.range[1] - s.range[0]) * s.ui.pps + 'px' } }));
  }
}
