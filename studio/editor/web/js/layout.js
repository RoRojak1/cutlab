// Раскладка окна: края между панелями тянутся (ширина колонок, высота панелей), в режиме «Настроить расположение»
// панели переставляются перетаскиванием за ⠿; боковые колонки прячутся и выезжают (клик по активной иконке полоски, 💬).
// Расстановка и размеры — localStorage (это удобство конкретного окна); спрятано/показано — ui проекта (leftOpen, reviewOpen).
import { el, lsGet, lsSet } from './util.js';
import { toast } from './ui.js';

const KEY = 'layout';
const IDS = ['panelLeft', 'inspector', 'viewerIsland', 'timeline', 'review'];
const NAMES = { panelLeft: 'Медиа · звуки · надписи', inspector: 'Свойства клипа', viewerIsland: 'Плеер', timeline: 'Таймлайн', review: 'Правки' };
const MIN_H = { viewerIsland: 180, timeline: 150 }, MIN_H0 = 110, MIN_W = 200;
const DEF = { cols: { l: ['panelLeft', 'inspector'], c: ['viewerIsland', 'timeline'], r: ['review'] }, w: { l: 260, r: 300 },
  fr: { panelLeft: 0.56, inspector: 0.44, viewerIsland: 0.67, timeline: 0.33, review: 1 } };
const clone = (o) => JSON.parse(JSON.stringify(o));

function valid(L) {
  try {
    const all = ['l', 'c', 'r'].flatMap((k) => L.cols[k]);
    return all.length === IDS.length && IDS.every((id) => all.includes(id)) && L.cols.c.length > 0 && L.w.l > 0 && L.w.r > 0;
  } catch (e) { return false; }
}

export function mountLayout(store) {
  const main = document.querySelector('main.main');
  const col = { l: main.querySelector('.col.l'), c: main.querySelector('.col.c'), r: main.querySelector('.col.r') };
  const isl = Object.fromEntries(IDS.map((id) => [id, document.getElementById(id)]));
  const vs = { lc: el('div', { class: 'split v', 'data-tip': 'Потяните, чтобы изменить ширину · двойной клик — как было' }),
    cr: el('div', { class: 'split v', 'data-tip': 'Потяните, чтобы изменить ширину · двойной клик — как было' }) };
  const endGap = el('div', { class: 'gutter' });
  let L = lsGet(KEY, null);
  if (!valid(L)) L = clone(DEF);
  let editing = false, banner = null;

  const colOf = (id) => ['l', 'c', 'r'].find((k) => L.cols[k].includes(id));
  const sideShown = (k) => {
    if (k === 'c' || editing) return true;
    if (L.cols[k].includes('panelLeft') && store.ui.leftOpen === false) return false;
    if (L.cols[k].includes('review') && store.ui.reviewOpen === false) return false;
    return L.cols[k].length > 0;
  };
  const kick = () => requestAnimationFrame(() => dispatchEvent(new Event('resize')));

  // arrange — порядок панелей и края (только когда расстановка поменялась: перенос узлов сбивает прокрутку и фокус)
  function arrange() {
    main.querySelectorAll('.split, .gutter, .lay-drop').forEach((e) => e.remove());
    for (const k of ['l', 'c', 'r']) {
      const c = col[k];
      L.cols[k].forEach((id, i) => {
        if (i) c.append(hSplit(k, i));
        const e = isl[id]; e.style.flex = `${L.fr[id] || 1} 1 0px`; e.style.minHeight = (MIN_H[id] || MIN_H0) + 'px';
        if (e.parentElement !== c || c.lastElementChild !== e) c.append(e);
      });
      if (editing) {
        const txt = (w) => (L.cols[k].length ? (w === 'top' ? 'поставить сверху' : 'поставить снизу') : 'перетащите панель сюда');
        c.prepend(el('div', { class: 'lay-drop', 'data-col': k, 'data-where': 'top' }, txt('top')));
        if (L.cols[k].length) c.append(el('div', { class: 'lay-drop', 'data-col': k, 'data-where': 'end' }, txt('end')));
      }
    }
    col.l.after(vs.lc); col.c.after(vs.cr); main.insertBefore(endGap, main.querySelector('.stripe.r'));
    refresh();
  }
  // refresh — ширины, спрятано/показано, подсветка иконок (на каждое изменение ui)
  let lastKey = '';
  function refresh() {
    for (const k of ['l', 'r']) col[k].style.width = L.w[k] + 'px';
    const shown = { l: sideShown('l'), r: sideShown('r') };
    for (const k of ['l', 'c', 'r']) { col[k].classList.toggle('gone', k !== 'c' && !shown[k]); col[k].classList.toggle('empty', !L.cols[k].length); }
    vs.lc.classList.toggle('off', !shown.l); vs.cr.classList.toggle('off', !shown.r);
    const leftVisible = sideShown(colOf('panelLeft'));
    document.querySelectorAll('.stripe.l [data-panel]').forEach((b) => b.classList.toggle('on', leftVisible && b.dataset.panel === (store.ui.panel || 'media')));
    // «Правки» спрятаны — справа появляется полоска с кнопкой «показать» (иначе полоски нет вовсе)
    const sr = main.querySelector('.stripe.r'); if (sr) sr.hidden = sideShown(colOf('review'));
    const key = JSON.stringify([shown, L.w, L.cols]);
    if (key !== lastKey) { lastKey = key; kick(); setTimeout(kick, 260); }      // канвасам — новый размер (и после анимации выезда)
  }
  const apply = arrange;
  const save = () => lsSet(KEY, L);

  // ---- края: ширина колонок
  function vDrag(split, k) {
    split.addEventListener('pointerdown', (e) => {
      e.preventDefault(); split.setPointerCapture(e.pointerId); split.classList.add('drag'); document.body.classList.add('resizing-x');
      const x0 = e.clientX, w0 = L.w[k];
      const move = (ev) => { const dx = ev.clientX - x0; L.w[k] = Math.round(Math.max(MIN_W, Math.min(innerWidth * 0.45, w0 + (k === 'l' ? dx : -dx)))); col[k].style.width = L.w[k] + 'px'; kick(); };
      const up = () => { split.classList.remove('drag'); document.body.classList.remove('resizing-x'); split.removeEventListener('pointermove', move); save(); };
      split.addEventListener('pointermove', move); split.addEventListener('pointerup', up, { once: true });
    });
    split.addEventListener('dblclick', () => { L.w[k] = DEF.w[k]; save(); apply(); });
  }
  vDrag(vs.lc, 'l'); vDrag(vs.cr, 'r');

  // ---- края: высота панелей внутри колонки
  function hSplit(k, i) {
    const s = el('div', { class: 'split h', 'data-tip': 'Потяните, чтобы изменить высоту · двойной клик — поровну' });
    s.addEventListener('pointerdown', (e) => {
      e.preventDefault(); s.setPointerCapture(e.pointerId); s.classList.add('drag'); document.body.classList.add('resizing-y');
      const a = L.cols[k][i - 1], b = L.cols[k][i], ha = isl[a].getBoundingClientRect().height, hb = isl[b].getBoundingClientRect().height;
      const sum = (L.fr[a] || 1) + (L.fr[b] || 1), y0 = e.clientY;
      const move = (ev) => {
        const na = Math.max(MIN_H[a] || MIN_H0, Math.min(ha + hb - (MIN_H[b] || MIN_H0), ha + ev.clientY - y0));
        L.fr[a] = sum * na / (ha + hb); L.fr[b] = sum - L.fr[a];
        isl[a].style.flex = `${L.fr[a]} 1 0px`; isl[b].style.flex = `${L.fr[b]} 1 0px`; kick();
      };
      const up = () => { s.classList.remove('drag'); document.body.classList.remove('resizing-y'); s.removeEventListener('pointermove', move); save(); };
      s.addEventListener('pointermove', move); s.addEventListener('pointerup', up, { once: true });
    });
    s.addEventListener('dblclick', () => { const a = L.cols[k][i - 1], b = L.cols[k][i], m = ((L.fr[a] || 1) + (L.fr[b] || 1)) / 2; L.fr[a] = L.fr[b] = m; save(); apply(); });
    return s;
  }

  // ---- режим «Настроить расположение»: перетаскивание панелей за ⠿
  function overlays(on) {
    for (const id of IDS) {
      const old = isl[id].querySelector(':scope > .lay-ov'); if (old) old.remove();
      if (!on) continue;
      const ov = el('div', { class: 'lay-ov' }, el('div', { class: 'grip', 'data-tip': 'Тащите на другую панель — поменяются местами; на полосу «сверху/снизу» — встанет туда' }, el('b', {}, '⠿'), NAMES[id]));
      ov.firstChild.addEventListener('pointerdown', (e) => startDrag(e, id));
      isl[id].append(ov);
    }
  }
  function startDrag(e, id) {
    e.preventDefault();
    const ghost = el('div', { class: 'lay-ghost' }, '⠿ ' + NAMES[id]); document.body.append(ghost);
    let target = null;
    const pos = (ev) => { ghost.style.left = ev.clientX + 12 + 'px'; ghost.style.top = ev.clientY + 12 + 'px'; };
    const find = (ev) => {
      ghost.hidden = true; const t = document.elementFromPoint(ev.clientX, ev.clientY); ghost.hidden = false;
      const drop = t && t.closest('.lay-drop'), other = t && t.closest('.island');
      const next = drop || (other && other.id !== id && IDS.includes(other.id) ? other : null);
      if (next !== target) { if (target) target.classList.remove('lay-hot'); target = next; if (target) target.classList.add('lay-hot'); }
    };
    const move = (ev) => { pos(ev); find(ev); };
    const up = () => {
      removeEventListener('pointermove', move); ghost.remove();
      if (target) { target.classList.remove('lay-hot'); drop(id, target); }
    };
    pos(e); addEventListener('pointermove', move); addEventListener('pointerup', up, { once: true });
  }
  function drop(id, target) {
    const N = clone(L), from = colOf(id), fi = N.cols[from].indexOf(id);
    if (target.classList.contains('lay-drop')) {
      N.cols[from].splice(fi, 1);
      const k = target.dataset.col; target.dataset.where === 'top' ? N.cols[k].unshift(id) : N.cols[k].push(id);
    } else {                                              // поменять местами
      const t = target.id, tc = colOf(t), ti = N.cols[tc].indexOf(t);
      N.cols[from][fi] = t; N.cols[tc][ti] = id;
      [N.fr[id], N.fr[t]] = [N.fr[t], N.fr[id]];
    }
    if (!N.cols.c.length) return toast('В середине должна остаться хотя бы одна панель', 'error');
    L = N; save(); apply(); overlays(true);
  }
  function edit(on) {
    editing = on;
    document.body.classList.toggle('lay-edit', on);
    if (banner) { banner.remove(); banner = null; }
    if (on) {
      banner = el('div', { class: 'lay-banner' },
        el('span', {}, 'Тащите панели за ⠿ на новое место · края между панелями — размер'),
        el('button', { class: 'btn', onclick: () => reset() }, 'Как было'),
        el('button', { class: 'btn pri', onclick: () => edit(false) }, 'Готово'));
      document.body.append(banner);
    }
    apply(); overlays(on);
  }
  function reset() { L = clone(DEF); save(); apply(); if (editing) overlays(true); toast('Расположение как было', 'ok'); }
  addEventListener('keydown', (e) => { if (editing && e.key === 'Escape') { e.stopPropagation(); edit(false); } }, true);

  // ---- спрятать/показать боковые колонки
  function toggleLeft(panel) {
    const k = colOf('panelLeft');
    if (k === 'c') { if (panel) store.setUi({ panel }); return; }
    const open = store.ui.leftOpen !== false;
    if (panel && panel !== (store.ui.panel || 'media')) store.setUi({ panel, leftOpen: true });
    else store.setUi({ leftOpen: !open });
  }
  function toggleReview() { if (colOf('review') !== 'c') store.setUi({ reviewOpen: store.ui.reviewOpen === false }); }

  // Кнопка «спрятать» — в шапке панели справа от названия (Медиа, Звуки, Надписи, Проблемы); вернуть — любая иконка полоски
  const HIDE_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect class="fill" x="4.6" y="5.6" width="4.6" height="12.8" rx="1.6"/><rect x="3.5" y="4.5" width="17" height="15" rx="3.2"/><path d="M10 4.5v15"/></svg>';
  const CHAT_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.3c4.5 0 8.2 3 8.2 6.8s-3.7 6.8-8.2 6.8c-.95 0-1.86-.13-2.7-.38L5.3 19.3l1.05-3.25C4.8 14.8 3.8 13.05 3.8 11.1 3.8 7.3 7.5 4.3 12 4.3Z"/><circle class="f" cx="8.4" cy="11.1" r="1.05"/><circle class="f" cx="12" cy="11.1" r="1.05"/><circle class="f" cx="15.6" cy="11.1" r="1.05"/></svg>';
  const addHide = (id, svg, tip, fn) => {
    const ih = isl[id].querySelector(':scope > .ih');
    if (!ih || ih.querySelector('.hide-btn')) return;
    const b = el('button', { class: 'ic hide-btn', 'data-tip': tip });
    b.innerHTML = svg; b.onclick = () => fn();
    ih.append(b);
  };
  const hideLeft = () => addHide('panelLeft', HIDE_SVG, 'Спрятать панель · вернуть — иконкой слева', () => toggleLeft());
  const hideRev = () => addHide('review', CHAT_SVG, 'Спрятать «Правки» · вернуть — кнопкой у правого края', () => toggleReview());
  new MutationObserver(hideLeft).observe(isl.panelLeft, { childList: true });
  new MutationObserver(hideRev).observe(isl.review, { childList: true });
  hideLeft(); hideRev();
  // на кнопке «показать правки» — сколько новых правок ждут
  const cnt = document.querySelector('#reviewToggle .cnt');
  const showCnt = () => { if (!cnt) return; const n = ((store.review && store.review.comments) || []).filter((c) => c.status === 'new' || c.status === 'reopened').length; cnt.hidden = !n; cnt.textContent = n; };
  store.on('review', showCnt); showCnt();

  store.on('ui', refresh);
  arrange();
  return { edit, reset, toggleLeft, toggleReview, get editing() { return editing; } };
}
