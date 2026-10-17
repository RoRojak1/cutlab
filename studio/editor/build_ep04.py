#!/usr/bin/env python3
"""ep04 в Cutlab: пилот (холодный старт → тизер → заставка → глава 1). Остальные главы добавляются тем же способом.

Голос — мастер-блоки assets/voice/ep04/block_<B>_master.wav (у B0 — block_B0_edit.wav: +3,4 с тишины на 55,00 под H4a).
Время слов — assets/voice/ep04/line_timings.json. Склейки — за 0,12 с до слова. Сцены Ника — со скоростью k и сдвигом L0
по замеру губ (export/ep04/lipsync/LIPSYNC.md). Материалы берутся из манифестов (реальное видео, графика, доска) и
из готовых 3D/рисунков; чего ещё нет — жёлтая карточка с планом кадра (потом заменяем через «Правки»).

  python3 studio/editor/build_ep04.py            # план и список заглушек
  python3 studio/editor/build_ep04.py --apply    # создать/перезаписать проект ep04 через сервер Cutlab
"""
import json, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8777/api"
TITLE = "How Do Criminals Actually Get Caught?"
FPS = 30
LEAD = 0.12
VO, SH, ST, PD = "assets/voice/ep04", "assets/shots/ep04", "assets/stock/ep04", "assets/stock/ep04/pd"
S4, S3 = "assets/sfx/epidemic/ep04", "assets/sfx/epidemic/ep03"
TIM = json.loads((ROOT / VO / "line_timings.json").read_text())
EN = json.loads((ROOT / "script/ep04_en.json").read_text())["lines"]
MISSING = []


def jload(p):
    p = ROOT / p
    return json.loads(p.read_text()) if p.exists() else {}


MREAL, MGFX, MBOARD = jload("export/ep04/MANIFEST_real.json"), jload("export/ep04/MANIFEST_gfx.json"), jload("export/ep04/MANIFEST_board.json")
MSFX = jload("export/ep04/MANIFEST_sfx.json")          # звуковые стемы под графику, доску и 3D (studio/ep04/gfx_sfx.py)


def fr(t):
    return round(t * FPS) / FPS


def ex(p):
    return (ROOT / p).exists()


def probe(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ROOT / p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def word(block, w, after=0.0, nth=1):
    """начало слова (без знаков) в блоке после времени after; nth — какое по счёту"""
    k = 0
    for t, s, e in TIM["blocks"][block]:
        if s + 1e-6 >= after and "".join(ch for ch in t.lower() if ch.isalnum() or ch == "'") == w:
            k += 1
            if k == nth: return s
    raise KeyError(f"{block}: нет слова {w!r} после {after}")


def cut_at(block, w, after=0.0, nth=1):
    return word(block, w, after, nth) - LEAD


def three_d(slug):
    for f in (f"{SH}/3d/{slug}/{slug}_v1.mp4", f"{SH}/3d/{slug}/{slug}_draft.mp4"):
        if ex(f): return f
    return None


def real(line, i=0):
    items = MREAL.get(line) or []
    if i < len(items) and ex(items[i]["file"]): return items[i]
    return None


def gfx(gid):
    g = MGFX.get(gid)
    return g if g and ex(g["file"]) else None


def board(bid):
    b = MBOARD.get(bid)
    return b if b and ex(b["file"]) else None


# ---------------------------------------------------------------- куски видео
class Seg:
    """кусок дорожки v1 во времени блока: a, b + источник"""
    def __init__(s, a, b, kind, src=None, inp=0.0, speed=1.0, motion="static", text="", transition="cut", line="", stem=None, sound=False):
        s.a, s.b, s.kind, s.src, s.inp, s.speed, s.motion, s.text, s.transition, s.line = a, b, kind, src, inp, speed, motion, text, transition, line
        s.stem, s.sound = stem, sound        # стем звуков под кусок (сдвиг = inp) / звук самого ролика


def V(a, b, src, inp=0.0, speed=1.0, text="", line="", transition="cut"):
    return Seg(a, b, "video", src, inp, speed, text=text or Path(src).stem, line=line, transition=transition)


def I(a, b, src, motion="zoom_in", text="", line=""):
    return Seg(a, b, "image", src, motion=motion, text=text or Path(src).stem, line=line)


def C(a, b, text, line=""):
    MISSING.append(f"{line or '?'}: {text}")
    return Seg(a, b, "card", text=text, line=line)


def from_real(a, b, line, i, plan):
    r = real(line, i)
    if r: return V(a, b, r["file"], r.get("in", 0.0), r.get("speed", 1.0), r.get("note", ""), line)
    return C(a, b, f"{line} · [REAL] {plan}", line)


def from_gfx(a, b, gid, line, plan, inp=None):
    """графика ставится по времени из манифеста (start — время блока, где у ролика 0): если слот раньше — начало сдвигаем
    (предыдущий кусок дотягивается), если позже — пропускаем начало ролика"""
    g = gfx(gid)
    if g:
        if inp is None:
            st = g.get("start")
            if st is not None and st > a: a = min(st, b - 0.5)
            inp = max(0.0, a - st) if st is not None else 0.0
        sg = V(a, b, g["file"], inp, 1.0, f"{gid} · {g.get('note', '')}", line); sg.stem = MSFX.get(gid); return sg
    return C(a, b, f"{line} · [GFX {gid}] {plan}", line)


def from_3d(a, b, slug, inp, line, stem=True):
    f = three_d(slug)
    if f:
        sg = V(a, b, f, inp, 1.0, f"3D {slug}" + (" (черновик)" if f.endswith("_draft.mp4") else ""), line)
        sg.stem = MSFX.get("3d:" + slug) if stem else None
        sg.sound = slug == "mailbox"                     # у почтового ящика звук вшит в ролик
        return sg
    return C(a, b, f"{line} · [3D {slug}] рендерится", line)


def from_ai(a, b, cid, motion, line, plan):
    f = f"{SH}/ai/{cid}.png"
    if ex(f): return I(a, b, f, motion, f"AI {cid}", line)
    return C(a, b, f"{line} · [AI {cid}] {plan}", line)


def from_board(a, b, bid, line, plan):
    g = board(bid)
    if g:
        sg = V(a, b, g["file"], 0.0, 1.0, f"{bid} · {g['note']}", line); sg.stem = MSFX.get(bid); return sg
    return C(a, b, f"{line} · [BOARD {bid}] {plan}", line)


# ---------------------------------------------------------------- холодный старт: срезы готового черновика + сцены Ника
CO_FILE = "assets/shots/ep04/coldopen/ep04_coldopen_v2.mp4"   # плеер Cutlab отдаёт файлы только из assets/
CO_SEG = [(0.00, 2.31, "плакат ФБР на плёнке"), (2.31, 3.51, "фоторобот 1987 на плёнке"), (3.51, 8.50, "доска: карточка 16 бомб, плакат"),
          (8.50, 10.55, "отпечаток NO MATCH"), (10.55, 17.63, "доска: фоторобот + круг кистью"), (17.63, 22.81, "доска: стикер Натан"),
          (22.81, 25.15, "9 000 Натанов"), (25.15, 28.11, "нитка стикер → фоторобот"), (28.11, 35.90, "доска общий план, 150 / $50M"),
          ("H2", 35.90, 41.92), ("H3", 41.92, 46.25), (46.25, 52.00, "штампы 6 методов"), (52.00, 53.75, "наезд в фоторобот"),
          ("H3tail", 53.75, 54.95), (54.95, 55.25, "камера падает"), ("H4a", 55.25, 58.20), (58.20, 58.40, "подъём камеры, пыль"),
          ("H4b", 58.40, 66.35), (66.35, 67.20, "рывок в доску")]
LIP = {"H2": (1.17, 0.24, 36.10), "H3": (1.03, 0.04, 41.92), "H4b": (1.14, 0.16, 58.33)}     # k, L0, начало референса (время B0_edit)
CO_DUR = 67.20


def cold_open(T0):
    ch = "0. ХОЛОДНЫЙ СТАРТ"; v = []
    for s in CO_SEG:
        if isinstance(s[0], str):
            nid, a, b = s
            if nid in LIP:
                k, L0, r0 = LIP[nid]; f = f"{SH}/scenes/video/{nid}.mp4"; inp = L0 + k * (a - r0)
                v.append(clipv(f"{nid}", T0 + a, T0 + b, f, max(0.0, inp), ch, f"{nid} [NICK]", speed=k, line=nid))
            elif nid == "H3tail":
                v.append(clipv("H3tail", T0 + a, T0 + b, f"{SH}/scenes/video/H3.mp4", 4.85, ch, "H3 хвост: локоть задевает камеру", line="H3"))
            elif nid == "H4a":
                v.append(clipv("H4a", T0 + a, T0 + b, f"{SH}/scenes/video/H4a.mp4", 0.60, ch, "H4a [NICK] камера на полу", line="H4a"))
        else:
            a, b, note = s
            v.append(clipv(f"CO_{a:05.2f}", T0 + a, T0 + b, CO_FILE, a, ch, f"холодный старт · {note}"))
    au = [aclip("vo-B0", "voice", f"{VO}/block_B0_edit.wav", T0, probe(f"{VO}/block_B0_edit.wav")),
          aclip("sfx-coldopen", "sfx1", "assets/sfx/ep04_stems/coldopen_sfx.wav", T0, CO_DUR, tag="стем звуков холодного старта")]
    return v, au, T0 + CO_DUR


# ---------------------------------------------------------------- тизер: 11 пунктов, по 2–4 куска
def teaser(T0):
    B = "BT"; ch = "1. ТИЗЕР"; W = lambda w, after=0.0, nth=1: cut_at(B, w, after, nth)
    starts = [0.0, W("how", 5.9), W("how", 9.6), W("why", 15.0), W("how", 20.0), W("how", 24.0), W("why", 27.0),
              W("why", 30.2), W("how", 34.2), W("what", 41.0), W("and", 44.4), 49.05]
    segs = []
    st = lambda gid, default: (MGFX.get(gid) or {}).get("start", default)
    S = starts
    segs += [from_real(S[0], st("HL_T1", 3.63), "T1", 0, "лимон в slow motion"), from_gfx(st("HL_T1", 3.63), S[1], "HL_T1", "T1", "[HL] камера, пунктир вокруг объектива")]
    segs += [from_gfx(S[1], S[2], "HL_T2", "T2", "[HL] сыр, кончики пальцев")]
    h3 = st("HL_T3", S[2]) + (MGFX.get("HL_T3") or {}).get("dur", 2.6)
    segs += [from_gfx(S[2], h3, "HL_T3", "T3", "[HL] пицца, EXHIBIT"), from_real(h3, S[3], "T3", 1, "мазок ватой")]
    m4 = (S[3] + S[4]) / 2; segs += [from_3d(S[3], m4, "air_dna", 8.6, "T4"), from_3d(m4, S[4], "air_dna", 11.4, "T4")]
    m5 = (S[4] + S[5]) / 2; segs += [from_3d(S[4], m5, "family_tree", 4.6, "T5"), from_3d(m5, S[5], "family_tree", 11.4, "T5")]   # пробирки на стоке нет
    segs += [from_real(S[5], st("T6g", 25.55), "T6", 0, "фитнес-браслет"), from_gfx(st("T6g", 25.55), S[6], "T6g", "T6", "график шагов")]
    m7 = (S[6] + S[7]) / 2; segs += [from_3d(S[6], m7, "printer_dots", 3.6, "T7"), from_3d(m7, S[7], "printer_dots", 15.6, "T7")]
    m8 = (S[7] + S[8]) / 2; segs += [from_real(S[7], m8, "T8", 0, "сортировочная машина"), from_3d(m8, S[8], "mail_camera", 1.0, "T8")]
    segs += [from_real(S[8], st("T9g", 38.31), "T9", 0, "телефон с перепиской"), from_gfx(st("T9g", 38.31), S[9], "T9g", "T9", "27 000 000")]
    lv = W("louvre's", 41.0); segs += [from_gfx(S[9], lv, "T10g", "T10", "поле пароля"), from_real(lv, S[10], "T10", 0, "Лувр ночью")]
    m11 = S[10] + 2.6
    segs += [from_3d(S[10], m11, "typewriter_letters", 0.9, "T11"),
             I(m11, S[11], f"{PD}/Unabomber_Auction_01.jpg", "zoom_in", "фото ФБР: машинка Smith-Corona", "T11")]
    v = place(segs, T0, 0.0, ch)
    au = [aclip("vo-BT", "voice", f"{VO}/block_BT_master.wav", T0, 49.05)]
    for i, s in enumerate(starts[1:-1], 1):
        au.append(aclip(f"sfx-t{i:02d}", "sfx2", f"{S3}/whoosh_air_short.wav", T0 + s - 0.1, 0.55, db=-15, tag="whoosh"))
    return v, au, T0 + 49.05


def intro(T0):
    v = [clipv("INTRO", T0, T0 + 7.6, "assets/intro/intro_v3.mp4", 0.0, "1. ТИЗЕР", "INTRO заставка канала")]
    return v, [aclip("m-intro", "music", "assets/intro/intro_music.wav", T0, 7.6)], T0 + 7.6


# ---------------------------------------------------------------- глава 1
def chapter1(T0):
    B = "B1"; ch = "2. ГЛАВА 1 — TRACE EVIDENCE"; W = lambda w, after=0.0, nth=1: cut_at(B, w, after, nth)
    L = lambda lid: TIM["lines"][lid]["start"] - LEAD
    l = {k: L(k) for k in ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.6+", "1.7", "1.8", "1.9", "1.10"]}
    end = 181.91
    s = []
    # 1.0 — Ник прикалывает карту (клип 6 с), наезд в крестик → рисованная парковка сверху
    s.append(V(0.0, 6.0, f"{SH}/scenes/video/1.0.mp4", 0.0, 1.0, "1.0 [NICK] карта Чикаго", "1.0"))
    s.append(from_ai(6.0, l["1.1"], "1.0_1", "zoom_in", "1.0", "парковка сверху"))
    # 1.1 — свёрток, охранник, досье
    t0, t1 = W("a", W("address", l["1.1"])), W("except", l["1.1"])
    g11 = TIM["lines"]["1.1"]["start"] - LEAD            # досье G1.1 идёт под голос всей реплики (рисунки 1.1_1/1.1_2 + бирки, штамп BOMB #1)
    if gfx("G1.1"):
        s += [from_gfx(l["1.1"], t0, "G1.1", "1.1", "", inp=l["1.1"] - g11),                        # «The return address:»
              from_real(t0, t1, "1.1", 0, "старое кирпичное здание университета"),                   # «a professor at a nearby university…»
              from_gfx(t1, l["1.2"], "G1.1", "1.1", "", inp=t1 - g11)]                               # «Except he never sent it…» → охранник → BOMB #1
    else:
        t2 = W("a", W("sent", l["1.1"]))
        s += [from_ai(l["1.1"], t0, "1.1_1", "zoom_in", "1.1", "свёрток с марками"), from_real(t0, t1, "1.1", 0, "здание университета"),
              from_gfx(t1, t2, "G1.1", "1.1", "досье"), from_ai(t2, l["1.2"], "1.1_2", "pan_left", "1.1", "охранник поднимает свёрток")]
    # 1.2 — термин, криминалист начала XX века
    t3 = (MGFX["TERM1"]["start"] + MGFX["TERM1"]["dur"]) if gfx("TERM1") else l["1.2"] + 4.0      # карточка целиком: штамп METHOD 1 в её конце
    s += [from_gfx(l["1.2"], t3, "TERM1", "1.2", "METHOD 1 — TRACE EVIDENCE"), from_ai(t3, l["1.3"], "1.2_1", "zoom_in", "1.2", "криминалист 1900-х")]
    # 1.3 — Локар (реальное видео + частицы), потом рукав
    s += [from_3d(l["1.3"], 40.70, "locard", 0.0, "1.3"), from_real(40.70, l["1.4"], "1.3", 0, "макро ткани рукава, чужие волокна [HL]")]
    # 1.4 — трубы ФБР, винты, батарейки, котелок, счётчик
    a1, a2, a3, a4 = W("old", l["1.4"]), W("he", W("roadside", l["1.4"])), W("according", l["1.4"]), W("16", l["1.4"])
    s += [I(l["1.4"], a1, f"{PD}/Pipes_in_Ted_Kaczynskis_cabin.jpg", "zoom_in", "фото ФБР: трубы в хижине", "1.4"),
          from_real(a1, a2, "1.4", 0, "старые винты макро"), from_real(a2, a3, "1.4", 1, "батарейки без этикеток"),
          from_ai(a3, a4, "1.4_1", "zoom_in", "1.4", "котелок на печке"), from_gfx(a4, l["1.5"], "G1.4", "1.4", "16 BOMBS → 0 PARTS TRACED")]
    # 1.5 — осколок FC + круг кистью
    s.append(from_gfx(l["1.5"], l["1.6"], "C1.5", "1.5", "круг вокруг FC") if gfx("C1.5")
             else I(l["1.5"], l["1.6"], f"{PD}/April_2016_Unabomber_Bomb_Shrapnel_(26213562526).jpg", "zoom_in", "фото ФБР: осколок FC", "1.5"))
    # 1.6 — доска, квиз, ящик через улицу, 3D
    q0, q1 = W("why", l["1.6"]), W("the", W("guesses", l["1.6"]))
    s += [from_board(l["1.6"], q0, "B1.6a", "1.6", "доска, наезд на карту"), from_gfx(q0, q1, "G1.6", "1.6", "квиз: Why a parking lot — not a mailbox?"),
          from_real(q1, 92.69, "1.6", 0, "синий почтовый ящик на улице"), from_3d(92.69, l["1.6+"], "mailbox", 0.0, "1.6")]
    # 1.6+ — полароид на доске, записка
    n0 = W("and", l["1.6+"])
    s += [from_board(l["1.6+"], n0, "B1.6p", "1.6+", "полароид MAILBOX TEST + нитка"), from_gfx(n0, l["1.7"], "G1.6n", "1.6+", "записка my bomb doesn't fit in the mailbox")]
    # 1.7 — автовокзал, волос, записка RV, список R.V.
    h0, h1, h2 = W("into", l["1.7"]), W("another", l["1.7"]), W("the", W("rv", l["1.7"]))
    s += [from_real(l["1.7"], h0, "1.7", 0, "автовокзал"), from_real(h0, h1, "1.7", 1, "волос под микроскопом"),
          from_gfx(h1, h2, "G1.7", "1.7", "записка Wu — It works! — RV"), from_gfx(h2, l["1.8"], "G1.7rv", "1.7", "инициалы R.V. перечёркнуты")]
    # 1.8 — цепочка
    s.append(from_gfx(l["1.8"], l["1.9"], "G1.8", "1.8", "CONTACT → TRACE → COMPARE → ?"))
    # 1.9 — мини-дело Берлин
    if gfx("W1.9"):
        w0 = MGFX["W1.9"].get("start", l["1.9"])
        s += [from_board(l["1.9"], w0, "B1.9a", "1.9", "наезд на фоторобот"), from_gfx(w0, l["1.10"], "W1.9", "1.9", "окно EVIDENCE 01 · TRACE")]
    else:
        b1, b2, b3, b4 = W("they", l["1.9"]), W("the", W("wheelbarrow", l["1.9"])), W("but", W("cut", l["1.9"])), W("two", W("glass", l["1.9"]))
        s += [from_real(l["1.9"], b1, "1.9", 0, "музейный зал ночью / золотая монета"), from_real(b1, b2, "1.9", 1, "тачка + [CIRCLE]"),
              from_real(b2, b3, "1.9", 2, "золотая монета"), from_real(b3, b4, "1.9", 3, "золотые блёстки на ткани [HL], осколки витрины"),
              from_gfx(b4, l["1.10"], "S1.9", "1.9", "штамп 4.5 YEARS")]
    # 1.10 — вердикт главы, Ник (2 куска: вторая фраза в клипе опаздывает на ~1 с → разрез в паузе + наезд)
    s.append(from_gfx(l["1.10"], 177.05, "V1", "1.10", "вердикт: TRACE EVIDENCE — HIM ✗ · YOU ✓"))
    p2 = word(B, "speaking", 177.0) - LEAD
    s.append(V(177.05, p2, f"{SH}/scenes/video/1.10.mp4", 0.02, 1.0, "1.10 [NICK] фраза 1", "1.10"))
    s.append(V(p2, end, f"{SH}/scenes/video/1.10.mp4", 0.02 + (p2 - 177.05) + 1.0, 1.0, "1.10 [NICK] Speaking of fingerprints", "1.10", "zoom_punch"))
    # пауза квиза: в голос B1 вставлена 1,0 с на 88,33 (block_B1_edit.wav) — всё после неё сдвигается
    E1 = lambda t: t + (1.0 if t >= 88.33 - 1e-6 else 0.0)
    for sg in s: sg.a, sg.b = E1(sg.a), E1(sg.b)
    v = place(s, T0, 0.0, ch)
    au = [aclip("vo-B1", "voice", f"{VO}/block_B1_edit.wav", T0, end + 1.0)]
    return v, au, T0 + end + 1.0


# ---------------------------------------------------------------- общие функции
def clipv(cid, start, end, src, inp, chapter, text, speed=1.0, line="", transition="cut", motion="static", kind="video"):
    c = {"id": cid, "track": "v1", "shot": line or cid, "chapter": chapter, "start": fr(start), "dur": round(fr(end) - fr(start), 6),
         "motion": motion, "transition": transition, "fit": "fill", "kind": kind, "text": text}
    if kind == "video": c.update(src=src, mute=True, **{"in": round(inp, 4)})
    if kind == "image": c.update(src=src)
    if speed != 1.0: c["speed"] = speed
    if line and line in EN: c["say_en"] = EN[line]["tts"]
    return c


SFX_CLIPS = []


def place(segs, T0, base, chapter):
    out, seen = [], {}
    for sg in segs:
        if sg.b - sg.a < 1 / FPS: continue
        key = sg.line or "x"; n = seen[key] = seen.get(key, 0) + 1
        cid = f"{key}" if n == 1 else f"{key}_{n}"
        if sg.kind == "video":
            c = clipv(cid, T0 + sg.a - base, T0 + sg.b - base, sg.src, sg.inp, chapter, sg.text, sg.speed, sg.line, sg.transition)
            if sg.sound: c["mute"] = False
            out.append(c)
            if sg.stem and ex(sg.stem):
                SFX_CLIPS.append(aclip(f"sfx-{cid}", "sfx2", sg.stem, T0 + sg.a - base, sg.b - sg.a, inp=max(0.0, sg.inp), tag="звуки ролика"))
        elif sg.kind == "image": out.append(clipv(cid, T0 + sg.a - base, T0 + sg.b - base, sg.src, 0, chapter, sg.text, line=sg.line, motion=sg.motion, kind="image"))
        else: out.append(clipv(cid, T0 + sg.a - base, T0 + sg.b - base, None, 0, chapter, sg.text, line=sg.line, kind="card"))
    for x, y in zip(out, out[1:]):                       # стык без дыр: конец = начало следующего
        x["dur"] = round(y["start"] - x["start"], 6)
    return out


def aclip(cid, track, src, start, dur, inp=0.0, db=0.0, fi=0.0, fo=0.0, tag=None):
    c = {"id": cid, "track": track, "src": src, "start": fr(start), "dur": round(dur, 4), "in": round(inp, 4), "volume_db": db, "loop": False}
    if fi: c["fade_in"] = fi
    if fo: c["fade_out"] = fo
    if tag: c["tag"] = tag
    return c


def api(path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=120))


def main():
    v1, a1, t1 = cold_open(0.0)
    v2, a2, t2 = teaser(t1)
    v3, a3, t3 = intro(t2)
    v4, a4, t4 = chapter1(t3)
    amb = [aclip("amb-ch1", "sfx1", f"{S4}/city_rain_night.wav", t3, t4 - t3, inp=20.0, db=-34, fi=2.0, fo=2.0, tag="фон: дождь за окном")]
    clips = v1 + v2 + v3 + v4 + a1 + a2 + a3 + a4 + SFX_CLIPS + amb
    cards = [c for c in v1 + v2 + v3 + v4 if c.get("kind") == "card"]
    print(f"холодный старт до {t1:.1f} с, тизер до {t2:.1f}, заставка до {t3:.1f}, глава 1 до {t4:.1f}; клипов {len(clips)}, заглушек {len(cards)}")
    for m in MISSING: print("  ЗАГЛУШКА", m)
    if "--apply" not in sys.argv: return
    projs = api("/projects")["projects"]
    pid = next((p["id"] for p in projs if p["title"] == TITLE), None)
    if not pid:
        pid = api("/projects", {"title": TITLE, "id": "ep04"}).get("id"); print("создан проект", pid)
    proj = api(f"/projects/{pid}")
    ops = [{"op": "remove", "id": c["id"], "fill": False} for c in proj["clips"]]
    ops += [{"op": "add", "clip": c, "restore": True} for c in clips]
    r = api(f"/projects/{pid}/ops", {"ops": ops, "client": "claude", "base_revision": proj.get("revision")})
    print(f"проект {pid}: ревизия {r['revision']}, клипов {len(r['project']['clips'])}")


if __name__ == "__main__":
    main()
