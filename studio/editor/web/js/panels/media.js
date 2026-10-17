// Левые панели (задача 13, шаг 3): переключатель .stripe.l → #panelLeft, «Медиа», «Надписи», «Проблемы».
// «Звуки и музыка» — в sounds.js (renderSounds), подключается отсюда.
import { el, fmtTC, thumbURL } from '../util.js';
import { renderSounds } from './sounds.js';

export function mountLeftPanels(store) {
  const root = document.getElementById('panelLeft');
  const buttons = [...document.querySelectorAll('.stripe.l [data-panel]')];
  let current = null;

  function switchTo(panel) {
    if (current && current.panel === panel) return;
    if (current && current.cleanup) current.cleanup();
    buttons.forEach((b) => b.classList.toggle('on', b.dataset.panel === panel));
    root.innerHTML = '';
    if (panel === 'sounds') current = renderSounds(store, root);
    else if (panel === 'text') current = mountText(store, root);
    else if (panel === 'problems') current = mountProblems(store, root);
    else current = mountMedia(store, root);
  }
  // Точка на иконке «Проблемы» и store.problems (штрихует такие клипы на таймлайне) — независимо от того, открыта панель или нет.
  // Регистрируем до первого switchTo и сигналим отдельным событием 'problems', чтобы не зависеть от порядка подписчиков на 'project'.
  refreshProblems(store);
  store.on('project', () => refreshProblems(store));

  // клик по иконке: другая панель — открыть её; та же — спрятать/показать левую колонку (layout.js)
  buttons.forEach((b) => { b.onclick = () => (window.NE.layout ? window.NE.layout.toggleLeft(b.dataset.panel) : store.setUi({ panel: b.dataset.panel })); });
  store.on('ui', () => switchTo(store.ui.panel || 'media'));
  switchTo(store.ui.panel || 'media');
}

async function refreshProblems(store) {
  const r = await store.api.get(store.url('/problems'));
  store._problemsList = r.problems;
  store.problems = new Set(r.problems.map((p) => p.id));
  const btn = document.querySelector('.stripe.l [data-panel="problems"]');
  if (btn) {
    let dot = btn.querySelector('.dot');
    if (!dot) { dot = el('span', { class: 'dot' }); btn.append(dot); }
    dot.hidden = store.problems.size === 0;
  }
  if (window.NE && window.NE.timeline) NE.timeline.render();
  store.emit('problems');
}

// ---------------------------------------------------------------- Медиа
function mountMedia(store, root) {
  const search = el('input', { class: 'psearch', placeholder: 'Кадр…' });
  const list = el('div', { class: 'scroll tree' });
  root.append(el('div', { class: 'ih' }, 'Медиа'), search, list);
  const expanded = new Set();
  let chapters = [];

  function draw() {
    const q = search.value.trim().toLowerCase();
    list.innerHTML = '';
    for (const ch of chapters) {
      const shots = q ? ch.shots.filter((s) => s.shot.toLowerCase().includes(q)) : ch.shots;
      if (!shots.length) continue;
      const open = !!q || expanded.has(ch.chapter);
      list.append(el('div', {
        class: 'rw ch', onclick: () => { if (expanded.has(ch.chapter)) expanded.delete(ch.chapter); else expanded.add(ch.chapter); draw(); },
      }, el('span', { class: 'ar' }, open ? '▾' : '▸'), el('span', { style: { flex: 1 } }, ch.chapter || '(без главы)'), el('span', { class: 'mu' }, String(ch.shots.length))));
      if (!open) continue;
      for (const s of shots) {
        list.append(el('div', {
          class: 'rw shot' + (store.sel.has(s.clip) ? ' on' : ''), 'data-clip': s.clip,
          onclick: () => { store.select([s.clip]); store.setTime(s.start); window.NE.timeline.ensureVisible(s.start); },
        }, el('span', { style: { flex: 1 } }, s.shot), el('span', { class: 'mu mono' }, fmtTC(s.start))));
        if (s.files && s.files.length) {
          const th = el('div', { class: 'thumbs' });
          for (const f of s.files) {
            const img = el('img', { src: thumbURL(f.src, 120), draggable: true, title: f.name, class: f.src === s.used ? 'used' : '' });
            img.addEventListener('dragstart', (e) => e.dataTransfer.setData('application/x-nick-asset', JSON.stringify({ type: 'media', src: f.src, kind: f.kind, name: f.name })));
            th.append(f.new ? el('span', { class: 'thw', 'data-tip': 'Новый вариант от Claude — выбрать можно в «Правках»' }, img, el('b', { class: 'mi-new' }, '✦ новое')) : img);
          }
          list.append(th);
        }
      }
    }
    if (!list.children.length) list.append(el('div', { class: 'empty' }, 'Ничего не нашлось.'));
  }
  // список с сервера — не чаще раза в 300 мс и без перерисовки, если ничего не поменялось;
  // выделение клипа — только подсветка строк, без пересборки сотен превью
  let lastJson = '', timer = 0;
  async function load() {
    const media = (await store.api.get(store.url('/media'))).media, j = JSON.stringify(media);
    if (j === lastJson) return;
    lastJson = j; chapters = media; draw();
  }
  const loadSoon = () => { clearTimeout(timer); timer = setTimeout(() => load().catch(() => {}), 300); };
  const mark = () => { for (const r of list.querySelectorAll('.rw.shot')) r.classList.toggle('on', store.sel.has(r.dataset.clip)); };
  search.oninput = draw;
  const offs = [store.on('project', loadSoon), store.on('review', loadSoon), store.on('sel', mark)];
  load();
  return { panel: 'media', cleanup: () => { clearTimeout(timer); offs.forEach((f) => f()); } };
}

// ---------------------------------------------------------------- Надписи
function mountText(store, root) {
  const list = el('div', { class: 'scroll' });
  const addBtn = el('button', { class: 'btn pri', style: { margin: '8px 10px' } }, '+ Надпись на красной линии');
  root.append(el('div', { class: 'ih' }, 'Надписи'), addBtn, list);

  function draw() {
    list.innerHTML = '';
    const items = store.track('text').slice().sort((a, b) => a.start - b.start);
    if (!items.length) { list.append(el('div', { class: 'empty' }, 'Пока нет надписей.')); return; }
    for (const c of items) {
      list.append(el('div', {
        class: 'rw' + (store.sel.has(c.id) ? ' on' : ''),
        onclick: () => { store.select([c.id]); store.setTime(c.start); window.NE.timeline.ensureVisible(c.start); },
      }, el('span', { style: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' } }, c.text || '(пусто)'), el('span', { class: 'mu mono' }, fmtTC(c.start))));
    }
  }
  addBtn.onclick = async () => {
    const text = 'ТЕКСТ', start = store.t, dur = 2;
    const words = store.kineticFor ? store.kineticFor({ start, dur }, text) : [];
    const r = await store.dispatch([{ op: 'add', clip: { track: 'text', style: 'kinetic', text, start, dur, words } }], { label: 'надпись' });
    if (r.changed && r.changed.length) store.select(r.changed);
  };
  const offs = [store.on('project', draw), store.on('sel', draw)];
  draw();
  return { panel: 'text', cleanup: () => offs.forEach((f) => f()) };
}

// ---------------------------------------------------------------- Проблемы
function mountProblems(store, root) {
  const list = el('div', { class: 'scroll' });
  root.append(el('div', { class: 'ih' }, 'Проблемы'), list);
  function draw() {
    list.innerHTML = '';
    const items = store._problemsList || [];
    if (!items.length) { list.append(el('div', { class: 'empty' }, 'Проблем не найдено.')); return; }
    for (const p of items) {
      list.append(el('div', {
        class: 'rw',
        onclick: () => { const c = store.clip(p.id); if (!c) return; store.select([p.id]); store.setTime(c.start); window.NE.timeline.ensureVisible(c.start); },
      }, el('span', { style: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' } }, p.problem)));
    }
  }
  const offs = [store.on('project', draw), store.on('problems', draw)];
  draw();
  return { panel: 'problems', cleanup: () => offs.forEach((f) => f()) };
}
