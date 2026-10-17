// Окно справки: поиск по клавишам и разделам — задача 16.
import { dialog } from '../ui.js';
import { el } from '../util.js';

let DATA = null;
async function load() {
  if (!DATA) DATA = await fetch('/web/help.json').then((r) => r.json());
  return DATA;
}

export async function openHelp(query = '') {
  const data = await load();
  const input = el('input', { class: 'hsearch', type: 'search', placeholder: 'Искать в справке…', value: query });
  const out = el('div');
  const body = el('div', {}, input, out);

  function render() {
    const q = input.value.trim().toLowerCase();
    out.innerHTML = '';
    for (const sec of data.sections) {
      if (sec.keys) {
        const rows = sec.keys.filter(([k, v]) => !q || k.toLowerCase().includes(q) || v.toLowerCase().includes(q));
        if (!rows.length) continue;
        out.append(el('div', { class: 'hsec' }, el('h5', {}, sec.title),
          el('table', { class: 'htbl' }, ...rows.map(([k, v]) => el('tr', {}, el('td', {}, el('kbd', { class: 'k' }, k)), el('td', {}, v))))));
      } else if (sec.text) {
        const paras = sec.text.filter((p) => !q || p.toLowerCase().includes(q));
        if (!paras.length) continue;
        out.append(el('div', { class: 'hsec' }, el('h5', {}, sec.title), ...paras.map((p) => el('p', {}, p))));
      }
    }
    if (!out.children.length) out.append(el('div', { class: 'empty' }, 'Ничего не найдено.'));
  }
  input.oninput = render;
  render();

  const { close } = dialog({ title: 'Справка', body, ok: 'Закрыть', cancel: null, wide: true });
  setTimeout(() => { input.focus(); input.select(); }, 0);
  return close;
}
