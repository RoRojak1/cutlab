// Кадр: фон/видео/карточка + Ник (хромакей) + надписи. Порт геометрии из studio/capcut/render.py
// (motion/outer) и studio/app.js:955-1210 (renderFrame/chromaKey/MX).
import { assetURL, clamp, el } from '../util.js';
import { levelScale } from './mix.js';

const W = 1920, H = 1080, ZOOM = 0.06, POOL = 10;   // POOL — сколько <video> держим загруженными
const ease = (x) => 1 - Math.pow(1 - clamp(x, 0, 1), 3);

export function motion(m, p, t) {
  if (m === 'zoom_in') return [1 + ZOOM * p, 0, 0, 0];
  if (m === 'zoom_out') return [1 + ZOOM - ZOOM * p, 0, 0, 0];
  if (m === 'pan_left') return [1 + ZOOM + 0.01, (-2.5 + 5 * p) / 100, 0, 0];
  if (m === 'pan_right') return [1 + ZOOM + 0.01, (2.5 - 5 * p) / 100, 0, 0];
  if (m === 'pan_up') return [1 + ZOOM + 0.01, 0, (-2.5 + 5 * p) / 100, 0];
  if (m === 'pan_down') return [1 + ZOOM + 0.01, 0, (2.5 - 5 * p) / 100, 0];
  if (m === 'shake') { const n = (k) => Math.sin(t * 37 * k) * 0.6 + Math.sin(t * 91 * k + 1.3) * 0.4; return [1.06, n(1) * 0.9 / 100, n(1.37) * 0.7 / 100, n(0.71) * 0.5]; }
  return [1, 0, 0, 0];
}
export function outer(tr, lt) {
  const o = { s: 1, tx: 0, ty: 0, blur: 0, veil: null, va: 0, gk: null };
  if (tr === 'slide' && lt < 0.3) o.tx = 1 - ease(lt / 0.3);
  else if (tr === 'whoosh' && lt < 0.28) { const k = 1 - ease(lt / 0.28); o.tx = k * 0.35; o.blur = k * 28; }
  else if (tr === 'zoom_punch' && lt < 0.25) o.s = 1 + 0.22 * Math.pow(1 - lt / 0.25, 2);
  else if (tr === 'glitch' && lt < 0.35) { o.gk = Math.floor(lt * 40); o.tx = (((o.gk * 37) % 13) - 6) * 2 / W; o.ty = (((o.gk * 17) % 7) - 3) * 2; }
  if (tr === 'flash' && lt < 0.3) { o.veil = '#fff'; o.va = 1 - lt / 0.3; }
  if (tr === 'dip_black' && lt < 0.4) { o.veil = '#000'; o.va = 1 - lt / 0.4; }
  return o;
}
export function chromaKey(d) {          // из studio/app.js:1040 — мягкий край + подавление зелёного
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2], m = r > b ? r : b, diff = g - m;
    if (diff > 70 && g > 90) d[i + 3] = 0;
    else if (diff > 22) { d[i + 3] = 255 * (1 - (diff - 22) / 48); d[i + 1] = m; }
    else if (diff > 0) d[i + 1] = m + diff * 0.4;
  }
}
function drawFit(ctx, src, fit, sw, sh) {
  const sc = fit === 'fit' ? Math.min(W / sw, H / sh) : Math.max(W / sw, H / sh), w = sw * sc, h = sh * sc;
  ctx.drawImage(src, (W - w) / 2, (H - h) / 2, w, h);
}
function drawFitSmall(ctx, v) { const sc = Math.max(640 / v.videoWidth, 360 / v.videoHeight), w = v.videoWidth * sc, h = v.videoHeight * sc; ctx.drawImage(v, (640 - w) / 2, (360 - h) / 2, w, h); }

export class Viewer {
  constructor(store, canvas, overlay) {
    this.s = store; this.cv = canvas; this.ctx = canvas.getContext('2d'); this.ov = overlay;
    this.imgs = new Map(); this.vids = new Map();
    // WebKit (Cutlab.app) в энергосбережении пускает play() у <video> только из жеста пользователя: новый элемент,
    // созданный во время игры, получал NotAllowedError, стоял на паузе, а syncVideo догонял его перемоткой раз в 0,25 с —
    // ролики шли слайд-шоу ~4 к/с. Элемент, которому хоть раз сделали play() в жесте, дальше играет и после смены src,
    // поэтому держим пул и «разблокируем» его на любом клике/клавише, а новые ролики грузим в свободные элементы пула.
    this.pool = Array.from({ length: POOL }, () => this.newVideo());
    const unlock = () => this.unlock();
    addEventListener('pointerdown', unlock, true); addEventListener('keydown', unlock, true);
    this.kw = document.createElement('canvas'); this.kw.width = 640; this.kw.height = 360; this.kctx = this.kw.getContext('2d', { willReadFrequently: true });
    this.textEls = new Map();
    store.on('project', ({ changed }) => {
      // changed пуст — правка файла, откат версии, настройки: какие надписи поменялись, неизвестно — сбросить все
      const ids = changed && changed.length ? changed : [...this.textEls.keys()];
      for (const id of ids) { const e = this.textEls.get(id); if (e) { e.remove(); this.textEls.delete(id); } }
    });
  }
  // Предпросмотр варианта из «Правок»: на месте клипа рисуется другой файл, проект не меняется.
  setPreview(p, label = '') {
    this.preview = p;
    if (!this.pvBadge) {
      this.pvBadge = el('div', { class: 'pvbadge' }, el('span', {}), el('button', { 'data-tip': 'Снять предпросмотр', onclick: () => this.setPreview(null) }, '✕'));
      this.ov.append(this.pvBadge);
    }
    this.pvBadge.hidden = !p;
    this.pvBadge.firstChild.textContent = p ? `предпросмотр: ${label}` : '';
    this.s.emit('preview', p);
    this.draw(this.s.t);
  }
  img(src) {
    const u = assetURL(src);                       // ключ с версией файла: перерендер под тем же именем — новая картинка
    let i = this.imgs.get(u);
    if (!i) { i = new Image(); i.onload = () => { if (!this.playing) this.draw(this.s.t); }; i.src = u; this.imgs.set(u, i); }
    if (!i._bm && !i._bmq && !i._bmBad) this.bitmap(i, src);
    i._used = performance.now();
    return i;
  }
  // Картинку заранее (warmNext — за 3 с) декодирует и уменьшает под кадр воркер (imgworker.js): первый drawImage
  // большой картинки (4K JPEG, PNG) WebKit делал прямо в кадре — рывок 40–250 мс на склейке, а createImageBitmap
  // на странице тоже синхронный. Пока битмапа нет (перемотка на паузе) — рисуем саму картинку. Держим 8 (~10 МБ каждая).
  bitmap(i, src) {
    if (!this.iw) {
      try { this.iw = new Worker(new URL('./imgworker.js', import.meta.url)); } catch (e) { this.iw = null; }
      if (!this.iw) { i._bmBad = true; return; }
      this.iwq = new Map();
      this.iw.onmessage = ({ data }) => { const cb = this.iwq.get(data.id); this.iwq.delete(data.id); if (cb) cb(data); };
      this.iw.onerror = () => { for (const cb of this.iwq.values()) cb({}); this.iwq.clear(); };
    }
    const id = (this.iwn = (this.iwn || 0) + 1);
    i._bmq = true;
    this.iwq.set(id, ({ bm }) => {
      i._bmq = false;
      if (!bm) { i._bmBad = true; return; }
      i._bm = bm;
      const live = [...this.imgs.values()].filter((x) => x._bm).sort((a, b) => b._used - a._used);
      for (const x of live.slice(8)) { x._bm.close(); x._bm = null; }
      if (!this.playing) this.draw(this.s.t);        // во время игры рисует transport; draw() без playing поставил бы ролик на паузу
    });
    this.iw.postMessage({ id, url: new URL(assetURL(src), location.href).href, w: W * 1.08, h: H * 1.08 });   // запас на наезд
  }
  // Кадры (v1) с одним и тем же файлом делят ОДИН <video>: соседние отрезки одного ролика (3D-блок, 7 битов)
  // идут без перемотки и без чёрного кадра на стыке. Ник и прочее — отдельный элемент на клип.
  vkey(src, id, track) { const u = assetURL(src); return track === 'v1' ? 'v1|' + u : id + '|' + u; }
  newVideo() {
    const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.preload = 'auto';
    // на паузе кадр готов только после перемотки — дорисовать (во время игры рисует transport каждый кадр).
    // Один раз на момент для каждого события — без цикла перемоток; общий флаг терял 'seeked' после 'loadeddata' (чёрный кадр)
    const redraw = (e) => { const k = '_at_' + e.type; if (!this.playing && v[k] !== this.s.t) { v[k] = this.s.t; this.draw(this.s.t); } };
    v.addEventListener('seeked', redraw); v.addEventListener('loadeddata', redraw);
    return v;
  }
  // вызывать только из жеста (клик, клавиша, пуск): play()+pause() снимает с элемента запрет WebKit навсегда
  unlock() {
    if (navigator.userActivation && !navigator.userActivation.isActive) return;
    for (const v of this.pool) {
      if (v._ok) continue;
      const was = v.paused;
      try { const p = v.play(); if (p) p.catch((e) => { if (e.name === 'NotAllowedError') v._ok = false; }); if (was) v.pause(); v._ok = true; } catch (e) { /* без src WebKit иногда шумит — не важно */ }   // AbortError от pause() — это норма
    }
  }
  vid(src, id, track) {
    const key = this.vkey(src, id, track);
    let v = this.vids.get(key);
    if (!v) { v = this.take(); v._at_seeked = v._at_loadeddata = null; v.src = assetURL(src); this.stale(v); this.vids.set(key, v); }
    v._used = performance.now();
    return v;
  }
  // элемент под новый ролик: свободный из пула, иначе самый давний на паузе (каждый ролик с полной предзагрузкой
  // держать нельзя — после прогона их копились десятки и грузили память и декодер); src меняем, элемент не выбрасываем
  take() {
    const busy = new Set(this.vids.values());
    const free = this.pool.find((x) => !busy.has(x)); if (free) return free;
    let old = null;
    for (const [k, v] of this.vids) if (v.paused && (!old || (v._used || 0) < (old[1]._used || 0))) old = [k, v];
    if (old) { this.vids.delete(old[0]); return old[1]; }
    const v = this.newVideo(); this.pool.push(v); return v;     // все играют — запасной (до следующего жеста может не пойти)
  }
  syncVideo(v, want, playing, speed, loop) {
    if (loop && v.duration) want = want % Math.max(0.1, v.duration - 0.05);
    if (playing) {
      if (v.playbackRate !== (speed || 1)) v.playbackRate = speed || 1;
      // play() — один запрос за раз, не каждый кадр; отказ не глотаем молча
      if (v.paused && !v._req) {
        v._req = true;
        v.play().then(() => { v._ok = true; }, (e) => { if (e.name === 'NotAllowedError' && !this._warned) { this._warned = true; console.warn('Cutlab: браузер не дал запустить видео без клика — ролик пойдёт рывками до следующего клика/клавиши'); } })
          .finally(() => { v._req = false; });
      }
      if (Math.abs(v.currentTime - want) > 0.25) this.seek(v, want);
    } else { if (!v.paused) v.pause(); if (Math.abs(v.currentTime - want) > 0.02) this.seek(v, want); }
  }
  seek(v, t) { v.currentTime = t; this.stale(v); }
  // После перемотки/смены файла кадр рисуем, только когда он реально готов (requestVideoFrameCallback): WebKit отдаёт
  // 'seeked' раньше кадра, а drawImage такого ролика ждал до 1 с (тяжёлые 3D, ключевой кадр раз в 8 с) — вставало всё
  // окно; пока держим предыдущий кадр. На паузе заодно дорисовываем (раньше мог остаться чёрный экран). Страховка — 1,5 с.
  stale(v) {
    if (!v.requestVideoFrameCallback) return;
    v._fresh = false; clearTimeout(v._ft);
    const ok = () => { v._fresh = true; clearTimeout(v._ft); if (!this.playing) this.draw(this.s.t); };
    v._ft = setTimeout(ok, 1500);
    if (v._rvfc) return;
    const cb = () => { v._rvfc = 0; if (v.seeking) v._rvfc = v.requestVideoFrameCallback(cb); else if (!v._fresh) ok(); };
    v._rvfc = v.requestVideoFrameCallback(cb);
  }
  draw(t, playing = false) {
    const t0 = performance.now();
    if (this.subs) this.subs.update(t);               // русские субтитры для просмотра (subs.js)
    this.playing = playing;
    const ctx = this.ctx, pv = this.preview;
    let c = this.s.clipAt('v1', t);
    if (c && pv && pv.clip === c.id) c = { ...c, src: pv.src, kind: pv.kind, in: pv.kind === 'video' ? 0 : c.in, speed: pv.kind === 'video' ? 1 : c.speed, reverse: false };
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.filter = 'none'; ctx.globalAlpha = 1; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    const curKey = c && c.kind === 'video' && c.src ? this.vkey(c.src, c.id, 'v1') : null;
    for (const [k, v] of this.vids) if (!v.paused && k !== curKey && !k.startsWith('nick-')) v.pause();
    if (!c) { this.drawText(t); this._perf(t0); return; }
    const lt = t - c.start, p = clamp(lt / c.dur, 0, 1), [sm, txm, tym, rot] = motion(c.motion, p, t), o = outer(c.transition, lt);
    ctx.save();
    ctx.translate(W / 2 + o.tx * W, H / 2 + o.ty); ctx.scale(sm * o.s, sm * o.s); ctx.rotate(rot * Math.PI / 180); ctx.translate(-W / 2 + txm * W, -H / 2 + tym * H);
    const f = [];
    if (o.blur > 0.5) f.push(`blur(${o.blur}px)`);
    if (o.gk != null) f.push(`hue-rotate(${(o.gk * 97) % 360}deg) saturate(2.2) contrast(1.3)`);
    ctx.filter = f.join(' ') || 'none';
    if (c.kind === 'image' && c.src) { const i = this.img(c.src), b = i._bm; if (b) drawFit(ctx, b, c.fit, b.width, b.height); else if (i.complete && i.naturalWidth) drawFit(ctx, i, c.fit, i.naturalWidth, i.naturalHeight); this.lastFrame(); }
    else if (c.kind === 'video' && c.src) {
      const v = this.vid(c.src, c.id, 'v1'), sp = c.speed || 1;
      const want = c.reverse ? (c.in || 0) + Math.max(0, (c.dur - lt)) * sp : (c.in || 0) + lt * sp;
      this.syncVideo(v, want, playing && !c.reverse, sp, false);
      v.muted = !!c.mute || !!this.s.ui.off.v1 || (this.s.ui.solo && this.s.ui.solo !== 'v1') || (this.s.audioLang && this.s.audioLang !== 'en');   // в дубляже звук роликов уже в дорожке
      v.volume = Math.min(1, Math.pow(10, (c.volume_db ?? -22) / 20) * levelScale(this.s.project, 'video'));
      // кадр не готов (загрузка, перемотка — см. stale) — держим предыдущий, а не чёрный экран
      if (v.readyState >= 2 && !v.seeking && v._fresh !== false) { drawFit(ctx, v, c.fit, v.videoWidth, v.videoHeight); this.lastFrame(); }
      else this.drawLast(ctx);
    } else if (c.kind === 'card') this.drawCard(ctx, c.text || '');
    const n = this.s.clipAt('nick', t);
    if (n && n.src) {
      const v = this.vid(n.src, n.id); this.syncVideo(v, t - n.start, playing, 1, true);
      if (v.readyState >= 2) {
        this.kctx.clearRect(0, 0, 640, 360); drawFitSmall(this.kctx, v);
        const img = this.kctx.getImageData(0, 0, 640, 360); chromaKey(img.data); this.kctx.putImageData(img, 0, 0);
        ctx.drawImage(this.kw, 0, 0, W, H);
      }
    }
    ctx.restore();
    if (o.va > 0) { ctx.globalAlpha = Math.min(1, o.va); ctx.fillStyle = o.veil; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
    this.drawText(t);
    this.warmNext(c, t, playing);
    this._perf(t0);
  }
  // за 1,5 с до склейки заранее грузим и ставим на нужный кадр следующий ролик (картинку — за 3 с) — склейка без задержки
  warmNext(c, t, playing) {
    if (!c) return;
    const end = c.start + c.dur; if (end - t > 3) return;
    const n = this.s.clipAt('v1', end + 1e-3); if (!n || n.id === c.id || !n.src) return;
    if (n.kind === 'image') { this.img(n.src); return; }
    if (n.kind !== 'video' || end - t > 1.5) return;
    if (c.kind === 'video' && n.src === c.src) return;          // тот же файл — продолжится сам
    const v = this.vid(n.src, n.id, 'v1'), want = n.in || 0;
    if (!v.paused) return;
    if (v.readyState >= 1 && Math.abs(v.currentTime - want) > 0.05) this.seek(v, want);
  }
  lastFrame() {
    if (!this.hold) { this.hold = document.createElement('canvas'); this.hold.width = W / 4; this.hold.height = H / 4; this.hctx = this.hold.getContext('2d'); }
    if (this._holdN = ((this._holdN || 0) + 1) % 4) return;     // раз в 4 кадра достаточно
    this.hctx.drawImage(this.canvas || this.ctx.canvas, 0, 0, this.hold.width, this.hold.height);
    this.hasHold = true;
  }
  drawLast(ctx) { if (this.hasHold) { ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(this.hold, 0, 0, W, H); ctx.restore(); } }
  _perf(t0) { const ms = performance.now() - t0; if (ms > 16) console.warn(`viewer.draw ${ms.toFixed(1)} ms`); this.lastDrawMs = ms; }
  drawCard(ctx, text) {
    const g = ctx.createRadialGradient(W * 0.5, H * 0.45, 0, W * 0.5, H * 0.45, Math.hypot(W * 0.5, H * 0.55));
    g.addColorStop(0, '#1b1d22'); g.addColorStop(1, '#070809'); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    let size = 0.09 * W, lines; ctx.fillStyle = '#ffd23f'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const words = text.toUpperCase().split(/\s+/);
    for (;;) {                                   // как render_mp4.card_image: длинный текст — меньше кегль, чтобы влез в кадр
      ctx.font = `800 ${size}px "Avenir Next Condensed", Impact, sans-serif`; lines = []; let cur = '';
      for (const w of words) { const tt = (cur + ' ' + w).trim(); if (ctx.measureText(tt).width <= W * 0.88 || !cur) cur = tt; else { lines.push(cur); cur = w; } }
      if (cur) lines.push(cur);
      if (size * 0.98 * lines.length <= H * 0.92 || size < 0.03 * W) break;
      size *= 0.92;
    }
    const lh = size * 0.98, y0 = H / 2 - lh * lines.length / 2;
    lines.forEach((ln, k) => ctx.fillText(ln, W / 2, y0 + lh * k + lh / 2));
  }
  drawText(t) {
    const act = new Set();
    for (const c of this.s.track('text')) {
      if (t < c.start || t >= c.start + c.dur || this.s.ui.off.text) continue;
      act.add(c.id);
      let e = this.textEls.get(c.id);
      if (!e) {
        e = document.createElement('div'); e.className = c.style === 'keyword' ? 'a-kw' : 'a-ost';
        if (c.style !== 'keyword') for (const [w] of (c.words && c.words.length ? c.words : [[c.text, 0]])) { const sp = document.createElement('span'); sp.className = 'w' + (/\d/.test(w) ? ' num' : ''); sp.textContent = w; e.append(sp); }
        else e.textContent = c.text;
        if (c.color) e.style.color = c.color;
        if (c.font) e.style.fontFamily = c.font;
        this.ov.append(e); this.textEls.set(c.id, e);
      }
      const lt = t - c.start;
      if (c.style === 'keyword') { const k = clamp(lt / 0.18, 0, 1); e.style.opacity = k; e.style.transform = `translateX(-50%) scale(${0.6 + 0.48 * ease(k)})`; }
      else [...e.children].forEach((sp, k) => { const t0 = (c.words && c.words[k] ? c.words[k][1] : 0), d = lt - t0; if (d >= 0) { const q = clamp(d / 0.12, 0, 1); sp.style.opacity = 1; sp.style.transform = `scale(${1.35 - 0.35 * ease(q)})`; } else { sp.style.opacity = 0; sp.style.transform = 'scale(1.35)'; } });
    }
    for (const [id, e] of this.textEls) if (!act.has(id)) { e.remove(); this.textEls.delete(id); }
  }
  snapshot() { return new Promise((res) => this.cv.toBlob(res, 'image/jpeg', 0.82)); }
}
