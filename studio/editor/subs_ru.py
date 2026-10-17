"""Русские субтитры для просмотра монтажа (в итоговый ролик не идут — пользователю, чтобы понимать, что говорит Ник).
Фразы берутся из голоса проекта Cutlab: клипы дорожки «Голос» → слова мастер-блоков (assets/voice/<ep>/line_timings.json)
с учётом вставленной в файлы *_edit.wav тишины. Перевод — export/<ep>/subs_ru_text.json {английская фраза: русская}.

  python3 studio/editor/subs_ru.py --project ep04 [--list]   → assets/subs/<ep>_ru.json (плеер Cutlab, кнопка RU) + export/<ep>/<ep>_ru.srt
  --list — показать фразы без перевода (их дописать в subs_ru_text.json и запустить снова).
После любого сдвига голоса в проекте — запустить снова (тайминг считается заново).
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_DUR, MAX_WORDS = 6.5, 15


def edits_for(pid):
    """файл голоса → (блок, правки {inserts, cuts} во времени мастера) из export/<ep>/voice_edits.json; мастер — без правок"""
    m = {}
    vj = f"{ROOT}/export/{pid}/voice_edits.json"
    spec = json.load(open(vj)) if os.path.exists(vj) else {}
    for blk in json.load(open(f"{ROOT}/assets/voice/{pid}/line_timings.json"))["blocks"]:
        m[f"block_{blk}_master.wav"] = (blk, {})
        if blk in spec: m[os.path.basename(spec[blk]["file"])] = (blk, spec[blk])
    return m


def map_time(sp, t):
    """время мастера → время файла правки; None — слово вырезано"""
    sh = 0.0
    for a, b, *_ in sp.get("cuts", []):
        if t >= b: sh -= (b - a)
        elif t > a - 1e-6: return None
    for at, d, *_ in sp.get("inserts", []):
        if t >= at - 1e-6: sh += d
    return t + sh


def fmt(t):
    h, r = divmod(max(0.0, t), 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def words_from_timeline(pid, p):
    """с ep05: голос собран studio/ep05/voice_timeline.py → export/<ep>/build/{timeline.json, words_ep.json} (слова во времени
    timeline; блок = файл правки + in → start). Клипы голоса проекта переводят время timeline → время монтажа."""
    B = f"{ROOT}/export/{pid}/build"
    tl = json.load(open(f"{B}/timeline.json")); ww = json.load(open(f"{B}/words_ep.json"))
    segs = [s for s in tl["segments"] if s.get("kind") == "block"]
    words = []
    for c in p["clips"]:
        if c["track"] != "voice" or c.get("kind") == "pause" or not c.get("src"): continue
        f, a = os.path.basename(c["src"]), float(c.get("in") or 0.0); b = a + c["dur"]
        for s in segs:
            if os.path.basename(s["file"]) != f: continue
            s_in = float(s.get("in") or 0.0)
            for w, t, e, *_ in ww:
                if not (s["start"] - 1e-3 <= t < s["start"] + s["dur"]): continue
                tf, ef = s_in + t - s["start"], s_in + e - s["start"]             # время файла голоса
                if a - 1e-3 <= tf < b: words.append((c["start"] + tf - a, c["start"] + min(ef, b) - a, w, s["id"].split(":")[0]))
    return words


def cues_for(pid, clips=None):
    """clips — свои клипы голоса (например, глав, ещё не поставленных в проект); по умолчанию — из проекта"""
    p = {"clips": clips} if clips is not None else json.load(open(f"{ROOT}/projects/{pid}/project.json"))
    end_re = r"[.?!…]$"
    if os.path.exists(f"{ROOT}/export/{pid}/build/words_ep.json") and os.path.exists(f"{ROOT}/export/{pid}/build/timeline.json"):
        words = words_from_timeline(pid, p)
        end_re = r"[.?!…][\"”»']?$"                                 # с ep05: конец фразы и внутри цитаты
    else:
        lt = json.load(open(f"{ROOT}/assets/voice/{pid}/line_timings.json"))["blocks"]
        words = []                                                 # (t0, t1, слово, блок) во времени таймлайна
        E = edits_for(pid)
        for c in p["clips"]:
            if c["track"] != "voice" or c.get("kind") == "pause" or not c.get("src"): continue
            name = os.path.basename(c["src"])
            if name not in E: print("нет карты правок для", name, file=sys.stderr); continue
            blk, sp = E[name]
            a, b = c.get("in", 0.0), c.get("in", 0.0) + c["dur"]
            for w, t, e, *_ in lt[blk]:
                tf, ef = map_time(sp, t), map_time(sp, e)
                if tf is None: continue
                ef = ef if ef is not None else tf + 0.2
                if a - 1e-3 <= tf < b: words.append((c["start"] + tf - a, c["start"] + min(ef, b) - a, w, blk))
    words.sort()
    cues, cur = [], []
    def flush():
        if cur: cues.append({"t0": cur[0][0], "t1": cur[-1][1], "en": " ".join(w for _, _, w, _ in cur)})
        cur.clear()
    for i, wd in enumerate(words):
        if cur and (wd[3] != cur[-1][3] or wd[0] - cur[-1][1] > 1.2): flush()   # другой блок или долгая пауза
        cur.append(wd)
        w = wd[2]; dur = cur[-1][1] - cur[0][0]
        if re.search(end_re, w) or (re.search(r"[,;:—]$", w) and (dur > MAX_DUR * 0.6 or len(cur) >= MAX_WORDS)) or len(cur) >= MAX_WORDS + 6:
            flush()
    flush()
    for c in cues: c["t0"] = round(max(0.0, c["t0"] - 0.08), 3)  # чуть раньше слова
    for i, c in enumerate(cues):                                   # держать до следующей фразы, без нахлёста
        nxt = cues[i + 1]["t0"] - 0.04 if i + 1 < len(cues) else c["t1"] + 0.8
        c["t1"] = round(max(c["t0"] + 0.6, min(nxt, c["t1"] + 0.7)), 3)
    return cues


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", required=True); ap.add_argument("--list", action="store_true")
    a = ap.parse_args(); pid = a.project
    cues = cues_for(pid)
    tp = f"{ROOT}/export/{pid}/subs_ru_text.json"
    tr = json.load(open(tp)) if os.path.exists(tp) else {}
    miss = [c["en"] for c in cues if c["en"] not in tr]
    if a.list:
        for c in cues: print(f'{c["t0"]:7.2f}  {"   " if c["en"] in tr else "?? "}{c["en"]}')
        print(f"\nфраз {len(cues)}, без перевода {len(miss)}"); return
    for c in cues: c["ru"] = tr.get(c["en"], "")
    os.makedirs(f"{ROOT}/assets/subs", exist_ok=True)
    json.dump(cues, open(f"{ROOT}/assets/subs/{pid}_ru.json", "w"), ensure_ascii=False, indent=0)
    with open(f"{ROOT}/export/{pid}/{pid}_ru.srt", "w") as f:
        for i, c in enumerate([c for c in cues if c["ru"]], 1): f.write(f"{i}\n{fmt(c['t0'])} --> {fmt(c['t1'])}\n{c['ru']}\n\n")
    print(f"фраз {len(cues)}, с переводом {len(cues) - len(miss)}; без перевода {len(miss)}"
          + (" — см. --list" if miss else "") + f"\n→ assets/subs/{pid}_ru.json, export/{pid}/{pid}_ru.srt")


if __name__ == "__main__":
    main()
