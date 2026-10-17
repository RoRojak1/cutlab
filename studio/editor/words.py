"""Слова озвучки: words.json по частям (время внутри части) и их время на таймлайне через клипы голоса."""
import bisect, json, re
from pathlib import Path
import model as M

LEAD = 0.12


def toks(s):
    return re.findall(r"[a-z]+|\d+", (s or "").lower().replace("\u2019", "'"))


def build_words(parts, vdir=None):
    vdir = Path(vdir) if vdir else M.ROOT / "assets" / "voice"
    out = {}
    for p in parts:
        j = M.read_json(vdir / f"{p}.words.json")
        lst = []
        for t in j["transcription"]:
            for w in toks(t["text"]):
                lst.append([w, t["offsets"]["from"] / 1000.0, t["offsets"]["to"] / 1000.0])
        out[p] = lst
    return {"version": 1, "parts": out}


def _voice_for(proj, part, t):
    for c in proj["clips"]:
        if c["track"] == "voice" and c.get("part") == part and c["in"] - 1e-6 <= t < c["in"] + c["dur"] - 1e-6:
            return c
    return None


def word_time(proj, words, ref):
    part, i = ref.rsplit(":", 1)
    lst = words["parts"].get(part) or []
    i = int(i)
    if not 0 <= i < len(lst):
        return None
    t = lst[i][1]
    c = _voice_for(proj, part, t)
    return None if c is None else round(c["start"] + t - c["in"], 4)


def timeline_words(proj, words):
    out = []
    for c in M.on_track(proj, "voice"):
        if c.get("kind") == "pause":
            continue
        for i, (w, a, _b) in enumerate(words["parts"].get(c.get("part")) or []):
            if c["in"] - 1e-6 <= a < c["in"] + c["dur"] - 1e-6:
                out.append((round(c["start"] + a - c["in"], 4), f"{c['part']}:{i}", w))
    out.sort()
    return out


def snap(tw, t, lead=LEAD, max_dist=0.25):
    ts = [x[0] - lead for x in tw]
    k = bisect.bisect_left(ts, t)
    best = None
    for j in (k - 1, k):
        if 0 <= j < len(ts):
            d = abs(ts[j] - t)
            if d <= max_dist and (best is None or d < best[0]):
                best = (d, round(ts[j], 4), tw[j][1])
    return None if best is None else (best[1], best[2])


def words_between(tw, a, b):
    return " ".join(w for t, _r, w in tw if a - 1e-6 <= t < b - 1e-6)


def find_word(tw, token, after=0.0, nth=1):
    token = token.lower()
    n = 0
    for t, ref, w in tw:
        if t >= after - 1e-6 and w == token:
            n += 1
            if n == nth:
                return t, ref
    return None


def anchor_for(tw, t, max_dist=0.3):
    s = snap(tw, t, lead=0.0, max_dist=max_dist)
    if not s:
        return None
    wt, ref = s
    return {"word": ref, "lead": round(wt - t, 4)}
