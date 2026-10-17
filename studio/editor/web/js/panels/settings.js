// Настройки: громкость уведомлений, подсветка угла, сброс раскладки — задача 16.
import { dialog, toast } from '../ui.js';
import { el, lsGet, lsSet, debounce } from '../util.js';

// Применяем сохранённую подсветку угла сразу при загрузке модуля (main.js импортирует его при загрузке).
document.documentElement.style.setProperty('--glow', lsGet('glow', 0.25));

const previewAudio = new Audio('/assets/ui/notify.wav');
const previewChime = debounce((v) => { if (v > 0) { previewAudio.volume = v; previewAudio.currentTime = 0; previewAudio.play().catch(() => {}); } }, 150);

export function openSettings(store) {
  const chime = lsGet('chime', 0.6), glow = lsGet('glow', 0.25);
  const chimeIn = el('input', { type: 'range', min: 0, max: 1, step: 0.05, value: chime });
  const chimeVal = el('span', { class: 'val' }, Math.round(chime * 100) + '%');
  const glowIn = el('input', { type: 'range', min: 0, max: 1, step: 0.05, value: glow });
  const glowVal = el('span', { class: 'val' }, Math.round(glow * 100) + '%');
  chimeIn.oninput = () => { const v = +chimeIn.value; chimeVal.textContent = Math.round(v * 100) + '%'; lsSet('chime', v); previewChime(v); };
  glowIn.oninput = () => { const v = +glowIn.value; glowVal.textContent = Math.round(v * 100) + '%'; lsSet('glow', v); document.documentElement.style.setProperty('--glow', v); };

  const resetBtn = el('button', { class: 'btn', onclick: () => {
    store.setUi({ pps: 60, scroll: 0, off: {}, solo: null, panel: 'media', tabs: [], reviewOpen: true, leftOpen: true });
    if (window.NE.layout) window.NE.layout.reset(); else toast('Раскладка сброшена', 'ok');
  } }, 'Сбросить раскладку');

  const body = el('div', {},
    el('div', { class: 'settrow' }, el('span', { class: 'lb' }, 'Звук уведомлений'), chimeIn, chimeVal),
    el('div', { class: 'settrow' }, el('span', { class: 'lb' }, 'Подсветка угла'), glowIn, glowVal),
    el('div', { class: 'settrow' }, el('span', { class: 'lb' }, 'Раскладка окон'), resetBtn));

  return dialog({ title: 'Настройки', body, ok: 'Готово', cancel: null });
}
