export const FPS = 30;
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const frame = (t) => Math.round(t * FPS) / FPS;
export function fmtTC(t) {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
}
export function fmtShift(dt) {
  const sign = dt < 0 ? '−' : '+';
  return `${sign}${Math.abs(dt).toFixed(2).replace('.', ',')} с · ${Math.abs(Math.round(dt * FPS))} кадр.`;
}
export function parseTC(s) {
  s = String(s).trim();
  if (s.includes(':')) { const [m, sec] = s.split(':'); return Math.round((+m * 60 + +sec) * 1e4) / 1e4; }
  return +s;
}
export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const dbGain = (d) => Math.pow(10, d / 20);
export function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
// Версия файла (mtime с сервера, project._mtimes): перерендер под тем же именем даёт новый адрес — плеер и браузер не играют старое.
const VER = new Map();
export function setAssetVersions(m) { VER.clear(); for (const [k, v] of Object.entries(m || {})) VER.set(k, v); }
export const assetURL = (src) => { const v = VER.get(String(src)); return '/' + String(src).split('/').map(encodeURIComponent).join('/') + (v ? `?v=${v}` : ''); };
export const thumbURL = (src, w = 240) => `/api/thumb?path=${encodeURIComponent(src)}&w=${w}${VER.get(String(src)) ? `&v=${VER.get(String(src))}` : ''}`;
export function lsGet(k, d) { try { const v = localStorage.getItem('nick.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
export function lsSet(k, v) { try { localStorage.setItem('nick.' + k, JSON.stringify(v)); } catch (e) { /* приватный режим */ } }
export function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, '');
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}
