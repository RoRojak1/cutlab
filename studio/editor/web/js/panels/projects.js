// Меню проекта (заголовок «projBtn») и диалог настроек проекта — задача 13, шаг 2.
import { dialog, toast } from '../ui.js';
import { el, fmtTC } from '../util.js';

// Пункты «Проекты» и «Этот проект» для общего меню Cutlab ▾ (main.js); название проекта — в строке состояния внизу.
export async function projectMenuItems(store) {
  const { projects } = await store.api.get('/api/projects');
  const recent = projects.slice().sort((a, b) => (b.opened || 0) - (a.opened || 0));
  return [
    { header: 'Проекты' },
    ...recent.map((p) => ({
      label: p.title, checked: p.id === store.pid,
      hint: `${p.id} · ${fmtTC(p.duration || 0).replace(/\.\d+$/, '')}`,
      run: () => { if (p.id !== store.pid) location.search = '?p=' + encodeURIComponent(p.id); },
    })),
    { label: 'Новый проект…', run: () => newProject(store) },
    { sep: true },
    { header: 'Этот проект' },
    { label: 'Настройки проекта…', hint: 'название, громкость', run: () => openProjectSettings(store) },
    { label: 'Версии…', run: () => store.emit('openVersions') },
    { label: 'Сохранить версию сейчас', run: async () => { await store.api.post(store.url('/history'), { label: 'вручную' }); toast('Версия сохранена', 'ok'); } },
    { label: 'Дубляж…', run: () => store.emit('openDub') },
    { label: 'Показать в Finder', run: () => store.api.post(store.url('/reveal')) },
    { label: 'Экспорт в CapCut', disabled: true, tip: 'Появится вместе с готовым MP4 (этап 3)' },
  ];
}

export function mountProjects(store) {
  // Название проекта — внизу слева (клик — настройки проекта) и в заголовке окна
  const name = document.getElementById('projName');
  name.onclick = () => openProjectSettings(store);
  const sync = () => {
    name.textContent = store.project.title;
    document.title = `${store.project.title} — Cutlab`;
  };
  store.on('project', sync); sync();
}

function newProject(store) {
  const inp = el('input', { placeholder: 'Название выпуска', style: { width: '100%' } });
  const { okBtn } = dialog({
    title: 'Новый проект', body: inp, ok: 'Создать',
    onOk: async () => { const r = await store.api.post('/api/projects', { title: inp.value }); location.search = '?p=' + encodeURIComponent(r.id); },
  });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); okBtn.click(); } });
  setTimeout(() => inp.focus());
}

export function openProjectSettings(store) {
  const p = store.project, lv = p.settings.levels_db;
  const field = (k, label, v) => [el('span', { class: 'mu' }, label), el('input', { type: 'number', step: '1', value: v, 'data-k': k })];
  const title = el('input', { value: p.title, style: { width: '100%' } });
  const body = el('div', { class: 'kv' },
    el('span', { class: 'mu' }, 'Название'), title,
    ...field('voice', 'Голос, дБ', lv.voice), ...field('sfx', 'Эффекты, дБ', lv.sfx), ...field('music', 'Музыка, дБ', lv.music), ...field('video', 'Звук роликов, дБ', lv.video),
    el('span', { class: 'mu' }, 'Кадр'), el('span', { class: 'ro' }, `${p.width}×${p.height}, ${p.fps} fps`),
    el('span', { class: 'mu' }, 'Голос Ника'), el('span', { class: 'ro' }, p.settings.voice));
  dialog({
    title: 'Настройки проекта', body, ok: 'Сохранить',
    onOk: async () => {
      const levels = { ...lv };
      body.querySelectorAll('input[data-k]').forEach((i) => { levels[i.dataset.k] = +i.value; });
      await store.api.post(store.url('/settings'), { title: title.value, settings: { levels_db: levels } });
    },
  });
  setTimeout(() => title.focus());
}
