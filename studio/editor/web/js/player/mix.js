// Web Audio: голос, эффекты, музыка — декодированные буферы через bus-гейны.
// Звук роликов (v1) не проходит здесь — он живёт у самого <video> в viewer.js.
import { assetURL, dbGain } from '../util.js';
import { cuesIn } from './mixplan.js';

const XF = 1.5; // перекрёстная склейка петли музыки

// Уровни по умолчанию (см. constraints.md): голос 0, эффекты −9, музыка −17, звук роликов −22.
// Громкость самих клипов (clip.volume_db) уже "запечена" исходя из этих значений — поэтому
// bus-гейн остаётся 1, если project.settings.levels_db совпадает с default, и лишь довешивает
// разницу, если пользователь поменял глобальный уровень дорожки в настройках проекта.
export const DEFAULT_LEVELS_DB = { voice: 0, sfx: -9, music: -17, video: -22 };
export function levelScale(project, bus) {
  const def = DEFAULT_LEVELS_DB[bus] ?? 0;
  const lv = (project && project.settings && project.settings.levels_db) || {};
  const cur = lv[bus] ?? def;
  return dbGain(cur - def);
}

export class Mixer {
  constructor(store) { this.s = store || null; this.ctx = null; this.bufs = new Map(); this.live = []; this.done = new Set(); this.playing = false; this.bus = {}; this.on = {}; }
  ensure() {
    if (this.ctx) return;
    this.ctx = new AudioContext({ latencyHint: 'interactive' });
    for (const b of ['voice', 'sfx', 'music']) {
      const g = this.ctx.createGain(); g.connect(this.ctx.destination); this.bus[b] = g; this.on[b] = true;
      g.gain.value = this.levelScale(b);
    }
  }
  levelScale(bus) { return this.s ? levelScale(this.s.project, bus) : 1; }
  buf(src) {
    const u = assetURL(src);                       // с версией файла: новый звук под тем же именем — новый буфер
    if (!this.bufs.has(u)) this.bufs.set(u, fetch(u).then((r) => r.arrayBuffer()).then((a) => this.ctx.decodeAudioData(a)).catch(() => null));
    return this.bufs.get(u);
  }
  now() { return this.playing ? this.t0 + (this.ctx.currentTime - this.c0) : this.t0 || 0; }
  start(t, cues) {
    this.ensure(); this.stop(); this.ctx.resume();
    this.sess = (this.sess || 0) + 1;            // старые pump() после await не должны играть в новом запуске
    for (const b of ['voice', 'sfx', 'music']) this.bus[b].gain.value = this.on[b] ? this.levelScale(b) : 0;   // уровни могли поменять в настройках
    this.cues = cues.filter((c) => !c.element); this.t0 = t; this.c0 = this.ctx.currentTime + 0.08; this.playing = true;
    for (const c of cuesIn(this.cues, t, t + 30)) this.buf(c.src);
    this.pump(); this.timer = setInterval(() => this.pump(), 250);
  }
  stop() { clearInterval(this.timer); for (const n of this.live) { try { n.stop(); } catch (e) { /* уже остановлен */ } } this.live = []; this.done = new Set(); if (this.playing) this.t0 = this.now(); this.playing = false; }
  setBus(b, on) { this.ensure(); this.on[b] = on; this.bus[b].gain.value = on ? this.levelScale(b) : 0; }
  async pump() {
    if (!this.playing) return;
    const t = this.now(), sess = this.sess, cues = this.cues, done = this.done;
    for (const c of cuesIn(cues, t, t + 2.5)) {
      if (c.loop) { await this.pumpLoop(c, t, sess); continue; }
      if (done.has(c.id)) continue;
      done.add(c.id);
      const b = await this.buf(c.src); if (!b || !this.playing || sess !== this.sess) continue;
      this.play(b, c, c.at, c.offset, Math.min(c.dur, b.duration - c.offset), c.fadeIn, c.fadeOut);
    }
  }
  async pumpLoop(c, t, sess = this.sess) {
    const b = await this.buf(c.src); if (!b || !this.playing || sess !== this.sess) return;
    const L = b.duration, step = Math.max(1, L - XF);
    for (let k = Math.max(0, Math.floor((t - c.at) / step)); c.at + k * step < Math.min(c.at + c.dur, t + 2.5); k++) {
      const key = `${c.id}#${k}`; if (this.done.has(key)) continue; this.done.add(key);
      const segAt = c.at + k * step, segDur = Math.min(L, c.at + c.dur - segAt);
      this.play(b, c, segAt, 0, segDur, k === 0 ? c.fadeIn : XF, segAt + segDur >= c.at + c.dur - 1e-3 ? c.fadeOut : XF);
    }
  }
  play(b, c, at, offset, dur, fi, fo) {
    const ctx = this.ctx, when = this.c0 + (at - this.t0), g = ctx.createGain(), s = ctx.createBufferSource();
    let off = offset, w = when, d = dur;
    if (w < ctx.currentTime) { const late = ctx.currentTime - w; off += late; d -= late; w = ctx.currentTime; }
    if (d <= 0.01) return;
    const gain = dbGain(c.gainDb);
    g.gain.setValueAtTime(fi > 0 && off - offset < fi ? 0.0001 : gain, w);
    if (fi > 0 && off - offset < fi) g.gain.linearRampToValueAtTime(gain, w + (fi - (off - offset)));
    if (fo > 0) { g.gain.setValueAtTime(gain, Math.max(w, w + d - fo)); g.gain.linearRampToValueAtTime(0.0001, w + d); }
    s.buffer = b; s.connect(g); g.connect(this.bus[c.bus]);
    s.start(w, off, d);
    this.live.push(s);
    s.onended = () => { this.live = this.live.filter((x) => x !== s); };
  }
}
