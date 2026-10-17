// Меню по правой кнопке на таймлайне: действия под тип клипа (кадр, надпись, эффект, музыка, Ник, голос),
// для нескольких выделенных клипов и для пустого места на дорожке. Всё — обычными операциями (⌘Z отменяет).
import { menu, dialog, toast } from '../ui.js';
import { el, fmtTC, frame } from '../util.js';
import { openInPoint } from '../panels/inpoint.js';
import { MOTIONS, TRANSITIONS, FITS, STYLES, COLORS, FONTS, NICK_CLIPS } from '../panels/inspector.js';

const F = 1 / 30;
const PRE = { whoosh: 0.15, riser: 1.2, swipe: 0.1 };
const TRACK_RU = { v1: 'Кадры', nick: 'Ник', text: 'Надписи', voice: 'Голос', music: 'Музыка', sfx1: 'Эффекты 1', sfx2: 'Эффекты 2' };
const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const SFX_DB = [-18, -12, -9, -6, -3, 0], MUSIC_DB = [-26, -22, -17, -14, -10];
const FADES = [0, 0.5, 1, 2, 4], LENS = [1, 1.5, 2, 3, 4, 6];
const db = (v) => `${v > 0 ? '+' : ''}${v} дБ`;
const sec = (v) => `${String(v).replace('.', ',')} с`;
const short = (s, n = 18) => ((s || '').length > n ? s.slice(0, n - 1) + '…' : s || '');
const name = (src) => (src || '').split('/').pop().replace(/\.[a-z0-9]+$/i, '');

const run = (store, ops, label) => store.dispatch(ops, { label }).catch(() => {});      // ошибка уже показана через store 'error'
const setAll = (store, clips, fields, label) => run(store, clips.map((c) => ({ op: 'set', id: c.id, fields: typeof fields === 'function' ? fields(c) : fields })), label);
const pick = (opts, cur, on) => opts.map(([v, label]) => ({ label, checked: v === cur, run: () => on(v) }));
const same = (clips, key, def) => { const v = clips.map((c) => c[key] ?? def); return v.every((x) => x === v[0]) ? v[0] : undefined; };
const inside = (c, t) => c.start + F - 1e-6 <= t && t <= c.start + c.dur - F + 1e-6;
const copyable = (c) => c.track !== 'v1' && c.track !== 'voice';
const compose = (preset) => window.NE.review && window.NE.review.compose(true, preset);
function nb(store, c) { const tr = store.track(c.track), i = tr.findIndex((x) => x.id === c.id); return [tr[i - 1], tr[i + 1]]; }
function kinetic(store, c, start, dur, text = c.text) { return c.style === 'keyword' || !store.kineticFor ? c.words : store.kineticFor({ ...c, start, dur }, text); }
function nearestWord(store, t, maxd = 0.6) {
  let best = null;
  for (const w of store.words || []) { const d = Math.abs(w[0] - t); if (d <= maxd && (!best || d < Math.abs(best[0] - t))) best = w; }
  return best;
}

export function duplicate(store, c) {
  const clip = JSON.parse(JSON.stringify(c)); delete clip.id; delete clip.anchor;
  clip.start = frame(c.start + c.dur);
  return run(store, [{ op: 'add', clip }], 'дубль');
}
function copy(store, c) { const cb = JSON.parse(JSON.stringify(c)); delete cb.id; store.clipboard = cb; toast(`Скопировано: ${short(cb.text || cb.tag || name(cb.src) || TRACK_RU[cb.track])}`, 'ok'); }

function title(c) {
  if (c.track === 'v1') return `Кадр ${c.shot || c.id} · ${fmtTC(c.start)}`;
  if (c.track === 'text') return `Надпись «${short(c.text)}»`;
  if (c.track.startsWith('sfx')) return `Эффект «${c.tag || name(c.src)}»`;
  if (c.track === 'music') return `Музыка «${short(name(c.src), 22)}»`;
  return `${TRACK_RU[c.track] || c.track} · ${fmtTC(c.start)}`;
}

function editText(store, c) {
  const inp = el('input', { value: c.text || '', style: { width: '100%' } });
  const { okBtn } = dialog({ title: 'Текст надписи', body: inp, ok: 'Сохранить', onOk: async () => {
    const text = inp.value.trim(); if (!text || text === c.text) return;
    await run(store, [{ op: 'set', id: c.id, fields: { text, words: kinetic(store, c, c.start, c.dur, text) } }], 'текст');
  } });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); okBtn.click(); } });
  setTimeout(() => { inp.focus(); inp.select(); });
}

// начало/конец клипа (не кадра) — к красной линии
function edgeItems(store, c) {
  const t = frame(store.t), end = c.start + c.dur;
  const setSpan = (start, dur, label) => run(store, [{ op: 'set', id: c.id, fields: { start, dur, ...(c.track === 'text' ? { words: kinetic(store, c, start, dur) } : {}), ...(c.in != null && start !== c.start ? { in: Math.max(0, c.in + (start - c.start)) } : {}) } }], label);
  return [
    { label: 'Начало — к красной линии', disabled: !(t < end - F), tip: 'Красная линия должна быть левее конца клипа', run: () => setSpan(t, frame(end - t), 'начало к линии') },
    { label: 'Конец — к красной линии', disabled: !(t > c.start + F), tip: 'Красная линия должна быть правее начала клипа', run: () => setSpan(c.start, frame(t - c.start), 'конец к линии') },
  ];
}

function frameItems(store, c) {
  const [prev, next] = nb(store, c), t = frame(store.t), video = c.kind === 'video';
  const cutOk = (a, b) => a && b && t > a.start + F && t < b.start + b.dur - F;
  return [
    { label: 'Движение', sub: pick(MOTIONS, c.motion || 'static', (v) => setAll(store, [c], { motion: v }, 'движение')) },
    { label: 'Переход', sub: pick(TRANSITIONS, c.transition || 'cut', (v) => setAll(store, [c], { transition: v }, 'переход')) },
    { label: 'Кадрирование', sub: pick(FITS, c.fit || 'fill', (v) => setAll(store, [c], { fit: v }, 'кадрирование')) },
    video ? { label: 'Выбрать начало видео…', run: () => openInPoint(store, c) } : null,
    video ? { label: 'Скорость видео', sub: SPEEDS.map((v) => ({ label: `×${String(v).replace('.', ',')}`, checked: (c.speed || 1) === v, run: () => setAll(store, [c], { speed: v === 1 ? null : v }, 'скорость') })) } : null,
    video ? { label: 'Задом наперёд', checked: !!c.reverse, run: () => setAll(store, [c], { reverse: c.reverse ? null : true }, 'задом наперёд') } : null,
    video ? { label: c.mute ? 'Включить звук ролика' : 'Выключить звук ролика', run: () => setAll(store, [c], { mute: c.mute ? null : true }, 'звук ролика') } : null,
    { sep: true },
    { label: 'Начало кадра — к красной линии', disabled: !cutOk(prev, c), tip: 'Склейка с предыдущим кадром встанет на красную линию', run: () => run(store, [{ op: 'move_cut', left: prev.id, right: c.id, t }], 'склейка') },
    { label: 'Конец кадра — к красной линии', disabled: !cutOk(c, next), tip: 'Склейка со следующим кадром встанет на красную линию', run: () => run(store, [{ op: 'move_cut', left: c.id, right: next.id, t }], 'склейка') },
    { label: 'Поменять местами', sub: [
      { label: `с предыдущим${prev ? ' · ' + (prev.shot || prev.id) : ''}`, disabled: !prev, run: () => run(store, [{ op: 'swap', a: c.id, b: prev.id }], 'обмен кадров') },
      { label: `со следующим${next ? ' · ' + (next.shot || next.id) : ''}`, disabled: !next, run: () => run(store, [{ op: 'swap', a: c.id, b: next.id }], 'обмен кадров') },
    ] },
    { sep: true },
    { label: 'Заменить картинку…', tip: 'Откроет «Медиа» на этом кадре: перетащите файл на клип', run: () => { store.setUi({ panel: 'media', leftOpen: true }); store.select([c.id]); } },
    { label: 'Регенерировать в Higgsfield…', tip: 'Правка с ценой и галочкой «разрешаю»; варианты придут карточкой — поставите сами', run: () => { store.select([c.id]); compose({ text: 'Сгенерируй другую картинку для этого кадра: ', type: 'higgsfield' }); } },
    { label: 'Показать файл в Finder', disabled: !c.src, run: () => store.api.post(store.url('/reveal'), { asset: c.src }).catch((e) => toast(e.message, 'error')) },
  ];
}

function textItems(store, c) {
  const w = nearestWord(store, store.t);
  return [
    { label: 'Изменить текст…', hint: 'двойной клик', run: () => editText(store, c) },
    { label: 'Цвет', sub: COLORS.map(([hex, n]) => ({ label: n, checked: (c.color || '#FFFFFF').toUpperCase() === hex, run: () => setAll(store, [c], { color: hex === '#FFFFFF' ? null : hex }, 'цвет надписи') })) },
    { label: 'Стиль', sub: pick(STYLES, c.style || 'kinetic', (v) => setAll(store, [c], { style: v }, 'стиль надписи')) },
    { label: 'Шрифт', sub: pick(FONTS.map((f) => [f, f]), c.font || FONTS[0], (v) => setAll(store, [c], { font: v }, 'шрифт')) },
    { label: 'Длина', sub: LENS.map((v) => ({ label: sec(v), checked: Math.abs(c.dur - v) < 0.02, run: () => run(store, [{ op: 'set', id: c.id, fields: { dur: v, words: kinetic(store, c, c.start, v) } }], 'длина надписи') })) },
    { sep: true },
    { label: w ? `Появляться на слове «${w[2]}»` : 'Появляться на слове у красной линии', disabled: !w, tip: w ? null : 'Поставьте красную линию на слово', run: () => {
      const start = Math.max(0, frame(w[0] - 0.12));
      return run(store, [{ op: 'move', id: c.id, start, anchor: { word: w[1], lead: 0.12 } }, { op: 'set', id: c.id, fields: { words: kinetic(store, c, start, c.dur) } }], 'слово появления');
    } },
    ...edgeItems(store, c),
  ];
}

function sfxItems(store, c) {
  const lib = (store.library && store.library.sounds) || [], other = c.track === 'sfx1' ? 'sfx2' : 'sfx1', pre = PRE[c.tag] || 0;
  return [
    { label: 'Громкость', sub: SFX_DB.map((v) => ({ label: db(v), checked: Math.round(c.volume_db ?? -9) === v, run: () => setAll(store, [c], { volume_db: v }, 'громкость эффекта') })) },
    { label: 'Заменить звук', disabled: !lib.length, sub: lib.map((a) => ({ label: a.name, hint: sec(Math.round(a.dur * 10) / 10), checked: a.src === c.src, run: () => setAll(store, [c], { src: a.src, tag: a.name, dur: a.dur }, 'звук эффекта') })) },
    { label: `Перенести на «${TRACK_RU[other]}»`, run: () => run(store, [{ op: 'move', id: c.id, start: c.start, track: other }], 'перенос') },
    { label: 'Поставить на красную линию', tip: pre ? `С упреждением ${sec(pre)}, чтобы удар пришёлся на линию` : null, run: () => run(store, [{ op: 'move', id: c.id, start: Math.max(0, frame(store.t - pre)), anchor: null }], 'перемещение') },
    ...edgeItems(store, c),
  ];
}

function musicItems(store, c, interact, x, y) {
  const lib = (store.library && store.library.music) || [];
  return [
    { label: 'Громкость', sub: MUSIC_DB.map((v) => ({ label: db(v), checked: Math.round(c.volume_db ?? -17) === v, run: () => setAll(store, [c], { volume_db: v }, 'громкость музыки') })) },
    { label: 'Заменить трек', disabled: !lib.length, sub: lib.map((a) => ({ label: a.name, checked: a.src === c.src, run: () => setAll(store, [c], { src: a.src }, 'трек') })) },
    { label: 'Растянуть…', tip: 'На весь выпуск, на главу, на отрезок или отсюда до конца', run: () => setTimeout(() => interact.openMusicChooser({ src: c.src, name: name(c.src) }, store.t, x, y)) },
    { label: 'Появление', sub: FADES.map((v) => ({ label: v ? sec(v) : 'сразу', checked: (c.fade_in || 0) === v, run: () => setAll(store, [c], { fade_in: v || null }, 'появление') })) },
    { label: 'Затухание', sub: FADES.map((v) => ({ label: v ? sec(v) : 'сразу', checked: (c.fade_out || 0) === v, run: () => setAll(store, [c], { fade_out: v || null }, 'затухание') })) },
    { label: 'Зациклить', checked: !!c.loop, run: () => setAll(store, [c], { loop: c.loop ? null : true }, 'петля') },
    ...edgeItems(store, c),
  ];
}

function nickItems(store, c) {
  const found = new Map();
  for (const x of store.project.clips) if (x.track === 'nick' && x.src) for (const [id] of NICK_CLIPS) if (x.src.includes(id) && !found.has(id)) found.set(id, x.src);
  const cur = NICK_CLIPS.find(([id]) => (c.src || '').includes(id))?.[0];
  return [
    { label: 'Поза Ника', sub: NICK_CLIPS.map(([id, n]) => ({ label: n + (found.has(id) ? '' : ' (нет файла)'), checked: id === cur, disabled: !found.has(id), run: () => setAll(store, [c], { src: found.get(id) }, 'клип Ника') })) },
    ...edgeItems(store, c),
  ];
}

function oneItems(store, c, interact, x, y) {
  const t = frame(store.t);
  const own = c.track === 'v1' ? frameItems(store, c) : c.track === 'text' ? textItems(store, c) : c.track.startsWith('sfx') ? sfxItems(store, c)
    : c.track === 'music' ? musicItems(store, c, interact, x, y) : c.track === 'nick' ? nickItems(store, c) : [];
  return [
    { header: title(c) },
    { label: 'Играть с начала клипа', run: () => { store.setTime(c.start); window.NE.transport.play(); } },
    c.track === 'voice' && c.kind === 'audio' ? { label: 'Сдвинуть голос', sub: [-0.2, -0.1, -0.05, 0.05, 0.1, 0.2].map((d) => ({ label: `${d > 0 ? '+' : '−'}${Math.abs(d)} с`, run: () => run(store, [{ op: 'move', id: c.id, start: Math.max(0, c.start + d) }], 'сдвиг голоса') })) } : null,
    c.track !== 'voice' ? { label: 'Разрезать на красной линии', hint: 'B', disabled: !inside(c, t), tip: inside(c, t) ? null : 'Поставьте красную линию внутрь клипа', run: () => run(store, [{ op: 'split', id: c.id, t }], 'разрез') } : null,
    own.length ? { sep: true } : null,
    ...own,
    { sep: true },
    { label: 'Копировать', hint: '⌘C', disabled: !copyable(c), run: () => copy(store, c) },
    { label: 'Дублировать', hint: '⌘D', disabled: !copyable(c), tip: 'Копия встанет сразу после клипа', run: () => duplicate(store, c) },
    { label: 'Выделить', sub: [
      { label: `всё на дорожке «${TRACK_RU[c.track]}»`, run: () => store.select(store.track(c.track).map((k) => k.id)) },
      { label: 'всё правее на этой дорожке', run: () => store.select(store.track(c.track).filter((k) => k.start >= c.start).map((k) => k.id)) },
      { label: 'отрезок по клипу', tip: 'Для «что играть → выделенный отрезок» и правок', run: () => store.setRange([c.start, c.start + c.dur]) },
    ] },
    { sep: true },
    { label: 'Оставить правку…', hint: 'C', run: () => compose() },
    c.track !== 'voice' ? { label: c.track === 'v1' ? 'Удалить кадр' : 'Удалить', hint: '⌫', danger: true, tip: c.track === 'v1' ? 'Соседний кадр займёт его место' : null, run: () => run(store, [{ op: 'remove', id: c.id }], 'удаление') } : null,
  ];
}

function multiItems(store, clips) {
  const v1 = clips.filter((c) => c.track === 'v1'), texts = clips.filter((c) => c.track === 'text');
  const aud = clips.filter((c) => c.track.startsWith('sfx') || c.track === 'music'), del = clips.filter((c) => c.track !== 'voice');
  const a = Math.min(...clips.map((c) => c.start)), b = Math.max(...clips.map((c) => c.start + c.dur));
  const defDb = (c) => (c.track === 'music' ? -17 : -9);
  return [
    { header: `Выделено ${clips.length} · ${fmtTC(a)}–${fmtTC(b)}` },
    { label: 'Играть с начала выделенного', run: () => { store.setTime(a); window.NE.transport.play(); } },
    { label: 'Отрезок по выделенному', run: () => store.setRange([a, b]) },
    v1.length ? { sep: true } : null,
    v1.length ? { label: `Движение · ${v1.length} кадр.`, sub: pick(MOTIONS, same(v1, 'motion', 'static'), (v) => setAll(store, v1, { motion: v }, 'движение')) } : null,
    v1.length ? { label: `Переход · ${v1.length} кадр.`, sub: pick(TRANSITIONS, same(v1, 'transition', 'cut'), (v) => setAll(store, v1, { transition: v }, 'переход')) } : null,
    v1.length ? { label: `Кадрирование · ${v1.length} кадр.`, sub: pick(FITS, same(v1, 'fit', 'fill'), (v) => setAll(store, v1, { fit: v }, 'кадрирование')) } : null,
    texts.length ? { sep: true } : null,
    texts.length ? { label: `Цвет · ${texts.length} надп.`, sub: COLORS.map(([hex, n]) => ({ label: n, checked: same(texts, 'color', '#FFFFFF') === hex, run: () => setAll(store, texts, { color: hex === '#FFFFFF' ? null : hex }, 'цвет надписей') })) } : null,
    texts.length ? { label: `Шрифт · ${texts.length} надп.`, sub: pick(FONTS.map((f) => [f, f]), same(texts, 'font', FONTS[0]), (v) => setAll(store, texts, { font: v }, 'шрифт')) } : null,
    aud.length ? { sep: true } : null,
    aud.length ? { label: `Громкость · ${aud.length} зв.`, sub: [
      { label: 'громче на 3 дБ', run: () => setAll(store, aud, (c) => ({ volume_db: (c.volume_db ?? defDb(c)) + 3 }), 'громче') },
      { label: 'тише на 3 дБ', run: () => setAll(store, aud, (c) => ({ volume_db: (c.volume_db ?? defDb(c)) - 3 }), 'тише') },
      { sep: true },
      ...SFX_DB.map((v) => ({ label: db(v), run: () => setAll(store, aud, { volume_db: v }, 'громкость') })),
    ] } : null,
    { sep: true },
    { label: `Оставить правку к ${clips.length} клипам…`, hint: 'C', run: () => compose() },
    del.length ? { label: `Удалить ${del.length}`, hint: '⌫', danger: true, run: () => run(store, del.map((c) => ({ op: 'remove', id: c.id })), 'удаление') } : null,
  ];
}

function emptyItems(store, lane, t) {
  const cb = store.clipboard, kind = (tr) => store.project.tracks.find((x) => x.id === tr)?.kind;
  const target = cb && (lane && kind(lane) === kind(cb.track) ? lane : cb.track);
  return [
    { header: `${TRACK_RU[lane] || 'Таймлайн'} · ${fmtTC(t)}` },
    { label: 'Поставить красную линию сюда', run: () => store.setTime(t) },
    { label: 'Вставить сюда', hint: '⌘V', disabled: !cb, tip: cb ? null : 'Сначала скопируйте клип (⌘C)', run: () => run(store, [{ op: 'add', clip: { ...cb, track: target, start: frame(t) } }], 'вставка') },
    lane === 'text' || !lane ? { label: 'Надпись здесь', run: async () => {
      const text = 'ТЕКСТ', start = frame(t), dur = 2;
      const r = await store.dispatch([{ op: 'add', clip: { track: 'text', style: 'kinetic', text, start, dur, words: store.kineticFor ? store.kineticFor({ start, dur }, text) : [] } }], { label: 'надпись' }).catch(() => null);
      if (r && r.changed && r.changed.length) store.select(r.changed);
    } } : null,
    lane && (lane.startsWith('sfx') || lane === 'music') ? { label: lane === 'music' ? 'Выбрать музыку…' : 'Выбрать звук…', run: () => store.setUi({ panel: 'sounds', leftOpen: true, sndTab: lane === 'music' ? 'music' : 'sounds' }) } : null,
    lane ? { label: `Выделить всё на дорожке «${TRACK_RU[lane]}»`, run: () => store.select(store.track(lane).map((k) => k.id)) } : null,
    { sep: true },
    { label: 'Правка к этому месту…', hint: 'C', run: () => { store.select([]); store.setTime(t); compose(); } },
  ];
}

export function attachContextMenu(store, tl, interact) {
  tl.body.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const ce = e.target.closest('.cl'), t = tl.tAt(e.clientX), lane = tl.laneAt(e.clientY);
    if (ce && store.clip(ce.dataset.id)) {
      if (!store.sel.has(ce.dataset.id)) store.select([ce.dataset.id]);
      const clips = [...store.sel].map((id) => store.clip(id)).filter(Boolean);
      menu(e.clientX, e.clientY, clips.length > 1 ? multiItems(store, clips) : oneItems(store, clips[0], interact, e.clientX, e.clientY));
    } else menu(e.clientX, e.clientY, emptyItems(store, lane, t));
  });
}
