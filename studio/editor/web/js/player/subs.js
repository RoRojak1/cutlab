// Русские субтитры для просмотра монтажа (в рендер не идут): assets/subs/<pid>_ru.json [{t0, t1, en, ru}],
// собирает studio/editor/subs_ru.py по голосу проекта. Кнопка «RU» под плеером, вкл/выкл — localStorage у каждого свой.
import { el } from '../util.js';

const KEY = 'nick.subs';

export class Subs {
  constructor(store, overlay) {
    this.s = store; this.cues = []; this.cur = -2;
    try { this.on = localStorage.getItem(KEY) !== '0'; } catch { this.on = true; }
    this.el = el('div', { class: 'subs' }); this.el.hidden = true;
    overlay.append(this.el);
    this.load();
    store.on('project', () => this.load());          // после сдвигов голоса файл пересобирается скриптом — подхватить
  }
  get available() { return this.cues.length > 0; }
  load() {
    clearTimeout(this.lt);
    this.lt = setTimeout(async () => {
      const had = this.available;
      try {
        const r = await fetch(`/assets/subs/${encodeURIComponent(this.s.pid)}_ru.json?t=${Date.now()}`, { cache: 'no-store' });
        this.cues = r.ok ? await r.json() : [];
      } catch { this.cues = []; }
      this.cur = -2; this.update(this.s.t);
      if (had !== this.available) this.s.emit('subs');
    }, 300);
  }
  toggle() {
    this.on = !this.on;
    try { localStorage.setItem(KEY, this.on ? '1' : '0'); } catch { /* приватный режим — просто не запомним */ }
    this.cur = -2; this.update(this.s.t);
  }
  update(t) {
    let i = -1;
    if (this.on && this.cues.length) {
      let lo = 0, hi = this.cues.length - 1;                   // последняя фраза с t0 <= t
      while (lo <= hi) { const m = (lo + hi) >> 1; if (this.cues[m].t0 <= t) lo = m + 1; else hi = m - 1; }
      const c = this.cues[hi];
      if (c && t < c.t1 && c.ru) i = hi;
    }
    if (i === this.cur) return;
    this.cur = i; this.el.hidden = i < 0; this.el.textContent = i < 0 ? '' : this.cues[i].ru;
  }
}
