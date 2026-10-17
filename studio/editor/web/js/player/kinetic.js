// Кинетические надписи: время появления каждого слова заголовка (ost) относительно начала клипа.
// Порт kinetic_times из studio/capcut/timeline.py:48-90 (используется также в studio/app.js).
const norm = (w) => String(w).toLowerCase().replace(/[^a-z0-9%]+/g, '');
export const NUM = { forty: '40', thirty: '30', twenty: '20', fifty: '50', sixty: '60', seventy: '70', eighty: '80', ninety: '90', hundred: '100', ten: '10', one: '1', two: '2', three: '3', four: '4', five: '5', six: '6', seven: '7', eight: '8', nine: '9' };

export function kineticTimes(ost, en, dur, spoken) {
  const words = String(ost).split(/\s+/).filter(Boolean);
  const out = []; let last = null;
  if (spoken && spoken.length) {
    let frm = 0;
    for (const w of words) {
      const low = w.toLowerCase(), m = low.match(/\d+/), num = m ? m[0] : '', lett = low.replace(/[^a-z]+/g, '');
      const key = num && !/^[a-z]{2,}/.test(lett) ? num : (lett || num);
      let t = null;
      if (key) for (let j = frm; j < spoken.length; j++) {
        const tok = spoken[j][0];
        if (tok === key || (key.length > 3 && (tok.startsWith(key) || (key.startsWith(tok) && tok.length > 3)))) { t = spoken[j][1]; frm = j + 1; break; }
      }
      if (t == null) t = last == null ? Math.min(0.15 * dur, 0.3) : last + 0.18;
      t = Math.min(Math.max(t, last == null ? 0 : last + 0.06), Math.max(0, dur - 0.25));
      last = t; out.push({ w, t });
    }
    return out;
  }
  const enW = String(en).split(/\s+/).filter(Boolean).map(norm), n = Math.max(1, enW.length);
  let frm = 0;
  for (const w of words) {
    const key = norm(w).replace(/%$/, '');
    let t = null;
    if (key) for (let j = frm; j < enW.length; j++) {
      const ew = enW[j];
      if (ew && (ew === key || ew.replace(/%$/, '') === key || (key.length > 3 && ew.startsWith(key)))) { t = j / n * dur; frm = j + 1; break; }
    }
    if (t == null) t = last == null ? Math.min(0.15 * dur, 0.4) : last + 0.22;
    t = Math.max(t, last == null ? 0 : last + 0.08);
    last = t; out.push({ w, t });
  }
  return out;
}

// Абсолютные времена слов голоса (store.words: [t, ref, tok]) внутри окна [a, b) →
// относительное время + числительные заменены на цифры (NUM), как в новых надписях монтажки.
export function spokenIn(words, a, b) {
  const out = [];
  for (const [t, , tok] of words) if (t >= a - 1e-6 && t < b) out.push([NUM[tok] || tok, Math.round((t - a) * 1000) / 1000]);
  return out;
}

export function kineticFor(store, clip, text) {
  return kineticTimes(text, '', clip.dur, spokenIn(store.words, clip.start, clip.start + clip.dur)).map(({ w, t }) => [w, Math.round(t * 1000) / 1000]);
}
