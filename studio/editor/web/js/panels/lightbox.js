// Большой просмотр вариантов: картинка/видео сразу во весь экран, без плеера и таймлайна.
// ← → — листать, Enter — «Поставить», Esc / клик мимо — закрыть.
import { el, assetURL, thumbURL } from '../util.js';

let open = null;

export function lightbox(items, start = 0) {
  // items: [{ src, kind, label, note, put?: () => Promise, chosen?: bool }]
  if (open) open.close();
  let i = Math.max(0, Math.min(items.length - 1, start));
  const stage = el('div', { class: 'lb-stage' });
  const cap = el('div', { class: 'lb-cap' });
  const prev = el('button', { class: 'lb-nav l', 'data-tip': '← предыдущий' }, '‹');
  const next = el('button', { class: 'lb-nav r', 'data-tip': '→ следующий' }, '›');
  const root = el('div', { class: 'lb' }, stage, prev, next, cap, el('button', { class: 'lb-x', 'data-tip': 'Esc' }, '×'));
  const cache = new Map();          // заранее грузим соседей, чтобы листание было мгновенным
  const media = (it) => {
    if (cache.has(it.src)) return cache.get(it.src);
    let m;
    if (it.kind === 'video') {
      m = el('video', { src: assetURL(it.src), poster: thumbURL(it.src, 1280), loop: true, playsinline: true, preload: 'auto', controls: true });
      m.muted = true;
    } else m = el('img', { src: assetURL(it.src), alt: it.label });
    cache.set(it.src, m);
    return m;
  };
  function show() {
    const it = items[i];
    stage.querySelectorAll('video').forEach((v) => v.pause());
    stage.replaceChildren(media(it));
    if (it.kind === 'video') { const v = stage.firstChild; v.currentTime = 0; v.play().catch(() => {}); }
    cap.replaceChildren(
      el('div', { class: 'lb-t' }, `${it.label}${it.kind === 'video' ? ' · видео' : ''}`, el('span', { class: 'lb-n' }, `  ${i + 1} / ${items.length}`)),
      it.speech ? el('div', { class: 'lb-speech' }, el('b', {}, 'Речь: '), it.speech) : '',
      it.note ? el('div', { class: 'lb-note' }, it.note) : '',
      it.chosen ? el('b', { class: 'okm' }, '✓ стоит в монтаже')
        : it.put ? el('button', { class: 'btn pri', onclick: async () => { await it.put(); close(); } }, 'Поставить  ⏎') : '');
    prev.hidden = i === 0; next.hidden = i === items.length - 1;
    for (const k of [i - 1, i + 1]) if (items[k]) media(items[k]);   // предзагрузка соседей
  }
  const go = (d) => { const j = i + d; if (j >= 0 && j < items.length) { i = j; show(); } };
  const key = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); go(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); go(1); }
    else if (e.key === 'Enter' && items[i].put && !items[i].chosen) { e.preventDefault(); items[i].put().then(close); }
  };
  function close() {
    stage.querySelectorAll('video').forEach((v) => v.pause());
    cache.forEach((m) => { if (m.tagName === 'VIDEO') { m.pause(); m.removeAttribute('src'); m.load(); } });
    root.remove(); removeEventListener('keydown', key, true); open = null;
  }
  prev.onclick = () => go(-1); next.onclick = () => go(1);
  root.querySelector('.lb-x').onclick = close;
  root.onmousedown = (e) => { if (e.target === root || e.target === stage) close(); };
  addEventListener('keydown', key, true);
  document.body.append(root);
  show();
  open = { close };
  return open;
}
