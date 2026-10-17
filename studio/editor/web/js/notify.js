// Уведомления: баннеры с таймкодами (справа сверху), колокольчик, звук — задача 15.
import { el, fmtTC, lsGet } from './util.js';

export class Notifier {
  constructor(store) {
    this.s = store; this.host = document.getElementById('toasts'); this.bell = document.getElementById('bellBtn'); this.panel = document.getElementById('bellPanel');
    this.audio = new Audio('/assets/ui/notify.wav');
    store.on('notify', (n) => this.show(n));
    store.on('review', () => this.dot());
    store.on('external', (ev) => { if (ev.by === 'claude' && ev.changed && ev.changed.length) this.toast(`Claude изменил ${ev.changed.slice(0, 4).join(', ')}${ev.changed.length > 4 ? '…' : ''}`, 'ok'); });
    store.on('error', (m) => this.toast(m, 'error'));
    this.bell.onclick = () => this.openBell();
    this.dot();
  }
  unread() { return ((this.s.review && this.s.review.notifications) || []).filter((n) => !n.read); }
  dot() { this.bell.querySelector('.dot').hidden = this.unread().length === 0; }
  chime() { const v = lsGet('chime', 0.6); if (v > 0) { this.audio.volume = v; this.audio.currentTime = 0; this.audio.play().catch(() => {}); } }
  jump(t, clip) { this.panel.hidden = true; this.s.setTime(t); if (clip && this.s.clip(clip)) this.s.select([clip]); window.NE.timeline && window.NE.timeline.ensureVisible(t); }
  items(n) {
    return (n.items || []).map((it) => el('div', { class: 'it' }, it.t != null ? el('a', { onclick: () => { this.jump(it.t, it.clip); if (it.comment) this.s.emit('openComment', it.comment); } }, `${it.clip ? it.clip + ' · ' : ''}${fmtTC(it.t)}`) : null, it.text));
  }
  show(n) {
    this.chime();
    const b = el('div', { class: 'banner' + (n.kind === 'question' ? ' q' : '') }, el('h4', {}, n.title), ...this.items(n), el('button', { class: 'x', 'data-tip': 'Закрыть — уйдёт в колокольчик', onclick: () => this.away(b) }, '✕'));
    this.mount(b, 8000);
  }
  toast(text, kind = 'info') { const b = el('div', { class: 'banner' + (kind === 'error' ? ' err' : '') }, el('div', { class: 'it' }, text), el('button', { class: 'x', onclick: () => b.remove() }, '✕')); this.mount(b, kind === 'error' ? 7000 : 3500, false); }
  mount(b, ms, toBell = true) {
    this.host.prepend(b);
    while (this.host.children.length > 3) this.host.lastChild.remove();
    let timer = setTimeout(() => (toBell ? this.away(b) : b.remove()), ms);
    b.onmouseenter = () => clearTimeout(timer);
    b.onmouseleave = () => { timer = setTimeout(() => (toBell ? this.away(b) : b.remove()), 2500); };
    let x0 = null;
    b.onpointerdown = (e) => { if (e.target.closest('a,button')) return; x0 = e.clientX; b.setPointerCapture(e.pointerId); b.style.transition = 'none'; };
    b.onpointermove = (e) => { if (x0 == null) return; const dx = Math.max(0, e.clientX - x0); b.style.transform = `translateX(${dx}px)`; b.style.opacity = String(1 - dx / 300); };
    b.onpointerup = (e) => { if (x0 == null) return; const dx = e.clientX - x0; x0 = null; b.style.transition = ''; if (dx > 90) { toBell ? this.away(b) : b.remove(); } else { b.style.transform = ''; b.style.opacity = ''; } };
  }
  away(b) {
    if (!b.isConnected) return;
    const r = b.getBoundingClientRect(), t = this.bell.getBoundingClientRect();
    b.style.setProperty('--fx', `${t.left + t.width / 2 - (r.left + r.width / 2)}px`); b.style.setProperty('--fy', `${t.top + t.height / 2 - (r.top + r.height / 2)}px`);
    b.classList.add('fly'); setTimeout(() => b.remove(), 380); this.dot();
  }
  openBell() {
    if (!this.panel.hidden) { this.panel.hidden = true; return; }
    const list = ((this.s.review && this.s.review.notifications) || []).slice().reverse();
    this.panel.innerHTML = '';
    this.panel.append(el('div', { class: 'bh' }, 'Уведомления', el('button', { onclick: async () => { await this.s.reviewPost('notifications/read', {}); this.dot(); this.panel.hidden = true; } }, 'прочитано всё')));
    if (!list.length) this.panel.append(el('div', { class: 'empty' }, 'Пока пусто. Сюда приходят сообщения Claude о сделанных правках.'));
    for (const n of list) this.panel.append(el('div', { class: 'bn' + (n.read ? '' : ' unread') }, el('div', { class: 'tm' }, n.at.slice(11, 16) + (n.batch ? ' · ' + n.batch : '')), el('b', {}, n.title), ...this.items(n)));
    this.panel.hidden = false;
    const off = (e) => { if (!this.panel.contains(e.target) && !this.bell.contains(e.target)) { this.panel.hidden = true; removeEventListener('mousedown', off, true); } };
    addEventListener('mousedown', off, true);
  }
}
