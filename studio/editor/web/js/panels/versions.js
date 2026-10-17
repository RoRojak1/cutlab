// Версии проекта: список, ручное сохранение, откат — задача 16.
import { dialog, confirmBox, toast } from '../ui.js';
import { el, fmtTC } from '../util.js';

function hhmm(atSec) {
  const d = new Date(atSec * 1000), now = new Date(), p = (n) => String(n).padStart(2, '0');
  const t = p(d.getHours()) + ':' + p(d.getMinutes());
  if (d.toDateString() === now.toDateString()) return t;
  const y = new Date(now); y.setDate(now.getDate() - 1);
  return (d.toDateString() === y.toDateString() ? 'вчера ' : `${p(d.getDate())}.${p(d.getMonth() + 1)} `) + t;
}

export async function openVersions(store) {
  const list = el('div', { class: 'scroll', style: { maxHeight: '380px' } });
  const labelIn = el('input', { type: 'text', placeholder: 'Название версии…', style: { flex: 1 } });
  const saveBtn = el('button', { class: 'btn pri', onclick: save }, 'Сохранить версию…');
  const body = el('div', {}, el('div', { style: { display: 'flex', gap: '8px', padding: '2px 14px 12px' } }, labelIn, saveBtn), list);

  async function refresh() {
    const { versions } = await store.api.get(store.url('/history'));
    list.innerHTML = '';
    if (!versions.length) { list.append(el('div', { class: 'empty' }, 'Версий пока нет — они появятся автоматически или по кнопке выше.')); return; }
    for (const v of versions) {
      list.append(el('div', { class: 'vrow', onclick: () => restore(v) },
        el('span', { class: 'tm' }, hhmm(v.at)),
        el('span', { class: 'lb' }, v.label || 'без названия'),
        el('span', { class: 'dur' }, fmtTC(v.duration || 0).replace(/\.00$/, ''))));
    }
  }
  async function save() {
    const label = labelIn.value.trim() || 'вручную';
    try { await store.api.post(store.url('/history'), { label }); labelIn.value = ''; toast('Версия сохранена', 'ok'); await refresh(); }
    catch (e) { toast(e.message, 'error'); }
  }
  async function restore(v) {
    const ok = await confirmBox(`Вернуть проект к версии «${v.label || 'без названия'}» от ${hhmm(v.at)}? Текущее состояние сохранится как «перед откатом».`);
    if (!ok) return;
    try {
      await store.api.post(store.url(`/history/${v.id}/restore`), {});
      const p = await store.api.get(store.url());
      store.setProject(p, [], 'restore');
      toast('Проект возвращён к выбранной версии', 'ok');
      close();
    } catch (e) { toast(e.message, 'error'); }
  }
  await refresh();
  const { close } = dialog({ title: 'Версии проекта', body, ok: 'Закрыть', cancel: null, wide: true });
  return close;
}
