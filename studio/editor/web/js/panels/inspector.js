// Свойства выделенного клипа — задача 13, шаг 4.
import { el, fmtTC } from '../util.js';
import { openInPoint } from './inpoint.js';

export const MOTIONS = [['static', 'статично'], ['zoom_in', 'наезд'], ['zoom_out', 'отъезд'], ['pan_left', 'панорама влево'], ['pan_right', 'панорама вправо'], ['pan_up', 'панорама вверх'], ['pan_down', 'панорама вниз'], ['shake', 'тряска']];
export const TRANSITIONS = [['cut', 'склейка'], ['whoosh', 'вжух'], ['flash', 'вспышка'], ['glitch', 'глитч'], ['zoom_punch', 'зум-удар'], ['slide', 'сдвиг'], ['dip_black', 'через чёрное']];
export const FITS = [['fill', 'заполнить'], ['fit', 'вписать']];
export const STYLES = [['kinetic', 'по словам'], ['keyword', 'ключевое слово']];
export const COLORS = [['#FFFFFF', 'белый'], ['#FFD23F', 'жёлтый'], ['#8FCB6B', 'акцент']];
export const FONTS = ['Avenir Next Condensed', 'Futura Condensed ExtraBold', 'Impact'];
export const NICK_CLIPS = [
  ['e66cc4fe', 'сверху, ухмылка'], ['c68d59c9', '3/4 влево, ухмылка'], ['addf7572', 'анфас, нейтральный'],
  ['fa5d5599', 'снизу, ухмылка'], ['f79353fc', '3/4 вправо, ухмылка'], ['13139fae', 'анфас, сигарета'], ['2e30a2e3', '3/4 влево, сигарета'],
];

function wordsBetween(words, a, b) { return (words || []).filter(([t]) => t >= a - 1e-6 && t < b - 1e-6).map(([, , tok]) => tok).join(' '); }
const kv = (...kids) => el('div', { class: 'kv' }, ...kids);
const row = (label, ctl) => [el('span', { class: 'mu' }, label), ctl];
const sel = (opts, val, on) => { const s = el('select', { onchange: (e) => on(e.target.value) }); for (const [v, label] of opts) s.append(el('option', { value: v, selected: v === val }, label)); return s; };
const num = (val, on, opts = {}) => el('input', Object.assign({ type: 'number', value: val, onchange: (e) => on(+e.target.value) }, opts));
const chk = (checked, on) => el('input', { type: 'checkbox', checked, onchange: (e) => on(e.target.checked) });

export function mountInspector(store) {
  const root = document.getElementById('inspector');
  function render() {
    root.innerHTML = '';
    const ids = [...store.sel];
    if (!ids.length) { root.append(el('div', { class: 'empty' }, 'Выделите клип — здесь появятся его настройки')); return; }
    if (ids.length > 1) return renderMulti(root, store, ids);
    const c = store.clip(ids[0]);
    if (!c) { root.append(el('div', { class: 'empty' }, 'Выделите клип — здесь появятся его настройки')); return; }
    if (c.track === 'v1') renderFrame(root, store, c);
    else if (c.track === 'text') renderText(root, store, c);
    else if (c.track.startsWith('sfx')) renderSfx(root, store, c);
    else if (c.track === 'music') renderMusic(root, store, c);
    else if (c.track === 'nick') renderNick(root, store, c);
    else root.append(el('div', { class: 'ih' }, 'Голос'), el('div', { class: 'empty' }, 'Свойства этой дорожки не редактируются здесь.'));
  }
  // Изменения проекта (свои или Claude) не должны стирать поле, в котором сейчас печатают: перерисуем после ухода фокуса.
  let stale = false;
  const editing = () => root.contains(document.activeElement) && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  root.addEventListener('focusout', () => setTimeout(() => { if (stale && !editing()) { stale = false; render(); } }));
  store.on('sel', () => { stale = false; render(); });
  store.on('project', () => { if (editing() && store.sel.size === 1 && store.clip([...store.sel][0])) stale = true; else render(); });
  render();
}

function renderMulti(root, store, ids) {
  const clips = ids.map((id) => store.clip(id)).filter(Boolean);
  const delible = clips.filter((c) => c.track !== 'voice');
  root.append(el('div', { class: 'ih' }, `Выделено ${ids.length}`));
  root.append(el('div', { class: 'selrow' },
    delible.length ? el('button', {
      class: 'btn', onclick: async () => { await store.dispatch(delible.map((c) => ({ op: 'remove', id: c.id })), { label: 'удаление' }); },
    }, 'Удалить') : null,
    el('button', { class: 'btn', onclick: () => window.NE.review && window.NE.review.compose() }, 'Оставить правку (C)')));
}

function setOne(store, c, fields, label) { return store.dispatch([{ op: 'set', id: c.id, fields }], { label }); }

// ---------------------------------------------------------------- Кадр (v1)
function renderFrame(root, store, c) {
  root.append(el('div', { class: 'ih' }, `Кадр ${c.shot || c.id} · ${fmtTC(c.start)}`));
  const body = kv(
    ...row('Длина, с', num(+c.dur.toFixed(2), async (v) => {
      const v1 = store.track('v1'), i = v1.findIndex((x) => x.id === c.id), next = v1[i + 1];
      if (!next) return; // последний кадр — длину меняют перетаскиванием края
      await store.dispatch([{ op: 'move_cut', left: c.id, right: next.id, t: c.start + Math.max(1 / 30, v) }], { label: 'длина кадра' });
    }, { step: '0.1', min: '0.03' })),
    ...row('Движение', sel(MOTIONS, c.motion || 'static', (v) => setOne(store, c, { motion: v }, 'движение'))),
    ...row('Переход', sel(TRANSITIONS, c.transition || 'cut', (v) => setOne(store, c, { transition: v }, 'переход'))),
    ...row('Кадрирование', sel(FITS, c.fit || 'fill', (v) => setOne(store, c, { fit: v }, 'кадрирование'))),
    ...row('Слова', el('span', { class: 'ro' }, wordsBetween(store.words, c.start, c.start + c.dur) || '—')),
  );
  root.append(body);
  if (c.kind === 'video') {
    body.append(
      ...row('Старт видео, с', el('div', { class: 'row2' }, num(c.in || 0, (v) => setOne(store, c, { in: Math.max(0, v) }, 'старт видео'), { step: '0.1', min: '0' }),
        el('button', { class: 'btn', 'data-tip': 'Выбрать момент по превью', onclick: () => openInPoint(store, c) }, 'Выбрать…'))),
      ...row('Скорость', num(c.speed || 1, (v) => setOne(store, c, { speed: Math.min(4, Math.max(0.25, v)) }, 'скорость'), { step: '0.05', min: '0.25', max: '4' })),
      ...row('Задом наперёд', chk(!!c.reverse, (v) => setOne(store, c, { reverse: v || null }, 'задом наперёд'))),
      ...row('Звук ролика', el('div', { class: 'row2' },
        num(c.volume_db ?? -22, (v) => setOne(store, c, { volume_db: v }, 'звук ролика'), { step: '1', style: { flex: 1 } }),
        el('label', { class: 'row2' }, chk(!!c.mute, (v) => setOne(store, c, { mute: v || null }, 'выкл. звук ролика')), 'выкл'))),
    );
  }
}

// ---------------------------------------------------------------- Надпись (text)
function renderText(root, store, c) {
  root.append(el('div', { class: 'ih' }, 'Надпись'));
  const ta = el('textarea', {}, c.text || ''); // value= через setAttribute textarea не наполняет — только дочерний текстовый узел
  ta.addEventListener('blur', async () => {
    const text = ta.value.trim();
    if (!text || text === c.text) return;
    const words = c.style === 'keyword' ? c.words : (store.kineticFor ? store.kineticFor(c, text) : c.words);
    await setOne(store, c, { text, words }, 'текст');
  });
  const swatches = el('div', { class: 'swatches' });
  for (const [hex, name] of COLORS) {
    const on = (c.color || '#FFFFFF').toUpperCase() === hex;
    swatches.append(el('span', {
      class: 'swatch' + (on ? ' on' : ''), style: { background: hex }, 'data-tip': name,
      onclick: () => setOne(store, c, { color: hex === '#FFFFFF' ? null : hex }, 'цвет надписи'),
    }));
  }
  const wordOpts = store.words.filter(([t]) => t >= c.start - 3 && t <= c.start + 3);
  const curAnchor = c.anchor && c.anchor.word;
  const wordSel = el('select', {
    onchange: async (e) => {
      const [t, ref] = JSON.parse(e.target.value);
      if (ref == null) { await setOne(store, c, { anchor: null }, 'слово появления'); return; }   // «—» — без привязки
      const start = Math.max(0, t - 0.12);
      const words = c.style === 'kinetic' ? (store.kineticFor ? store.kineticFor({ start, dur: c.dur }, c.text) : c.words) : c.words;
      await store.dispatch([{ op: 'move', id: c.id, start, anchor: { word: ref, lead: 0.12 } }, { op: 'set', id: c.id, fields: { words } }], { label: 'слово появления' });
    },
  }, el('option', { value: '[]', selected: !curAnchor }, '—'), ...wordOpts.map(([t, ref, tok]) => el('option', { value: JSON.stringify([t, ref]), selected: ref === curAnchor }, `«${tok}» · ${fmtTC(t)}`)));
  root.append(kv(
    ...row('Текст', ta),
    ...row('Стиль', sel(STYLES, c.style || 'kinetic', (v) => setOne(store, c, { style: v }, 'стиль надписи'))),
    ...row('Цвет', swatches),
    ...row('Шрифт', sel(FONTS.map((f) => [f, f]), c.font || FONTS[0], (v) => setOne(store, c, { font: v }, 'шрифт'))),
    ...row('Появляется на слове', wordSel),
  ));
}

// ---------------------------------------------------------------- Эффект (sfx1/sfx2)
function renderSfx(root, store, c) {
  root.append(el('div', { class: 'ih' }, 'Эффект'));
  const sounds = store.library.sounds || [];
  root.append(kv(
    ...row('Звук', sel(sounds.map((a) => [a.src, a.name]), c.src, (v) => {
      const a = sounds.find((x) => x.src === v); if (a) setOne(store, c, { src: a.src, tag: a.name, dur: a.dur }, 'звук эффекта');
    })),
    ...row('Громкость, дБ', num(c.volume_db ?? -9, (v) => setOne(store, c, { volume_db: v }, 'громкость эффекта'), { step: '1' })),
    ...row('Упреждение, с', num((c.anchor && c.anchor.pre) || 0, (v) => setOne(store, c, { anchor: { ...(c.anchor || {}), pre: Math.max(0, v) } }, 'упреждение'), { step: '0.01', min: '0' })),
  ));
}

// ---------------------------------------------------------------- Музыка
function renderMusic(root, store, c) {
  root.append(el('div', { class: 'ih' }, 'Музыка'));
  const music = store.library.music || [];
  root.append(kv(
    ...row('Трек', sel(music.map((a) => [a.src, a.name]), c.src, (v) => setOne(store, c, { src: v }, 'трек'))),
    ...row('Громкость, дБ', num(c.volume_db ?? -17, (v) => setOne(store, c, { volume_db: v }, 'громкость музыки'), { step: '1' })),
    ...row('Нарастание, с', num(c.fade_in || 0, (v) => setOne(store, c, { fade_in: Math.max(0, v) }, 'нарастание'), { step: '0.1', min: '0' })),
    ...row('Затухание, с', num(c.fade_out || 0, (v) => setOne(store, c, { fade_out: Math.max(0, v) }, 'затухание'), { step: '0.1', min: '0' })),
    ...row('Зациклить', chk(!!c.loop, (v) => setOne(store, c, { loop: v || null }, 'зациклить'))),
  ));
}

// ---------------------------------------------------------------- Ник
function renderNick(root, store, c) {
  root.append(el('div', { class: 'ih' }, 'Ник'));
  // На сервере нет метода перечислить файлы assets/nick_clips — определяем доступные варианты по уже использованным в проекте клипам.
  const found = new Map();
  for (const x of store.project.clips) {
    if (x.track !== 'nick' || !x.src) continue;
    for (const [id] of NICK_CLIPS) if (x.src.includes(id) && !found.has(id)) found.set(id, x.src);
  }
  const curId = NICK_CLIPS.find(([id]) => (c.src || '').includes(id))?.[0] || '';
  const s = el('select', {
    onchange: (e) => { const src = found.get(e.target.value); if (src) setOne(store, c, { src }, 'клип Ника'); },
  });
  for (const [id, label] of NICK_CLIPS) s.append(el('option', { value: id, selected: id === curId, disabled: !found.has(id) }, `${label}${found.has(id) ? '' : ' (нет файла)'}`));
  root.append(kv(...row('Клип Ника', s)));
}
