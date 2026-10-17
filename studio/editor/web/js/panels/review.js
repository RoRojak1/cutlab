// Правки — задача 14: панель, создание по C, стоп-кадр, Higgsfield с галочкой, «Исправить».
import { el, fmtTC, assetURL, thumbURL } from '../util.js';
import { lightbox } from './lightbox.js';
import { dialog, toast } from '../ui.js';

const TYPES = ['timing', 'image', 'higgsfield', 'sound', 'text', 'other'];
const TYPE_RU = { timing: 'тайминг', image: 'картинка', higgsfield: 'Higgsfield', sound: 'звук', text: 'текст', other: 'другое' };
const STATUS_RU = { new: 'новая', reopened: 'переоткрыта', working: 'Claude работает…', question: 'нужен ответ', done: 'готово ✓', accepted: 'принято' };
// Те же правила, что review.GUESS на сервере (review.py) — только определяют тип по умолчанию для показа полей, финальное решение всё равно принимает сервер.
const GUESS = [
  ['higgsfield', /сгенер|higgsfield|хиксфилд|хигсфилд|нейросет/],
  ['sound', /звук|громк|тише|громче|эффект|музык|всплеск|шум/],
  ['text', /надпис|текст|шрифт|титр/],
  ['timing', /переход|раньше|позже|склейк|тайминг|успева|слов|синхрон|длин/],
  ['image', /картин|фото|видео|кадр|качеств|изображ/],
];
function guessType(text) { const low = (text || '').toLowerCase(); for (const [t, rx] of GUESS) if (rx.test(low)) return t; return 'other'; }
const MODELS = [
  { id: 'gpt_image_2.5_medium_1k', label: 'GPT Image 2.5 medium 1k', cost: 0.5 },
  { id: 'gpt_image_2.5_high_2k', label: 'GPT Image 2.5 high 2k', cost: 2.75 },
  { id: 'seedance_2.5_720p_5s', label: 'Видео Seedance 2.5 720p 5 с', cost: 35 },
  { id: 'seedance_2.5_1080p_5s', label: 'Видео Seedance 2.5 1080p 5 с', cost: 60 },
];
const FILTERS = [['all', 'все', null], ['new', 'новые', ['new', 'reopened']], ['working', 'в работе', ['working']], ['done', 'готово', ['done', 'accepted']], ['question', 'нужен ответ', ['question']]];
// уже решённое (вариант поставлен, правка принята) в общем списке не висит — оно во вкладке «готово»
const settled = (c) => c.status === 'accepted' || (c.status === 'done' && c.chosen != null);   // переоткрытая — снова в общем списке
const inFilter = (c, id) => { const st = FILTERS.find((f) => f[0] === id)[2]; return st ? st.includes(c.status) : !settled(c); };
const fmtCr = (v) => `${(Math.round(v * 100) / 100).toString().replace('.', ',')} кр`;
const wordsBetween = (words, a, b) => (words || []).filter(([t]) => t >= a - 1e-6 && t < b - 1e-6).map(([, , tok]) => tok).join(' ');

// Речь под кадрами правки: строка сценария клипа («1.8 [NICK] Откуда разница…») и, если голос уже привязан к словам, — английские слова этого отрезка.
function speechOf(store, c) {
  const ids = [...new Set([...(c.clips || []), c.variant_clip].filter(Boolean))];
  const cl = ids.map((id) => store.clip(id)).filter((x) => x && x.track === 'v1');
  // say — полная русская реплика сценария (build_ep02.py --say), say_en — что звучит по-английски; иначе — метка из text
  const lines = cl.map((x) => {
    const m = /^\S+\s+\[([^\]]+)\]\s*(.*)$/s.exec(x.text || '');
    const tag = m ? m[1] : '', txt = (x.say || (m ? m[2] : x.text || '')).replace(/^★[^)]*\)\s*/, '').trim();
    return txt ? { shot: x.shot || x.id, tag, txt, en: x.say_en || '' } : null;
  }).filter(Boolean);
  let en = '';
  if (cl.length && (store.words || []).length && !lines.some((l) => l.en)) {
    const a = Math.min(...cl.map((x) => x.start)), b = Math.max(...cl.map((x) => x.start + x.dur));
    en = wordsBetween(store.words, a, b);
  }
  return { lines, en };
}
function speechEl(sp) {
  if (!sp.lines.length && !sp.en) return null;
  const box = el('div', { class: 'speech', 'data-tip': 'Что звучит, пока идут эти кадры · клик — развернуть' },
    ...sp.lines.flatMap((l) => [el('div', { class: 'sl' }, sp.lines.length > 1 ? el('b', {}, l.shot + ' ') : null, l.tag ? el('span', { class: 'stag' }, l.tag) : null, l.txt),
      l.en ? el('div', { class: 'sl en' }, el('span', { class: 'stag' }, 'EN'), l.en) : null]),
    sp.en ? el('div', { class: 'sl en' }, el('span', { class: 'stag' }, 'EN'), `«${sp.en}»`) : null);
  box.onclick = () => box.classList.toggle('open');
  return box;
}

function jump(store, c) {
  const cl = (c.clips || []).map((id) => store.clip(id)).filter(Boolean);
  const t = c.range ? c.range[0] : cl.length ? cl[0].start : store.t;
  if (c.clips && c.clips.length) { const ids = c.clips.filter((id) => store.clip(id)); if (ids.length) store.select(ids); }
  store.setTime(t);
  window.NE.timeline.ensureVisible(t);
}

// Черновики ответов переживают перерисовку списка (события проекта/правок во время работы Claude): id правки → {text, focus}.
const drafts = new Map();

function inlineReply(card, placeholder, onSend, id) {
  const d = drafts.get(id) || { text: '' };
  drafts.set(id, d);
  const inp = el('input', { placeholder });
  inp.value = d.text;
  inp.addEventListener('input', () => { d.text = inp.value; });
  inp.dataset.draft = id;
  if (d.focus) setTimeout(() => {           // перерисовок подряд может быть несколько — фокус в последнее живое поле
    if (!d.focus) return; d.focus = false;
    const cur = [...document.querySelectorAll('#review [data-draft]')].find((x) => x.dataset.draft === id);
    const a = document.activeElement;
    if (cur && (!a || a === document.body)) { cur.focus(); const k = d.caret ?? cur.value.length; cur.setSelectionRange(k, k); }
  });
  const btn = el('button', { class: 'btn pri' }, 'Отправить');
  const wrap = el('div', { class: 'answer' }, inp, btn);
  const send = async () => {
    const text = inp.value.trim(); if (!text) return;
    btn.disabled = true;
    try { await onSend(text); drafts.delete(id); wrap.remove(); } catch (e) { toast(e.message, 'error'); } finally { btn.disabled = false; }
  };
  btn.onclick = send;
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } });
  card.append(wrap);
  return wrap;
}

// Варианты кадра от Claude: предпросмотр в плеере на месте клипа, «Поставить» — одна операция set (⌘Z вернёт).
function variantsEl(store, c) {
  const vs = c.variants || [], viewer = window.NE.viewer;
  const clipId = c.variant_clip || (c.clips || [])[0], clip = store.clip(clipId);
  if (!vs.length || !viewer) return null;
  const pv = viewer.preview;
  const run = (fn) => Promise.resolve().then(fn).catch((e) => toast(e.message, 'error'));
  const look = (src, kind, label) => {
    if (pv && pv.clip === clipId && pv.src === src) return viewer.setPreview(null);
    jump(store, { clips: [clipId] });
    viewer.setPreview({ clip: clipId, src, kind }, label);
  };
  const setSrc = (f, label) => store.dispatch([{ op: 'set', id: clipId, fields: { src: f.src, kind: f.kind, in: f.kind === 'video' ? (f.in ?? 0) : null } }], { label });
  async function put(i) {
    const cur = store.clip(clipId);
    if (!cur) throw new Error(`клипа ${clipId} больше нет`);
    const prev = { src: cur.src, kind: cur.kind, in: cur.in ?? null };
    await setSrc({ src: vs[i].src, kind: vs[i].kind }, `вариант ${i + 1}`);
    viewer.setPreview(null);
    // в склеенной карточке вариант помнит, из какой правки он пришёл (_cid/_idx)
    await store.reviewPost(`review/comments/${vs[i]._cid || c.id}/choose`, { idx: vs[i]._idx ?? i, prev });
    toast(`Вариант ${i + 1} поставлен в ${clipId} — карточка ушла в «готово», ⌘Z вернёт`, 'ok');
  }
  async function back() {
    await setSrc(c.prev_src, 'вернуть старый кадр');
    viewer.setPreview(null);
    await store.reviewPost(`review/comments/${c.id}/revert`, {});
  }
  // список для большого просмотра: «сейчас» + все варианты; клик по плитке — сразу крупно, без плеера
  const items = [], sp = speechOf(store, c), speech = [...sp.lines.map((l) => l.en ? `${l.txt}  ·  EN: ${l.en}` : l.txt), sp.en ? `EN: «${sp.en}»` : ''].filter(Boolean).join('  ·  ') || null;
  // отвергнутые варианты не показываем снова: помеченные old (пришли новые) и все прежние, пока по правке «Claude работает»
  const last = (c.thread || [])[c.thread ? c.thread.length - 1 : 0];
  const waiting = c.chosen == null && ['new', 'working', 'reopened'].includes(c.status) && last && last.who === 'user';
  const isOld = (v) => c.chosen == null && (v.old || waiting);
  const shown = vs.map((v, i) => i).filter((i) => !isOld(vs[i])), older = vs.map((v, i) => i).filter((i) => isOld(vs[i]));
  if (clip && clip.src && c.chosen == null) items.push({ src: clip.src, kind: clip.kind, label: 'сейчас в монтаже', note: null, speech, chosen: true });
  shown.forEach((i) => items.push({ src: vs[i].src, kind: vs[i].kind, label: `вариант ${i + 1}`, note: vs[i].note || null, speech, chosen: c.chosen === i, put: () => run(() => put(i)) }));
  function tile(src, kind, label, cls, btn, tip, idx) {
    if (/\/ai_[^/]*$/.test(src)) label += ' · AI';
    // превью — готовая картинка с сервера (мгновенно); видео начинает играть только при наведении
    const m = el('img', { src: thumbURL(src, 480), loading: 'lazy' });
    if (kind === 'video') {
      let v = null;
      m.onmouseenter = () => { v = el('video', { src: assetURL(src), loop: true, playsinline: true, preload: 'auto', class: 'hov' }); v.muted = true; m.replaceWith(v); v.play().catch(() => {}); v.onmouseleave = () => { v.pause(); v.replaceWith(m); v = null; }; v.onclick = () => lightbox(items, idx); };
    }
    m.onclick = () => lightbox(idx >= 0 ? items : [{ src, kind, label, note: tip }], Math.max(0, idx));
    const on = pv && pv.clip === clipId && pv.src === src;
    return el('div', { class: 'var' + (on ? ' on' : '') + cls, 'data-tip': tip || 'Открыть крупно (← → листать, ⏎ поставить)' }, m,
      el('div', { class: 'vl' }, el('span', {}, label + (kind === 'video' ? ' · видео' : '')), btn));
  }
  const strip = el('div', { class: 'vstrip' });
  let n = 0;
  if (clip && clip.src && c.chosen == null) strip.append(tile(clip.src, clip.kind, 'сейчас', ' cur', null, 'Что стоит в монтаже сейчас', n++));
  const vtile = (i, idx) => tile(vs[i].src, vs[i].kind, `вариант ${i + 1}`, c.chosen === i ? ' chosen' : '',
    c.chosen === i ? el('b', { class: 'okm' }, '✓ стоит') : el('button', { class: 'btn pri sm', onclick: () => run(() => put(i)) }, 'Поставить'), vs[i].note || null, idx);
  shown.forEach((i) => strip.append(vtile(i, n++)));
  const box = el('div', { class: 'vars' }, strip);
  if (waiting && !shown.length) box.prepend(el('div', { class: 'vwait' }, 'Claude ищет новые варианты…'));
  if (older.length) {
    const more = el('button', { class: 'btn ghost sm' }, `прежние варианты (${older.length}) — показать`);
    more.onclick = () => { const st = el('div', { class: 'vstrip old' }); older.forEach((i) => st.append(vtile(i, -1))); more.replaceWith(st); };
    box.append(el('div', { class: 'actions' }, more));
  }
  const first = shown.length ? shown[0] : null;
  if (first != null) box.append(el('div', { class: 'actions' }, el('button', { class: 'btn', 'data-tip': 'Посмотреть вариант прямо в монтаже, на месте клипа', onclick: () => look(vs[first].src, vs[first].kind, `вариант ${first + 1}`) }, 'в плеере')));
  if (c.chosen != null && c.prev_src) box.append(el('div', { class: 'actions' },
    el('button', { class: 'btn', onclick: () => look(c.prev_src.src, c.prev_src.kind, 'было') }, 'было'),
    el('button', { class: 'btn', onclick: () => { viewer.setPreview(null); jump(store, { clips: [clipId] }); } }, 'стало'),
    el('button', { class: 'btn', onclick: () => run(back) }, 'вернуть старую')));
  return box;
}

function cardEl(store, c) {
  const cl = (c.clips || []).map((id) => store.clip(id)).filter(Boolean);
  const refLabel = cl.length ? cl.map((x) => x.shot || x.id).join(' → ') : null;
  const t0 = c.range ? c.range[0] : cl.length ? cl[0].start : null;
  const card = el('div', { class: `cm ${c.status}`, 'data-id': c.id, 'data-group': c._group ? c._group.join(' ') : null });
  card.append(el('div', { class: 'hd' },
    (refLabel || t0 != null) ? el('span', { class: 'ref', onclick: () => jump(store, c) }, `${refLabel ? refLabel + ' · ' : ''}${t0 != null ? fmtTC(t0) : ''}`) : null,
    c.author === 'claude' ? el('span', { class: 'by' }, 'Claude предлагает') : null,
    el('span', { class: 't' }, TYPE_RU[c.type] || c.type)));
  const sp = speechEl(speechOf(store, c));
  if (sp) card.append(sp);
  const thread = el('div', { class: 'thread' });
  for (const m of c.thread || []) thread.append(el('div', { class: 'msg' + (m.who === 'claude' ? ' claude' : '') }, el('b', {}, m.who === 'claude' ? 'Claude' : 'Вы'), ': ' + m.text));
  card.append(thread);
  if (c.snapshot) {
    const img = el('img', { class: 'snap', src: `/projects/${store.pid}/${c.snapshot}`, 'data-tip': 'Открыть крупнее' });
    img.onclick = () => dialog({ title: 'Стоп-кадр', body: el('img', { src: img.src, style: { width: '100%', display: 'block', borderRadius: '8px' } }), ok: 'Закрыть', cancel: '' });
    card.append(img);
  }
  if (c.higgsfield) {
    const h = c.higgsfield, m = MODELS.find((x) => x.id === h.model);
    const cb = el('input', { type: 'checkbox', checked: h.approved });
    cb.onchange = async () => { try { await store.reviewPost(`review/comments/${c.id}/higgsfield`, { approved: cb.checked }); } catch (e) { toast(e.message, 'error'); cb.checked = !cb.checked; } };
    card.append(el('div', { class: 'hf' }, `${h.count} × ${m ? m.label : h.model} = ${fmtCr(h.cost)}`, el('label', {}, cb, 'разрешаю')));
  }
  const vars = variantsEl(store, c);
  if (vars) card.append(vars);
  card.append(el('div', { class: 'st' }, `${(c.variants || []).length && c.status === 'question' ? 'выберите вариант' : STATUS_RU[c.status] || c.status}${t0 != null ? ' · ' + fmtTC(t0) : ''}`));
  if (c.status === 'done') {
    card.append(el('div', { class: 'actions' },
      el('button', { class: 'btn pri', onclick: async (e) => { try { await store.reviewPost(`review/comments/${c.id}/status`, { status: 'accepted' }); } catch (err) { toast(err.message, 'error'); } } }, 'принято'),
      el('button', { class: 'btn', onclick: () => { if (!drafts.has(c.id)) redo(); } }, 'переделать…')));
    const redo = () => inlineReply(card, 'Что переделать…', (text) => store.reviewPost(`review/comments/${c.id}/reply`, { who: 'user', text, status: 'reopened' }), c.id);
    if (drafts.has(c.id)) redo();
  } else if (c.status === 'question') {
    inlineReply(card, (c.variants || []).length ? 'Ни один не подходит? Напишите, что поправить…' : 'Ваш ответ…', (text) => store.reviewPost(`review/comments/${c.id}/reply`, { who: 'user', text }), c.id);
  }
  return card;
}

// несколько карточек Claude по одному кадру (реальные кадры, AI-картинки…) → одна карточка со всеми вариантами
function mergeCards(arr) {
  const f = arr[0], clip = f.variant_clip || (f.clips || [])[0], generic = /^\d+ вариант\S* для .+ — выберите$/;
  const variants = arr.flatMap((c) => c.variants.map((v, i) => ({ ...v, _cid: c.id, _idx: i })));
  const n = variants.length, word = n % 10 === 1 && n % 100 !== 11 ? 'вариант' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'варианта' : 'вариантов';
  const msgs = arr.flatMap((c) => (c.thread || []).filter((m) => !(m.who === 'claude' && generic.test(m.text))));
  return { ...f, _group: arr.map((c) => c.id), variants, thread: [{ who: 'claude', text: `${n} ${word} для ${clip} — выберите один` }, ...msgs] };
}

function mountFixBtn(store) {
  const btn = document.getElementById('fixBtn'), nEl = document.getElementById('fixN');
  function update() {
    const n = (store.review.comments || []).filter((c) => (c.status === 'new' || c.status === 'reopened') && !c.batch).length;
    nEl.textContent = String(n);
    btn.disabled = n === 0;
  }
  btn.onclick = async () => {
    try {
      const b = await store.reviewPost('fix', {});
      // Claude не следит за сигналом — пачка ждёт, пока пользователь не напишет в чат
      if (store.review.presence === 'offline') toast(`Claude не подключён — правки ждут (${b.comments.length}). Напишите Claude в чат «исправь»`, 'info');
      else toast(`Отправил ${b.comments.length} правок Claude`, 'ok');
    } catch (e) { toast(e.message, 'error'); }
  };
  store.on('review', update);
  update();
}

function mountComposer(store, viewer, root) {
  const input = el('textarea', { placeholder: 'Напишите правку к выделенным клипам… ⏎' });
  const chip = el('div', { class: 'chip' });
  const typeSel = el('select', {}, el('option', { value: 'auto' }, 'авто'), ...TYPES.map((t) => el('option', { value: t }, TYPE_RU[t])));
  const sendBtn = el('button', { class: 'btn pri send' }, 'Отправить ⏎');
  const countSel = el('select', {}, ...[1, 2, 3, 4].map((n) => el('option', { value: n }, `× ${n}`)));
  const modelSel = el('select', {}, ...MODELS.map((m) => el('option', { value: m.id }, `${m.label} — ${fmtCr(m.cost)}`)));
  const priceEl = el('span', { class: 'price' });
  const approve = el('input', { type: 'checkbox' });
  const hfRow = el('div', { class: 'hfrow', hidden: true }, countSel, modelSel, priceEl, el('label', {}, approve, 'разрешаю'));
  const atts = el('div', { class: 'atts' });
  let attachments = [];

  function priceVal() { const m = MODELS.find((x) => x.id === modelSel.value); return +countSel.value * (m ? m.cost : 0); }
  function updatePrice() { priceEl.textContent = fmtCr(priceVal()); }
  countSel.onchange = updatePrice; modelSel.onchange = updatePrice; updatePrice();

  function currentCtx() {
    const clipsSel = [...store.sel].filter((id) => store.clip(id));
    const ctx = clipsSel.length ? clipsSel : [store.clipAt('v1', store.t)?.id].filter(Boolean);
    const cl = ctx.map((id) => store.clip(id));
    const range = store.range || (cl.length ? [Math.min(...cl.map((c) => c.start)), Math.max(...cl.map((c) => c.start + c.dur))] : null);
    return { ctx, cl, range };
  }
  function updateChip() {
    chipAt = performance.now();
    const { cl, range } = currentCtx();
    let txt = 'нет клипа под красной линией';
    if (cl.length || range) {
      const label = cl.map((c) => c.shot || c.id).join(', ');
      const tc = range ? `${fmtTC(range[0])}–${fmtTC(range[1])}` : '';
      const words = range ? wordsBetween(store.words, range[0], range[1]) : '';
      txt = [label, tc, words ? `«${words}»` : ''].filter(Boolean).join(' · ');
    }
    if (chip.textContent !== txt) chip.textContent = txt;
  }
  // время меняется каждый кадр — строку обновляем не чаще 4 раз в секунду (и в конце перемотки)
  let chipAt = 0, chipT = 0;
  const chipOnTime = () => { clearTimeout(chipT); if (performance.now() - chipAt > 250) updateChip(); else chipT = setTimeout(updateChip, 260); };
  function updateHfVisibility() {
    const guessed = guessType(input.value);
    hfRow.hidden = !(typeSel.value === 'higgsfield' || (typeSel.value === 'auto' && guessed === 'higgsfield'));
  }
  input.addEventListener('input', updateHfVisibility);
  typeSel.onchange = updateHfVisibility;
  for (const ev of ['sel', 'range', 'project']) store.on(ev, updateChip);
  store.on('time', chipOnTime);
  updateChip();

  async function submit() {
    const text = input.value.trim();
    if (!text) return;
    const { ctx, range } = currentCtx();
    const body = { text, clips: ctx, range, type: typeSel.value === 'auto' ? undefined : typeSel.value, attachments };
    const guessed = guessType(text);
    if (body.type === 'higgsfield' || (!body.type && guessed === 'higgsfield')) body.higgsfield = { count: +countSel.value, model: modelSel.value, cost: priceVal(), approved: approve.checked };
    sendBtn.disabled = true;
    try {
      const c = await store.reviewPost('review/comments', body);
      const blob = await viewer.snapshot();
      if (blob) await store.api.postRaw(store.url(`/review/comments/${c.id}/snapshot`), blob, 'image/jpeg');
      await store.reloadReview();
      input.value = ''; attachments = []; atts.innerHTML = ''; approve.checked = false; typeSel.value = 'auto'; updateHfVisibility();
    } catch (e) { toast(e.message, 'error'); } finally { sendBtn.disabled = false; }
  }
  sendBtn.onclick = submit;
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });

  const wrap = el('div', { class: 'composer' }, input, chip, el('div', { class: 'crow' }, typeSel, sendBtn), hfRow, atts);
  wrap.addEventListener('dragover', (e) => { if ([...(e.dataTransfer.types || [])].includes('Files')) { e.preventDefault(); wrap.classList.add('drop'); } });
  wrap.addEventListener('dragleave', () => wrap.classList.remove('drop'));
  wrap.addEventListener('drop', async (e) => {
    wrap.classList.remove('drop');
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    e.preventDefault();
    try {
      const { ctx } = currentCtx();
      const shot = (ctx[0] && (store.clip(ctx[0])?.shot || ctx[0])) || 'review';
      const up = await store.api.postRaw(`/api/upload?shot=${encodeURIComponent(shot)}`, f, f.type || 'application/octet-stream', { 'X-Filename': encodeURIComponent(f.name) });
      attachments.push(up.src);
      atts.append(el('span', {}, f.name));
    } catch (err) { toast(err.message, 'error'); }
  });
  root.append(wrap);
  return { open: (focus, preset) => {
    if (preset) { input.value = preset.text || ''; typeSel.value = preset.type || 'auto'; updateHfVisibility(); updateChip(); }
    if (window.NE.layout && store.ui.reviewOpen === false) window.NE.layout.toggleReview();
    wrap.scrollIntoView({ block: 'nearest' });
    if (focus) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
  } };
}

export function mountReview(store, viewer) {
  const root = document.getElementById('review');
  root.innerHTML = '';
  const countEl = el('span', { class: 'mu' }, '');
  const head = el('div', { class: 'ih' }, 'Правки', countEl);
  const filters = el('div', { class: 'rfilters' });
  const list = el('div', { class: 'scroll' });
  root.append(head, filters, list);

  let filter = 'all';
  function drawFilters() {
    filters.innerHTML = '';
    for (const [id, label] of FILTERS) filters.append(el('span', { class: 'rf' + (filter === id ? ' on' : ''), 'data-f': id, onclick: () => { filter = id; drawFilters(); drawList(); } }, label, el('span', { class: 'rfn' })));
  }
  function countFilters(comments) {
    for (const [id] of FILTERS) {
      const n = comments.filter((c) => inFilter(c, id)).length, e = filters.querySelector(`[data-f="${id}"] .rfn`);
      const txt = n ? ` ${n}` : '';
      if (e && e.textContent !== txt) e.textContent = txt;
    }
  }
  // Карточки не пересобираются заново на каждое событие: сотни карточек с превью на любую правку проекта
  // тормозили всё окно. Карточка строится заново, только если поменялось то, что на ней видно.
  const cards = new Map();                           // id правки → { sig, el }
  function sigOf(c) {
    const ids = [...new Set([...(c.clips || []), c.variant_clip].filter(Boolean))];
    const pv = window.NE.viewer && window.NE.viewer.preview;
    return JSON.stringify([c, ids.map((id) => { const x = store.clip(id); return x && [x.shot, x.start, x.dur, x.src, x.kind, x.text, x.say, x.say_en]; }), speechOf(store, c).en,
      pv && ids.includes(pv.clip) ? pv.src : null, drafts.has(c.id)]);
  }
  function drawList() {
    dirty = false;
    const comments = store.review.comments || [];
    const n = comments.filter((c) => c.status === 'new' || c.status === 'reopened').length;
    const cnt = n ? `${n} новые` : '';
    if (countEl.textContent !== cnt) countEl.textContent = cnt;
    countFilters(comments);
    // по порядку в ролике, а не по времени создания: реальные кадры, сгенерированные и правки идут вперемешку, как в фильме
    const tOf = (c) => { if (c.range) return c.range[0]; const x = store.clip(c.variant_clip || (c.clips || [])[0]); return x ? x.start : Infinity; };
    const order = new Map(comments.map((c, i) => [c.id, i]));
    const sorted = comments.filter((c) => inFilter(c, filter)).sort((a, b) => (tOf(a) - tOf(b)) || (order.get(a.id) - order.get(b.id)));
    // открытые предложения Claude для одного кадра — одной карточкой: реальные и AI рядом, выбор один
    const groups = new Map(), items = [];
    for (const c of sorted) {
      if (!(c.author === 'claude' && c.status === 'question' && c.chosen == null && (c.variants || []).length)) { items.push(c); continue; }
      const k = c.variant_clip || (c.clips || [])[0], g = groups.get(k);
      if (g) g.push(c); else { const arr = [c]; groups.set(k, arr); items.push(arr); }
    }
    for (let i = 0; i < items.length; i++) if (Array.isArray(items[i])) items[i] = items[i].length === 1 ? items[i][0] : mergeCards(items[i]);
    const a = document.activeElement;                // печатают ответ — после перерисовки вернуть фокус в то же поле
    if (a && a.dataset && a.dataset.draft && list.contains(a) && drafts.has(a.dataset.draft)) Object.assign(drafts.get(a.dataset.draft), { focus: true, caret: a.selectionStart });
    const alive = new Set(comments.map((c) => c.id));
    for (const id of cards.keys()) if (!alive.has(id)) cards.delete(id);
    if (!items.length) { list.replaceChildren(el('div', { class: 'empty' }, 'Правок нет.')); return; }
    const want = items.map((c) => {
      const sig = sigOf(c); let k = cards.get(c.id);
      if (!k || k.sig !== sig) { k = { el: cardEl(store, c) }; k.sig = sigOf(c); cards.set(c.id, k); }   // подпись — после постройки: карточка сама заводит черновик ответа
      return k.el;
    });
    // расставить по порядку, трогая только то, что сдвинулось: сперва убрать ушедшие/заменённые,
    // иначе каждая карточка после заменённой переставлялась бы заново
    // несколько карточек одного кадра подряд — речь показываем только в первой, чтобы не было «одно и то же подряд»
    items.forEach((c, i) => { const k = (x) => x && (x.variant_clip || (x.clips || [])[0]); want[i].classList.toggle('same-clip', i > 0 && k(c) != null && k(c) === k(items[i - 1])); });
    const keep = new Set(want);
    for (const e of [...list.children]) if (!keep.has(e)) e.remove();
    let cur = list.firstChild;
    for (const e of want) { if (cur === e) cur = cur.nextSibling; else list.insertBefore(e, cur); }
    while (cur) { const nx = cur.nextSibling; cur.remove(); cur = nx; }
  }
  // события приходят пачками (операция → проект → правки → предпросмотр) — рисуем один раз за кадр;
  // спрятанную панель не рисуем вовсе, догоним при показе
  let dirty = false, queued = false;
  const hidden = () => store.ui.reviewOpen === false;
  function schedule() {
    dirty = true;
    if (queued || hidden()) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; if (dirty && !hidden()) drawList(); });
  }
  drawFilters(); drawList();
  store.on('review', schedule);
  store.on('project', schedule);
  store.on('preview', schedule);
  store.on('ui', () => { if (dirty && !hidden()) schedule(); });
  store.on('openComment', (id) => {
    if (store.ui.reviewOpen === false) store.setUi({ reviewOpen: true });
    const oc = (store.review.comments || []).find((c) => c.id === id);
    filter = oc && !inFilter(oc, 'all') ? 'done' : 'all'; drawFilters(); drawList();
    const card = list.querySelector(`[data-id="${id}"], [data-group~="${id}"]`);
    if (!card) return;
    card.scrollIntoView({ block: 'center' });
    card.classList.add('flash'); setTimeout(() => card.classList.remove('flash'), 1200);
  });

  const composer = mountComposer(store, viewer, root);
  mountFixBtn(store);
  return { compose: (focus = true, preset = null) => composer.open(focus, preset) };
}
