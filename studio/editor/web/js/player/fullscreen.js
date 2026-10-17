// Просмотр во весь экран: кнопка ⛶ под плеером, клавиша F, двойной клик по кадру; выход — Esc или те же F / ⛶.
// Сам режим — класс .fs у #viewerIsland (кадр на весь экран, снизу полоса перемотки и панель, прячутся без движения мыши).
// Экран целиком: Fullscreen API (браузер, Cutlab.app с включённым element fullscreen), иначе окно Cutlab.app — в полноэкранный режим.
import { fmtTC } from '../util.js';

const HIDE_MS = 2200;

export function mountFullscreen(store, transport) {
  const isl = document.getElementById('viewerIsland');
  const stage = document.getElementById('stage');
  const native = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.cutlab;
  let on = false, viaApi = false, hideT = 0;

  const bar = document.createElement('div');
  bar.className = 'fsbar';
  bar.innerHTML = '<div class="fill"></div><div class="knob"></div><div class="hint" hidden></div>';
  isl.appendChild(bar);
  const fill = bar.querySelector('.fill'), knob = bar.querySelector('.knob'), hint = bar.querySelector('.hint');

  const docFs = () => document.fullscreenElement || document.webkitFullscreenElement || null;
  const paint = (t) => {
    if (!on) return;
    const d = store.duration() || 1, p = Math.max(0, Math.min(1, t / d)) * 100;
    fill.style.width = p + '%'; knob.style.left = p + '%';
  };

  function showUi() {
    isl.classList.remove('fs-idle');
    clearTimeout(hideT);
    hideT = setTimeout(() => { if (on && transport.m.playing && !bar.matches(':hover') && !transport.ctl.matches(':hover')) isl.classList.add('fs-idle'); }, HIDE_MS);
  }

  function enter() {
    if (on) return;
    on = true; isl.classList.add('fs'); paint(store.t); showUi();
    const req = isl.requestFullscreen || isl.webkitRequestFullscreen;
    viaApi = false;
    const fallback = () => { if (native) native.postMessage({ fullscreen: true }); };
    if (req) {
      try {
        const r = req.call(isl);
        if (r && r.then) r.then(() => { viaApi = true; }, fallback); else viaApi = !!docFs();
      } catch (e) { fallback(); }
      setTimeout(() => { if (on && !docFs() && !viaApi) fallback(); }, 300);   // WebKit без element fullscreen молча игнорирует запрос
    } else fallback();
    transport.render();
  }

  function exit() {
    if (!on) return;
    on = false; isl.classList.remove('fs', 'fs-idle'); clearTimeout(hideT);
    if (docFs()) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    else if (native) native.postMessage({ fullscreen: false });
    viaApi = false;
    transport.render();
  }

  const toggle = () => (on ? exit() : enter());

  // Esc из Fullscreen API браузер обрабатывает сам — выходим из режима вслед за ним
  for (const ev of ['fullscreenchange', 'webkitfullscreenchange']) {
    document.addEventListener(ev, () => { if (!docFs() && on && viaApi) { viaApi = false; exit(); } });
  }
  // Esc без Fullscreen API (окно Cutlab.app) — раньше общего обработчика, который снимает выделение
  addEventListener('keydown', (e) => { if (on && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); exit(); } }, true);

  stage.addEventListener('dblclick', (e) => { e.preventDefault(); toggle(); });
  isl.addEventListener('mousemove', () => { if (on) showUi(); });
  addEventListener('keydown', () => { if (on) setTimeout(showUi, 0); });   // пуск пробелом — таймер скрытия заново
  store.on('time', paint);
  store.on('project', () => paint(store.t));

  // полоса перемотки: клик и протяжка
  const seekAt = (x) => {
    const r = bar.getBoundingClientRect(), k = Math.max(0, Math.min(1, (x - r.left) / r.width));
    return k * store.duration();
  };
  bar.addEventListener('mousemove', (e) => {
    hint.hidden = false; hint.textContent = fmtTC(seekAt(e.clientX));
    hint.style.left = Math.max(0, Math.min(bar.clientWidth, e.clientX - bar.getBoundingClientRect().left)) + 'px';
  });
  bar.addEventListener('mouseleave', () => { hint.hidden = true; });
  bar.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const wasPlaying = transport.m.playing; if (wasPlaying) transport.pause();
    const go = (ev) => store.setTime(seekAt(ev.clientX));
    go(e);
    const up = () => { removeEventListener('mousemove', go); removeEventListener('mouseup', up); if (wasPlaying) transport.play(); };
    addEventListener('mousemove', go); addEventListener('mouseup', up);
  });
  // при паузе панель не прячем; при пуске — запускаем таймер скрытия
  store.on('time', () => { if (on && !transport.m.playing) isl.classList.remove('fs-idle'); });

  return { toggle, enter, exit, get on() { return on; } };
}
