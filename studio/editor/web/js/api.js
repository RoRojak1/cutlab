export function makeApi(base = '') {
  async function req(method, url, body) {
    const r = await fetch(base + url, { method, headers: body !== undefined ? { 'Content-Type': 'application/json' } : {}, body: body !== undefined ? JSON.stringify(body) : undefined });
    const j = await r.json().catch(() => null);
    if (!r.ok) throw new Error((j && j.error) || `HTTP ${r.status}`);
    return j;
  }
  return {
    get: (u) => req('GET', u),
    post: (u, b = {}) => req('POST', u, b),
    async postRaw(u, blob, type, headers = {}) {
      const r = await fetch(base + u, { method: 'POST', headers: { 'Content-Type': type, ...headers }, body: blob });
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new Error((j && j.error) || `HTTP ${r.status}`);
      return j;
    },
    events(pid, onEvent) {
      const es = new EventSource(`${base}/api/events?project=${encodeURIComponent(pid)}`);
      es.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch (err) { console.error(err); } };
      es.onerror = () => onEvent({ type: 'offline' });
      es.onopen = () => onEvent({ type: 'online' });
      return es;
    },
  };
}
