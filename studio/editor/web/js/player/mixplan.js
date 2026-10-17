// Строит список звуковых/видео «cue» из клипов проекта — что и когда играть.
const BUS = { voice: 'voice', music: 'music', sfx1: 'sfx', sfx2: 'sfx', v1: 'video' };

export function buildCues(project, { off = {}, solo = null } = {}) {
  const out = [];
  for (const c of project.clips) {
    const bus = BUS[c.track];
    if (!bus || off[c.track] || (solo && solo !== c.track)) continue;
    if (c.kind === 'pause' || c.mute) continue;
    if (c.track === 'v1' && c.kind !== 'video') continue;
    out.push({ id: c.id, bus, src: c.src, at: c.start, offset: c.in || 0, dur: c.dur, gainDb: c.volume_db ?? 0,
      loop: !!c.loop, fadeIn: c.fade_in || 0, fadeOut: c.fade_out || 0, element: c.track === 'v1', speed: c.speed || 1 });
  }
  // Array#sort is stable (ES2019+): equal `at` keeps clips.json insertion order —
  // required for the fixture's tie at t=0 (voice clip listed before the music cue).
  return out.sort((a, b) => a.at - b.at);
}
export const cuesIn = (cues, a, b) => cues.filter((c) => c.at < b && c.at + c.dur > a);
