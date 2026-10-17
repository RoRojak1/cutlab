// «Звуки и музыка» — задача 13, шаг 3. Прослушивание через один общий <audio> (общий на всё приложение).
import { el, assetURL } from '../util.js';

const audio = new Audio();
audio.volume = 0.6;
let curBtn = null;
function setPlaying(btn) { if (curBtn && curBtn !== btn) curBtn.classList.remove('playing'); curBtn = btn; if (btn) btn.classList.add('playing'); }
audio.addEventListener('ended', () => setPlaying(null));
function play(src, btn) { try { audio.pause(); audio.currentTime = 0; audio.src = assetURL(src); audio.play().catch(() => {}); setPlaying(btn); } catch (e) { /* браузер иногда шумит на быструю смену src */ } }
function stop() { audio.pause(); setPlaying(null); }

function fmtLen(sec, music) {
  sec = sec || 0;
  if (music) { const m = Math.floor(sec / 60), s = Math.round(sec % 60); return `${m}:${String(s).padStart(2, '0')}`; }
  return `${sec.toFixed(1)} с`;
}

export function renderSounds(store, root) {
  let tab = store.ui.sndTab || 'sounds';
  const tabs = el('div', { class: 'ptabs' });
  const list = el('div', { class: 'scroll' });
  const hint = el('div', { class: 'phint' });
  root.append(el('div', { class: 'ih' }, 'Звуки и музыка'), tabs, list, hint);

  function draw() {
    const sounds = store.library.sounds || [], music = store.library.music || [];
    tabs.innerHTML = '';
    tabs.append(
      el('div', { class: 'tab' + (tab === 'sounds' ? ' on' : ''), onclick: () => { tab = 'sounds'; store.ui.sndTab = tab; draw(); } }, `Звуки (${sounds.length})`),
      el('div', { class: 'tab' + (tab === 'music' ? ' on' : ''), onclick: () => { tab = 'music'; store.ui.sndTab = tab; draw(); } }, `Музыка (${music.length})`),
    );
    list.innerHTML = '';
    const items = tab === 'sounds' ? sounds : music;
    for (const a of items) {
      const plBtn = el('button', { class: 'pl' }, '▶');
      const row = el('div', { class: 'rw snd', draggable: true },
        plBtn,
        el('span', { class: 'nm' }, a.name),
        tab === 'music' && a.mood ? el('span', { class: 'mu' }, a.mood) : null,
        el('span', { class: 'mu mono' }, fmtLen(a.dur, tab === 'music')),
        tab === 'music' ? el('button', { class: 'plus', 'data-tip': 'Добавить на дорожку «Музыка»' }, '+') : null);
      plBtn.onclick = (e) => { e.stopPropagation(); if (curBtn === plBtn) stop(); else play(a.src, plBtn); };
      if (tab === 'music') row.querySelector('.plus').onclick = (e) => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); window.NE.interact.openMusicChooser(a, store.t, r.left, r.bottom + 4); };
      row.addEventListener('dragstart', (e) => e.dataTransfer.setData('application/x-nick-asset', JSON.stringify({ type: tab === 'sounds' ? 'sfx' : 'music', src: a.src, name: a.name, dur: a.dur })));
      let hoverTimer = null;
      row.addEventListener('mouseenter', () => { hoverTimer = setTimeout(() => play(a.src, plBtn), 300); });
      row.addEventListener('mouseleave', () => { clearTimeout(hoverTimer); if (curBtn === plBtn) stop(); });
      list.append(row);
    }
    if (!items.length) list.append(el('div', { class: 'empty' }, 'Библиотека пуста.'));
    hint.textContent = tab === 'sounds' ? 'перетащите на дорожку «Эффекты»' : 'перетащите на «Музыку» или нажмите +';
  }
  draw();
  return { panel: 'sounds', cleanup: stop };
}
