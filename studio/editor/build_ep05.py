#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ep05 «What Is the Meaning of Life? (According to Science)» в Cutlab — первая сборка (07.10).

Источники (все в export/ep05/build/):
  timeline.json, words_ep.json — голос ролика (studio/ep05/voice_edits.py + voice_timeline.py): блоки, вставки, сцены Ника;
  shots_p1.json, shots_p2.json — куски визуального плана с файлами; audio_plan.json — музыка, звуки, фоны.
Время куска: начало реплики (мастер) + сдвиг плана → voice_edits.ep_time → ролик; граница в ±0,25 с от начала слова —
за 0,12 с до слова; дорожка «Кадры» сплошная. Сцены Ника — кадр 0 = clip_start, целиком, ×1,0; 3D — целиком (×0,8…1,2);
вставки без голоса (книга, заставка, карточки, концовка) — по timeline.json. Рамки 4A — studio/ep05/frame_shot.py (пакет).
С 08.10 куски window / window_916 / photo_corners из grid_groups.json стоят стопкой «лист в клетку» (framed_grid/, звуки
ge-* из grid_events.json) — настройка export/ep05/build/frame_style.json ("style": "grid" | "windows" — прежние окна и fe-*;
"keep_windows": куски, где окно остаётся — p1_036 продолжает бумагу H2). Шлепки вырезок-терминов term-* — только когда
вырезка есть в кадре (term_done). Круг маркером через паузу и слово — кусками (circle_parts).
Чего нет (3D рендерится, GFX, текст) — жёлтая карточка с данными куска в поле "plan"; --fill ставит файл на её место.

  python3 studio/editor/build_ep05.py                 # план: куски, заглушки, сводка (+ build_plan.json, frames_jobs.json)
  python3 studio/editor/build_ep05.py --frames        # рамки 4A пакетом (frame_shot --batch --jobs 4), потом холодное начало в ТВ
  python3 studio/editor/build_ep05.py --tv            # только холодное начало: каждый кусок — на экране одного ТВ (правки 37–41)
  python3 studio/editor/build_ep05.py --retime        # 3D ×≠1 вне тизера → готовые файлы ×1,0 (minterpolate; правка 48)
  python3 studio/editor/build_ep05.py --audio         # приглушённые куски музыки (_ducked) — до --apply
  python3 studio/editor/build_ep05.py --apply         # создать/перезаписать проект ep05 через сервер Cutlab
  python3 studio/editor/build_ep05.py --fill          # только жёлтые карточки, для которых появился материал (set по месту)
  python3 studio/editor/build_ep05.py --report        # сводка сборки (markdown) + qc_scan — в stdout
  python3 studio/editor/build_ep05.py --sheet a.mp4 b.jpg [--step 3]   # лист кадров превью с подписями кусков
  --from 0 --to 140                                   # вывод плана только для отрезка (с)
"""
import argparse, bisect, difflib, hashlib, json, math, os, re, subprocess, sys, time, urllib.request, wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "studio", "ep05"))
import voice_edits as VE                                              # noqa: E402

URL = "http://127.0.0.1:8777/api"
PID, TITLE = "ep05", "What Is the Meaning of Life? (According to Science)"
FPS, LEAD, SNAP, EPS = 30, 0.12, 0.25, 1e-6
B = "export/ep05/build"
FR = "assets/shots/ep05/framed"
DUCK = "assets/music/ep05/_ducked"
JOBS = B + "/frames_jobs.json"
PLAN_OUT = B + "/build_plan.json"
FS = "studio/ep05/frame_shot.py"
# Рамки окна/фото: "grid" — стопка «лист в клетку» (studio/ep05/frame_grid_stack.py → framed_grid/, звуки grid_events.json),
# "windows" — прежние окна framed/ (звуки fe-*). Откат одной строкой — "style" в export/ep05/build/frame_style.json.
FRAME_STYLE_JSON = B + "/frame_style.json"
GRID_DIR = "assets/shots/ep05/framed_grid"
GRID_GROUPS, GRID_EVENTS = B + "/grid_groups.json", B + "/grid_events.json"


def jl(p):
    with open(p, encoding="utf-8") as f: return json.load(f)


TL = jl(B + "/timeline.json")
WORDS = jl(B + "/words_ep.json")
LTM = jl("assets/voice/ep05/line_timings.json")["lines"]            # время реплик в мастере (сдвиги плана — от него)
S1, S2 = jl(B + "/shots_p1.json"), jl(B + "/shots_p2.json")
AP = jl(B + "/audio_plan.json")


def _frame_style():
    try: d = jl(FRAME_STYLE_JSON); return str(d.get("style") or "windows"), set(d.get("keep_windows") or [])
    except (OSError, ValueError): return "windows", set()


FRAME_STYLE, KEEP_WINDOWS = _frame_style()                            # grid | windows; keep_windows — куски, где окно остаётся
GRID = ({p["piece"] for g in jl(GRID_GROUPS)["groups"] for p in g["pieces"]} - KEEP_WINDOWS
        if FRAME_STYLE == "grid" and os.path.exists(GRID_GROUPS) else set())
LINES, SEG = TL["lines"], {s["id"]: s for s in TL["segments"]}
NICK = {n["clip"]: n for n in TL["nick"]}
WST = [w[1] for w in WORDS]
CHAP = {"0": "0. ХОЛОДНОЕ НАЧАЛО", "H": "1. ХУК", "T": "2. ТИЗЕР", "I": "3. ЗАСТАВКА", "1": "4. ГЛАВА 1 — ГЕНЫ",
        "2": "5. ГЛАВА 2 — МОЗГ", "3": "6. ГЛАВА 3 — ВРЕМЯ", "R": "7. СПУСК", "4": "8. ГЛАВА 4 — ЛЮДИ",
        "5": "9. ГЛАВА 5 — СМЫСЛ", "6": "10. ГЛАВА 6 — ВСЕЛЕННАЯ", "F": "11. ФИНАЛ", "E": "12. КОНЦОВКА"}
# цвет главы для рамок (frame_shot --chapter)
FCH = {"hook": "hook", "teaser": "hook", "intro": "hook", "gene": "gene", "brain": "brain", "time": "time",
       "descent": "people", "people": "people", "meaning": "meaning", "universe": "universe", "finale": "universe"}
FRAMED = ("window", "window_916", "photo_corners", "film", "tv", "tv_caption", "reel_916", "full")
AI_MOVES = ["zoom_in", "zoom_out", "pan_right", "zoom_in", "pan_left", "zoom_out"]
GREEN = "0x63FC17"                                                  # зелёный экран стоковых ТВ (замер 07.10)
LOG = []


def log(msg):
    LOG.append(msg)


def fr(t): return round(round(float(t) * FPS) / FPS, 6)


def tc(t):
    m, s = divmod(max(0.0, t), 60)
    return "%d:%04.1f" % (m, s)


_PR = {}


def probe(p):
    """{ok, dur, w, h, audio} — файл читается ffprobe (недописанный mp4 без moov — нет)"""
    if p in _PR: return _PR[p]
    r = {"ok": False, "dur": 0.0, "w": 0, "h": 0, "audio": False}
    if p and os.path.exists(p):
        q = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                            "-of", "json", p], capture_output=True, text=True)
        if q.returncode == 0:
            try:
                d = json.loads(q.stdout); r["dur"] = float(d.get("format", {}).get("duration") or 0)
                for st in d.get("streams", []):
                    if st.get("codec_type") == "video" and not r["w"]: r["w"], r["h"] = st.get("width", 0), st.get("height", 0)
                    if st.get("codec_type") == "audio": r["audio"] = True
                r["ok"] = r["dur"] > 0
            except ValueError:
                pass
    _PR[p] = r
    return r


def chapter_at(t):
    cur = TL["chapters"][0]["id"]
    for c in TL["chapters"]:
        if c["start"] <= t + 0.05: cur = c["id"]
    return CHAP.get(cur, cur)


# ------------------------------------------------------------------ время
def ep_line(lid, off=0.0, at="start"):
    """«реплика + сдвиг» плана (сдвиг — секунды мастера от начала реплики) → секунды ролика"""
    ln = LTM[lid]
    return VE.ep_time(LINES[lid]["block"], (ln["start"] if at == "start" else ln["end"]) + off)


def snap(t):
    """граница в ±0,25 с от начала слова → за 0,12 с до слова"""
    i = bisect.bisect_left(WST, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(WST) and abs(WST[j] - t) <= SNAP and (best is None or abs(WST[j] - t) < abs(best - t)): best = WST[j]
    return t if best is None else best - LEAD


def norm(w): return "".join(ch for ch in w.lower() if ch.isalnum() or ch == "'")


def snap_phrase(t, phrase):
    """склейка — за 0,12 с до первого слова фразы куска (ищем его в ±0,6 с от точки плана); нет — обычный snap"""
    toks = [norm(x) for x in re.split(r"[\s\u2014\u2013-]+", phrase or "") if norm(x)]
    if toks and not (phrase or "").lstrip().startswith(("(", "\u2026", "...")):
        i0 = bisect.bisect_left(WST, t - 0.6); best = None
        for j in range(i0, len(WORDS)):
            if WST[j] > t + 0.6: break
            if norm(WORDS[j][0]) == toks[0] and (best is None or abs(WST[j] - t) < abs(WST[best] - t)): best = j
        if best is not None: return WST[best] - LEAD
    return snap(t)


# --- фраза куска → слово голоса (проверка 07.10: точка плана по line_timings расходится со словами до 1,5 с)
NUMW = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
           "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion".split())


def stem(t):
    if t and (t[0].isdigit() or t in NUMW): return "#"
    for suf in ("'s", "ing", "ed", "s", "d"):
        if len(t) > 4 and t.endswith(suf): return t[:-len(suf)]
    return t


def ptoks(ph):
    ph = (ph or "").replace("…", " ").replace("/", " ")
    return [norm(x).strip("'") for x in re.split(r"[\s—–-]+", ph) if norm(x).strip("'")]


WN = [stem(norm(w[0])) for w in WORDS]


def sim(a, b): return difflib.SequenceMatcher(None, a, b).ratio()


def match_words(tk0, near, line):
    """первое слово фразы: токены фразы ↔ слова голоса по порядку (difflib) в ±2 с от точки плана; ближе — лучше"""
    tk = [stem(x) for x in tk0[:6]]
    if not tk: return None
    ln = LINES.get(line) or {}
    lo = max(0, bisect.bisect_left(WST, near - 2.0)); hi = min(len(WORDS), bisect.bisect_right(WST, near + 2.0))
    best = None
    for j in range(lo, hi):
        ws = [w if w in tk else next((x for x in tk if len(x) > 3 and sim(w, x) >= 0.75), w) for w in WN[j:j + 8]]
        sm = difflib.SequenceMatcher(None, tk, ws, autojunk=False)   # «victor» = «viktor» (опечатки распознавания)
        bl = [b for b in sm.get_matching_blocks() if b.size]
        if not bl or bl[0].b != 0 or bl[0].a > 2: continue
        a0 = bl[0].a; n = sum(b.size for b in bl if b.a < 5)
        skip = (bl[-1].b + bl[-1].size) - sum(b.size for b in bl)    # пропущенные слова голоса между совпадениями
        if tk[a0] == "#" and n < 2: continue
        if n < min(2, len(tk)) and not (a0 <= 1 and len(tk[a0]) >= 5): continue
        idx = j
        for _ in range(a0):                                  # слово перед совпадением похоже на пропущенное начало фразы
            pw = norm(WORDS[idx - 1][0]) if idx > 0 else ""
            sm_ = max([sim(pw, x) for x in tk0[:a0]] or [0.0]); gap = WORDS[idx][1] - WORDS[idx - 1][2]
            if pw and ((gap < 0.4 and sm_ >= 0.6) or (gap < 1.0 and sm_ >= 0.75)): idx -= 1
            else: break
        d = abs(WST[idx] - near)
        sc = n - 0.6 * a0 - 0.4 * skip - 0.8 * d + (0.3 if ln and ln["w0"] <= idx <= ln["w1"] else 0.0)
        if best is None or sc > best[0]: best = (sc, idx)
    return None if best is None else best[1]


def phrase_word(s, raw):
    """→ (индекс первого слова куска в WORDS или None, время этого слова по плану)"""
    a = s["anchor"]; ph = (s.get("phrase") or "").strip()
    if a.get("kind") != "line": return None, raw
    w0 = a.get("w0") if s.get("sub") else None              # ч.2, общая фраза у кусков a/b: первое слово куска из w0
    if w0:
        plan_w = ep_line(a["line"], float(w0[1])); tk = ptoks(ph); first = norm(w0[0])
        cand = [match_words(tk[k:], plan_w, a["line"]) for k in range(len(tk)) if tk[k] == first] or \
               [match_words([first], plan_w, a["line"])]
        cand = [j for j in cand if j is not None]
        return (min(cand, key=lambda j: abs(WST[j] - plan_w)) if cand else None), plan_w
    if not ph or ph.startswith("(") or ph in ("—", "-"): return None, raw
    return match_words(ptoks(ph), raw, a["line"]), raw


WARP = {}                                                   # реплика → [(время по плану, время по словам)]


def warp(t, line=None):
    """время по плану (line_timings) → время по словам голоса: поправка по найденным словам кусков этой реплики"""
    an = WARP.get(line) or WARP.get("*") or []
    if not an: return t
    i = bisect.bisect_left([x[0] for x in an], t)
    if i <= 0: return t + (an[0][1] - an[0][0])
    if i >= len(an): return t + (an[-1][1] - an[-1][0])
    (p0, a0), (p1, a1) = an[i - 1], an[i]
    u = 0.0 if p1 - p0 < 1e-6 else (t - p0) / (p1 - p0)
    return t + (a0 - p0) + u * ((a1 - p1) - (a0 - p0))


def soft_snap(t):
    """не прилипать к чужому слову: только если t внутри слова или слово начинается в ближайшие 0,25 с"""
    i = bisect.bisect_left(WST, t - 3.0)
    for j in range(i, len(WORDS)):
        w = WORDS[j]
        if w[1] > t + SNAP: break
        if w[1] - 0.05 <= t <= w[2] or t < w[1] <= t + SNAP: return w[1] - LEAD
    return t


def word_time(line, text, nth=1, at="start"):
    ln = LINES[line]; k = 0
    for w in WORDS[ln["w0"]:ln["w1"] + 1]:
        if norm(w[0]) == norm(text):
            k += 1
            if k == nth: return w[1] if at == "start" else w[2]
    raise KeyError("%s: нет слова %r №%d" % (line, text, nth))


# ------------------------------------------------------------------ куски плана
def pid_of(s):
    return s.get("id") or "p%d_%03d%s" % (s["part"], s["n"], s.get("sub") or "")


def nick_id(s): return os.path.basename(s["src"]["file"])[:-4]


def insert_slot(s):
    """вставки без голоса — по timeline.json"""
    f = os.path.basename(s["src"].get("file") or "")
    if s["type"] == "card": seg = SEG["CARD_" + f.replace("card_", "").replace("_v1.mp4", "")]
    elif s["type"] == "insert3d": seg = SEG["book_close"]
    elif s["type"] == "intro": seg = SEG["INTRO"] if s["part"] == 1 else SEG["END"]
    elif s["anchor"].get("after") == "2.14":                        # experience_machine_p2: 4,5 с после клипа N5
        e = NICK["N5"]["clip_end"]; return e, e + float(s["anchor"].get("dur") or s["dur"])
    else: raise KeyError("вставка %s: не знаю места" % pid_of(s))
    return seg["start"], seg["start"] + seg["dur"]


def plan_pieces():
    out = []
    for s in S1 + S2:
        if s["src"].get("status") == "superseded":
            log("%s вытеснен по плану (%s)" % (pid_of(s), s["desc"][:60])); continue
        a = s["anchor"]; it = {"pid": pid_of(s), "s": s, "fixed": None}
        if a["kind"] == "abs":
            t1 = a["t1"] + float(s.get("hold_end") or 0)
            it["raw"], it["fixed"] = a["t0"], (a["t0"], t1)
        elif a["kind"] == "insert":
            it["fixed"] = insert_slot(s); it["raw"] = it["fixed"][0]
        elif s["type"] == "nick":
            n = NICK[nick_id(s)]; it["fixed"] = (n["clip_start"], n["clip_end"]); it["raw"] = n["clip_start"]
        else:
            it["raw"] = ep_line(a["line"], float(a["t0"]))
        out.append(it)
    return out


def build_warp(items):
    """первые слова кусков → WARP: поправка «время плана → время слов» по каждой реплике"""
    WARP.clear(); allp = []
    for it in items:
        it["wraw"] = it["raw"]; it["word"] = None
        if it["fixed"]: continue
        j, plan_w = phrase_word(it["s"], it["raw"])
        if j is None: continue
        it["word"] = j; it["wraw"] = WST[j] - (plan_w - it["raw"])
        WARP.setdefault(it["s"]["anchor"]["line"], []).append((plan_w, WST[j])); allp.append((plan_w, WST[j]))
    for lid, ln in LINES.items():                              # реплика без найденных слов — по её первому слову
        if lid not in WARP and lid in LTM:
            p = ep_line(lid, 0.0); WARP[lid] = [(p, WST[ln["w0"]])]; allp.append((p, WST[ln["w0"]]))
    for k in list(WARP): WARP[k] = sorted(set(WARP[k]))
    WARP["*"] = sorted(set(allp))


def layout(items):
    """начала → сплошная дорожка: фиксированные (Ник, вставки, холодное начало) не двигаются, соседи подстраиваются.
    Склейка — за 0,12 с до первого слова фразы куска (сопоставление фразы со словами); не нашли — точка плана с поправкой WARP"""
    build_warp(items)
    for it in items:
        if it["fixed"]: it["start"] = fr(it["fixed"][0]); continue
        if it["word"] is not None: it["start"] = fr(WST[it["word"]] - LEAD); continue
        line = it["s"]["anchor"].get("line")
        it["wraw"] = warp(it["raw"], line)
        it["start"] = fr(soft_snap(it["wraw"]) if line else it["wraw"])
        log("%s: слово фразы не найдено — точка плана %.2f → %.2f" % (it["pid"], it["raw"], it["wraw"]))
    for a, b in zip(items, items[1:]):
        if b["start"] < a["start"] - EPS and not b["fixed"]:
            log("%s: начало %.2f раньше %s (%.2f) — поставлен следом" % (b["pid"], b["start"], a["pid"], a["start"]))
            b["start"] = a["start"]
    for i, it in enumerate(items[:-1]):
        nx = items[i + 1]
        if it["fixed"]:
            e = fr(it["fixed"][1])
            if not nx["fixed"]:
                if abs(nx["start"] - e) > 0.02: it.setdefault("adj", []).append("следующий с конца %.2f (было %.2f)" % (e, nx["start"]))
                nx["start"] = e
            elif nx["start"] > e + EPS:
                it["hold"] = round(nx["start"] - e, 3)                # стоп-кадр до следующей вставки
            elif nx["start"] < e - EPS:
                log("%s заходит на %s на %.2f с" % (it["pid"], nx["pid"], e - nx["start"]))
    shift3d(items)
    keep = []
    for i, it in enumerate(items):
        it["end"] = fr(items[i + 1]["start"]) if i + 1 < len(items) else fr(it["fixed"][1])
        if it["end"] - it["start"] < 2.0 / FPS - EPS:
            log("%s выпал: слот %.2f с (%s)" % (it["pid"], it["end"] - it["start"], it["s"]["desc"][:50])); continue
        keep.append(it)
    for a, b in zip(keep, keep[1:]): a["end"] = b["start"]
    return keep


# ------------------------------------------------------------------ материалы
def ready3d(path, expect):
    pr = probe(path)
    return pr["ok"] and (not expect or pr["dur"] >= float(expect) - 0.2)


T3D = ("3d", "step", "card")


def info3d(it):
    """→ (длина файла, in плана, скорость плана, показ целиком?)"""
    s = it["s"]; f = s["src"].get("file")
    L = probe(f)["dur"] if f and probe(f)["ok"] else float(s["src"].get("src_dur") or 10.0)
    k0 = float(s.get("speed") or 1.0); in0 = float(s["src"].get("in") or 0.0); plan_dur = float(s.get("dur") or 0)
    full = s["type"] in ("card", "step", "insert3d") or (in0 <= 0.05 and plan_dur * k0 >= L - 0.1)
    return L, in0, k0, full


def knot_word(what, near, line, t):
    """«слово» из описания метки → его время в голосе; «слово» +x,y — метка задумана на (x,y − t) раньше слова"""
    if re.search(r"до \+", what or ""): return None             # «(до +x)» — событие-отрезок: время плана
    for m in re.finditer("«([^»]+)»", what or ""):
        q = ptoks(m.group(1))
        if not q: continue
        j = match_words(q, near, line)
        if j is None: continue
        m2 = re.match(r"\s*\(?\+(\d+)[,.](\d+)", what[m.end():])
        lead = (float(m2.group(1) + "." + m2.group(2)) - t) if m2 and t is not None else 0.0
        return WST[j] - (lead if 0 <= lead < 1.5 else 0.0)
    return None


def knots(it):
    """метки синхрона сцены: (время в файле, время в ролике по словам, что). Цель — слово из «…» в описании метки,
    иначе время плана с поправкой WARP"""
    out = []
    for y in it["s"].get("sync") or []:
        if y.get("src_t") is None: continue
        line, t = y.get("line"), y.get("t")
        if line and t is not None:
            try: T = warp(ep_line(line, float(t)), line)
            except KeyError: continue
        elif y.get("t_in_shot") is not None:
            T = it.get("wraw", it["raw"]) + float(y["t_in_shot"]); line = it["s"]["anchor"].get("line"); t = None
        else: continue
        Tw = knot_word(y.get("what"), T, line, float(t) if t is not None else None)
        out.append((float(y["src_t"]), Tw if Tw is not None else T, (y.get("what") or "")[:40]))
    return sorted(out)


def shift3d(items):
    """3D целиком с синхроном: если от склейки до первой метки скорость уходит дальше ±10 % от плановой —
    сдвинуть начало сцены к точке плана (−0,35…+0,6 с; соседний кусок удлиняется)"""
    for i, it in enumerate(items):
        if it["fixed"] or it["s"]["type"] not in T3D or i == 0 or items[i - 1]["fixed"]: continue
        L, in0, k0, full = info3d(it)
        kn = [k for k in knots(it) if k[0] > in0 + 0.3]
        if not full or not kn: continue
        src1, T1, _ = kn[0]
        need = (src1 - in0) / max(0.05, T1 - it["start"])
        if 0.9 <= need / k0 <= 1.1: continue
        # зажим −11 кадров (было −0,35 с = 10,5 кадра: ничья округления, сдвиг блока на чётное/нечётное число кадров
        # давал то 10, то 11 кадров — p1_126 / p2_098 / p2_126 после тизера S1 «уехали» на кадр; проверка 08.10)
        lo = max(it["start"] - 11.0 / FPS, items[i - 1]["start"] + 0.8); hi = it["start"] + 0.6
        if i + 1 < len(items): hi = min(hi, items[i + 1]["start"] - 1.0)
        new = fr(min(hi, max(lo, T1 - (src1 - in0) / k0)))
        if abs(new - it["start"]) > 0.02:
            log("%s: начало 3D %.2f → %.2f (первая метка «%s»)" % (it["pid"], it["start"], new, kn[0][2]))
            it["start"] = new


def fit_segs(kn, a, b, src_a, src_len, full, lo_k, hi_k, k0):
    """скорости по меткам: перебор разбиений меток на 1–3 группы, у группы своя скорость (МНК, в пределах lo_k…hi_k);
    целиком — хвост после последней метки подогнать к слоту. Цена: худшая ошибка метки + 0,08 за кусок + хвост"""
    import itertools
    if not kn:
        k = min(hi_k, max(lo_k, (src_len - src_a) / max(0.05, b - a))) if full else min(hi_k, max(lo_k, k0))
        return [[a, src_a, k]]
    lo_u, hi_u = 1.0 / hi_k, 1.0 / lo_k
    grid = [lo_u + (hi_u - lo_u) * i / 40.0 for i in range(41)]
    wt = lambda x: x if x > 0 else -0.5 * x                      # позже слова — вдвое хуже, чем раньше (карточка уже стоит)
    n = len(kn); best = None
    for ng in range(1, min(3, n) + 1):
        for cuts in itertools.combinations(range(1, n), ng - 1):
            bounds = [0] + list(cuts) + [n]; segs = []; e, s0 = a, src_a; errs = []
            for g in range(len(bounds) - 1):
                grp = kn[bounds[g]:bounds[g + 1]]
                u = min(grid, key=lambda u_: (max(wt(e + (st - s0) * u_ - T) for st, T, _ in grp), abs(u_ * k0 - 1)))
                errs += [e + (st - s0) * u - T for st, T, _ in grp]
                segs.append([e, s0, 1.0 / u])
                if g + 1 < len(bounds) - 1:
                    st = grp[-1][0]; e, s0 = e + (st - s0) * u, st
            cost = max(wt(x) for x in errs) + 0.08 * (len(segs) - 1)
            if full:
                e, s0, k = segs[-1]; end = e + (src_len - s0) / k
                if (end - b > 0.1 or b - end > 0.6) and len(segs) < 3:   # хвост после последней метки — своя скорость
                    st = kn[-1][0]; et = e + (st - s0) / k
                    kt = min(hi_k, max(lo_k, (src_len - st) / max(0.05, b - et)))
                    segs.append([et, st, kt]); end = et + (src_len - st) / kt; cost += 0.08
                cost += 2.0 * max(0.0, end - b - 0.05) + 0.3 * max(0.0, b - end - 0.6)
            if best is None or cost < best[0]: best = (cost, segs)
    out = [best[1][0]]
    for g in best[1][1:]:                                       # почти одинаковые скорости — один кусок
        if abs(g[2] - out[-1][2]) >= 0.03: out.append(g)
    return out


def fit3d(it, src_len):
    """→ in, скорость, заметка, ошибка синхрона. Целиком (план берёт весь файл): 0,8…1,2, короче слота — стоп-кадр.
    Отрезок сцены: скорость плана, in едет вместе с началом куска (время сцены — по словам, WARP).
    Метки синхрона: по меткам — свои скорости (в пределах ±20 %), не больше 3 кусков; it["segs3d"] = [[начало, in, k]]"""
    s = it["s"]; k0 = float(s.get("speed") or 1.0); in0 = float(s["src"].get("in") or 0.0)
    a, b = it["start"], it["end"]; slot = b - a; plan_dur = float(s.get("dur") or slot)
    full = s["type"] in ("card", "step", "insert3d") or (in0 <= 0.05 and plan_dur * k0 >= src_len - 0.1)
    it["full3d"] = full
    if full: lo_k, hi_k, src_a = 0.8, 1.2, in0
    else: lo_k, hi_k, src_a = k0 * 0.8, k0 * 1.2, max(0.0, in0 + (a - it.get("wraw", it["raw"])) * k0)
    kn = [k for k in knots(it) if src_a + 0.3 < k[0] < src_len - 0.05] if s["type"] != "insert3d" else []
    segs = fit_segs(kn, a, b, src_a, src_len, full, lo_k, hi_k, k0)
    cont = s.get("seg_speed") == "continue" and len(segs) > 1
    if cont:   # правка 61 (08.10, p1_087): куски после первой группы меток — та же скорость продолжением (время файла
        k1 = segs[0][2] = round(segs[0][2], 4)   # непрерывно, стык без скачка скорости; k как в клипе); хвост за склейкой срезан —
        for j in range(1, len(segs)):        # стоп-кадра в конце нет; метки после стыка — где выпадут при этой скорости
            e0 = fr(segs[j][0]); segs[j] = [e0, segs[j - 1][1] + (e0 - segs[j - 1][0]) * k1, k1]

    def endpoint(i):
        if i + 1 < len(segs): return segs[i + 1][0], segs[i + 1][1]
        e, s_, k = segs[i]
        return (e + (src_len - s_) / k, src_len) if full else (b, s_ + (b - e) * k)

    segs = [[round(g[0], 4), round(g[1], 4), round(g[2], 4)] for g in segs]
    it["segs3d"] = segs if len(segs) > 1 else None
    inn, k = segs[0][1], segs[0][2]
    note = "×%.3f" % k + ("" if full else " (отрезок с %.2f с)" % inn)
    if len(segs) > 1: note += "".join(" → ×%.3f с %.1f с" % (g[2], g[1]) for g in segs[1:])
    e_end, _ = endpoint(len(segs) - 1)
    if cont: note += ", одной скоростью продолжением"
    if full and e_end < b - 0.05: note += ", стоп-кадр %.2f с" % (b - e_end)
    elif full and e_end > b + 0.05: note += (", хвост %.2f с за склейкой" if cont else ", ⚠ хвост %.2f с срезан") % (e_end - b)
    err = []
    for st, T, w in kn:
        g = [x for x in segs if x[1] <= st + 1e-6][-1]
        err.append(g[0] + (st - g[1]) / g[2] - T)
    if err: note += ", метки ↔ слова %s" % " ".join("%+.2f" % x for x in err)
    it["sync_errs"] = err
    return round(inn, 4), round(k, 4), note, (max(abs(x) for x in err) if err else 0.0)


def fvariant(v, pr):
    """вариант плана → параметры frame_shot"""
    out = {}
    v = (v or "").lower()
    if "кругл" in v or "окуляр" in v: out["variant"] = "круглое"
    elif "видоиск" in v: out["variant"] = "видоискатель"
    elif "vhs" in v: out["variant"] = "VHS"
    elif "булавк" in v: out["variant"] = "булавка"
    return out


# авторы рилсов холодного начала — все разные (проверка 07.10: у 5 из 12 был один «@grind.mode.daily»).
# С правки 75 (09.10) рилсов в холодном начале нет (p1_013–p1_024 — горизонтальные каналы ТВ), словарь — на случай отката
HANDLES = {"p1_013": "@neon.vlogs", "p1_014": "@5am.club.daily", "p1_015": "@ice.mind.co", "p1_016": "@quit.the.9to5",
           "p1_017": "@millionaire.habits", "p1_018": "@alpha.morning", "p1_019": "@grind.mode.daily", "p1_020": "@cash.flow.kings",
           "p1_021": "@laptop.nomad", "p1_022": "@manifest.money", "p1_023": "@cold.plunge.club", "p1_024": "@coach.unlimited"}


def ovr(pid, pr):
    """ручные поправки по находкам проверки кадров (RESOLVE_p1/p2 и проверка 07.10)"""
    w, h = pr["w"] or 1920, pr["h"] or 1080
    if pid == "p1_023":                                             # голова целиком, вывеска FIT слева срезана (9:16)
        return {"crop": "%d:%d:%d:0" % (w - int(w / 6), int((w - int(w / 6)) * 16 / 9), int(w / 6))}
    if pid == "p1_018":                                             # мужчина и корма седана; эмблема и номер — за кадром
        return {"focus": "0.67,0.5"}
    if pid in ("p1_009", "p1_011"):                                 # значок VOA справа внизу — срезать (16:9 сохраняется)
        return {"crop": "%d:%d:0:0" % (int(w * 0.8), int(h * 0.8))}
    if pid == "p1_032":                                             # на будильнике 4:20, а голос — «five»: только верх
        return {"kind": "window", "crop": "%d:%d:0:%d" % (w, int(h / 3), int(h * 0.31))}  # (звонки и 12), стрелок не видно
    # p1_071 (тизер S1, самолётик ×2) — кроп и 25 → 30 к/с в prep_src
    if pid in ("p1_141",):                                          # «Silver»: крупно серебряная медаль (другой кадр, чем #138); p1_057 — теперь другой кусок тизера S1
        return {"crop": "%d:%d:%d:%d" % (int(w * 0.4), int(h * 0.4), int(w * 0.055), int(h * 0.4))}
    return {}


def _sig(*a):
    return hashlib.sha1(json.dumps(a, default=str).encode()).hexdigest()[:12]


def _fresh(out, sig):
    side = out + ".json"
    return os.path.exists(out) and os.path.exists(side) and jl(side).get("sig") == sig


def _done(out, sig, **kw):
    json.dump(dict(sig=sig, made=time.strftime("%Y-%m-%d %H:%M:%S"), **kw), open(out + ".json", "w"), ensure_ascii=False)


def prep_src(pid, src, inn, span, k=1.0):
    """исходник куска, подготовленный до рамки (framed/_src/<кусок>_*.mp4, кэш по подписи): логотипы размыты,
    зелёные экраны заполнены, наезд/отъезд. → путь или None (кусок без подготовки)"""
    os.makedirs(FR + "/_src", exist_ok=True)
    if pid == "p1_102":                                             # GUINNESS на бокалах (арфа и надпись) — размыть
        out = "%s/_src/%s_clean.mp4" % (FR, pid); sig = _sig("clean2", src, inn, span, os.path.getmtime(src))
        if not _fresh(out, sig):
            boxes = [(1130, 190, 320, 270), (1520, 180, 300, 260)]   # x, y, w, h в пикселях исходника 1920×1080
            fc = "[0:v]setpts=PTS-STARTPTS,fps=%d[b0];" % FPS; cur = "b0"
            for i, (x, y, bw, bh) in enumerate(boxes):
                fc += ("[%s]split[m%d][c%d];[c%d]crop=%d:%d:%d:%d,boxblur=22:3[z%d];[m%d][z%d]overlay=%d:%d[b%d];"
                       % (cur, i, i, i, bw, bh, x, y, i, i, i, x, y, i + 1)); cur = "b%d" % (i + 1)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % inn, "-t", "%.3f" % span, "-i", src, "-filter_complex",
                            fc.rstrip(";"), "-map", "[%s]" % cur, "-an", "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", out], check=True)
            _done(out, sig, why="логотипы на бокалах размыты")
        return out
    if pid == "p1_021":                                             # зелёные экраны ноутбука и телефона → график криптоприложения
        out = "%s/_src/%s_key.mp4" % (FR, pid)
        bg, bg_in = "assets/stock/ep05/354546893.mp4", 10.0             # кусок #22 (палец выбирает биткоин) — та же лента
        sig = _sig("key3", src, inn, span, bg, bg_in, os.path.getmtime(src))
        if not _fresh(out, sig): key_fill(src, inn, span, bg, bg_in, out); _done(out, sig, why="зелёные экраны заполнены", bg=bg)
        return out
    if pid == "p1_071":                                             # тизер S1: самолётик мелкий → середина кадра ×2; сток 25 к/с —
        out = "%s/_src/%s_mi.mp4" % (FR, pid)                       # кроп удваивал рывок 5:6 → 30 к/с промежуточными кадрами (mci)
        sig = _sig("mi30crop2", src, inn, span, k, os.path.getmtime(src))
        if not _fresh(out, sig):
            pr = probe(src); W0, H0 = pr["w"] or 1920, pr["h"] or 1080
            fc = ("setpts=(PTS-STARTPTS)/%.4f,minterpolate=fps=%d:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                  "crop=%d:%d:%d:%d,scale=1920:1080:flags=lanczos,setsar=1" % (k, FPS, W0 // 2, H0 // 2, W0 // 4, H0 // 4))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % inn, "-t", "%.3f" % (span / k + 0.2), "-i", src, "-vf", fc,
                            "-an", "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", out], check=True)
            _done(out, sig, why="кроп ×2 середины + 25 → 30 к/с (minterpolate mci): без рывка 5:6, проверка 08.10")
        return out
    if pid == "p2_100":                                             # Artemis I: Земля — точка; отъезд от серпа Земли до точки
        out = "%s/_src/%s_pull.mp4" % (FR, pid); n = int(round(span / k * FPS))
        sig = _sig("pull2", src, inn, span, k, os.path.getmtime(src))
        if not _fresh(out, sig):
            pr = probe(src); W0, H0 = pr["w"] or 1280, pr["h"] or 1024
            ch = int(W0 * 9 / 16) // 2 * 2; cy = int(min(H0 - ch, max(0, H0 * 0.56 - ch / 2)))
            ex, ey = 0.557, (H0 * 0.56 - cy) / ch                       # Земля в долях кадра 16:9
            z = "if(lte(on,%d),5.5-4.3*pow(on/%d,0.6),1.2)" % (n, n)
            fc = ("setpts=(PTS-STARTPTS)/%.4f,fps=%d,crop=%d:%d:0:%d,scale=1920:1080,"
                  "zoompan=z='%s':x='iw*%.4f-iw/zoom/2':y='ih*%.4f-ih/zoom/2':d=1:s=1920x1080:fps=%d"
                  % (k, FPS, W0, ch, cy, z, ex, ey, FPS))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % inn, "-t", "%.3f" % (span + 0.2), "-i", src, "-vf", fc,
                            "-frames:v", str(n + 2), "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", out], check=True)
            _done(out, sig, why="отъезд ×5,5 → ×1,2 от Земли")
        return out
    return None


def key_fill(src, inn, span, bg, bg_in, out):
    """зелёный экран → фон bg: маска зелёного с закрытыми дырками (кресты трекинга), мягкий край"""
    import numpy as np
    from PIL import Image, ImageFilter
    pr = probe(src); w, h = pr["w"], pr["h"]; n = int(round(span * FPS)) + 2

    def frames(f, t0, sw, sh):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t0, "-i", f, "-frames:v", str(n), "-vf",
                              "fps=%d,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (FPS, sw, sh, sw, sh),
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        sz = sw * sh * 3
        return [np.frombuffer(raw[i * sz:(i + 1) * sz], np.uint8).reshape(sh, sw, 3) for i in range(len(raw) // sz)]
    fg, bgf = frames(src, inn, w, h), frames(bg, bg_in, w, h)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h), "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for i, a in enumerate(fg):
        f = a.astype(np.int16); g = (f[..., 1] > f[..., 0] + 60) & (f[..., 1] > f[..., 2] + 60)
        m = Image.fromarray((g * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.MinFilter(11))
        m = np.asarray(m.filter(ImageFilter.GaussianBlur(1.5)), np.float32)[..., None] / 255.0
        b = bgf[min(i, len(bgf) - 1)].astype(np.float32)
        enc.stdin.write((a * (1 - m) + b * m).clip(0, 255).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait()


def unmute_map():
    m = {}
    for u in AP["video_audio"]["unmute"]: m[(u["part"], u["n"])] = float(u.get("volume_db") or 0.0)
    return m


def reversed_src(s):
    """реверс отрезка (frame_shot назад не читает): assets/shots/ep05/framed/_src/<кусок>_rev.mp4"""
    src = s["src"]["file"]; inn = float(s["src"].get("in") or 0); k = float(s.get("speed") or 1)
    span = float(s["dur"]) * k + 0.4
    out = "%s/_src/%s_rev.mp4" % (FR, pid_of(s))
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % inn, "-t", "%.3f" % span, "-i", src, "-an",
                        "-vf", "reverse,fps=%d" % FPS, "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", out], check=True)
    return out


def frame_job(it, unm):
    """кусок с подачей 4A → задание frame_shot (выход assets/shots/ep05/framed/<кусок>.mp4)"""
    s = it["s"]; p = s["presentation"]; src = s["src"]["file"]; slot = it["end"] - it["start"]
    pr = probe(src); img = bool(re.search(r"\.(png|jpe?g|tif|webp)$", src, re.I))
    job = {"kind": p["kind"], "src": src, "dur": round(slot, 4), "chapter": FCH.get(s["chapter"], "none"),
           "out": "%s/%s.mp4" % (FR, it["pid"])}
    if not img:
        k = float(s.get("speed") or 1.0); inn = float(s["src"].get("in") or 0.0)
        if s.get("reverse"):
            job["src"] = reversed_src(s); pr = probe(job["src"]); inn = 0.0; k = float(s.get("speed") or 1.0)
        need = inn + slot * k
        if pr["dur"] and need > pr["dur"] - 0.03:
            new = max(0.0, pr["dur"] - slot * k - 0.05)
            it.setdefault("adj", []).append("in %.2f → %.2f (исходник %.2f с)" % (inn, new, pr["dur"]))
            inn = new
        job["in"] = round(inn, 3)
        if abs(k - 1.0) > 1e-6: job["speed"] = k
        if (s["part"], s["n"]) in unm or (s.get("segment") == "cold_open" and s.get("vaudio")):
            if pr["audio"]: job["audio"] = True
        if p["kind"] in ("tv", "tv_caption") and pr["w"] and pr["w"] / max(1, pr["h"]) < 1.5:
            job.update(crop="auto", fit="contain")                   # 4:3 в кинескопе — целиком, без среза шапки
        if p["kind"] == "film": job["crop"] = "auto"
    if p.get("tag"): job["tag"] = p["tag"]
    if p.get("caption"): job["caption"] = p["caption"]
    if p.get("group"): job["group"] = p["group"]
    ov = s.get("overlay") or {}
    if p["kind"] == "reel_916" and ov.get("kind") == "text" and ov.get("text"):
        job["caption"] = ov["text"]; it["overlay_done"] = True          # плашка рилса — сама рамка
    job.update(fvariant(p.get("variant"), pr))
    if p["kind"] in ("window", "window_916", "photo_corners") and ("маленьк" in (p.get("variant") or "")
                                                                 or (pr["w"] and pr["w"] < 800)):
        job["size"] = 0.42                                          # мелкий исходник — маленькое окно/снимок
    if it["pid"] == "p1_037": job.update(kind="full", look="archival")
    job.update(ovr(it["pid"], pr))
    if not img:
        ps = prep_src(it["pid"], job["src"], float(job.get("in") or 0), slot * float(job.get("speed") or 1) + 0.4,
                      float(job.get("speed") or 1))
        if ps:
            job["src"], job["in"] = ps, 0.0; job.pop("speed", None); job.pop("crop", None)
            if job.get("audio"): job.pop("audio")
    if p["kind"] == "reel_916" and it["pid"] in HANDLES: job["handle"] = HANDLES[it["pid"]]
    return job


def card_clip(it, text, plan):
    return {"kind": "card", "text": text, "plan": plan, "mat": plan.get("mat", "card")}


def short_desc(desc, n=72):
    """суть куска для жёлтой карточки (в плеере кегль крупный): до первого «;» / « — » / « → » после 25 знаков, ≤ n знаков по слову"""
    cut = len(desc)
    inq = lambda k: desc.count("«", 0, k) > desc.count("»", 0, k)           # внутри «…» не режем
    for sep in (";", " — ", " → ", " ("):
        k = desc.find(sep, 25)
        while k > 0 and inq(k): k = desc.find(sep, k + 1)
        if 0 < k < cut: cut = k
    t = desc[:cut].strip(" ,.:")
    if len(t) > n: t = t[:n].rsplit(" ", 1)[0].rstrip(" ,.:") + "…"
    elif cut < len(desc): t += "…"
    return t


def offsets_from_card(desc, it):
    """«(+5,9)» в описании GFX — секунды от начала реплики по плану → секунды от начала карточки (по словам голоса)"""
    line = it["s"]["anchor"].get("line")
    if not line or line not in LTM: return desc

    def rep(m):
        x = float(m.group(1) + "." + m.group(2))
        try: d = warp(ep_line(line, x), line) - it["start"]
        except KeyError: return m.group(0)
        return "(+%s с от начала карточки)" % ("%.1f" % d).replace(".", ",")
    return re.sub(r"\(\+(\d+),(\d+)\)", rep, desc)


def resolve(it, unm, counters):
    """кусок → поля клипа v1 (+ задание рамки)"""
    s = it["s"]; t = s["type"]; src = s["src"].get("file"); p = s.get("presentation") or {}; pid = it["pid"]
    desc = s["desc"]; st = s["src"].get("status")
    base = {"piece": pid, "plan_n": "ч.%d #%d%s" % (s["part"], s["n"], s.get("sub") or "")}
    if t == "nick":
        return dict(base, kind="video", src=src, **{"in": 0.0}, mute=True, mat="nick",
                    text="%s · %s [NICK %s] %s" % (pid, s["anchor"].get("line"), nick_id(s), s["phrase"][:120])), None
    if t in ("3d", "step", "card", "insert3d"):
        exp = s["src"].get("src_dur") if s["src"].get("src_dur_expected") or st == "pending_3d" else None
        slug = s["src"].get("slug") or os.path.basename(src or "").replace("_v1.mp4", "")
        if src and ready3d(src, exp):
            inn, k, note, err = fit3d(it, probe(src)["dur"])
            if s.get("segment") == "teaser" and abs(k - 1) < 1e-6: inn = fr(inn)   # тизер ×1,0: in на кадр — без дублей/пропусков
            it["note3d"] = note; it["sync_err"] = err
            c = dict(base, kind="video", src=src, **{"in": inn}, mute=True, mat="3d" if t != "step" else "step",
                     text="%s · 3D %s %s — %s" % (pid, slug, note, desc[:200]))
            if abs(k - 1) > 1e-6: c["speed"] = k
            return c, None
        src_len = float(s["src"].get("src_dur") or 0) or 10.0
        inn, k, note, err = fit3d(it, src_len)
        it["note3d"] = note; it["sync_err"] = err
        plan = {"mat": "3d" if t != "step" else "step", "wait": "3d", "file": src, "slug": slug, "in": inn, "speed": k,
                "src_len": src_len, "start": it["start"], "raw": it["raw"], "type": t, "full": bool(it.get("full3d"))}
        counters["3d"].append(it)
        return dict(base, **card_clip(it, "3D %s рендерится · ×%.2f · %s" % (slug, k, pid), plan)), None
    if t == "intro":
        return dict(base, kind="video", src=src, **{"in": 0.0}, mute=True, mat="intro", text="%s · %s" % (pid, desc[:200])), None
    if t == "gfx" and s["src"].get("ready") and src and probe(src)["ok"]:   # готовая своя анимация (правка 44: p1_038)
        return dict(base, kind="video", src=src, **{"in": float(s["src"].get("in") or 0.0)}, mute=True, mat="gfx",   # in — тизер S1
                    text="%s · GFX %s — %s" % (pid, os.path.basename(src), desc[:160])), None
    if t in ("gfx", "text") or st in ("todo_gfx", "todo_text") or not src:
        kind = "GFX" if t == "gfx" else ("ТЕКСТ" if t == "text" else t.upper())
        counters["gfx" if t == "gfx" else "text"].append(it)
        plan = {"mat": "gfx", "wait": t, "gfx_id": s["src"].get("gfx_id"), "beat": s["src"].get("beat"), "start": it["start"],
                "full": offsets_from_card(desc, it)}
        return dict(base, **card_clip(it, "%s · %s · %s" % (kind, short_desc(desc), pid), plan)), None
    if (s["src"].get("ready") and src and not re.search(r"\.(png|jpe?g|tif|webp)$", src, re.I) and probe(src)["ok"]
            and s.get("segment") != "cold_open"):
        # готовый ролик с запечённой подачей (тон, наезд, подсветка) — как есть, без рамки и движения; правка 76:
        # p1_037 = assets/shots/ep05/ai/p1_037_hl.mp4 (studio/ep05/gfx/hl_p1_037.py), прежняя картинка — в src.was
        mat = {"real": "real", "pd_film": "archive", "pd_photo": "photo", "cc_photo": "photo", "ai": "ai"}.get(t, "real")
        c = dict(base, kind="video", src=src, **{"in": float(s["src"].get("in") or 0.0)}, mute=True, mat=mat,
                 text="%s · готовый ролик %s — %s" % (pid, os.path.basename(src), desc[:160]))
        if s.get("credit"): c["credit"] = s["credit"]
        if (s["src"].get("was") or {}).get("ai_cycle"):              # правка 77 (p1_041): прежняя картинка занимала шаг
            counters["ai_i"] += 1                                    # цикла AI_MOVES — у следующих картинок ход не сдвигается
        return c, None
    if p.get("kind") in FRAMED or pid == "p1_037":
        if s.get("segment") == "cold_open":                          # правки 37–41: всё — на экране одного ТВ (своя сборка)
            out = "%s/%s.mp4" % (FR, pid)
            how = {"p1_001": "ТВ включается", "p1_026": "кинескоп гаснет на экране того же ТВ"}.get(
                pid, "лента рилсов на экране ТВ" if p.get("kind") == "reel_916" else "канал на экране ТВ, переключение — помеха")
            mat = {"pd_film": "archive"}.get(t, "real")
            c = dict(base, kind="video", src=out, **{"in": 0.0}, mute=True, mat=mat, text="%s · %s (%s)" % (pid, desc[:160], how))
            if s.get("credit"): c["credit"] = s["credit"]
            job = {"composite": pid}
            if p.get("kind") == "reel_916":                          # рилс в нашем интерфейсе (frame_shot) — содержимое экрана
                rj = frame_job(it, unm); rj["out"] = "%s/_tv/%s.mp4" % (FR, pid); job["content_job"] = rj
            return c, job
        job = frame_job(it, unm)
        mat = {"real": "real", "pd_film": "archive", "pd_photo": "photo", "cc_photo": "photo", "ai": "ai"}.get(t, "real")
        c = dict(base, kind="video", src=job["out"], **{"in": 0.0}, mute=True, mat=mat,
                 text="%s · %s · %s — %s" % (pid, p["kind"], os.path.basename(src), desc[:160]))
        if (s["part"], s["n"]) in unm:
            c["mute"] = False; c["volume_db"] = unm[(s["part"], s["n"])]
        if s.get("credit"): c["credit"] = s["credit"]
        if pid in GRID:                                              # стопка «лист в клетку» вместо окна (frame_style.json)
            gf = "%s/%s.mp4" % (GRID_DIR, pid)
            pg, pw = probe(gf), probe(job["out"])
            if pg["ok"] and (not pw["ok"] or abs(pg["dur"] - pw["dur"]) < 0.05):
                c["src"] = gf; it["grid"] = True
                c["text"] = "%s · стопка (%s) · %s — %s" % (pid, p["kind"], os.path.basename(src), desc[:160])
            else:
                log("%s: стопка %s — %s, стоит окно framed/" % (pid, gf, "нет файла" if not pg["ok"] else
                                                                 "длина %.3f ≠ %.3f" % (pg["dur"], pw["dur"])))
        return c, job
    if t in ("ai", "pd_photo", "cc_photo") or re.search(r"\.(png|jpe?g)$", src or "", re.I):
        mv = (s.get("motion") or {})
        k = mv.get("kind") or "zoom_in"
        if mv.get("move") in AI_MOVES:                                # ход цикла закреплён (правка 73: вытесненный AI p2_048
            m = mv["move"]; counters["ai_i"] += 1                     # сдвинул бы цикл у 7 следующих картинок) — счётчик идёт дальше
        elif k in ("pan_lr", "pan") or "left_to_right" in str(mv.get("dir")): m = "pan_right"
        elif k == "zoom_out": m = "zoom_out"
        elif mv.get("focus") or mv.get("to") or abs(float(mv.get("amount") or 0.06) - 0.06) > 1e-3: m = "zoom_in"
        else: m = AI_MOVES[counters["ai_i"] % len(AI_MOVES)]; counters["ai_i"] += 1
        return dict(base, kind="image", src=src, motion=m, mat="ai" if t == "ai" else "photo",
                    text="%s · %s %s — %s" % (pid, t.upper(), os.path.basename(src), desc[:160])), None
    # видео без рамки
    c = dict(base, kind="video", src=src, **{"in": float(s["src"].get("in") or 0)}, mute=True, mat="real",
             text="%s · %s — %s" % (pid, os.path.basename(src), desc[:160]))
    if abs(float(s.get("speed") or 1) - 1) > 1e-6: c["speed"] = float(s["speed"])
    return c, None


# ------------------------------------------------------------------ дорожка «Кадры»
def build_v1():
    items = layout(plan_pieces())
    unm = unmute_map()
    counters = {"3d": [], "gfx": [], "text": [], "ai_i": 0}
    clips, jobs, comps = [], [], []
    for it in items:
        c, job = resolve(it, unm, counters)
        c.update(id=it["pid"], track="v1", shot=it["s"]["anchor"].get("line") or it["pid"], chapter=chapter_at(it["start"]),
                 start=it["start"], dur=round(it["end"] - it["start"], 6), transition="cut", fit="fill")
        c.setdefault("motion", "static")
        if it.get("hold"): c["dur"] = round(c["dur"], 6)
        if job and "composite" in job:
            comps.append((it, c))
            if job.get("content_job"): jobs.append(job["content_job"])
        elif job: jobs.append(job); it["job"] = job
        it["clip"] = c
        clips.append(c)
    expand_segs(items, clips)
    split_cover(items, clips, counters)
    for a, b in zip(clips, clips[1:]): a["dur"] = round(b["start"] - a["start"], 6)
    return items, clips, jobs, comps, counters


def expand_segs(items, clips):
    """3D с несколькими скоростями (метки синхрона) → куски того же файла подряд, время файла непрерывно"""
    i = 0
    while i < len(clips):
        it, c = items[i], clips[i]
        sg = it.get("segs3d")
        if not sg or c.get("kind") != "video" or it.get("seg_of"):
            i += 1; continue
        nc, ni = [c], [it]
        for k, g in enumerate(sg[1:], 2):
            c2 = dict(c, id="%s-%d" % (c["id"], k), start=fr(g[0]), text="%s (кусок %d: с %.2f с, ×%.3f)" % (c["text"], k, g[1], g[2]))
            c2["in"] = g[1]
            if abs(g[2] - 1) > 1e-6: c2["speed"] = g[2]
            else: c2.pop("speed", None)
            nc.append(c2); ni.append({"pid": c2["id"], "s": it["s"], "clip": c2, "start": c2["start"], "seg_of": it["pid"]})
        end = it["end"]
        for a, b in zip(ni, ni[1:]): a["end"] = b["start"]
        ni[-1]["end"] = end
        clips[i:i + 1] = nc; items[i:i + 1] = ni
        log("%s: 3D по меткам — %d куска (%s)" % (it["pid"], len(nc), ", ".join("×%.3f" % g[2] for g in sg)))
        i += len(nc)


def split_cover(items, clips, counters):
    """N3s: у Ника три руки (0,917–3,54 с клипа) → врезка cover[0] (shots_p1.json p1_117): src_t0…src_t1 клипа.
    С 08.10 (правка 57) врезка — своя бумажная GFX (cover["with"] = файл .mp4, готовый: in 0, ×1,0) с 0,0 с клипа:
    куска Ника до врезки нет (dur ≤ 0 — не создаём), Ник один раз — после врезки, тем же клипом со своим in.
    Прежняя врезка 3D smoke_detector 19,6 с ×1,2 — запасной путь, если в "with" не файл."""
    for i, c in enumerate(clips):
        cov = (items[i]["s"].get("cover") or [None])[0] if i < len(items) else None
        if not cov or c.get("mat") != "nick": continue
        a, b = fr(c["start"] + cov["src_t0"]), fr(c["start"] + cov["src_t1"])
        end = c["start"] + c["dur"]
        c1 = dict(c, dur=round(a - c["start"], 6))
        sd = "assets/shots/ep05/3d/smoke_detector/smoke_detector_v1.mp4"
        wf = str(cov.get("with") or "")
        if wf.endswith(".mp4") and probe(wf)["ok"] and probe(wf)["dur"] >= b - a - 0.02:   # своя GFX (правка 57)
            mid = dict(c, id=c["id"] + "c", kind="video", src=wf, mat="gfx", start=a, dur=round(b - a, 6), mute=True,
                       text="%s · врезка: своя бумажная GFX %s (будильник 3:00, каракули, штамп NOT A BUG; у Ника три руки)"
                            % (c["id"], os.path.basename(wf)))
            mid["in"] = 0.0; mid.pop("speed", None)
        elif ready3d(sd, 23.9):
            mid = dict(c, id=c["id"] + "c", kind="video", src=sd, mat="3d", start=a, dur=round(b - a, 6), speed=1.2,
                       text="%s · врезка: 3D smoke_detector 19,6 с ×1,2 (у Ника три руки)" % c["id"])
            mid["in"] = 19.6
        else:
            plan = {"mat": "3d", "wait": "3d", "file": sd, "slug": "smoke_detector", "in": 19.6, "speed": 1.2,
                    "src_len": 24.0, "start": a, "raw": a, "type": "3d", "cover": True}
            mid = dict(c, id=c["id"] + "c", start=a, dur=round(b - a, 6), **card_clip(None, "3D smoke_detector рендерится · "
                       "врезка в N3s (три руки) · 19,6 с ×1,2", plan))
            mid.pop("src", None); mid.pop("in", None); mid.pop("mute", None)
            counters["3d"].append({"pid": c["id"] + "c", "start": a, "end": b, "s": {"src": {"slug": "smoke_detector"}},
                                   "note3d": "врезка N3s"})
        c2 = dict(c, id=c["id"] + "b", start=b, dur=round(end - b, 6), text=c["text"] + " (после врезки)")
        c2["in"] = round(b - c["start"], 4)
        it_mid = {"pid": mid["id"], "s": items[i]["s"], "clip": mid, "start": a, "end": b}
        it_c2 = {"pid": c2["id"], "s": items[i]["s"], "clip": c2, "start": b, "end": end}
        if c1["dur"] > 1e-6:
            clips[i:i + 1] = [c1, mid, c2]; items[i:i + 1] = [items[i], it_mid, it_c2]
        else:                                                        # врезка с 0,0 с клипа — нулевого куска Ника нет
            clips[i:i + 1] = [mid, c2]; items[i:i + 1] = [it_mid, it_c2]
        log("N3s разрезан: %.2f–%.2f врезка (%s)%s" % (a, b, {"gfx": "GFX"}.get(mid.get("mat"), "3D") if mid.get("kind") == "video"
                                                      else "карточка", "" if c1["dur"] > 1e-6 else ", Ник до врезки — нет"))
        return


# ------------------------------------------------------------------ холодное начало: всё в ОДНОМ телевизоре (правки 37–41, 07.10)
TVS = "assets/stock/ep05/352355865.mp4"   # ТВ: выкл 0–0,5 с, снег 0,5–1,5, зелёный (136,251,38) с 1,6; камера медленно наезжает
TV_IN, TV_LAST = 0.30, 8.96               # ролик t → сток 0,3 + t (выкл → вспышка 0,48–0,6 → снег → зелёный с 1,48 = ролик 1,18);
                                          # после последнего кадра стока (8,96 с) — он же + тот же наезд цифрой
TV_FIX, TV_RATE = (227.0, 975.0), math.log(1.0129)  # наезд стока: неподвижная точка (низ-лево экрана) и +1,29 %/с (замер 07.10)
TV_SCR = (827.5, 522.5)                   # центр экрана на последнем кадре стока
TV_PUSH = (12.0, 13.4, 1.18)              # камера наезжает на тот же ТВ: 12,0–13,4 с, ×1,18 к центру экрана (центр → к центру кадра)
TV_OFF = (13.4, 13.9, 14.4)               # кинескоп гаснет на экране 13,4–13,9; затемнение в чёрный к 14,3
TV_SW = 3                                 # кадров помехи при переключении канала (у коротких кусков меньше — tv_sw)
TV_GLASS = (17, 20, 23)                   # погасший кинескоп
TVV = "tv1-5"


def tv_sw(n):
    """кадров помехи на переключении куска из n кадров: 3; у коротких кусков ускоряющейся ленты каналов (правка 75,
    0,27–0,10 с) — 2 / 1, чтобы картинка канала успела мелькнуть (у каналов #2–10, ≥ 10 кадров, — как было, 3)"""
    return TV_SW if n >= 9 else (2 if n >= 6 else 1)


SW_MIX = {3: ((1.0, 0.6, 0.25), (0, 0.18, 0.05)), 2: ((1.0, 0.5), (0, 0.12)), 1: ((1.0,), (0,))}   # доля снега, сдвиг «катится»


def tv_view(t):
    """плоскость стока → кадр ролика: (масштаб A, сдвиг bx, by); out = A·p + b"""
    ex = max(0.0, TV_IN + t - TV_LAST)
    s1 = math.exp(TV_RATE * ex); fx, fy = TV_FIX
    b1x, b1y = fx * (1 - s1), fy * (1 - s1)                       # наезд стока, продолженный цифрой
    a0, a1, z = TV_PUSH
    u = min(1.0, max(0.0, (t - a0) / (a1 - a0))); e = u * u * (3 - 2 * u)
    s2 = 1 + (z - 1) * e + 0.02 * max(0.0, t - a1)
    cx, cy = TV_SCR[0] * s1 + b1x, TV_SCR[1] * s1 + b1y           # центр экрана после первого наезда
    tx, ty = cx + (960 - cx) * e, cy + (540 - cy) * e               # и он едет к центру кадра
    A = s1 * s2
    return A, b1x * s2 + tx - cx * s2, b1y * s2 + ty - cy * s2


class Plate:
    """кадры ТВ-стока для отрезка ролика [a, a + n/30): fps 30 от 0,6 + a; после 8,96 с — последний кадр"""
    def __init__(s, a, n):
        import numpy as np
        s.np = np; s.a, s.n, s.i = a, n, 0; s.last = None; s.p = None
        if TV_IN + a < TV_LAST:
            s.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", "%.4f" % (TV_IN + a), "-i", TVS, "-vf", "fps=%d" % FPS,
                                    "-frames:v", str(n + 2), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "8.80", "-i", TVS, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout                 # последний кадр стока (8,96 с)
        n = len(raw) // (1920 * 1080 * 3)
        s.tail = np.frombuffer(raw[(n - 1) * 1920 * 1080 * 3:n * 1920 * 1080 * 3], np.uint8).reshape(1080, 1920, 3)

    def get(s, t):
        if s.p is not None and TV_IN + t < TV_LAST - 0.5 / 25:
            raw = s.p.stdout.read(1920 * 1080 * 3)
            if len(raw) == 1920 * 1080 * 3:
                s.last = s.np.frombuffer(raw, s.np.uint8).reshape(1080, 1920, 3); return s.last
        return s.tail

    def close(s):
        if s.p is not None: s.p.stdout.close(); s.p.wait()


class Feed:
    """содержимое канала: кадры исходника с in, 30 к/с, вырез crop (x, y, w, h в долях) — для экрана"""
    def __init__(s, src, inn, crop=(0.02, 0.02, 0.96, 0.96), n=100000):
        import numpy as np
        s.np = np; pr = probe(src); s.w, s.h = pr["w"], pr["h"]; s.last = None
        cx, cy, cw, ch = crop
        s.cr = (int(s.w * cx) // 2 * 2, int(s.h * cy) // 2 * 2, int(s.w * cw) // 2 * 2, int(s.h * ch) // 2 * 2)
        s.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", "%.4f" % inn, "-i", src, "-vf",
                                "fps=%d,crop=%d:%d:%d:%d" % (FPS, s.cr[2], s.cr[3], s.cr[0], s.cr[1]), "-frames:v", str(n + 2),
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def get(s):
        n = s.cr[2] * s.cr[3] * 3; raw = s.p.stdout.read(n)
        if len(raw) == n: s.last = s.np.frombuffer(raw, s.np.uint8).reshape(s.cr[3], s.cr[2], 3)
        return s.last

    def close(s): s.p.stdout.close(); s.p.wait()


def tv_key(fr_):
    """зелёный экран → альфа (мягкий край, без дыр) и рамка экрана (x0, y0, x1, y1) или None"""
    import numpy as np
    from PIL import Image, ImageFilter
    f = fr_.astype(np.int16); g = f[..., 1] - np.maximum(f[..., 0], f[..., 2])
    a = np.clip((g - 30) / 50.0, 0, 1).astype(np.float32)
    if a.sum() < 5000: return None, None
    m = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(5))   # +1 px наружу
    a = np.asarray(m.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0
    rs, cs = a.sum(1), a.sum(0)
    ry, cx = np.where(rs > 0.3 * rs.max())[0], np.where(cs > 0.3 * cs.max())[0]
    return a, (int(cx[0]), int(ry[0]), int(cx[-1]) + 1, int(ry[-1]) + 1)


def crt_screen(img, w, h, k, seed):
    """кадр канала → экран w×h: cover, строки развёртки, виньетка, чуть приподнятый чёрный, лёгкий сдвиг красного"""
    import numpy as np
    from PIL import Image
    ih, iw = img.shape[:2]; ar = w / h
    if iw / ih > ar: cw = int(ih * ar); x0 = (iw - cw) // 2; img = img[:, x0:x0 + cw]
    else: ch = int(iw / ar); y0 = (ih - ch) // 2; img = img[y0:y0 + ch]
    a = np.asarray(Image.fromarray(np.ascontiguousarray(img)).resize((w, h), Image.BICUBIC), np.float32)
    yy = np.arange(h, dtype=np.float32)[:, None]; xx = np.arange(w, dtype=np.float32)[None, :]
    nx, ny = (xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)
    vig = 1 - 0.24 * np.clip(nx * nx * 0.75 + ny * ny, 0, 2) ** 1.5
    scan = 1 - 0.07 * (0.5 - 0.5 * np.cos(2 * np.pi * yy / 3.0))
    a = (a * 0.93 + 10) * (vig * scan)[..., None]
    a[..., 0] = np.roll(a[..., 0], 1, axis=1)
    return np.clip(a, 0, 255)


def tv_static(w, h, rng):
    """помеха: снег + горизонтальные полосы"""
    import numpy as np
    from PIL import Image
    n = rng.integers(25, 235, (max(2, h // 2), max(2, w // 2))).astype(np.uint8)
    n = np.asarray(Image.fromarray(n).resize((w, h), Image.NEAREST), np.float32)
    band = 0.75 + 0.5 * rng.random(h).astype(np.float32)
    return np.repeat((n * band[:, None])[..., None], 3, 2).clip(0, 255)


def tv_glass(w, h):
    import numpy as np
    yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]; xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    g = np.array(TV_GLASS, np.float32)[None, None, :] * (1.15 - 0.3 * (xx * xx + yy * yy))[..., None]
    hl = np.clip(1 - np.abs((xx + yy * 0.8) + 0.9) / 0.35, 0, 1) * np.clip(1 - (xx * xx + yy * yy) * 0.6, 0, 1) * 9
    return np.clip(g + hl[..., None], 0, 255)


def tv_caption_img(text):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    f = ImageFont.truetype("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", 30)
    w = int(f.getlength(text)) + 40; im = Image.new("RGBA", (w, 46), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sh = Image.new("L", im.size, 0); ImageDraw.Draw(sh).text((22, 36), text, font=f, fill=230, anchor="ls")
    im.paste((0, 0, 0, 255), (0, 0), sh.filter(ImageFilter.GaussianBlur(3)))
    d.rectangle([8, 12, 11, 37], fill=(255, 255, 255, 210))
    d.text((20, 35), text, font=f, fill=(246, 244, 238, 235), anchor="ls")
    return im


def tv_spec(it, by):
    """что показывает экран в куске: (вид, исходник, in, вырез, подпись)"""
    s = it["s"]; pid = it["pid"]; p = s.get("presentation") or {}
    if pid == "p1_001": return ("on", None, 0.0, None, None)
    if pid == "p1_026":                                              # гаснет последний кадр последнего канала (#24)
        last = by.get("p1_024")
        if not last: return ("off", None, 0.0, None, None)
        if (last["s"].get("presentation") or {}).get("kind") == "reel_916":
            return ("off", "%s/_tv/p1_024.mp4" % FR, 0.0, None, None)
        k, lsrc, linn, lcrop, _ = tv_spec(last, by)
        n = int(round((last["end"] - last["start"]) * FPS))
        return ("off", lsrc, round(linn + (n - 1) / FPS, 4), lcrop, None)
    if p.get("kind") == "reel_916": return ("reel", "%s/_tv/%s.mp4" % (FR, pid), 0.0, (0.0, 0.0, 1.0, 1.0), None)
    src = s["src"]["file"]; inn = float(s["src"].get("in") or 0)
    crop = (0.02, 0.02, 0.96, 0.96)
    if pid == "p1_009": crop = (0.0, 0.0, 0.8, 0.8)                 # значок VOA справа внизу — за кадром
    if s["src"].get("tv_crop"): crop = tuple(float(v) for v in s["src"]["tv_crop"])   # вырез (x, y, w, h в долях): вертикальный
    return ("chan", src, inn, crop, p.get("caption") if p.get("kind") == "tv_caption" else None)   # исходник → полоса 4:3


def tv_render(it, c, spec, out):
    """один кусок холодного начала: ТВ-сток (хромакей) + канал на экране; кадры — на абсолютном времени ролика"""
    import numpy as np
    from PIL import Image, ImageFilter
    a0 = c["start"]; n = int(round(c["dur"] * FPS)); kind, src, inn, crop, cap = spec
    rng = np.random.default_rng(int(a0 * 1000) % 9973)
    plate = Plate(a0, n)
    feed = Feed(src, inn, crop, n) if kind in ("chan", "reel") else None
    still = None
    sw = tv_sw(n); mixes, rolls = SW_MIX[sw]
    if kind == "off" and src and os.path.exists(src) and "/_tv/" in src:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout                 # последний кадр последнего рилса
        k = len(raw) // (1920 * 1080 * 3)
        if k: still = np.frombuffer(raw[(k - 1) * 1920 * 1080 * 3:k * 1920 * 1080 * 3], np.uint8).reshape(1080, 1920, 3)[:, 247:1673]
    elif kind == "off" and src and os.path.exists(src):              # правка 75: последний показанный кадр канала #24 (тот же вырез)
        fd = Feed(src, inn, crop or (0.02, 0.02, 0.96, 0.96), 1); still = fd.get(); fd.close()
    capim = tv_caption_img(cap) if cap else None
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-g", "15",
                            "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i in range(n):
        t = a0 + i / FPS
        pl = plate.get(t)
        A, bx, by_ = tv_view(t)
        if abs(A - 1) > 1e-4 or abs(bx) > 0.01 or abs(by_) > 0.01:
            im = Image.fromarray(np.ascontiguousarray(pl)).transform((1920, 1080), Image.AFFINE,
                                                                       (1 / A, 0, -bx / A, 0, 1 / A, -by_ / A), Image.BICUBIC)
            pl = np.asarray(im)
        frame = pl.astype(np.float32)
        img = feed.get() if feed else None                           # кадр канала — каждый кадр (синхрон со звуком), даже без зелёного
        al, box = tv_key(pl)
        if box is not None:
            x0, y0, x1, y1 = box; w, h = x1 - x0, y1 - y0
            gx = frame[..., 1] - np.maximum(frame[..., 0], frame[..., 2])          # зелёная кайма у края стекла → тёмная
            kk = np.clip(gx / 60.0, 0, 1)[..., None]
            frame = frame * (1 - kk) + np.array(TV_GLASS, np.float32) * kk
            scr = None
            if kind == "on":
                scr = tv_static(w, h, rng)
            elif kind in ("chan", "reel"):
                scr = crt_screen(img, w, h, i, 0) if img is not None else tv_static(w, h, rng)
                if kind == "chan" and i < sw:                        # переключение канала: помеха, картинка «катится»
                    mix = mixes[i]; scr = np.roll(scr, int(rolls[i] * h), axis=0)
                    scr = scr * (1 - mix) + tv_static(w, h, rng) * mix
            elif kind == "off":
                tt = t - TV_OFF[0]; scr = tv_glass(w, h)
                if still is not None and tt < 0.27:
                    u = tt / 0.27; hh = max(4, int(h * (1 - u) ** 2.2)); ww = min(w, int(w * (1 + 0.04 * u)))
                    sc = crt_screen(still, w, h, i, 0) * (1 + 2.5 * u) + 255 * u * u
                    sm = np.asarray(Image.fromarray(np.clip(sc, 0, 255).astype(np.uint8)).resize((ww, hh), Image.BILINEAR), np.float32)
                    yy0, xx0 = (h - hh) // 2, (w - ww) // 2; scr[yy0:yy0 + hh, xx0:xx0 + ww] = sm
                elif tt < 0.55:
                    glow = np.zeros((h, w), np.float32)
                    if tt < 0.42:
                        u = (tt - 0.27) / 0.15; ww = max(6, int(w * (1 - u) ** 2)); glow[h // 2 - 2:h // 2 + 2, w // 2 - ww // 2:w // 2 + ww // 2] = 255
                    else:
                        u = (tt - 0.42) / 0.13; r = max(1, int(7 * (1 - u))); glow[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r] = 255 * (1 - u)
                    gl = np.asarray(Image.fromarray(glow.astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)), np.float32)
                    scr = np.clip(scr + (gl * 1.7 + glow * 0.6)[..., None], 0, 255)
            if scr is not None:
                m = al[y0:y1, x0:x1, None]
                frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - m) + scr * m
            if capim is not None and i >= sw:                        # подпись источника под экраном, на корпусе ТВ
                cy = min(1080 - capim.height - 4, y1 + 10)
                fi = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)); fi.paste(capim, (x0 + 4, cy), capim)
                frame = np.asarray(fi, np.float32)
        if kind == "off" and t > TV_OFF[1]:                          # затемнение в чёрный к 14,3
            u = min(1.0, (t - TV_OFF[1]) / max(0.05, TV_OFF[2] - TV_OFF[1] - 0.1)); frame *= (1 - u * u * (3 - 2 * u))
        enc.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait(); plate.close()
    if feed: feed.close()


def composites(comps, items):
    """холодное начало: каждый кусок — свой файл того же ТВ (время стока и наезд — по абсолютному времени ролика)"""
    by = {it["pid"]: it for it in items}
    for it, c in sorted(comps, key=lambda x: x[1]["start"]):
        spec = tv_spec(it, by); out = c["src"]
        dep = [TVS] + ([spec[1]] if spec[1] and os.path.exists(spec[1]) else [])
        sig = _sig(TVV, it["pid"], round(c["start"], 4), round(c["dur"], 4), spec, TV_IN, TV_PUSH, TV_OFF, TV_SW, TV_GLASS,
                   [round(os.path.getmtime(f), 2) for f in dep])
        if _fresh(out, sig): continue
        if spec[0] == "reel" and not os.path.exists(spec[1]): print("нет рилса", spec[1], "— сначала --frames"); continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tv_render(it, c, spec, out)
        _done(out, sig, how="ТВ 352355865 + экран: %s" % spec[0], content=spec[1], in_=spec[2])
        print("ТВ", it["pid"], spec[0], out)


# ------------------------------------------------------------------ 3D со скоростью ≠ 1,0 → готовый файл точной длины (правка 48, 07.10)
# Плеер и рендер при нецелой скорости берут кадры через раз / дублируют (×1,2 — пропуск каждого 6-го кадра: рывок на быстром
# движении), а 47 Мбит/с исходника тяжелы для плеера. Здесь отрезок [in, in + dur·k] пересчитывается на 30 к/с с интерполяцией
# движения (minterpolate mci) → клип ×1,0, in 0; поле "retime" хранит исходник и карту «время исходника → время клипа» (звуки 3D).
RT_V = "rt3"
RT_DONE = []
RT_SKIP_TEASER = False                    # тизер S1 (правки 51, 52): 3D/GFX там ×1,0; если где-то ×≠1 — тоже готовый файл ×1,0
SRC_FIX = {"assets/shots/ep05/3d/ladder_zoom/ladder_zoom_v1.mp4":
           [(341, 348, "страница на перевороте «прыгает назад» (второй переворот с середины): кадры 341–348 вырезаны, стык 340 → 349")]}
MI = "minterpolate=fps=%d:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" % FPS


def teaser_span():
    t0 = TL["lines"]["T"]["start"] - 0.5; t1 = SEG["book_close"]["start"]
    return t0, t1


def rt_plan(c):
    """→ (исходник, отрезок в «исправленном» времени [t0f, t1f], скорость, карта [[t_исх, τ]...], вырезы) для клипа c"""
    src, inn, k, dur = c["src"], float(c.get("in") or 0), float(c.get("speed") or 1), c["dur"]
    cuts = [(a, b) for a, b, _ in SRC_FIX.get(src, [])]
    rm = lambda t: sum((b - a + 1) / FPS for a, b in cuts if (b + 1) / FPS <= t + 1e-9)
    L = probe(src)["dur"]
    t1 = min(inn + dur * k, L)
    t0f, t1f = inn - rm(inn), t1 - rm(t1)
    clipped = inn + dur * k > L - 1e-3                          # хвост за концом файла — стоп-кадр (tpad), скорость не меняем
    keff = k if (clipped or not cuts) else (t1f - t0f) / dur    # вырезанный брак — равномерно на весь клип (события после выреза на месте)
    mp = [[round(inn, 4), 0.0]]
    for a, b in cuts:
        if inn < a / FPS < t1:
            ta = a / FPS; mp.append([round(ta, 4), round((ta - rm(ta) - t0f) / keff, 4)])
            tb = (b + 1) / FPS; mp.append([round(tb, 4), round((tb - rm(tb) - t0f) / keff, 4)])
    mp.append([round(t1, 4), round((t1f - t0f) / keff, 4)])
    return src, t0f, t1f, keff, mp, [c_ for c_ in cuts if inn < c_[0] / FPS < t1]


def rt_smooth(path):
    """ровность движения: разница соседних кадров; дубль (≈0 при движении) и скачок (> 2,2× соседей) — число"""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=320:180", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    n = len(raw) // (320 * 180)
    if n < 3: return {"frames": n}
    a = np.frombuffer(raw, np.uint8).reshape(n, 180, 320).astype(np.float32)
    d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    dup = jump = 0
    for i in range(len(d)):
        nb = np.median(np.concatenate([d[max(0, i - 3):i], d[i + 1:i + 4]])) if len(d) > 1 else d[i]
        if nb > 1.0 and d[i] < 0.15 * nb: dup += 1
        if nb > 1.0 and d[i] > 2.2 * nb: jump += 1
    return {"frames": n, "dup": dup, "jump": jump, "diff_med": round(float(np.median(d)), 2), "diff_max": round(float(d.max()), 2)}


def rt_sig(c, exact=False):
    """подпись готового файла: исходник (путь + время изменения — перерендер сцены делает файл устаревшим), отрезок, скорость"""
    src, t0f, t1f, keff, mp, cuts = rt_plan(c)
    a = [RT_V, src, round(t0f, 4), round(t1f, 4), round(keff, 5), int(round(c["dur"] * FPS)), cuts, os.path.getmtime(src)]
    return _sig(*(a + ["exact"] if exact else a))


def rt_cont(v1):
    """клипы-продолжения (правка 61): тот же исходник и та же скорость, время файла непрерывно с предыдущим клипом, in — между
    кадрами исходника. -ss отдаёт первым ближайший кадр ПОСЛЕ in (STARTPTS обнуляет) → фаза уезжает до кадра и на стыке
    шаг ×1,7; для них кадр 0 = ровно in (exact). Остальные клипы — прежней подписью (кэш не сбрасывается)."""
    out = set()
    for p, c in zip(v1, v1[1:]):
        if c.get("kind") != "video" or p.get("kind") != "video" or c.get("mat") not in ("3d", "step"): continue
        if p.get("piece") != c.get("piece") or p.get("src") != c.get("src"): continue
        kp, kc, inn = float(p.get("speed") or 1), float(c.get("speed") or 1), float(c.get("in") or 0)
        if abs(kp - kc) > 1e-4 or abs(float(p.get("in") or 0) + (c["start"] - p["start"]) * kp - inn) > 0.25 / FPS: continue
        if abs(inn * FPS - round(inn * FPS)) > 1e-3: out.add(c["id"])
    return out


def retime_3d(c, exact=False):
    """готовый файл клипа 3D ×1,0: assets/shots/ep05/3d/<сцена>/_retime/<клип>.mp4 (кэш по подписи) → путь, карта, проверка"""
    src, t0f, t1f, keff, mp, cuts = rt_plan(c)
    n = int(round(c["dur"] * FPS))
    out = os.path.join(os.path.dirname(src), "_retime", "%s.mp4" % c["id"])
    sig = rt_sig(c, exact)
    if _fresh(out, sig): return out, mp, jl(out + ".json").get("smooth")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if exact and not cuts:                                       # продолжение (правка 61): исходник с начала файла (pts = время
        P = (math.ceil(0.3 / keff * FPS) + 1) / float(FPS)     # исходника), in ложится на кадр сетки P выхода minterpolate
        vf = ("trim=start=%.4f:end=%.4f,setpts=(PTS-%.6f/TB)/%.6f,%s,trim=start=%.6f,setpts=PTS-STARTPTS,"
              "tpad=stop_mode=clone:stop_duration=1" % (max(0.0, t0f - 0.3), t1f + 0.3, t0f - P * keff, keff, MI, P - 0.5 / FPS))
        args = ["-i", src]
    elif cuts:                                                   # вырез брака: кадры по номеру — читаем с начала файла
        sel = "+".join("between(n,%d,%d)" % (a, b) for a, b in cuts)
        vf = ("select='not(%s)',setpts=N/%d/TB,trim=start=%.4f:end=%.4f,setpts=(PTS-STARTPTS)/%.6f,%s,tpad=stop_mode=clone:stop_duration=1"
              % (sel, FPS, t0f, t1f + 0.2, keff, MI))
        args = ["-i", src]
    else:
        vf = "setpts=(PTS-STARTPTS)/%.6f,%s,tpad=stop_mode=clone:stop_duration=1" % (keff, MI)
        args = ["-ss", "%.4f" % t0f, "-t", "%.4f" % (t1f - t0f + 0.2), "-i", src]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-an", "-vf", vf, "-frames:v", str(n), "-r", str(FPS), "-c:v", "libx264",
                    "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p", "-g", "30", "-movflags", "+faststart", out], check=True)
    sm = rt_smooth(out)
    _done(out, sig, src=src, speed_was=c.get("speed"), keff=round(keff, 5), cuts=[list(x) for x in cuts], map=mp, smooth=sm,
          exact=bool(exact and not cuts), src_mtime=os.path.getmtime(src),
          why="правка 48: 3D ×%.3f → готовый файл ×1,0 (minterpolate mci), без пропусков и дублей кадров" % float(c.get("speed") or 1)
          + ("; правка 61: продолжение предыдущего куска, кадр 0 = ровно in %.4f" % t0f if exact and not cuts else ""))
    return out, mp, sm


RT_IN_TOL = 0.125 / FPS                   # 08.10 (вставка N7s): сдвиг голоса не кратный 0,001 с → слова в words_ep округлены по-
_RT_PREV = {}                              # другому → in 3D «дрожит» на доли мс; ≤ 1/8 кадра — готовый файл тот же, без пересчёта


def rt_reuse(c, exact=False):
    """готовый файл ×1,0 устарел только из-за дрожания in (≤ RT_IN_TOL) от округления времени слов: тот же исходник (и его
    время изменения), скорость и число кадров, что у клипа в текущем проекте → берём прежний in, файл не пересчитываем.
    → True, если in заменён (подпись с прежним in совпала с записанной)"""
    out = os.path.join(os.path.dirname(c["src"]), "_retime", "%s.mp4" % c["id"])
    if not (os.path.exists(out) and os.path.exists(out + ".json")): return False
    if not _RT_PREV:
        try: _RT_PREV.update({p["id"]: p for p in jl("projects/%s/project.json" % PID)["clips"] if p.get("retime")})
        except (OSError, ValueError): _RT_PREV["-"] = None
    r = (_RT_PREV.get(c["id"]) or {}).get("retime") or {}
    if r.get("src") != c["src"] or r.get("in") is None or abs(float(r.get("speed") or 1) - float(c.get("speed") or 1)) > 1e-6: return False
    if abs(float(r["in"]) - float(c.get("in") or 0)) > RT_IN_TOL: return False
    c2 = dict(c, **{"in": float(r["in"])})
    if rt_sig(c2, exact) != jl(out + ".json").get("sig"): return False
    LOG.append("3D %s: in %.4f → прежний %.4f (дрожание ≤ 1/8 кадра от округления слов) — готовый файл тот же"
               % (c["id"], float(c.get("in") or 0), float(r["in"])))
    c["in"] = float(r["in"])
    return True


def retime_all(v1, render=False, workers=3):
    """клипы 3D (вне тизера) со скоростью ≠ 1,0 → готовые файлы; render=False — только те, что уже готовы (кэш)"""
    from concurrent.futures import ThreadPoolExecutor
    a, b = teaser_span(); sel, todo = [], []
    cont = rt_cont(v1)                                              # правка 61: продолжения — точная фаза
    for c in v1:
        if c.get("kind") != "video" or c.get("mat") not in ("3d", "step"): continue
        k = float(c.get("speed") or 1)
        if abs(k - 1) < 1e-3 and not SRC_FIX.get(c["src"]): continue
        if RT_SKIP_TEASER and a <= c["start"] < b: continue
        src = c["src"]
        out = os.path.join(os.path.dirname(src), "_retime", "%s.mp4" % c["id"])
        if _fresh(out, rt_sig(c, c["id"] in cont)) or rt_reuse(c, c["id"] in cont): sel.append(c)
        elif render or os.path.exists(out):                         # нет файла (--retime) или устарел (исходник перерендерен,
            sel.append(c); todo.append(c)                           # отрезок/скорость сменились) — пересчитать и при --apply
            if not render: LOG.append("3D ×%.3f %s: готовый файл устарел — пересчитан" % (k, c["id"]))
        else: LOG.append("3D ×%.3f %s: готового файла ×1,0 нет (нужен --retime)" % (k, c["id"]))
    if todo:
        print("3D → ×1,0: пересчитываю %d клипов (%.0f с), %d потока" % (len(todo), sum(c["dur"] for c in todo), workers))
        with ThreadPoolExecutor(workers) as ex: list(ex.map(lambda c_: retime_3d(c_, c_["id"] in cont), todo))
    done = []
    for c in sel:
        k = float(c.get("speed") or 1)
        out, mp, sm = retime_3d(c, c["id"] in cont)                 # из кэша
        cuts = [list(x) for x in rt_plan(c)[5]]
        c["retime"] = {"src": c["src"], "in": c.get("in"), "speed": k, "map": mp, "cuts": cuts, "smooth": sm}
        c["src"], c["in"] = out, 0.0; c.pop("speed", None)
        c["text"] += " · ×1,0 готовый файл (был ×%.3f%s)" % (k, ", вырезан брак переворота" if cuts else "")
        done.append((c["id"], k, sm))
    return done


def interp(x, pts):
    """кусочно-линейная карта [[x, y], ...] (за краями — продолжение крайнего отрезка)"""
    if len(pts) == 1: return pts[0][1] + (x - pts[0][0])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1 or (x1, y1) == tuple(pts[-1]):
            return y0 + (y1 - y0) * (x - x0) / max(1e-9, x1 - x0)
    return pts[-1][1]


# ------------------------------------------------------------------ звук: якоря
class Anchors:
    def __init__(s, items, clips):
        s.by_piece = {}
        for it in items:
            sh = it["s"]; key = (sh["part"], sh["n"])
            s.by_piece.setdefault(key, []).append(it["clip"])
        s.v1 = clips

    def piece(s, part, n, at="start"):
        cs = s.by_piece.get((part, n))
        if not cs: raise KeyError("нет куска ч.%d #%d" % (part, n))
        cs = sorted(cs, key=lambda c: c["start"])
        return cs[0]["start"] if at == "start" else cs[-1]["start"] + cs[-1]["dur"]

    def t(s, a):
        k = a["kind"]
        if k == "piece": return s.piece(a["part"], a["n"], a.get("at", "start")) + float(a.get("offset") or 0)
        if k == "line": return ep_line(a["ref"], float(a.get("offset") or 0), a.get("at", "start"))
        if k == "word": return word_time(a["line"], a["text"], int(a.get("nth") or 1), a.get("at", "start")) + float(a.get("offset") or 0)
        if k == "clip": return NICK[a["src"]]["clip_start"] + float(a["t"])
        if k == "3d":
            part, n = a["piece"]; slug = a["src"].split("/")[-1]
            cs = sorted(s.by_piece.get((part, n)) or [], key=lambda c: c["start"])
            best = None
            for c in cs:
                rt = c.get("retime")                              # готовый файл ×1,0 (правка 48): карта «время исходника → клип»
                f = (rt or {}).get("src") or c.get("src") or (c.get("plan") or {}).get("file") or ""
                if slug not in f: continue
                if rt: tt = c["start"] + interp(float(a["t"]), rt["map"])
                else:
                    inn = float(c.get("in") if c.get("kind") == "video" else c["plan"]["in"])
                    k_ = float(c.get("speed") or 1) if c.get("kind") == "video" else float(c["plan"]["speed"])
                    tt = c["start"] + (float(a["t"]) - inn) / k_
                if c["start"] - 0.05 <= tt <= c["start"] + c["dur"] + 0.05: return tt
                if best is None: best = tt
            if best is None: raise KeyError("3D %s: нет клипа куска ч.%d #%d" % (slug, part, n))
            return best
        raise KeyError("якорь %s" % k)


def aclip(cid, track, src, start, dur, inn=0.0, db=0.0, fi=0.0, fo=0.0, loop=False, tag=None, chapter=None):
    c = {"id": cid, "track": track, "src": src, "start": fr(start), "dur": round(max(1.0 / FPS, dur), 4), "in": round(max(0.0, inn), 4),
         "volume_db": round(float(db), 2), "loop": bool(loop)}
    if fi: c["fade_in"] = round(fi, 3)
    if fo: c["fade_out"] = round(fo, 3)
    if tag: c["tag"] = tag[:200]
    if chapter: c["chapter"] = chapter
    return c


def voice_clips():
    out = []
    for sg in TL["segments"]:
        if sg["kind"] != "block": continue
        db = float(AP["levels"].get("teaser_voice_db", 0)) if sg["id"] == "BT" else 0.0
        out.append(aclip("vo-" + sg["id"].replace(":", "-"), "voice", sg["file"], sg["start"], sg["dur"], sg.get("in", 0.0), db,
                         tag="голос %s (файл правки)" % sg["id"], chapter=chapter_at(sg["start"] + 0.5)))
    return out


def file_dur(p):
    pr = probe(p)
    if pr["ok"]: return pr["dur"]
    with wave.open(p) as w: return w.getnframes() / w.getframerate()


DUCK_V = "pad3"     # 08.10: sidechaincompress отдаёт кратно 1024 отсчётам → хвост до 21 мс срезался (tape stop тизера);
                    # теперь входы длиннее на 0,2 с, обрезка до dur — после компрессора


MUSIC_DIP_DB, MUSIC_DIP_RAMP = -5.0, 0.06   # 08.10 ревью: под кругом маркером музыка −5 дБ (рампы 0,06 с) — иначе в паузе между
                                            # словами музыка поднимается (компрессор по голосу отпускает) и круг в ней тонет


def apply_dips(wav, start, dips):
    """приглушения музыки в готовом _ducked/<id>.wav: dips — [(от, до)] в секундах ролика (файл начинается в start)"""
    import numpy as np
    if not dips: return
    with wave.open(wav) as w:
        prm = w.getparams(); x = np.frombuffer(w.readframes(prm.nframes), np.int16).reshape(-1, prm.nchannels).astype(np.float32)
    tt = start + np.arange(len(x)) / prm.framerate
    g = np.ones(len(x), np.float32); k = 10 ** (MUSIC_DIP_DB / 20)
    for a, b in dips:
        r = MUSIC_DIP_RAMP
        d = np.clip(np.minimum((tt - (a - r)) / r, ((b + r) - tt) / r), 0, 1)
        g = np.minimum(g, 1 - (1 - k) * d)
    y = np.clip(x * g[:, None], -32768, 32767).astype(np.int16)
    with wave.open(wav, "wb") as w:
        w.setparams(prm); w.writeframes(y.tobytes())


def tapestop_tail(wav, L):
    """fx tapestop_end (09.10, правка 83): последние L с готового _ducked/<id>.wav — скорость чтения 1 → 0 (тон вниз), в конце
    короткое затухание; копия audio_edits.tapestop (как tape stop тизера) — музыка «садится», а не обрывается"""
    import numpy as np
    with wave.open(wav) as w:
        prm = w.getparams(); x = np.frombuffer(w.readframes(prm.nframes), np.int16).reshape(-1, prm.nchannels).astype(np.float32)
    m = min(len(x) - 1, int(round(L * prm.framerate)))
    if m < 2: return
    i0 = len(x) - m
    u = np.arange(m) / m; v = (1 - u) ** 1.6
    pos = i0 + np.cumsum(v) - v[0]
    seg = np.stack([np.interp(pos, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1)
    seg *= np.clip((1 - u) / 0.15, 0, 1)[:, None]
    x[i0:] = seg
    y = np.clip(x, -32768, 32767).astype(np.int16)
    with wave.open(wav, "wb") as w:
        w.setparams(prm); w.writeframes(y.tobytes())


def ducked(mid, src, m_in, start, dur, duck=None, dips=None, fx=None):
    """кусок трека: вырез 1,2 и 2,6 кГц + приглушение по голосу ролика (voice_full.wav на том же отрезке) → _ducked/<id>.wav;
    duck — свои параметры компрессора из audio_plan (например release: m-teaser держит приглушение через паузы S1 0,12–0,16 с);
    fx — обработка готового файла: {"tapestop_end": L} — tape stop последних L с (правка 83, 09.10)"""
    os.makedirs(DUCK, exist_ok=True)
    out = "%s/%s.wav" % (DUCK, mid); side = out + ".json"
    key = B + "/voice_full.wav"
    dk = dict({"threshold": 0.04, "ratio": 2.5, "attack": 25, "release": 450}, **(duck or {}))
    dips = [(round(a, 3), round(b, 3)) for a, b in (dips or []) if b > start and a < start + dur]
    sig = hashlib.sha1(json.dumps([src, round(m_in, 3), round(start, 3), round(dur, 3), os.path.getmtime(key),
                                   os.path.getmtime(src), DUCK_V, sorted(dk.items())]
                                  + ([dips, MUSIC_DIP_DB, MUSIC_DIP_RAMP] if dips else [])
                                  + ([sorted(fx.items())] if fx else [])).encode()).hexdigest()[:12]
    if os.path.exists(out) and os.path.exists(side) and jl(side).get("sig") == sig: return out
    tlen = file_dur(src)
    # петля — только если трек правда короче куска; хвост в пределах кадра (конец «до конца файла», m-teaser) — тишина,
    # иначе в последние мс попадало начало трека заново (08.10: −0,3 после tape stop)
    loop = ["-stream_loop", "-1"] if m_in + dur > tlen + 0.05 else []
    pad = dur + 0.2
    fc = ("[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:%.3f[key];"
          "[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:%.3f,"
          "equalizer=f=1200:t=q:w=1.0:g=-2.5,equalizer=f=2600:t=q:w=1.1:g=-5[m];"
          "[m][key]sidechaincompress=threshold=%g:ratio=%g:attack=%g:release=%g:knee=4:makeup=1,atrim=0:%.6f[o]"
          % (pad, pad, dk["threshold"], dk["ratio"], dk["attack"], dk["release"], dur))
    subprocess.run(["ffmpeg", "-v", "error", "-y", *loop, "-ss", "%.3f" % m_in, "-t", "%.3f" % dur, "-i", src,
                    "-ss", "%.3f" % max(0.0, start), "-t", "%.3f" % dur, "-i", key, "-filter_complex", fc, "-map", "[o]",
                    "-c:a", "pcm_s16le", out], check=True)
    apply_dips(out, start, dips)
    if fx and float(fx.get("tapestop_end") or 0) > 0: tapestop_tail(out, float(fx["tapestop_end"]))
    json.dump({"sig": sig, "src": src, "in": m_in, "start": start, "dur": dur, "duck": dk, "v": DUCK_V,
               **({"dips": dips, "dip_db": MUSIC_DIP_DB} if dips else {}), **({"fx": fx} if fx else {})},
              open(side, "w"), ensure_ascii=False)
    return out


def music_clips(A, render=False, dips=None):
    out, notes = [], []
    for m in AP["music"]:
        start = A.t(m["anchor"]); inn = m.get("in")
        if inn is None and m.get("sync"):
            t_sync = A.t(m["sync"]["at"]); inn = float(m["sync"]["track_t"]) - (t_sync - start)
            if m.get("snap_start") == "beat" and m.get("grid"):
                g = m["grid"]; inn = g["b0"] + round((inn - g["b0"]) / g["beat"]) * g["beat"]; start = t_sync - (m["sync"]["track_t"] - inn)
            if inn < float(m.get("clamp_in_min", -1e9)):
                start += float(m["clamp_in_min"]) - inn; inn = float(m["clamp_in_min"])
        inn = float(inn or 0.0)
        ea = m.get("end_anchor")
        if ea and ea.get("kind") == "file_end": end = start + file_dur(m["src"]) - inn
        elif ea: end = A.t(ea)
        else: end = start + float(m.get("dur") or 0)
        start, end = fr(start), fr(end)
        if end - start < 0.1:
            notes.append("%s: пустой отрезок %.2f–%.2f" % (m["id"], start, end)); continue
        src, sin = m["src"], inn
        if m.get("mode") == "ducked":
            if render or os.path.exists("%s/%s.wav" % (DUCK, m["id"])):
                src = ducked(m["id"], m["src"], inn, start, end - start, m.get("duck"), dips, m.get("fx")) if render \
                    else "%s/%s.wav" % (DUCK, m["id"])
                sin = 0.0
            else:
                notes.append("%s: приглушённый файл не собран (--audio) — пока исходник" % m["id"])
        # обрывы: клип режется, время трека идёт дальше
        cuts = []
        for d in m.get("drops") or []:
            a = A.t(d["from"]); b = A.t(d["to"]) if d.get("to") else a + float(d["dur"])
            if b > a: cuts.append((fr(a), fr(b), float(d.get("fade_out") or 0.1), float(d.get("fade_in") or 0.2)))
        cuts.sort()
        segs, cur, fi = [], start, float(m.get("fade_in") or 0)
        for a, b, dfo, dfi in cuts:
            if not (start < a < end): continue
            segs.append((cur, a, fi, dfo)); cur, fi = min(b, end), dfi
        segs.append((cur, end, fi, float(m.get("fade_out") or 0)))
        for k, (a, b, f_in, f_out) in enumerate(segs):
            if b - a < 0.05: continue
            cid = m["id"] if k == 0 else "%s-%d" % (m["id"], k + 1)
            out.append(aclip(cid, "music", src, a, b - a, sin + (a - start), m.get("volume_db", 0), f_in, f_out,
                             tag=("музыка: " + m.get("why", ""))[:200], chapter=chapter_at(a + 0.1)))
    return out, notes


def hl_done(part, n):
    """выделение 5A куска нарисовано (поле highlight.done в shots_p*.json ставит тот, кто его сделал)"""
    s = next((x for x in S1 + S2 if x["part"] == part and x["n"] == n and x.get("highlight")), None)
    return bool(s and s["highlight"].get("done"))


def term_done(part, n):
    """вырезка-термин 6A куска есть в кадре (overlay kind term со статусом не todo_*; 08.10 — ещё нигде нет)"""
    s = next((x for x in S1 + S2 if x["part"] == part and x["n"] == n and (x.get("overlay") or {}).get("kind") == "term"), None)
    return bool(s and not str(s["overlay"].get("status") or "todo").startswith("todo"))


def sfx_clips(A, items, prio=("A", "B")):
    out, notes, seen = [], [], set()
    vids = {it["pid"]: it for it in items}
    for e in AP["sfx"] + AP["ambience"]:
        if e.get("prio", "A") not in prio: continue
        m = re.match(r"hl-[a-z](\d)-(\d+)$", e["id"])
        if m and not hl_done(int(m.group(1)), int(m.group(2))):         # звук мелка/скотча без самого выделения — нет
            notes.append("%s: выделение 5A не нарисовано — звук не ставлю" % e["id"]); continue
        m = re.match(r"term-(\d)-(\d+)$", e["id"])
        if m and not term_done(int(m.group(1)), int(m.group(2))):       # шлепок вырезки-термина без самой вырезки — нет (08.10)
            notes.append("%s: вырезки-термина 6A в кадре нет — звук не ставлю" % e["id"]); continue
        try:
            start = A.t(e["anchor"])
        except KeyError as x:
            notes.append("%s: %s" % (e["id"], x)); continue
        src, inn, dur = e["src"], e.get("in", 0.0), e.get("dur")
        if src == "as_piece_video":
            a = e["anchor"]; pid = "p%d_%03d" % (a["part"], a["n"]); it = vids.get(pid)
            if not it: notes.append("%s: нет куска %s" % (e["id"], pid)); continue
            src = it["s"]["src"]["file"]; inn = float(it["job"]["in"] if it.get("job") else it["s"]["src"].get("in") or 0)
            dur = it["end"] - it["start"]
        if e.get("end_anchor"):
            try: dur = A.t(e["end_anchor"]) - start
            except KeyError as x: notes.append("%s: конец %s" % (e["id"], x)); continue
        if not src or not os.path.exists(src): notes.append("%s: нет файла %s" % (e["id"], src)); continue
        cid = e["id"]
        while cid in seen: cid += "+"
        seen.add(cid)
        out.append(aclip(cid, e.get("track", "sfx2"), src, start, float(dur or 0.5), float(inn or 0), e.get("volume_db", 0),
                         e.get("fade_in", 0), e.get("fade_out", 0), loop=e.get("loop", False),
                         tag=(e.get("why") or "")[:200], chapter=chapter_at(start + 0.05)))
    return out, notes


def frame_event_clips(items, music=None):
    """звуки рамок 4A: события из <рамка>.json (бирка, фото, скотч, булавка, свайп)"""
    fe = AP["frame_events"]; out = []
    for it in items:
        job = it.get("job")
        if not job or it.get("grid"): continue                      # у стопки свои звуки — grid_event_clips
        side = job["out"] + ".json"
        if not os.path.exists(side): continue
        try: ev = jl(side).get("events") or []
        except ValueError: continue
        for k, e in enumerate(ev):
            cfg = fe.get(e.get("sfx"))
            if not cfg or not os.path.exists(cfg["src"]): continue
            t = it["start"] + float(e.get("t") or 0)
            if t >= it["end"] - 0.02: continue
            out.append(aclip("fe-%s-%d" % (it["pid"], k), "sfx2", cfg["src"], t, cfg["dur"], cfg.get("in", 0), cfg["volume_db"],
                             fo=0.02, tag="рамка: " + e["sfx"], chapter=it["clip"]["chapter"]))
    return out + grid_event_clips(items, music)


# Громкость звуков стопки (08.10, правило как у H2 — audio_plan._h2_level): база — gain_db движка; в своём самом громком
# окне 100 мс (K) звук ≥ подложки музыки + GRID_OVER[kind] (иначе тонет: при базе вход фото в среднем на 6 дБ ТИШЕ музыки);
# не громче базы + 12. Голос: окна 100 мс с шагом 1 мс (результат не зависит от того, как легли окна; 08.10 ревью: при
# шаге 10 мс от начала звука запас «≥ 8,4» не воспроизводился при другом выравнивании), в окнах, где звук слышен
# (≥ пик − 20): голос звучит (≥ −25 K) — звук ≤ голос − 8 − запас; край слова (−30…−25 K: голос нарастает/спадает за
# 20–30 мс) — ≤ голос − 5 − запас. Вход фото «мягко» — +4 над подложкой, круг маркером — +6. Кэш замеров — grid_levels.json.
GRID_OVER = {"photo_in": 4.0, "circle": 6.0, "photo_in_teaser": -3.0}
# тизер (правка 58, событие "teaser": true): вход фото короткий и тихий — пик ровно на 3 дБ ПОД подложкой музыки тизера
# (отрицательный GRID_OVER: громкость ставится по подложке в обе стороны, не только вверх), предел голоса — как у всех
GRID_UNDER_VOICE, GRID_VOICE_ON, GRID_UP_MAX, GRID_MARGIN = 8.0, -25.0, 12.0, 0.5
GRID_EDGE_ON, GRID_UNDER_EDGE = -30.0, 5.0                           # край слова: голос −30…−25 K → звук на ≥ 5 дБ тише
GRID_STEP = 48                                                       # шаг окон, отсчётов 48 кГц (1 мс)
GRID_LV_VER = "lv3-step1ms-edge-tail"
GRID_LV_CACHE = B + "/grid_levels.json"
_GLV = {}


def _apcm(f, i, d):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.4f" % max(0.0, i), "-t", "%.4f" % d, "-i", f, "-ac", "2", "-ar", "48000",
                        "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2)


def _kwin(x, n_out, s=480):
    """K-уровни окон 100 мс с шагом s отсчётов (по умолчанию 10 мс; ITU-R BS.1770, 48 кГц), ровно n_out окон"""
    import numpy as np
    from scipy.signal import lfilter
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585], x, axis=0)
    y = lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], y, axis=0)
    p = (y ** 2).sum(1); n = 4800
    p = np.pad(p, (0, max(0, (n_out - 1) * s + n - len(p))))
    c = np.concatenate([[0.0], np.cumsum(p, dtype=np.float64)])
    i = np.arange(n_out) * s
    return 10 * np.log10((c[i + n] - c[i]) / n + 1e-12) - 0.691


def grid_level(kind, src, inn, dur, fo, t, base, music, fi=0.0):
    """→ (громкость клипа, заметка): см. GRID_OVER выше. music — клипы дорожки «Музыка» сборки (громкость абсолютная).
    Окна — от 0,1 с до звука до его конца включительно (окно, где хвост звука и начало слова, тоже считается)"""
    import numpy as np
    if not _GLV:
        try: _GLV.update(jl(GRID_LV_CACHE))
        except (OSError, ValueError): _GLV["_"] = 1
    vf = B + "/voice_full.wav"
    mus = [m for m in music if m["start"] < t + dur + 0.1 and m["start"] + m["dur"] > t - 0.1]
    key = hashlib.sha1(json.dumps([kind, src, round(inn, 4), round(dur, 4), fo, fi, round(t, 4), base, os.path.getmtime(vf),
                                   [(m["src"], m["in"], m["start"], m["dur"], m["volume_db"], m.get("fade_in"), m.get("fade_out"),
                                     os.path.getmtime(m["src"])) for m in mus],
                                   GRID_OVER.get(kind), GRID_UNDER_VOICE, GRID_VOICE_ON, GRID_UP_MAX, GRID_MARGIN,
                                   GRID_EDGE_ON, GRID_UNDER_EDGE, GRID_STEP, GRID_LV_VER]).encode()).hexdigest()[:16]
    if key in _GLV: return tuple(_GLV[key])
    pre = 0.1                                                         # окна, которые начинаются до звука и захватывают его начало
    t0 = max(0.0, t - pre); lead = t - t0; L = lead + dur + 0.1        # + окна, захватывающие конец звука
    nw = max(1, int(round((L - 0.1) * 48000 / GRID_STEP)) + 1)
    x = _apcm(src, inn, dur); tt = np.arange(len(x)) / 48000.0
    if fo: x = x * np.clip((dur - tt) / fo, 0, 1)[:, None]
    if fi: x = x * np.clip(tt / fi, 0, 1)[:, None]
    x = np.concatenate([np.zeros((int(round(lead * 48000)), 2), np.float32), x])
    s0 = _kwin(x, nw, GRID_STEP); v = _kwin(_apcm(vf, t0, L + 0.1), nw, GRID_STEP)
    bed = np.zeros((int((L + 0.1) * 48000) + 1, 2), np.float32)
    for m in mus:
        a, b = max(t0, m["start"]), min(t0 + L + 0.1, m["start"] + m["dur"])
        y = _apcm(m["src"], float(m.get("in") or 0) + (a - m["start"]), b - a) * 10 ** (float(m.get("volume_db") or 0) / 20)
        tm = a - m["start"] + np.arange(len(y)) / 48000.0
        if m.get("fade_in"): y = y * np.clip(tm / m["fade_in"], 0, 1)[:, None]
        if m.get("fade_out"): y = y * np.clip((m["dur"] - tm) / m["fade_out"], 0, 1)[:, None]
        i = int(round((a - t0) * 48000)); n = min(len(y), len(bed) - i); bed[i:i + n] += y[:n]
    mb = _kwin(bed, nw, GRID_STEP)
    jm = int(np.argmax(s0)); floor = float(mb[jm] + GRID_OVER.get(kind, 4.0) - s0[jm])
    hear = s0 >= s0.max() - 20
    caps = []
    for on, under in (((v >= GRID_VOICE_ON) & hear, GRID_UNDER_VOICE), ((v >= GRID_EDGE_ON) & (v < GRID_VOICE_ON) & hear, GRID_UNDER_EDGE)):
        if on.any(): caps.append(float((v[on] - under - GRID_MARGIN - s0[on]).min()))
    cap = min(caps) if caps else None
    if GRID_OVER.get(kind, 4.0) < 0: vol = math.floor(floor * 2) / 2   # под подложкой (тизер): и тише, и громче базы
    else: vol = math.ceil(floor * 2) / 2 if floor > base else float(base)
    vol = min(vol, math.floor((base + GRID_UP_MAX) * 2) / 2)
    if cap is not None: vol = min(vol, math.floor(cap * 2) / 2)
    note = "уровень %+.1f → %+.1f дБ (подложка %+.1f K в пике, %s)" % (
        base, vol, float(mb[jm]), "голос: потолок %+.1f" % cap if cap is not None else "без голоса")
    _GLV[key] = [vol, note]
    _GLV.pop("_", None)
    with open(GRID_LV_CACHE, "w", encoding="utf-8") as f: json.dump(_GLV, f, ensure_ascii=False, indent=0)
    return vol, note


def circle_dips(items):
    """[(от, до)] кругов маркером стопки в секундах ролика — под ними приглушается музыка (MUSIC_DIP_DB)"""
    if not GRID or not os.path.exists(GRID_EVENTS): return []
    by = {it["pid"]: it for it in items if it.get("grid") and it.get("clip")}
    out = []
    for e in jl(GRID_EVENTS):
        it = by.get(e.get("piece"))
        if it and e.get("kind") == "circle" and not e.get("muted"):
            t = fr(it["clip"]["start"] + float(e.get("t") or 0)); out.append((t, round(t + float(e.get("dur") or 0.6), 4)))
    return out


def grid_event_clips(items, music=None):
    """звуки стопки «лист в клетку» (grid_events.json, t — от начала куска): вход фото (бумага/скотч) и круг маркером;
    стрелки, подчёркивания, галочки — без звука. Конец звука — до склейки куска (≥ полкадра). Громкость — grid_level()"""
    if not GRID or not os.path.exists(GRID_EVENTS): return []
    by = {it["pid"]: it for it in items if it.get("grid") and it.get("clip")}
    out, nk = [], {}
    for e in jl(GRID_EVENTS):
        it = by.get(e.get("piece"))
        if not it or not e.get("sfx") or not os.path.exists(e["sfx"]) or e.get("muted"): continue   # muted — прореживание движка
        c = it["clip"]; end = c["start"] + c["dur"]
        t = fr(c["start"] + float(e.get("t") or 0))
        dur = round(math.floor((min(float(e.get("dur") or 0.3), end - t - 0.5 / FPS)) * FPS + 1e-6) / FPS, 6)   # на кадры, как сервер
        if dur < 0.08: continue
        k = nk[e["piece"]] = nk.get(e["piece"], -1) + 1
        base = float(e.get("gain_db", -20.0)); vol, note = base, ""
        cid, inn = "ge-%s-%d" % (e["piece"], k), float(e.get("in", 0))
        tag = "стопка: %s — %s" % (e.get("kind"), e.get("why") or "")
        parts = circle_parts(t, dur) if music is not None and e.get("kind") == "circle" else None
        if parts:                                                     # круг через паузу и слово — кусками (см. circle_parts)
            for j, (st_, d_, fi_, fo_, loud) in enumerate(parts):
                v_, n_ = grid_level("circle", e["sfx"], inn + st_, d_, fo_, round(t + st_, 6), base, music, fi=fi_)
                out.append(aclip(cid + ("" if j == 0 else "abcdefg"[j]), "sfx2", e["sfx"], round(t + st_, 6), d_, round(inn + st_, 4),
                                 v_, fi=fi_, fo=fo_, chapter=c["chapter"],
                                 tag=tag + " · кусок %d/%d (%s) · %s" % (j + 1, len(parts), "пауза" if loud else "под голосом", n_)))
            continue
        lk = "photo_in_teaser" if e.get("teaser") and e.get("kind") == "photo_in" else e.get("kind")   # тизер — под музыкой
        if music is not None: vol, note = grid_level(lk, e["sfx"], inn, dur, 0.03, t, base, music)
        out.append(aclip(cid, "sfx2", e["sfx"], t, dur, e.get("in", 0), vol,
                         fo=0.03, tag=tag + (" · " + note if note else ""), chapter=c["chapter"]))
    return out


CIRCLE_GUARD = 0.10


def circle_parts(t, dur):
    """круг маркером длится всю прорисовку (~0,6 с). Если внутри и пауза голоса (≥ 0,15 с), и слово, один уровень на весь
    звук либо тонет в музыке паузы, либо громче слова (08.10 ревью: 4 из 11 кругов под музыкой) → куски: в паузе — над
    музыкой (громкость — grid_level, окна захватывают и края слов), под словом — под голосом; стык — перекрытие 0,05 с,
    звук паузы гаснет/нарастает за 0,05 с у слова. Голос «есть» — окно 30 мс ≥ −30 K (шаг 5 мс); прогоны короче 0,06 с
    сливаются с соседними. → [(от, длина, fade_in, fade_out, пауза?)] от начала звука или None (одним куском)"""
    import numpy as np
    from scipy.signal import lfilter
    x = _apcm(B + "/voice_full.wav", t, dur)
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585], x, axis=0)
    y = lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], y, axis=0)
    pw = (y ** 2).sum(1); c = np.concatenate([[0.0], np.cumsum(pw, dtype=np.float64)])
    n, st = 1440, 240
    idx = np.arange(0, max(1, len(pw) - n + 1), st)
    on = (10 * np.log10((c[idx + n] - c[idx]) / n + 1e-12) - 0.691) >= GRID_EDGE_ON
    tt = idx / 48000.0 + 0.015
    runs = []                                                         # [от, до, голос?]
    for i in range(len(on)):
        if runs and runs[-1][2] == bool(on[i]): runs[-1][1] = tt[i]
        else: runs.append([tt[i], tt[i], bool(on[i])])
    if not runs: return None
    runs[0][0] = 0.0; runs[-1][1] = dur
    for i in range(len(runs) - 1): runs[i][1] = runs[i + 1][0] = (runs[i][1] + runs[i + 1][0]) / 2
    while len(runs) > 1:                                              # короткие прогоны — к соседям
        k = min(range(len(runs)), key=lambda i: runs[i][1] - runs[i][0])
        if runs[k][1] - runs[k][0] >= 0.06: break
        if k == 0: runs[1][0] = 0.0
        elif k == len(runs) - 1: runs[-2][1] = dur
        else: runs[k - 1][1] = runs[k + 1][1]; runs.pop(k + 1)
        runs.pop(k)
        m = []
        for r in runs:
            if m and m[-1][2] == r[2]: m[-1][1] = r[1]
            else: m.append(r)
        runs = m
    if not any(r[2] for r in runs) or not any((not r[2]) and r[1] - r[0] >= 0.15 for r in runs): return None
    G = CIRCLE_GUARD                                                  # громкий кусок паузы кончается за G до слова (и
    parts = []                                                        # начинается через G после него): окно 100 мс с
    for i, (a, b, voice) in enumerate(runs):                          # хвостом громкого куска почти не задевает слово
        first, last = i == 0, i == len(runs) - 1
        if voice:                                                     # под словом: заходит на G + 0,03 с в соседние паузы
            a2 = a if first else max(0.0, a - G - 0.03); b2 = b if last else min(dur, b + G + 0.03)
            parts.append([a2, b2, 0.0 if first else 0.03, 0.03, False])
        else:
            a2 = a if first else a + G; b2 = b if last else b - G
            if b2 - a2 < 0.12:                                       # пауза короче — без громкого куска (под голосом)
                parts.append([a, b, 0.0 if first else 0.03, 0.03, False]); continue
            parts.append([a2, b2, 0.0 if first else 0.05, 0.03 if last else 0.05, True])
    if not any(p_[4] for p_ in parts): return None
    out = []
    for a, b, fi_, fo_, loud in parts:
        a, b = round(math.floor(a * FPS + 1e-6) / FPS, 6), round(min(dur, math.ceil(b * FPS - 1e-6) / FPS), 6)   # на кадры, как сервер
        if b - a >= 0.08: out.append((a, round(b - a, 4), fi_, fo_, loud))
    return out if len(out) > 1 else None


# ------------------------------------------------------------------ сборка целиком
def build(render_audio=False, sfx_b=False, retime=False):
    items, v1, jobs, comps, counters = build_v1()
    RT_DONE[:] = retime_all(v1, render=retime)
    A = Anchors(items, v1)
    vo = voice_clips()
    mu, mnotes = music_clips(A, render_audio, circle_dips(items))
    sx, snotes = sfx_clips(A, items, ("A", "B") if sfx_b else ("A",))      # B — «по желанию» (план звука)
    fe = frame_event_clips(items, mu)
    return dict(items=items, v1=v1, jobs=jobs, comps=comps, counters=counters, voice=vo, music=mu, sfx=sx, fe=fe,
                notes=mnotes + snotes)


def stubs(R):
    """заглушки по видам"""
    st = {"3D рендерится": [], "GFX": [], "текст": [], "оверлеи и термины": [], "выделения 5A": [], "реплики TTS": [],
          "лестница 12А": 0, "прочее": []}
    for c in R["v1"]:
        if c.get("kind") != "card": continue
        w = (c.get("plan") or {}).get("wait")
        key = "3D рендерится" if w == "3d" else ("GFX" if w == "gfx" else ("текст" if w == "text" else "прочее"))
        st[key].append("%s %s %.1f с — %s" % (c["plan_n"] if "plan_n" in c else c["id"], tc(c["start"]), c["dur"], c["text"][:90]))
    for it in R["items"]:
        s = it["s"]
        if it.get("clip") is None or it.get("seg_of") or it["pid"].endswith(("b", "c")) and it["pid"][:-1] in ("p1_117",): continue
        ov = s.get("overlay") or {}
        if ov and not it.get("overlay_done") and it["pid"] != "p1_117c":
            st["оверлеи и термины"].append("%s %s — %s: %s" % (it["pid"], tc(it["start"]), ov.get("kind", "gfx"),
                                                              (ov.get("text") or ov.get("desc") or "")[:90]))
        h = s.get("highlight") or {}
        if h and not h.get("done"):
            st["выделения 5A"].append("%s %s — %s: %s" % (it["pid"], tc(it["start"]), h.get("kind"), (h.get("what") or "")[:80]))
        v = s.get("voice") or {}
        if v.get("kind") in ("tts", "tts_or_clip"): st["реплики TTS"].append("%s «%s»" % (it["pid"], v.get("text")))
        if s.get("ladder"): st["лестница 12А"] += 1
    return st


def stats(R):
    v1 = R["v1"]; tot = sum(c["dur"] for c in v1)
    by = {}
    for c in v1:
        m = c.get("mat") or "?"
        if c.get("kind") == "card": m = "заглушка " + ((c.get("plan") or {}).get("wait") or "?")
        by[m] = by.get(m, 0.0) + c["dur"]
    return tot, by


def report(R, a=None, b=None):
    v1 = R["v1"]
    tot, by = stats(R)
    print("v1: %d клипов, %.1f с (%s); голос %d, музыка %d, звуки %d (+ рамки %d)" % (len(v1), tot, tc(tot), len(R["voice"]),
          len(R["music"]), len(R["sfx"]), len(R["fe"])))
    print("доли: " + ", ".join("%s %.1f%%" % (k, v / tot * 100) for k, v in sorted(by.items(), key=lambda kv: -kv[1])))
    for c in v1:
        if a is not None and c["start"] + c["dur"] < a: continue
        if b is not None and c["start"] > b: continue
        extra = c.get("src") or ""
        print("  %-9s %8s %5.2f %-6s %-8s %s" % (c["id"], tc(c["start"]), c["dur"], c.get("kind"), c.get("mat"),
                                                 (c["text"] if c.get("kind") == "card" else os.path.basename(extra))[:90]))
    st = stubs(R)
    for k, v in st.items():
        if isinstance(v, list): print("заглушки — %s: %d" % (k, len(v)))
        else: print("заглушки — %s: %d кусков (оверлей поверх)" % (k, v))
    for n in R["notes"][:60]: print("  звук:", n)
    for l in LOG: print("  ·", l)


def save_plan(R):
    st = stubs(R)
    tot, by = stats(R)
    data = {"made": time.strftime("%Y-%m-%d %H:%M:%S"), "total": round(tot, 3), "shares_s": {k: round(v, 2) for k, v in by.items()},
            "v1": R["v1"], "voice": R["voice"], "music": R["music"], "sfx": R["sfx"], "frame_events": R["fe"], "stubs": st,
            "log": LOG, "audio_notes": R["notes"],
            "fit3d": [{"pid": it["pid"], "note": it.get("note3d"), "sync_err": round(it.get("sync_err", 0), 3)}
                      for it in R["items"] if it.get("note3d")]}
    with open(PLAN_OUT, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=1)
    with open(JOBS, "w", encoding="utf-8") as f: json.dump(R["jobs"], f, ensure_ascii=False, indent=1)


def runs_without_real(v1):
    """серии ≥ 3 кусков подряд без реального видео (правило «реальное каждый 3-й кусок»)"""
    out, cur = [], []
    v1 = [c for i, c in enumerate(v1) if i == 0 or c.get("piece") != v1[i - 1].get("piece")]   # куски одной 3D-сцены — один
    for c in v1:
        if c.get("mat") in ("real", "archive"):
            if len(cur) >= 3: out.append(cur)
            cur = []
        else: cur.append(c)
    if len(cur) >= 3: out.append(cur)
    return out


def write_report(R, qc_text, extra=None):
    """сводка сборки (markdown в stdout) — по сборке R и выводу qc_scan"""
    v1 = R["v1"]; tot, by = stats(R); st = stubs(R)
    pct = lambda keys: sum(by.get(k, 0.0) for k in keys) / tot * 100
    L = ["# ep05 · первая сборка в Cutlab — отчёт", "",
         "Собрано `studio/editor/build_ep05.py` (%s). Проект Cutlab **ep05** «%s»." % (time.strftime("%d.%m %H:%M"), TITLE), "",
         "## Коротко",
         "- Длина ролика **%s** (%.2f с), кусков на «Кадрах» %d, склеек в минуту %.1f." % (tc(tot), tot, len(v1), len(v1) / (tot / 60)),
         "- Голос — файлы правки блоков (`block_<B>_edit.wav`, %d клипов), музыка %d клипов, звуки %d + %d от рамок." % (
             len(R["voice"]), len(R["music"]), len(R["sfx"]), len(R["fe"])),
         "- Доли экранного времени: реальное видео %.1f %% (сток %.1f + архив/NASA %.1f), архивные фото и рисунки %.1f %%, "
         "3D готовое %.1f %% + 3D рендерится %.1f %%, AI %.1f %%, Ник %.1f %%, GFX-заглушки %.1f %%, заставки %.1f %%." % (
             pct(["real", "archive"]), pct(["real"]), pct(["archive"]), pct(["photo"]), pct(["3d", "step"]),
             pct(["заглушка 3d"]), pct(["ai"]), pct(["nick"]), pct(["заглушка gfx", "заглушка text"]), pct(["intro"])), ""]
    L += ["## Начала глав", "| глава | начало |", "|---|---|"]
    for c in TL["chapters"]: L.append("| %s | %s |" % (CHAP.get(c["id"], c["id"]), tc(c["start"])))
    L += ["", "## Клипов по типам (дорожка «Кадры»)", "| тип | клипов | с | % |", "|---|---|---|---|"]
    cnt = {}
    for c in v1:
        m = c.get("mat") or "?"
        if c.get("kind") == "card": m = "заглушка " + ((c.get("plan") or {}).get("wait") or "?")
        cnt[m] = cnt.get(m, 0) + 1
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]): L.append("| %s | %d | %.1f | %.1f |" % (k, cnt.get(k, 0), v, v / tot * 100))
    L += ["", "## Заглушки (жёлтые карточки и что поверх ещё не сделано)"]
    for k, v in st.items():
        if isinstance(v, list):
            L.append("### %s — %d" % (k, len(v)))
            L += ["- " + x for x in v]
        else:
            L.append("### %s — %d кусков с пометкой ladder (оверлей человечка YOU на лестнице в углу, файла нет)" % (k, v))
    L += ["", "## 3D: скорость и синхрон", "| кусок | как стоит |", "|---|---|"]
    for it in R["items"]:
        if it.get("note3d"): L.append("| %s | %s |" % (it["pid"], it["note3d"]))
    rw = runs_without_real(v1)
    L += ["", "## «Реальное видео каждый 3-й кусок»: серии ≥ 3 кусков без реального видео — %d" % len(rw)]
    for r in rw:
        L.append("- %s–%s: %s" % (tc(r[0]["start"]), tc(r[-1]["start"] + r[-1]["dur"]), ", ".join("%s(%s)" % (c["id"], c.get("mat") if c.get("kind") != "card" else "карточка") for c in r)))
    L += ["", "## qc_scan", "```", qc_text.strip(), "```", ""]
    if extra: L += extra
    L += ["", "## Журнал сборщика"] + ["- " + x for x in LOG]
    if R["notes"]: L += ["", "## Звук: замечания"] + ["- " + x for x in R["notes"]]
    print("\n".join(L))


def make_sheet(mp4, out, step=3.0, t0=0.0, cols=6, tw=384):
    """лист кадров превью: кадр каждые step с, подпись — время и кусок (по build_plan.json)"""
    from PIL import Image, ImageDraw, ImageFont
    th = tw * 9 // 16; cap = 22
    pl = jl(PLAN_OUT)["v1"] if os.path.exists(PLAN_OUT) else []
    dur = probe(mp4)["dur"]; ts = []
    t = 0.0
    while t < dur - 0.05: ts.append(t); t += step
    sel = "select='isnan(prev_selected_t)+gte(t-prev_selected_t,%g)',scale=%d:%d" % (step - 0.01, tw, th)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp4, "-vf", sel, "-fps_mode", "vfr", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (tw * th * 3); rows = (n + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * (th + cap + 6) + 6), (18, 18, 18))
    d = ImageDraw.Draw(sh); f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    for i in range(n):
        im = Image.frombytes("RGB", (tw, th), raw[i * tw * th * 3:(i + 1) * tw * th * 3])
        x = 6 + (i % cols) * (tw + 6); y = 6 + (i // cols) * (th + cap + 6)
        sh.paste(im, (x, y))
        tt = t0 + i * step                           # кадры — каждые step с от начала файла
        cid = next((c["id"] + " " + (c.get("mat") or c.get("kind", "")) for c in pl if c["start"] <= tt < c["start"] + c["dur"]), "")
        d.text((x + 3, y + th + 3), "%s  %s" % (tc(tt), cid), font=f, fill=(225, 225, 215))
    sh.save(out, quality=88)
    print("лист:", out, n, "кадров")


def api(path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=300))


def apply(R):
    clips = R["v1"] + R["voice"] + R["music"] + R["sfx"] + R["fe"]
    ids = [c["id"] for c in clips]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup: sys.exit("повтор id: %s" % sorted(dup)[:10])
    projs = api("/projects")["projects"]
    if not any(p["id"] == PID for p in projs):
        r = api("/projects", {"title": TITLE, "id": PID}); print("создан проект", r.get("id"))
    proj = api("/projects/" + PID)
    ops = [{"op": "remove", "id": c["id"], "fill": False} for c in proj["clips"]]
    ops += [{"op": "add", "clip": c, "restore": True} for c in clips]
    r = api("/projects/%s/ops" % PID, {"ops": ops, "client": "claude", "base_revision": proj.get("revision")})
    print("проект %s: ревизия %s, клипов %d" % (PID, r.get("revision"), len(r["project"]["clips"])))


def fill():
    """жёлтые карточки → файл, если 3D отрендерился (или GFX/текст появился в shots_p*.json); остальное не трогаем"""
    proj = api("/projects/" + PID)
    shots = {pid_of(s): s for s in S1 + S2}
    ops, done = [], []
    for c in proj["clips"]:
        pl = c.get("plan")
        if c.get("track") != "v1" or c.get("kind") != "card" or not pl: continue
        if pl.get("wait") == "3d":
            f = pl["file"]
            if not ready3d(f, pl.get("src_len") if pl.get("type") != "card" else 3.9): continue
            L = probe(f)["dur"]; k = float(pl["speed"]); inn = float(pl["in"])
            full = bool(pl.get("full")) and pl.get("type") != "insert3d"
            if full:
                k = min(1.2, max(0.8, (L - inn) / c["dur"]))
            else:
                inn = max(0.0, inn + (c["start"] - float(pl.get("start", c["start"]))) * k)
            fields = {"kind": "video", "src": f, "in": round(inn, 4), "speed": (round(k, 4) if abs(k - 1) > 1e-6 else None),
                      "mute": True, "plan": None, "text": c["text"].replace("рендерится", "готов"), "filled": time.strftime("%d.%m %H:%M")}
            ops.append({"op": "set", "id": c["id"], "fields": fields}); done.append("%s ← %s ×%.3f" % (c["id"], os.path.basename(f), k))
        elif pl.get("wait") in ("gfx", "text"):
            s = shots.get(c.get("piece") or c["id"])
            f = (s or {}).get("src", {}).get("file")
            if f and probe(f)["ok"]:
                ops.append({"op": "set", "id": c["id"], "fields": {"kind": "video", "src": f, "in": 0.0, "mute": True, "plan": None,
                                                                   "filled": time.strftime("%d.%m %H:%M")}})
                done.append("%s ← %s" % (c["id"], f))
    if not ops:
        print("нового материала для карточек нет"); return
    r = api("/projects/%s/ops" % PID, {"ops": ops, "client": "claude", "base_revision": proj.get("revision")})
    print("поставлено %d: ревизия %s" % (len(ops), r.get("revision")))
    for d in done: print("  ", d)


CREDITS = "export/ep05/CREDITS.md"
CRED_HEAD = "## Сверка с монтажом (build_ep05.py --credits)"


def credits_check(R):
    """CREDITS.md ↔ монтаж: какие файлы из списка стоят в проекте (и в каких кусках), каких нет, что стоит без строки.
    Раздел «Сверка с монтажом» в конце CREDITS.md переписывается целиком; остальной текст не трогается"""
    used = {}
    for it in R["items"]:
        if it.get("seg_of"): continue
        f = (it["s"].get("src") or {}).get("file")
        if f and it.get("clip") and it["clip"].get("kind") != "card": used.setdefault(f, []).append(it["s"])
        if it.get("clip") and it["clip"].get("kind") != "card":       # подлинник, вклеенный в свою GFX (src.embeds; правка 73)
            for g in (it["s"].get("src") or {}).get("embeds") or []: used.setdefault(g, []).append(it["s"])
    for e in AP["sfx"]:
        if str(e.get("src", "")).startswith("assets/shots/ep05/archive/"): used.setdefault(e["src"], [])
    txt = open(CREDITS, encoding="utf-8").read().split("\n" + CRED_HEAD)[0].rstrip()
    listed = []
    for ln in txt.splitlines():
        for m in re.finditer(r"`(assets/[^`]+)`", ln):
            if m.group(1) not in listed: listed.append(m.group(1))
    listed = [f for f in listed if not f.endswith("/")]
    sid = lambda f: re.match(r"(\d+)", os.path.basename(f)).group(1) if "/stock/" in f and re.match(r"\d", os.path.basename(f)) else f
    ids = {}
    for f in used: ids.setdefault(sid(f), []).append(f)              # сток: 4K-версии и альфа того же номера — тот же файл
    for f in listed:
        if f not in used and sid(f) in ids: used[f] = sum((used[g] for g in ids[sid(f)]), [])
    lab = lambda ss: ", ".join(sorted({"ч.%d #%d%s" % (x["part"], x["n"], x.get("sub") or "") for x in ss})) or "звук"
    real = lambda f: f.startswith(("assets/stock/", "assets/shots/ep05/archive/"))
    out = ["", CRED_HEAD, "Пересчитывается по сборке (%s). CC-строки в описание — только для файлов из первого списка." % time.strftime("%d.%m %H:%M"), ""]
    no = [f for f in listed if real(f) and f not in used]
    yes = [f for f in listed if f in used]
    lsid = {sid(f) for f in listed}
    extra = sorted(f for f in used if real(f) and f not in listed and sid(f) not in lsid)
    out.append("### В монтаже стоят — %d" % len(yes))
    out += ["- `%s` — %s" % (f, lab(used[f])) for f in yes if "/archive/" in f]
    out.append("- сток Storyblocks: %d файлов" % sum(1 for f in yes if "/stock/" in f))
    out += ["", "### В списке, но в монтаже нет — %d (строки выше оставлены для учёта; в описание не ставить)" % len(no)]
    out += ["- `%s`" % f for f in no]
    out += ["", "### В монтаже, но строки в списке нет — %d" % len(extra)] + ["- `%s` — %s" % (f, lab(used[f])) for f in extra]
    open(CREDITS, "w", encoding="utf-8").write(txt + "\n" + "\n".join(out) + "\n")
    print("CREDITS: стоят %d, нет в монтаже %d, без строки %d" % (len(yes), len(no), len(extra)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--fill", action="store_true")
    ap.add_argument("--frames", action="store_true"); ap.add_argument("--audio", action="store_true")
    ap.add_argument("--tv", action="store_true", help="только холодное начало в ТВ (рилсы уже отрендерены --frames)")
    ap.add_argument("--retime", action="store_true", help="3D ×≠1 вне тизера → готовые файлы ×1,0 (minterpolate), правка 48")
    ap.add_argument("--jobs", type=int, default=4); ap.add_argument("--report", action="store_true")
    ap.add_argument("--sfx-b", action="store_true", help="звуки приоритета B тоже")
    ap.add_argument("--credits", action="store_true", help="сверить CREDITS.md с монтажом")
    ap.add_argument("--from", dest="a", type=float); ap.add_argument("--to", dest="b", type=float)
    ap.add_argument("--sheet", nargs=2, metavar=("MP4", "JPG")); ap.add_argument("--step", type=float, default=3.0)
    a = ap.parse_args()
    if a.sheet:
        make_sheet(a.sheet[0], a.sheet[1], a.step, a.a or 0.0); return
    if a.fill:
        fill(); return
    R = build(render_audio=a.audio, sfx_b=a.sfx_b, retime=a.retime)
    for pid, k, sm in RT_DONE: print("  3D ×%.3f → ×1,0 %-10s %s" % (k, pid, sm))
    save_plan(R)
    report(R, a.a, a.b)
    if a.frames:                                                     # сначала рамки (рилсы холодного начала — содержимое ТВ)
        r = subprocess.run([sys.executable, FS, "--batch", JOBS, "--jobs", str(a.jobs)])
        if r.returncode: print("пакет рамок: есть ошибки (см. %s.report.json)" % JOBS)
        composites(R["comps"], R["items"])
    elif a.tv:
        composites(R["comps"], R["items"])
    if a.apply:
        R["fe"] = frame_event_clips(R["items"], R["music"])
        apply(R)
    if a.credits:
        credits_check(R)
    if a.report:
        R["fe"] = frame_event_clips(R["items"], R["music"])
        q = subprocess.run([sys.executable, "studio/editor/qc_scan.py", "--project", PID], capture_output=True, text=True)
        write_report(R, q.stdout + q.stderr)


if __name__ == "__main__":
    main()
