// «Выбрать начало видео…» — окно с превью исходного ролика: ползунок по всей длине файла,
// подсвечен кусок, который попадёт в кадр (длина кадра × скорость). «Проиграть кусок» — посмотреть выбранное.
import { el, fmtTC, assetURL, frame } from '../util.js';
import { dialog } from '../ui.js';

export function openInPoint(store, c) {
  if (!c || c.kind !== 'video' || !c.src) return;
  const sp = c.speed || 1, need = c.dur * sp;
  let inT = c.in || 0, stopAt = null;
  const v = el('video', { src: assetURL(c.src), muted: true, playsinline: true, preload: 'auto', style: { width: '100%', borderRadius: '8px', background: '#000', display: 'block' } });
  v.muted = true;
  const range = el('input', { type: 'range', min: '0', max: '1', step: '0.0333', value: String(inT), style: { width: '100%' } });
  const bar = el('div', { style: { position: 'relative', height: '6px', background: '#2a2a2f', borderRadius: '3px', margin: '6px 0 2px' } },
    el('div', { class: 'win', style: { position: 'absolute', top: 0, bottom: 0, background: 'var(--ac)', borderRadius: '3px', opacity: 0.8 } }));
  const info = el('div', { style: { font: '12px var(--mono)', color: 'var(--tx2)', display: 'flex', justifyContent: 'space-between', gap: '8px' } });
  const play = el('button', { class: 'btn', onclick: () => { v.currentTime = inT; stopAt = inT + need; v.playbackRate = sp; v.play().catch(() => {}); } }, '▶ Проиграть кусок');
  const back = el('button', { class: 'btn', onclick: () => set(inT - 1 / 30) }, '◀ кадр');
  const fwd = el('button', { class: 'btn', onclick: () => set(inT + 1 / 30) }, 'кадр ▶');
  const maxIn = () => Math.max(0, (v.duration || need) - need);
  function paint() {
    const D = v.duration || need;
    const w = bar.firstChild; w.style.left = (inT / D * 100) + '%'; w.style.width = Math.min(100, need / D * 100) + '%';
    info.textContent = '';
    info.append(el('span', {}, `начало: ${fmtTC(inT)}`), el('span', {}, `в кадр идёт ${need.toFixed(2)} с${sp !== 1 ? ` (×${sp})` : ''}`), el('span', {}, `длина файла: ${fmtTC(D)}`));
  }
  function set(t) { inT = frame(Math.max(0, Math.min(maxIn(), t))); range.value = String(inT); v.pause(); stopAt = null; v.currentTime = inT; paint(); }
  v.addEventListener('loadedmetadata', () => { range.max = String(maxIn()); set(inT); });
  v.addEventListener('timeupdate', () => { if (stopAt != null && v.currentTime >= stopAt) { v.pause(); v.currentTime = inT; stopAt = null; } });
  range.addEventListener('input', () => set(+range.value));
  paint();
  dialog({
    title: `Начало видео · кадр ${c.shot || c.id}`,
    wide: true,
    ok: 'Поставить это начало',
    body: el('div', { style: { display: 'grid', gap: '8px' } },
      v, range, bar, info,
      el('div', { style: { display: 'flex', gap: '8px' } }, back, play, fwd),
      el('div', { style: { color: 'var(--mu)', fontSize: '12px' } }, 'Тяните ползунок — в превью виден кадр, с которого начнётся видео. Зелёная полоса — кусок, который войдёт в монтаж.')),
    onOk: () => { v.pause(); return store.dispatch([{ op: 'set', id: c.id, fields: { in: inT } }], { label: 'начало видео' }); },
    onCancel: () => v.pause(),
  });
}
