import { makeApi } from './api.js';
import { initTooltips } from './tooltip.js';
import { Store } from './store.js';
import { Timeline } from './timeline/render.js';
import { attachInteract } from './timeline/interact.js';
import { attachContextMenu } from './timeline/context.js';
import { menu, menuAt } from './ui.js';
import { mountLayout } from './layout.js';
import { mountNative } from './native.js';
import { Mixer } from './player/mix.js';
import { Viewer } from './player/viewer.js';
import { Subs } from './player/subs.js';
import { Transport } from './player/transport.js';
import { mountFullscreen } from './player/fullscreen.js';
import { kineticFor } from './player/kinetic.js';
import { Notifier } from './notify.js';
import { setToast } from './ui.js';
import { bindHotkeys } from './hotkeys.js';
import { openHelp } from './panels/help.js';
import { openSearch } from './panels/search.js';
import { openVersions } from './panels/versions.js';
import { openDub } from './panels/dub.js';
import { openSettings } from './panels/settings.js';
import { mountProjects, projectMenuItems } from './panels/projects.js';
import { mountLeftPanels } from './panels/media.js';
import { mountInspector } from './panels/inspector.js';
import { mountReview } from './panels/review.js';

const api = makeApi();
window.NE = { api };

async function pickProject() {
  const q = new URLSearchParams(location.search).get('p');
  if (q) return q;
  const { projects } = await api.get('/api/projects');
  if (!projects.length) return null;
  return projects.slice().sort((a, b) => (b.opened || 0) - (a.opened || 0))[0].id;
}

function showClaude(state) {
  const e = document.getElementById('claudeState');
  e.className = state;
  e.textContent = { watching: 'Claude следит', working: 'Claude работает…', offline: 'Claude не подключён — правки ждут' }[state] || state;
}

async function boot() {
  initTooltips();
  mountNative();                                   // Cutlab.app: шапка в строке с кнопками окна
  const pid = await pickProject();
  if (!pid) { document.getElementById('projName').textContent = 'нет проектов'; return; }
  const store = new Store(api, pid);
  window.NE.store = store;
  await store.load();
  document.getElementById('projName').textContent = store.project.title;
  document.title = `${store.project.title} — Cutlab`;
  // запомненное состояние окна проекта (масштаб, прокрутка, панель, дорожки, позиция) — из projects/index.json
  const saved = ((await api.get('/api/projects').catch(() => ({ projects: [] }))).projects.find((x) => x.id === pid) || {}).ui || {};
  for (const k of ['pps', 'scroll', 'off', 'solo', 'panel', 'reviewOpen', 'leftOpen', 'sndTab']) if (saved[k] !== undefined) store.ui[k] = saved[k];
  if (typeof saved.t === 'number') store.t = Math.max(0, Math.min(saved.t, store.duration()));
  api.post(`/api/projects/${pid}/ui`, { ui: { ...store.ui, t: store.t } }).catch(() => {});
  store.on('claude', showClaude);
  showClaude(store.review.presence || 'offline');
  store.on('save', (s) => { const e = document.getElementById('saveState'); e.className = s; e.textContent = { saving: '● сохраняю…', err: '● ошибка сохранения', ok: '● сохранено' }[s]; });
  api.events(pid, (ev) => store.onServerEvent(ev));
  window.NE.timeline = new Timeline(store, document.getElementById('timeline'));
  window.NE.interact = attachInteract(store, NE.timeline);
  attachContextMenu(store, NE.timeline, NE.interact);            // правая кнопка: действия под тип клипа
  // Меню по событию 'menu' (режимы музыки и др.) — общий помощник ui.js.
  store.on('menu', ({ x, y, items }) => menu(x, y, items));

  // Плеер: картинка/движение/переходы/Ник — viewer.draw(); живой звук — mixer; play/pause/scope — transport.
  const mixer = new Mixer(store);
  const viewer = new Viewer(store, document.getElementById('cv'), document.getElementById('overlay'));
  viewer.subs = new Subs(store, document.getElementById('overlay'));
  const transport = new Transport(store, viewer, mixer);
  window.NE.viewer = viewer; window.NE.mixer = mixer; window.NE.transport = transport;
  window.NE.fullscreen = mountFullscreen(store, transport);       // ⛶ / F / двойной клик — кадр во весь экран
  document.getElementById('playBtn').onclick = () => transport.toggle();
  store.kineticFor = (c, text) => kineticFor(store, c, text);
  store.on('time', (t) => NE.timeline.ensureVisible(t));
  viewer.draw(store.t);

  // #scopeBtn: что играть — весь выпуск / текущая глава / выделенный отрезок.
  const scopeBtn = document.getElementById('scopeBtn');
  const SCOPES = [['all', 'Весь выпуск'], ['chapter', 'Эта глава'], ['range', 'Выделенный отрезок']];
  const setScopeLabel = (label) => { scopeBtn.firstChild.textContent = label + ' '; };
  scopeBtn.onclick = () => {
    const r = scopeBtn.getBoundingClientRect();
    store.emit('menu', { x: r.left, y: r.bottom + 4, items: SCOPES.map(([id, label]) => ({ label, run: () => { transport.scope = id; setScopeLabel(label); } })) });
  };
  // [A: панели + правки] — mountProjects / mountLeftPanels / mountInspector / mountReview (задачи 13–14)
  mountProjects(store);
  mountLeftPanels(store);
  mountInspector(store);
  window.NE.review = mountReview(store, viewer);

  // [B: уведомления + справка] — Notifier / help / hotkeys / search / versions / dub / settings (задачи 15–16)
  const notifier = new Notifier(store);
  setToast((t, k) => notifier.toast(t, k));
  window.NE.notifier = notifier;
  bindHotkeys({ store, transport, interact: NE.interact, openSearch, openHelp });
  document.getElementById('helpBtn').onclick = () => openHelp();
  document.getElementById('searchBtn').onclick = () => openSearch(store);
  document.getElementById('settingsBtn').onclick = () => openSettings(store);
  document.getElementById('verBtn').onclick = () => openVersions(store);
  store.on('openVersions', () => openVersions(store));
  document.getElementById('dubBtn').onclick = () => openDub(store);

  // Раскладка: края тянутся, панели переставляются («Cutlab ▾ → Настроить расположение»), боковые колонки прячутся
  const layout = mountLayout(store);
  window.NE.layout = layout;
  document.getElementById('reviewToggle').onclick = () => layout.toggleReview();
  document.getElementById('appBtn').onclick = async (e) => { const btn = e.currentTarget; menuAt(btn, [
    ...(await projectMenuItems(store)),
    { sep: true },
    { header: 'Окно' },
    { label: 'Настроить расположение панелей', hint: 'перетащить', run: () => layout.edit(true) },
    { label: 'Расположение как было', run: () => layout.reset() },
    { sep: true },
    { label: store.ui.leftOpen === false ? 'Показать левую панель' : 'Спрятать левую панель', run: () => layout.toggleLeft() },
    { label: store.ui.reviewOpen === false ? 'Показать «Правки»' : 'Спрятать «Правки»', run: () => layout.toggleReview() },
    { sep: true },
    { label: 'Настройки Cutlab…', hint: 'звук, подсветка', run: () => openSettings(store) },
    { label: 'Справка', hint: '?', run: () => openHelp() },
  ]); };
  store.on('openDub', () => openDub(store));

  // Строка-путь внизу: проект › глава › кадр › «слово»
  const crumbs = document.getElementById('crumbs');
  const showCrumbs = () => {
    const t = store.t, c = store.clipAt('v1', t), w = store.words || [];
    let lo = 0, hi = w.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (w[m][0] <= t + 1e-6) { k = m; lo = m + 1; } else hi = m - 1; }
    const txt = [c && c.chapter, c && (c.shot || c.id), k >= 0 && t - w[k][0] < 2 ? `«${w[k][2]}»` : null].filter(Boolean).join(' › ');
    if (crumbs.textContent !== txt) crumbs.textContent = txt;
  };
  for (const ev of ['time', 'project', 'words']) store.on(ev, showCrumbs);
  store.setTime(store.t);                       // таймкоды и путь — для восстановленной позиции
}
boot().catch((e) => { console.error(e); document.getElementById('projName').textContent = 'ошибка: ' + e.message; });
