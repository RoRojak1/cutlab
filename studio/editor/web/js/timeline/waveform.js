// Пики волны голоса: /api/peaks?src= → {per_sec, peaks:[0..127]}; рисуем только видимую часть клипов голоса
const cache = new Map();
export function peaksFor(src) {
  if (!cache.has(src)) cache.set(src, fetch(`/api/peaks?src=${encodeURIComponent(src)}`).then((r) => r.json()).catch(() => null));
  return cache.get(src);
}
export async function drawVoice(canvas, clips, t0, t1, color) {
  // generation guard: a slower older call must not clobber a newer frame's result once its
  // awaited peaks land — only the call that is still the latest for this canvas gets to paint.
  const gen = (canvas._gen = (canvas._gen || 0) + 1);
  const visible = clips.filter((c) => c.kind !== 'pause' && c.start <= t1 && c.start + c.dur >= t0);
  const peaks = await Promise.all(visible.map((c) => peaksFor(c.src)));
  if (canvas._gen !== gen) return;
  const dpr = devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  const nw = Math.round(w * dpr), nh = Math.round(h * dpr);
  if (canvas.width !== nw || canvas.height !== nh) { canvas.width = nw; canvas.height = nh; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = color;
  const pps = w / (t1 - t0);
  for (let idx = 0; idx < visible.length; idx++) {
    const c = visible[idx], pk = peaks[idx];
    if (!pk) continue;
    const a = Math.max(c.start, t0), b = Math.min(c.start + c.dur, t1);
    for (let x = Math.floor((a - t0) * pps); x < (b - t0) * pps; x += 2) {
      const tt = t0 + x / pps, i = Math.floor((c.in + tt - c.start) * pk.per_sec);
      const v = (pk.peaks[i] || 0) / 127, bh = Math.max(1, v * (h - 2));
      ctx.fillRect(x, (h - bh) / 2, 1.5, bh);
    }
  }
}
