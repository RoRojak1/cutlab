// Пуск/пауза, шаг по кадру, переход к времени, охват (весь выпуск / глава / отрезок), панель #ctl.
import { fmtTC, frame } from '../util.js';
import { buildCues } from './mixplan.js';
import { menuAt, toast } from '../ui.js';

export class Transport {
  constructor(store, viewer, mixer) {
    Object.assign(this, { s: store, v: viewer, m: mixer, raf: 0, scope: 'all' });
    // Язык звука: EN — живое сведение проекта; другой — готовая дорожка дубляжа (dubs/<lang>/<id>_<lang>.mp3) под картинку
    this.au = new Audio(); this.au.preload = 'auto'; store.audioLang = 'en';
    this.ctl = document.getElementById('ctl');
    this.render();
    store.on('subs', () => this.render());              // файл субтитров появился/пропал — кнопка RU
    // на паузе (перемотка, шаги) кадр рисуем один раз за кадр экрана, а не на каждое движение мыши
    this.tcEl = document.getElementById('tc');
    store.on('time', (t) => {
      if (!this.m.playing && !this.drawQ) {
        this.drawQ = true;
        const flush = () => { if (!this.drawQ) return; this.drawQ = false; if (!this.m.playing) this.v.draw(this.s.t); };
        requestAnimationFrame(flush); setTimeout(flush, 100);     // таймер — если окно в фоне и кадры экрана не идут
      }
      const a = fmtTC(t), b = `${a} / ${fmtTC(this.s.duration())}`;
      if (this.tcEl.textContent !== a) this.tcEl.textContent = a;
      if (this.tc.textContent !== b) this.tc.textContent = b;
    });
    store.on('project', () => { if (!this.m.playing) this.v.draw(this.s.t); else this.restart(); });
    // перезапуск звука — только если поменялось, что слышно (выкл/соло); прокрутка и масштаб таймлайна
    // (ensureVisible во время проигрывания) раньше рвали звук на каждой странице
    this.audioKey = this.key();
    store.on('ui', () => { const k = this.key(); if (k === this.audioKey) return; this.audioKey = k; this.render(); if (this.m.playing) this.restart(); });
  }
  render() {
    const off = this.s.ui.off, tg = (tr, label) => `<button class="tg ${off[tr] ? '' : 'on'}" data-tr="${tr}" data-tip="Вкл/выкл ${label}">${label}</button>`;
    this.ctl.innerHTML = `<button data-a="back" data-tip="Секунду назад" data-key="⇧←">⏮</button><button data-a="play" class="pl" data-tip="Пуск / пауза" data-key="Пробел">${this.m.playing ? '❚❚' : '▶'}</button><button data-a="fwd" data-tip="Секунду вперёд" data-key="⇧→">⏭</button><span id="ctlTc"></span><button data-a="fs" class="fsb" data-tip="${window.NE && NE.fullscreen && NE.fullscreen.on ? 'Выйти из полноэкранного режима' : 'Во весь экран'}" data-key="${window.NE && NE.fullscreen && NE.fullscreen.on ? 'Esc' : 'F'}">${window.NE && NE.fullscreen && NE.fullscreen.on ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>'}</button><span class="sp"></span><button data-a="lang" class="lang${this.s.audioLang !== 'en' ? ' on' : ''}" data-tip="Язык звука: английский (проект) или готовый дубляж">${this.s.audioLang.toUpperCase()} ▾</button>${this.v.subs && this.v.subs.available ? `<button data-a="subs" class="lang${this.v.subs.on ? ' on' : ''}" data-tip="Русские субтитры — только для просмотра, в ролик не идут">RU</button>` : ''} ${tg('voice', 'голос')} · ${tg('sfx1', 'эффекты')} · ${tg('music', 'музыка')} · ${tg('v1', 'звук роликов')}`;
    this.tc = this.ctl.querySelector('#ctlTc'); this.tc.textContent = `${fmtTC(this.s.t)} / ${fmtTC(this.s.duration())}`;
    this.ctl.onclick = (e) => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.a === 'play') this.toggle(); else if (b.dataset.a === 'back') this.jump(-1); else if (b.dataset.a === 'fwd') this.jump(1);
      else if (b.dataset.a === 'lang') this.langMenu(b);
      else if (b.dataset.a === 'subs') { this.v.subs.toggle(); this.render(); }
      else if (b.dataset.a === 'fs') { if (window.NE && NE.fullscreen) NE.fullscreen.toggle(); }
      else if (b.dataset.tr) { const tr = b.dataset.tr, o = { ...this.s.ui.off, [tr]: !this.s.ui.off[tr] }; if (tr === 'sfx1') o.sfx2 = o.sfx1; this.s.setUi({ off: o }); }
    };
    document.getElementById('playBtn').textContent = this.m.playing ? '❚❚' : '▶';
  }
  async langMenu(btn) {
    const { dubs } = await this.s.api.get(this.s.url('/dubs'));
    const items = [{ label: 'EN — английский (звук проекта)', hint: this.s.audioLang === 'en' ? '✓' : '', run: () => this.setLang('en') }];
    for (const d of dubs) items.push({ label: `${d.lang.toUpperCase()} — ${d.name}`, hint: d.status === 'done' ? (this.s.audioLang === d.lang ? '✓' : '') : 'ещё не готов',
      disabled: d.status !== 'done', run: () => this.setLang(d.lang, d.file) });
    if (!dubs.length) items.push({ label: 'Дубляжей пока нет — кнопка «Дубляж» сверху', disabled: true });
    menuAt(btn, items);
  }
  setLang(lang, file) {
    const p = this.m.playing; if (p) this.pause();
    this.s.audioLang = lang;
    if (lang !== 'en') this.au.src = `/projects/${this.s.pid}/dubs/${lang}/${encodeURIComponent(file)}`; else this.au.removeAttribute('src');
    this.render(); this.v.draw(this.s.t);
    if (lang !== 'en') toast(`Звук: ${lang.toUpperCase()} — готовая дорожка дубляжа. Для ep01 картинка монтажки может расходиться с CapCut на доли секунды.`, 'info');
    if (p) this.play();
  }
  key() { return JSON.stringify([this.s.ui.off, this.s.ui.solo]); }
  bounds() {
    if (this.scope === 'range' && this.s.range) return this.s.range;
    if (this.scope === 'chapter') { const c = this.s.clipAt('v1', this.s.t); const ch = this.s.track('v1').filter((x) => x.chapter === (c && c.chapter)); if (ch.length) return [ch[0].start, ch[ch.length - 1].start + ch[ch.length - 1].dur]; }
    return [0, this.s.duration()];
  }
  play() {
    cancelAnimationFrame(this.raf); // на случай повторного play() без предшествующего pause() (см. restart()) — не плодить осиротевшие RAF-петли
    this.v.unlock();                // пуск из жеста — разрешить пул <video> (WebKit в энергосбережении)
    const [a, b] = this.bounds(); let t = this.s.t; if (t < a || t >= b - 0.05) t = a;
    const dub = this.s.audioLang !== 'en';
    this.m.start(t, dub ? [] : buildCues(this.s.project, { off: this.s.ui.off, solo: this.s.ui.solo }));
    if (dub) { this.au.currentTime = t; this.au.play().catch((e) => toast(`Дорожка дубляжа не играет: ${e.message}`, 'error')); }
    const loop = () => {
      const now = this.m.now();
      if (dub && !this.au.paused && Math.abs(this.au.currentTime - now) > 0.15) this.au.currentTime = now;   // догнать часы картинки
      if (now >= this.bounds()[1]) { this.pause(); this.s.setTime(this.bounds()[1]); return; }
      this.s.t = now; this.v.draw(now, true); this.s.emit('time', now); this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop); this.render();
  }
  pause() { cancelAnimationFrame(this.raf); this.m.stop(); this.au.pause(); this.v.draw(this.s.t, false); this.render(); }
  toggle() { if (this.m.playing) this.pause(); else this.play(); }
  restart() { const t = this.m.now(); this.m.stop(); this.s.t = t; this.play(); }
  step(n) { if (this.m.playing) this.pause(); this.s.setTime(frame(this.s.t + n / 30)); }
  jump(sec) { const p = this.m.playing; if (p) this.pause(); this.s.setTime(this.s.t + sec); if (p) this.play(); }
}
