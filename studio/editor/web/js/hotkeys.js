// Горячие клавиши — один обработчик keydown на window — задача 16.
import { toast } from './ui.js';
import { frame } from './util.js';
import { duplicate } from './timeline/context.js';

function fieldFocused() {
  const a = document.activeElement;
  return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable);
}
const modalOpen = () => { const m = document.getElementById('modal'); return !!m && !m.hidden; };

export function bindHotkeys(ctx) {
  const { store, transport, interact, openSearch, openHelp } = ctx;

  function toggleOff(patch) { store.setUi({ off: { ...store.ui.off, ...patch } }); }

  function copySelected() {
    const c = [...store.sel].map((id) => store.clip(id)).find((x) => x && x.track !== 'v1' && x.track !== 'voice');
    if (!c) return false;
    const cb = JSON.parse(JSON.stringify(c)); delete cb.id; store.clipboard = cb;      // общий буфер с меню по правой кнопке
    toast(`Клип «${cb.text || cb.tag || cb.track}» скопирован`, 'ok');
    return true;
  }
  async function pasteAtPlayhead() {
    if (!store.clipboard) return;
    const clip = { ...store.clipboard, start: frame(store.t) };
    try { await store.dispatch([{ op: 'add', clip }], { label: 'вставка' }); toast('Клип вставлен', 'ok'); }
    catch (e) { /* ошибка уже показана через store 'error' */ }
  }
  function fitAll() {
    const tl = window.NE.timeline; if (!tl) return;
    const dur = store.duration(); if (dur <= 0) return;
    store.setUi({ pps: Math.max(2, Math.min(600, tl.laneW / dur)), scroll: 0 });
  }

  addEventListener('keydown', (e) => {
    const inField = fieldFocused(), meta = e.metaKey || e.ctrlKey, key = e.key;
    // открыт диалог — клавиши его (Esc закрывает сам диалог); иначе ⌫/Пробел били бы по таймлайну за окном
    if (modalOpen()) return;
    // в поле ввода ⌘Z/⌘C/⌘V — правка текста, не монтажа; из полей работает только ⌘K (и Esc)
    if (inField && !(meta && (key === 'k' || key === 'K')) && key !== 'Escape') return;

    if (key === 'Escape') { if (!inField) { store.select([]); store.setRange(null); } return; }
    if (meta && (key === 'z' || key === 'Z')) { e.preventDefault(); (e.shiftKey ? store.redoLast() : store.undoLast()).catch(() => {}); return; }
    if (meta && (key === 'k' || key === 'K')) { e.preventDefault(); openSearch(store); return; }
    if (meta && (key === 'c' || key === 'C')) { if (copySelected()) e.preventDefault(); return; }
    if (meta && (key === 'd' || key === 'D')) { const c = [...store.sel].map((id) => store.clip(id)).find((x) => x && x.track !== 'v1' && x.track !== 'voice'); if (c) { e.preventDefault(); duplicate(store, c); } return; }
    if (meta && (key === 'v' || key === 'V')) { if (store.clipboard) { e.preventDefault(); pasteAtPlayhead(); } return; }
    if (!meta && e.shiftKey && (key === 'z' || key === 'Z')) { e.preventDefault(); fitAll(); return; }
    if (inField || meta) return; // остальные клавиши — простые буквы вне полей ввода и без модификаторов

    switch (key) {
      case ' ': e.preventDefault(); transport.toggle(); break;
      case 'j': case 'J': transport.jump(-1); break;
      case 'k': case 'K': transport.pause(); break;
      case 'l': case 'L': transport.play(); break;
      case 'ArrowLeft': e.preventDefault(); e.shiftKey ? transport.jump(-1) : transport.step(-1); break;
      case 'ArrowRight': e.preventDefault(); e.shiftKey ? transport.jump(1) : transport.step(1); break;
      case 'b': case 'B': interact.splitAtPlayhead().catch(() => {}); break;
      case 'Backspace': case 'Delete': e.preventDefault(); interact.removeSelected().catch(() => {}); break;
      case 'c': case 'C': e.preventDefault(); if (window.NE.review && window.NE.review.compose) window.NE.review.compose(); break;
      case 't': case 'T': toggleOff({ text: !store.ui.off.text }); break;
      case 's': case 'S': { const v = !store.ui.off.sfx1; toggleOff({ sfx1: v, sfx2: v }); break; }
      case 'm': case 'M': toggleOff({ music: !store.ui.off.music }); break;
      case 'f': case 'F': if (window.NE.fullscreen) window.NE.fullscreen.toggle(); break;
      case '?': e.preventDefault(); openHelp(); break;
      default: break;
    }
  });
}
