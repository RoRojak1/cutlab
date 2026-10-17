"""Английские субтитры для загрузки на YouTube: тайминг фраз — из голоса проекта Cutlab (как subs_ru.py), текст — из сценария.
Слова whisper сверяются со сценарием (script/<ep>_en.json, поле tts по блокам): где whisper ослышался («nine pains» → «panes»),
берётся слово сценария; числа остаются цифрами из whisper («1945», «500 meters»). Строки — не длиннее 42 знаков, не больше двух.

  python3 studio/editor/subs_en.py --project ep06   → export/<ep>/<ep>_en.srt (+ --diff: показать все замены)
"""
import argparse, difflib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subs_ru

ROOT = subs_ru.ROOT
LINE = 42


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


def script_words(pid):
    d = json.load(open(f"{ROOT}/script/{pid}_en.json"))
    out = []
    for b in d["blocks"]:
        for i in b["ids"]:
            ln = d["lines"].get(i)
            if ln and ln.get("tts"): out += [w for w in ln["tts"].split() if norm(w)]
    return out


def respell(w, r):
    """слово сценария r на месте слова whisper w: пунктуация и заглавная буква — от whisper"""
    lead = re.match(r"^\W*", w).group(0); tail = re.search(r"\W*$", w).group(0)
    core = re.sub(r"^\W+|\W+$", "", r)
    if w[:1].isupper() and core[:1].islower(): core = core[:1].upper() + core[1:]
    return lead + core + tail


def fix_words(words, ref, show=False):
    """words — слова whisper; ref — слова сценария. Меняем только куски без цифр (числа — цифрами из whisper):
    1:1 — пословно; неравные куски до 4 слов («count at» → «counted») — целиком, в позицию первого слова."""
    idx = [i for i, w in enumerate(words) if norm(w)]            # «—» и прочие знаки в сверке не участвуют
    a, b = [norm(words[i]) for i in idx], [norm(w) for w in ref]
    out = list(words)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "replace": continue
        ws, rs = [words[idx[i]] for i in range(i1, i2)], ref[j1:j2]
        if re.search(r"\d", " ".join(ws + rs)) or any(re.fullmatch(r"[IVXLC]{2,}\W*", w) for w in ws): continue   # числа и «Gregory XIII» — как у whisper
        if len(ws) == len(rs): new = [respell(w, r) for w, r in zip(ws, rs)]
        elif max(len(ws), len(rs)) <= 4:
            joined = " ".join(re.sub(r"^\W+|\W+$", "", r) for r in rs)
            new = [respell(ws[0] if len(ws) == 1 else ws[0] + re.search(r"\W*$", ws[-1]).group(0), joined)] + [""] * (len(ws) - 1)
        else: continue
        if new != ws:
            if show: print(f"  {' '.join(ws)!r:>24} → {' '.join(x for x in new if x)!r}")
            for k, n in enumerate(new): out[idx[i1 + k]] = n
    return out


def wrap(text):
    if len(text) <= LINE: return text
    ws = text.split(); best = None
    for i in range(1, len(ws)):
        l1, l2 = " ".join(ws[:i]), " ".join(ws[i:])
        score = max(len(l1), len(l2)) - (3 if re.search(r"[,;:—]$", ws[i - 1]) else 0) + (100 if max(len(l1), len(l2)) > LINE else 0)
        if best is None or score < best[0]: best = (score, l1, l2)
    return best[1] + "\n" + best[2]


def split_long(c):
    """фраза длиннее двух строк — делим по словам пропорционально времени"""
    ws = c["en"].split()
    if len(c["en"]) <= 2 * LINE: return [c]
    n = -(-len(c["en"]) // (2 * LINE - 6)); per = -(-len(ws) // n)
    parts, t0, dur, total = [], c["t0"], c["t1"] - c["t0"], len(c["en"])
    for k in range(0, len(ws), per):
        txt = " ".join(ws[k:k + per]); d = dur * (len(txt) + 1) / (total + 1)
        parts.append({"t0": round(t0, 3), "t1": round(t0 + d, 3), "en": txt}); t0 += d
    parts[-1]["t1"] = c["t1"]
    return parts


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", required=True); ap.add_argument("--diff", action="store_true")
    a = ap.parse_args(); pid = a.project
    cues = subs_ru.cues_for(pid)
    flat = [(ci, w) for ci, c in enumerate(cues) for w in c["en"].split()]
    fixed = fix_words([w for _, w in flat], script_words(pid), show=a.diff)
    for c in cues: c["en"] = ""
    for (ci, _), w in zip(flat, fixed):
        if w: cues[ci]["en"] = (cues[ci]["en"] + " " + w).strip()
    out = [p for c in cues if c["en"] for p in split_long(c)]
    path = f"{ROOT}/export/{pid}/{pid}_en.srt"
    with open(path, "w") as f:
        for i, c in enumerate(out, 1): f.write(f"{i}\n{subs_ru.fmt(c['t0'])} --> {subs_ru.fmt(c['t1'])}\n{wrap(c['en'])}\n\n")
    print(f"фраз {len(out)} → {path}")


if __name__ == "__main__":
    main()
