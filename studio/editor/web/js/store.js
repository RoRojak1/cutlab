import { debounce, setAssetVersions } from './util.js';

export class Store {
  constructor(api, pid) {
    Object.assign(this, { api, pid, project: null, words: [], review: null, library: { sounds: [], music: [] },
      sel: new Set(), range: null, t: 0, undo: [], redo: [], subs: new Map(), _tracks: null, _rev: -1, _byId: new Map(),
      ui: { pps: 60, scroll: 0, off: {}, solo: null, panel: 'media', tabs: [], reviewOpen: true } });
    this.refreshWords = debounce(() => this._words(), 150);
  }
  on(ev, fn) { if (!this.subs.has(ev)) this.subs.set(ev, new Set()); this.subs.get(ev).add(fn); return () => this.subs.get(ev).delete(fn); }
  emit(ev, data) { for (const fn of this.subs.get(ev) || []) { try { fn(data); } catch (e) { console.error(e); } } }
  url(p = '') { return `/api/projects/${encodeURIComponent(this.pid)}${p}`; }

  async load() {
    const [p, w, r, s, m] = await Promise.all([this.api.get(this.url()), this.api.get(this.url('/words')), this.api.get(this.url('/review')),
      this.api.get('/api/library/sounds').catch(() => ({ sounds: [] })), this.api.get('/api/library/music').catch(() => ({ music: [] }))]);
    this.library = { sounds: s.sounds || [], music: m.music || [] };
    this.words = w.words; this.review = r;
    this.setProject(p, [], 'load');
  }
  async _words() { this.words = (await this.api.get(this.url('/words'))).words; this.emit('words', this.words); }

  setProject(p, changed, by) {
    // откат к версии: обратные операции прежнего состояния к ней не относятся — ⌘Z применил бы их поверх версии
    if (by === 'restore') { this.undo = []; this.redo = []; }
    setAssetVersions(p._mtimes); delete p._mtimes;
    this.project = p;
    this._byId = new Map(p.clips.map((c) => [c.id, c]));
    this._tracks = null;
    for (const id of [...this.sel]) if (!this._byId.has(id)) this.sel.delete(id);
    this.emit('project', { changed, by });
  }
  clip(id) { return this._byId.get(id) || null; }
  track(id) {
    if (!this._tracks || this._rev !== this.project.revision) {
      this._tracks = new Map(); this._rev = this.project.revision;
      for (const c of this.project.clips) { if (!this._tracks.has(c.track)) this._tracks.set(c.track, []); this._tracks.get(c.track).push(c); }
      for (const l of this._tracks.values()) l.sort((a, b) => a.start - b.start);
    }
    return this._tracks.get(id) || [];
  }
  clipAt(trackId, t) {
    const l = this.track(trackId);
    let lo = 0, hi = l.length - 1, best = null;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (l[m].start <= t + 1e-6) { best = m; lo = m + 1; } else hi = m - 1; }
    for (let k = best; k != null && k >= 0 && k > best - 4; k--) if (l[k].start <= t + 1e-6 && t < l[k].start + l[k].dur - 1e-6) return l[k];
    return null;
  }
  duration() { let e = 0; for (const c of this.project.clips) if (c.track === 'v1' || c.track === 'voice') e = Math.max(e, c.start + c.dur); return e; }

  // Отправки идут строго по очереди: ⌘Z с автоповтором или быстрые правки иначе приходят на сервер вперемешку
  // (отмена второй раньше первой — ошибка или порча). Цепочка не рвётся на ошибке.
  _serial(fn) { const r = (this._chain || Promise.resolve()).then(fn); this._chain = r.catch(() => {}); return r; }
  dispatch(ops, opts) { return this._serial(() => this._dispatch(ops, opts)); }
  async _dispatch(ops, { label = '', record = true } = {}) {
    this.emit('save', 'saving');
    try {
      const r = await this.api.post(this.url('/ops'), { base_revision: this.project.revision, ops, client: 'ui' });
      // guard against a slower in-flight dispatch response overwriting a newer project
      // (e.g. a faster concurrent dispatch, or an SSE-triggered refetch, that already landed)
      if (r.project.revision >= this.project.revision) this.setProject(r.project, r.changed, 'ui');
      if (record) { this.undo.push({ ops, inverse: r.inverse, label }); this.redo = []; }
      this.emit('save', 'ok');
      this.refreshWords();
      return r;
    } catch (e) { this.emit('save', 'err'); this.emit('error', e.message); throw e; }
  }
  canUndo() { return this.undo.length > 0; }
  canRedo() { return this.redo.length > 0; }
  undoLast() {
    return this._serial(async () => {
      const u = this.undo.pop(); if (!u) return;
      try {
        // r.inverse is the server's inverse-of-the-undo, i.e. an id-stable forward replay of
        // u.ops (id-generating ops like split/add would otherwise mint a NEW id if u.ops itself
        // were redispatched — see redoLast).
        const r = await this._dispatch(u.inverse, { record: false });
        this.redo.push({ ops: r.inverse, inverse: u.inverse, label: u.label });
      } catch (e) { this.undo.push(u); throw e; }
    });
  }
  redoLast() {
    return this._serial(async () => {
      const u = this.redo.pop(); if (!u) return;
      try {
        const r = await this._dispatch(u.ops, { record: false });
        this.undo.push({ ops: u.ops, inverse: r.inverse, label: u.label });
      } catch (e) { this.redo.push(u); throw e; }
    });
  }

  select(ids, mode = 'set') {
    if (mode === 'set') this.sel = new Set(ids);
    else for (const id of ids) { if (mode === 'toggle' && this.sel.has(id)) this.sel.delete(id); else this.sel.add(id); }
    this.emit('sel', this.sel);
  }
  setTime(t) { this.t = Math.max(0, Math.min(t, this.duration())); this.emit('time', this.t); }
  setRange(r) { this.range = r; this.emit('range', r); }
  setUi(patch) { Object.assign(this.ui, patch); this.emit('ui', this.ui); this.saveUi(); }
  saveUi = debounce(() => this.api.post(this.url('/ui'), { ui: { ...this.ui, t: this.t } }).catch((e) => console.error(e)), 1500);

  async reloadReview() {
    const seq = (this._rseq = (this._rseq || 0) + 1);
    const r = await this.api.get(this.url('/review'));
    if (seq !== this._rseq) return;              // пришёл ответ на более старый запрос — свежий уже в пути
    this.review = r; this.emit('review', this.review);
  }
  async reviewPost(path, body) { const r = await this.api.post(this.url('/' + path), body); await this.reloadReview(); return r; }

  async onServerEvent(ev) {
    try {
      if (ev.type === 'project' && ev.revision > this.project.revision) {
        const p = await this.api.get(this.url());
        // re-check: by the time the refetch lands, another update may already have caught us up
        if (p.revision > this.project.revision) { this.setProject(p, ev.changed || [], ev.by); this.refreshWords(); }
        if (ev.by !== 'ui') this.emit('external', ev);
      } else if (ev.type === 'review') await this.reloadReview();
      else if (ev.type === 'notify') { await this.reloadReview(); this.emit('notify', ev.notification); }
      else if (ev.type === 'claude') { this.presence = ev.state; if (this.review) this.review.presence = ev.state; this.emit('claude', ev.state); }
      else if (ev.type === 'error') this.emit('error', ev.error);
    } catch (e) { this.emit('error', e.message); }
  }
}
