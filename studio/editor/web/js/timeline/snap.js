export function snapTime(t, { words = [], lead = 0.12, edges = [], playhead = null, pps = 60, px = 8, disabled = false } = {}) {
  if (disabled) return { t, kind: null };
  const lim = px / pps;
  let best = null;
  const consider = (cand, kind, ref, label) => { const d = Math.abs(cand - t); if (d <= lim && (!best || d < best.d)) best = { d, t: cand, kind, ref, label }; };
  let lo = 0, hi = words.length;
  const target = t + lead;
  while (lo < hi) { const m = (lo + hi) >> 1; if (words[m][0] < target) lo = m + 1; else hi = m; }
  for (const j of [lo - 1, lo, lo + 1]) if (words[j]) consider(words[j][0] - lead, 'word', words[j][1], words[j][2]);
  for (const e of edges) consider(e, 'edge');
  if (playhead != null) consider(playhead, 'playhead');
  return best ? { t: best.t, kind: best.kind, ref: best.ref, label: best.label } : { t, kind: null };
}
