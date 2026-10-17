// Общие помощники интерфейса: меню, диалоги, подтверждение, тосты (Notifier подменяет toast через setToast).
import { el } from './util.js';

let closeMenu = null;

// Пункт меню: { label, run, hint, tip, disabled, danger, checked, sub: [пункты] } · { sep: true } · { header }.
export function menu(x, y, items) {
  if (closeMenu) closeMenu();
  const m = document.getElementById('menu');
  const subs = [];                                        // открытые подменю по уровням
  const closeSubs = (level) => { while (subs.length > level) subs.pop().remove(); };
  // пока открыто подменю, соседние пункты срабатывают с задержкой — мышь успевает дойти до подменю по диагонали
  let hoverT = 0;
  const later = (level, fn) => { clearTimeout(hoverT); if (subs.length > level) hoverT = setTimeout(fn, 220); else fn(); };
  function build(box, list, level) {
    box.innerHTML = '';
    const checks = list.some((it) => it && it.checked !== undefined);
    for (const it of list) {
      if (!it) continue;
      if (it.sep) { box.append(el('div', { class: 'sep' })); continue; }
      if (it.header) { box.append(el('div', { class: 'mh' }, it.header)); continue; }
      const row = el('div', { class: 'mi' + (it.disabled ? ' dis' : '') + (it.danger ? ' danger' : '') + (it.sub ? ' has-sub' : ''), 'data-tip': it.tip || null },
        checks ? el('span', { class: 'ck' }, it.checked ? '✓' : '') : null,
        el('span', { style: { flex: 1 } }, it.label), it.hint ? el('span', { class: 'mu' }, it.hint) : null, it.sub ? el('span', { class: 'mu arr' }, '›') : null);
      if (it.sub && !it.disabled) {
        const open = () => { if (subs[level] && subs[level]._row === row) return; closeSubs(level); openSub(row, it.sub, level); };
        row.onmouseenter = () => later(level, open); row.onclick = () => { clearTimeout(hoverT); open(); };
      } else {
        row.onmouseenter = () => later(level, () => closeSubs(level));
        if (!it.disabled) row.onclick = () => { close(); if (it.run) Promise.resolve(it.run()).catch((e) => toast(e.message, 'error')); };
      }
      box.append(row);
    }
  }
  function openSub(row, list, level) {
    const sb = el('div', { class: 'submenu' }); sb._row = row;
    sb.addEventListener('mouseenter', () => clearTimeout(hoverT));
    document.body.append(sb); subs.push(sb); build(sb, list, level + 1);
    const r = row.getBoundingClientRect();
    let left = r.right + 4; if (left + sb.offsetWidth > innerWidth - 8) left = r.left - sb.offsetWidth - 4;
    sb.style.left = Math.max(8, left) + 'px';
    sb.style.top = Math.max(8, Math.min(r.top - 6, innerHeight - sb.offsetHeight - 8)) + 'px';
  }
  build(m, items, 0);
  m.hidden = false;
  m.style.left = Math.max(8, Math.min(x, innerWidth - m.offsetWidth - 8)) + 'px';
  m.style.top = Math.max(8, Math.min(y, innerHeight - m.offsetHeight - 8)) + 'px';
  const inside = (t) => m.contains(t) || subs.some((sb) => sb.contains(t));
  const off = (e) => { if (!inside(e.target)) close(); };
  const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
  function close() {
    clearTimeout(hoverT); closeSubs(0); m.hidden = true; m.innerHTML = '';
    removeEventListener('pointerdown', off, true); removeEventListener('keydown', esc, true);
    closeMenu = null;
  }
  setTimeout(() => { addEventListener('pointerdown', off, true); addEventListener('keydown', esc, true); });
  closeMenu = close;
  return close;
}

export function menuAt(btn, items) { const r = btn.getBoundingClientRect(); return menu(r.left, r.bottom + 6, items); }

let closeDialog = null;

export function dialog({ title, body, ok = 'Готово', cancel = 'Отмена', onOk, onCancel, wide = false }) {
  const md = document.getElementById('modal');
  if (closeDialog) closeDialog();              // новое окно поверх старого: снять Esc-обработчик прежнего
  md.innerHTML = '';
  let open = true;
  const close = () => { if (!open) return; open = false; md.hidden = true; md.innerHTML = ''; removeEventListener('keydown', esc, true); if (closeDialog === close) closeDialog = null; };
  const doCancel = () => { close(); if (onCancel) onCancel(); };
  const esc = (e) => { if (e.key === 'Escape') doCancel(); };
  const okBtn = el('button', { class: 'btn pri', onclick: async () => {
    try { if (!onOk || (await onOk()) !== false) close(); } catch (e) { toast(e.message, 'error'); }
  } }, ok);
  md.append(el('div', { class: 'dlg', style: wide ? { width: '720px' } : {} },
    el('div', { class: 'ih' }, title), el('div', { class: 'body' }, body),
    el('div', { class: 'foot' }, cancel ? el('button', { class: 'btn', onclick: doCancel }, cancel) : null, okBtn)));
  md.hidden = false;
  md.onmousedown = (e) => { if (e.target === md) doCancel(); };
  addEventListener('keydown', esc, true);
  closeDialog = close;
  return { close, okBtn };
}

export function confirmBox(text, ok = 'Да') {
  return new Promise((res) => dialog({ title: 'Подтвердите', body: el('div', { style: { lineHeight: 1.5 } }, text), ok, onOk: () => res(true), onCancel: () => res(false) }));
}

export let toast = (text, kind = 'info') => console.log(`[${kind}]`, text);
export function setToast(fn) { toast = fn; }
