#!/usr/bin/env python3
"""Весь выпуск ep03 в Cutlab: пилот (холодный старт, тизер, заставка) + главы 0–10 + финал + конечная заставка.

Главы: голос — мастер-блоки assets/voice/ep03/block_<B>_master.wav; время реплик — lines_timing.json
(studio/editor/ep03_lines.py). Сцены Ника стоят ровно на своих репликах (губы без задержки), мостик главы доигрывает
наезд (хвост ≤ TAIL с) → 3D-карточка главы 4 с → следующая глава. 3D-объяснения — по своим меткам голоса
(время сырой записи блока − разгон); пока ролик не отрендерен — жёлтая карточка «рендерится». Анимации и реальные
кадры тизера — только там, где они ровно про ту же фразу. Всё остальное — жёлтая карточка с планом кадра
([AI]/[GFX]/[REAL]…): её потом заменяем материалом через «Правки» (propose).

  python3 studio/editor/build_ep03_full.py           # план
  python3 studio/editor/build_ep03_full.py --apply   # перезаписать проект ep03 через сервер Cutlab
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "editor"))
import build_ep03_pilot as P  # noqa: E402

FPS = P.FPS
SH, VO, SFX = "assets/shots/ep03", "assets/voice/ep03", "assets/sfx/epidemic/ep03"
ST = "assets/stock/ep03"
ORDER = ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B9", "B10", "BF"]
CHAPTER = {"B0": "2. УРОВЕНЬ 0 — ТЫ УЖЕ МУТАНТ", "B1": "3. УРОВЕНЬ 1 — МУТАНТЫ СРЕДИ НАС", "B2": "4. УРОВЕНЬ 2 — ПРЕДЕЛ ТЕЛА",
           "B3": "5. УРОВЕНЬ 3 — КИБОРГИ", "B4": "6. УРОВЕНЬ 4 — СУПЕРСИЛЫ ЖИВОТНЫХ", "B5": "7. УРОВЕНЬ 5 — СУПЕРСИЛА",
           "B6": "8. УРОВЕНЬ 6 — БЫСТРЕЕ ЗВУКА", "B7": "9. УРОВНИ 7–8 — КОСМОС", "B9": "10. УРОВЕНЬ 9 — СВЕТ",
           "B10": "11. УРОВЕНЬ 10 — ЛОМАЕМ ВСЕЛЕННУЮ", "BF": "12. ФИНАЛ"}
CARD_AFTER = {"B0": "K1_mutants", "B1": "K2_peak", "B2": "K3_cyborg", "B3": "K4_animal", "B4": "K5_strength",
              "B5": "K6_mach1", "B6": "K7_orbit", "B7": "K9_light", "B9": "K10_broken"}
CARD_DUR = 4.0
MUS = "assets/music/epidemic/ep03/chapters"
# музыка глав (Epidemic, выбор Claude 01.10 — пользователь может заменить): файл, с какой секунды, громкость
# громкость подобрана так, чтобы под словами музыка была на ~19 дБ тише голоса (замер по каждой главе)
CH_MUSIC = {"B0": ("B0_new_plan.wav", 0.0, -15), "B1": ("B1_cinematics.wav", 0.0, -11), "B2": ("B2_observatory.wav", 0.0, -15),
            "B3": ("B3_secure.wav", 0.0, -7), "B4": ("B4_wanderlust.wav", 0.0, -17), "B5": ("B5_out_there.wav", 0.0, -13),
            "B6": ("B6_trace.wav", 0.0, -8), "B7": ("B7_outer_orbit.wav", 0.0, -6), "B9": ("B9_sonar.wav", 0.0, -2),
            "B10": ("B10_turning_stones.wav", 0.0, -13), "BF": ("BF_blending_spaces.wav", 0.0, -6.5)}
TAIL = 2.0                       # сколько сцена-мостик доигрывает после голоса (наезд в предмет карточки)
SCENES = {"0.0": "S00", "0.9": "S09", "1.15": "S115", "2.18": "S218", "3.13": "S313", "4.15": "S415", "5.8": "S58",
          "6.11": "S611", "7.7": "S77", "9.9": "S99", "F1": "SF1", "F3": "SF3", "F4": "SF4"}
# 3D: блок, метка в сырой записи блока (кадр 1 сцены), длительность, подпись
THREE_D = {"bone_brake": ("B1", 18.15, 425 / FPS, "КОСТЬ БЕЗ ТОРМОЗА"), "mantis_strike": ("B4", 11.20, 479 / FPS, "ПРУЖИНА, ЗАЩЁЛКА, ПУЗЫРЬ"),
           "spine_car": ("B5", 13.58, 494 / FPS, "ПОЗВОНОЧНИК ПОД МАШИНОЙ"), "plasma_cocoon": ("B7", 14.14, 315 / FPS, "ПЛАЗМЕННЫЙ КОКОН"),
           "mach1_runner": ("B6", 47.79, 768 / FPS, "МАХ 1: БЕГУН И УДАРНАЯ ВОЛНА"),
           "finish_before_start": ("B10", 19.10, 426 / FPS, "ФИНИШ РАНЬШЕ СТАРТА")}
G = SH
# готовые материалы, точно про фразу: реплика → куски (файл, in, скорость, длительность)
REUSE = {
    "0.1": [(f"{ST}/sb_348485150_milk_glass.mp4", 10.0, 1.0, 3.6)],
    "1.12": [(f"{G}/T1/gfx_T1_no_match.mp4", 0.0, 1.0, 2.4), (f"{ST}/sb_11132309_blood_bags.mp4", 2.0, 1.0, 3.5)],
    "2.4": [(f"{ST}/sb_358246654_icy_creek.mp4", 9.9, 1.0, 5.0)],
    "2.5": [(f"{G}/T8/gfx_T8_thermometer.mp4", 0.0, 1.0, 2.4)],
    "2.15": [(f"{G}/T7/gfx_T7_rocket_sled.mp4", 0.0, 1.0, 1.43)],
    "2.16": [(f"{G}/T7/gfx_T7_rocket_sled.mp4", 1.43, 1.0, 3.87)],
    "2.17": [(f"{ST}/sb_348643774_seatbelt.mp4", 0.51, 1.0, 3.0)],
    "3.2": [(f"{ST}/sb_355039499_typing.mp4", 10.0, 1.0, 3.0), (f"{G}/T6/gfx_T6_mind_writing.mp4", 0.0, 1.0, 2.4),
            (f"{G}/T6/gfx_T6_brain_chip.mp4", 0.0, 1.0, 1.1)],
    "3.5": [(f"{G}/T5/gfx_T5_gecko_climb.mp4", 0.0, 1.0, 1.7), (f"{ST}/sb352195277_gecko_feet.mp4", 0.5, 1.0, 3.0)],
    "4.1": [(f"{ST}/sb355019350_mantis_crawl.mp4", 10.0, 1.0, 3.5), (f"{G}/T3/gfx_T3_mantis_cavitation.mp4", 0.0, 1.0, 2.7)],
    "4.6": [(f"{ST}/sb354913717_rattlesnake_tongue.mp4", 4.0, 1.0, 3.0), (f"{ST}/sb347376817_thermal_hand.mp4", 1.8, 1.0, 2.5),
            (f"{G}/T4/gfx_T4_trpa1_same_protein.mp4", 0.0, 1.0, 1.6), (f"{ST}/sb352111680_wasabi_grating.mp4", 0.6, 1.0, 3.0)],
    "9.1": [(f"{G}/T10/gfx_T10_muons_palm.mp4", 0.0, 1.0, 2.4)],
    "9.2": [(f"{G}/T10/gfx_T10_cloud_chamber.mp4", 1.0, 1.0, 1.45)],
    "9.3": [(f"{ST}/sb_353926275_satellite.mp4", 10.0, 1.0, 3.0), (f"{G}/T9/gfx_T9_gps_drift.mp4", 0.0, 1.0, 2.4)],
    "10.1": [(f"{G}/T11/gfx_T11_lightspeed_run.mp4", 0.0, 1.0, 3.4)],
    "4.5": [(f"{ST}/sb10891254_finger_snap.mp4", 0.5, 0.75, 3.6)],          # щелчок на «fingers»
    "3.1": [(f"{SH}/gfx/G08/G08.mp4", 10.2, 1.0, 3.4)],                       # «Remember ten bits per second?» — отсылка к G08
    # финал: повтор главного по словам (эхолокация, память, тюлень, «видеть ушами», шестой палец, башня, кости, скорость)
    "F2": [(f"{SH}/ai/2.7_2.png", "zoom_in", 1.0, 3.7), (f"{SH}/gfx/G210/G210.mp4", 6.0, 1.0, 2.2),
           (f"{ST}/sb_348955451_fur_seal_underwater.mp4", 6.0, 1.0, 2.2), (f"{SH}/ai/2.7_3.png", "pan_left", 1.0, 2.1),
           (f"{SH}/ai/3.8_1.png", "zoom_in", 1.0, 1.3), (f"{SH}/H5/3d_tower.mp4", 3.6, 1.0, 1.83),
           (f"{SH}/3d/bone_brake/bone_brake.mp4", 12.4, 1.0, 0.85), (f"{SH}/gfx/G62/G62.mp4", 0.3, 1.0, 0.85)],
    # призыв в середине (4.15, за кадром до сцены Ника) — быстрый повтор кадров главы
    "4.15": [(f"{G}/T3/gfx_T3_mantis_cavitation.mp4", 1.43, 1.0, 1.27), (f"{ST}/sb347376817_thermal_hand.mp4", 4.5, 1.0, 2.2),
             (f"{ST}/sb354913717_rattlesnake_tongue.mp4", 7.0, 1.0, 2.2), (f"{ST}/sb355019350_mantis_crawl.mp4", 14.0, 1.0, 3.1)],
}


GFX_LINE = {"G01": "0.1", "G04": "0.4", "G05": "0.5", "G06": "0.6", "G07": "0.7", "G08": "0.8", "G17": "1.7", "G21": "2.1",
            "G22": "2.2", "G25": "2.5", "G29": "2.9", "G210": "2.10", "G211": "2.11", "G216": "2.16", "G36": "3.6",
            "G43": "4.3", "G411": "4.11", "G413": "4.13", "G55": "5.5", "G57": "5.7", "G62": "6.2", "G63": "6.3", "G64": "6.4",
            "G68": "6.8", "G74": "7.4", "G75": "7.5", "G92": "9.2", "G95": "9.5", "G96": "9.6", "G98": "9.8", "G101": "10.1",
            "G106": "10.6", "G41": "4.1", "G35": "3.5", "G45": "4.5", "G414": "4.14", "G91": "9.1", "G93": "9.3",
            "GF2": "F2", "G37A": "3.7", "G37B": "3.7@end", "G39": "3.9@end", "G410": "4.10@end", "G610": "6.10@end",
            "G94": "9.4", "G104": "10.4"}
MOTIONS = ["zoom_in", "pan_left", "zoom_out", "pan_right"]
GFX_HOLD = {"G104": 0.8}        # держать последний кадр: «NOTHING.» по громкости звучит позже, чем у whisper
VO_BRIDGE = {"0.9", "1.15", "5.8"}          # начало мостика за кадром — продолжаем предыдущий кадр
# мемы-пародии в стиле Ника (решение пользователя 01.10): блок, начало и конец в мастере, картинка, движение, переход,
# приоритет (1.5 — поверх обычных кадров, но под 3D и сценами Ника; 3 — врезка поверх сцены Ника),
# звуки (файл, сдвиг от начала мема, с какой секунды файла, дБ). Второй вариант каждого — в assets/shots/ep03/memes/*_b.png
MEMES = {
    "M1_mib": ("B3", 42.42, 44.91, f"{SH}/memes/M1_mib_a.png", "zoom_in", "flash", 1.5,
               [(f"{SFX}/meme_flash_charge.wav", -0.10, 0.0, 6)]),
    "M4_drake": ("B2", 145.30, 147.43, f"{SH}/memes/M4_drake_a.png", "zoom_in", "cut", 1.5,
                 [(f"{SFX}/meme_record_scratch.wav", -0.35, 0.0, -8)]),
    "M6_point": ("B4", 57.29, 58.95, f"{SH}/memes/M6_point_a.png", "zoom_in", "cut", 1.5, [("assets/sfx/pop.wav", 0.0, 0.0, -10)]),
    "M2_matrix": ("B4", 72.11, 74.30, f"{SH}/memes/M2_matrix_a.png", "zoom_in", "cut", 1.5,
                  [(f"{SFX}/meme_bullets_airy.wav", 0.0, 1.6, -8)]),
    "M5_fine": ("B7", 22.59, 25.93, f"{SH}/memes/M5_fine_b.png", "zoom_in", "cut", 1.5,
                [(f"{SFX}/meme_fireball_slow.wav", 0.0, 0.0, -14)]),
    "M3_bttf": ("B10", 35.82, 38.78, f"{SH}/memes/M3_bttf_a.png", "zoom_out", "cut", 1.5,
                [(f"{SFX}/meme_fire_whoosh.wav", -0.30, 0.0, -10)]),
    "M7_buttons": ("BF", 39.87, 46.00, f"{SH}/memes/M7_buttons_b.png", "zoom_in", "cut", 3,
                   [(f"{SFX}/riser_fast_suspense.wav", 0.0, 0.0, -14)]),
}
# брак AI (не то содержание) — в сборку не идут, ждут перегенерации с «да» пользователя
AI_SKIP = {"5.4_3", "5.4_4", "1.4_2", "3.7_1", "1.10_4", "3.3_3"}


def materials():
    """реплика → список кусков для её свободной части: GFX, реальные видео (MANIFEST_chapters), AI-картинки (queue)"""
    out, tail = {}, {}
    for key, lid in GFX_LINE.items():
        f = f"{SH}/gfx/{key}/{key}.mp4"
        lid, at_end = lid.split("@")[0], lid.endswith("@end")
        if (ROOT / f).exists():
            (tail if at_end else out).setdefault(lid, []).append(("video", f, 0.0, 1.0, probe(f) + GFX_HOLD.get(key, 0.0), "gfx"))
    man = ROOT / ST / "MANIFEST_chapters.json"
    if man.exists():
        for lid, items in json.loads(man.read_text()).items():
            for it in items:
                if (ROOT / it["file"]).exists():
                    out.setdefault(lid, []).append(("video", it["file"], float(it.get("in") or 0), float(it.get("speed") or 1.0),
                                                    float(it.get("dur") or 4.0), "real"))
    q = ROOT / SH / "ai/queue.json"
    if q.exists():
        for i, x in enumerate(json.loads(q.read_text())):
            f = f"{SH}/ai/{x['id']}.png"
            if (ROOT / f).exists() and x["id"] not in AI_SKIP:
                lid = x["clip"].split("_")[0]
                out.setdefault(lid, []).append(("image", f, MOTIONS[i % 4], 1.0, float(x["dur"]), "ai"))
    for lid, items in tail.items():                 # «@end» — в конец реплики
        out.setdefault(lid, []).extend(items)
    return out


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ROOT / path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def parse_script():
    """id → {tag, ru, texts}: метки кадров и надписи [TEXT] из русского сценария"""
    L = (ROOT / "script/ep03_superhumans_narration.md").read_text().splitlines()
    pat = re.compile(r"^\*\*(\d+\.\d+|F\d)\s*\[([^\]]*)\]\**\s*(.*)")
    out, cur = {}, None
    for ln in L:
        m = pat.match(ln)
        if m:
            cur = m.group(1)
            rest = re.sub(r"\{[^}]*\}", "", m.group(3)).replace("**", "").strip()
            out[cur] = {"tag": m.group(2), "ru": rest, "texts": []}
        elif ln.startswith("## ") or ln.startswith("---"):
            cur = None
        elif cur and ln.startswith("- RU:"):
            out[cur]["ru"] = ln[5:].strip()
        if cur:
            for t in re.findall(r"\[TEXT\]\s*([^⚠\[{]+)", ln):
                t = t.strip().rstrip(".").strip()
                if t and t not in out[cur]["texts"]:
                    out[cur]["texts"].append(t)
    return out


def card_text(lid, info):
    tag = info["tag"].replace("★", "").strip()
    m = re.match(r"(QUIZ\s*→\s*)?([A-Z/]+(?:-голос)?)\s*[:;]?\s*(.*)", tag)
    kind = (m.group(2) if m else tag).strip()
    desc = (m.group(3) if m else "").strip(" ;:")
    if not desc:
        desc = re.sub(r"\s+", " ", info["ru"])
    desc = re.sub(r"\s+", " ", desc)
    if len(desc) > 90:
        desc = desc[:88].rsplit(" ", 1)[0] + "…"
    return f"{lid} · [{kind}] {desc}"


MAT = {}


def build():
    tim = json.loads((ROOT / VO / "lines_timing.json").read_text())
    scenes = json.loads((ROOT / VO / "nick/_scenes.json").read_text())
    en = json.loads((ROOT / "script/ep03_en.json").read_text())
    script = parse_script()
    global MAT
    MAT = materials()
    v1, au, tx = P.cold_open()
    v1, au = list(v1), list(au)
    t1 = tx
    vt, at, t2 = P.teaser(t1)
    vi, ai = P.intro(t2)
    v1 += vt + vi
    au += at + ai
    T = vi[-1]["start"] + vi[-1]["dur"]          # конец заставки → начало глав
    texts = []
    blocks = {b["id"]: b for b in en["blocks"]}
    for B in ORDER:
        ids = blocks[B]["ids"]
        D = tim[f"_{B}"]["dur"]
        cut = tim[f"_{B}"]["cut"]
        ch = CHAPTER[B]
        # куски голоса: в B0 после 0.0 — вставка K0 (после сцены S00)
        pieces = [(0.0, tim["0.1"]["start"], "K0_you"), (tim["0.1"]["start"], D, CARD_AFTER.get(B))] if B == "B0" \
            else [(0.0, D, CARD_AFTER.get(B))]
        for pi, (pa, pb, card) in enumerate(pieces):
            # 1) базовые отрезки по репликам (+ готовые материалы внутри реплики)
            segs = []          # (a, b, src) в времени мастера; src = ("card", text) | ("video", file, t0_master, in, speed)
            lids = [l for l in ids if l in tim and pa - 1e-6 <= tim[l]["start"] < pb]
            for i, lid in enumerate(lids):
                a = pa if i == 0 else tim[lid]["start"]
                b = tim[lids[i + 1]]["start"] if i + 1 < len(lids) else pb
                t = a
                for (src, sin, sp, d) in REUSE.get(lid, []):
                    if t >= b - 0.3:
                        break
                    if not (ROOT / src).exists():          # материал ещё делается — его место займут другие
                        continue
                    e = min(b, t + d)
                    if src.endswith(".png"):
                        segs.append((t, e, ("image", src, sin), lid))
                    else:
                        segs.append((t, e, ("video", src, t, sin, sp), lid))
                    t = e
                if t < b - 1e-6 and lid in VO_BRIDGE and segs:
                    pa_, pb_, ps, pt = segs[-1]                 # закадровое начало мостика — тянем предыдущий кадр
                    segs[-1] = (pa_, b, ps, pt)
                    t = b
                mats = MAT.get(lid, [])
                if t < b - 1e-6 and mats:
                    free = b - t
                    fixed = sum(m[4] for m in mats if m[0] == "video")
                    imgs = [m for m in mats if m[0] == "image"]
                    img_d = max(1.2, (free - fixed) / len(imgs)) if imgs else 0
                    for m in mats:
                        if t >= b - 0.3:
                            break
                        d = m[4] if m[0] == "video" else img_d
                        e = b if m is mats[-1] else min(b, t + d)
                        if m[0] == "video":
                            segs.append((t, e, ("video", m[1], t, m[2], m[3]), lid))
                        else:
                            segs.append((t, e, ("image", m[1], m[2]), lid))
                        t = e
                if t < b - 1e-6:
                    segs.append((t, b, ("card", card_text(lid, script.get(lid, {"tag": "", "ru": ""}))), lid))
            # 2) наложения: 3D и сцены Ника (Ник важнее)
            over = []
            for key, (bb, raw0, dur, label) in THREE_D.items():
                if bb != B:
                    continue
                a = raw0 - cut
                if pa - 1e-6 <= a < pb:
                    f = f"{SH}/3d/{key}/{key}.mp4"
                    src = ("video", f, a, 0.0, 1.0) if (ROOT / f).exists() else ("card", f"[3D] {label} — РЕНДЕРИТСЯ")
                    over.append((a, min(pb + 0.0, a + dur), src, f"3d_{key}", 1))
            for key, (bb, m0, m1, f, mot, trans, prio, sfx) in MEMES.items():
                if bb != B or not (pa - 1e-6 <= m0 < pb) or not (ROOT / f).exists():
                    continue
                over.append((m0, min(m1, pb), ("image", f, mot), key, prio))
                for i, (sf, off, inp, db) in enumerate(sfx):
                    au.append(P.aclip(f"sfx-{key}-{i}", "sfx2", sf, T + (m0 - pa) + off, probe(sf) - inp, inp=inp, db=db, tag="meme"))
            tail = 0.0
            for lid, s in SCENES.items():
                sc = scenes[s]
                if sc["block"] != B or not (pa - 1e-6 <= sc["start"] < pb):
                    continue
                f = f"{SH}/scenes/video/{s}.mp4"
                vd = probe(f)
                end = min(sc["start"] + vd, pb + TAIL)
                if end > pb:
                    tail = max(tail, end - pb)
                over.append((sc["start"], end, ("video", f, sc["start"], 0.0, 1.0), s, 2))
            # 3) разрезаем базу наложениями (по приоритету)
            pts = sorted({pa, pb + tail} | {x for s in segs for x in s[:2]} | {x for o in over for x in o[:2]})
            elem = []
            for a, b in zip(pts, pts[1:]):
                if b - a < 1e-6:
                    continue
                mid = (a + b) / 2
                win = max((o for o in over if o[0] <= mid < o[1]), key=lambda o: o[4], default=None)
                if win:
                    elem.append((a, b, win[2], win[3]))
                else:
                    base = next((s for s in segs if s[0] <= mid < s[1]), None)
                    if base:
                        elem.append((a, b, base[2], base[3]))
                    else:                   # хвост без сцены (не должно быть) — тёмная карточка
                        elem.append((a, b, ("card", ""), "tail"))
            merged = []
            for e in elem:
                if merged and merged[-1][2] == e[2] and merged[-1][3] == e[3] and abs(merged[-1][1] - e[0]) < 1e-6:
                    merged[-1] = (merged[-1][0], e[1], e[2], e[3])
                else:
                    merged.append(e)
            # обрезки короче 0,3 с (метка 3D/сцены чуть позже начала реплики) — отдаём соседу
            k = 0
            while k < len(merged):
                a, b, src, tag = merged[k]
                if b - a < 0.3 and len(merged) > 1:
                    if k + 1 < len(merged) and merged[k + 1][2][0] == "video":
                        na, nb, ns, nt = merged[k + 1]
                        _, f, t0, sin, sp = ns          # ролик начинается на обрезок раньше с той же точки
                        merged[k + 1] = (a, nb, ("video", f, t0 - (na - a), sin, sp), nt)
                    elif k > 0:
                        pa_, pb_, ps, pt = merged[k - 1]
                        merged[k - 1] = (pa_, b, ps, pt)
                    else:
                        k += 1
                        continue
                    merged.pop(k)
                    continue
                k += 1
            # короткие заглушки (< 1,2 с, между готовым куском и 3D/сценой) — тянем предыдущий кадр
            k = 1
            while k < len(merged):
                a, b, src, tag = merged[k]
                if src[0] == "card" and b - a < 1.2 and merged[k - 1][2][0] in ("video", "image"):
                    pa_, pb_, ps, pt = merged[k - 1]
                    merged[k - 1] = (pa_, b, ps, pt)
                    merged.pop(k)
                    continue
                k += 1
            # 4) клипы на таймлайн (T + (м − pa))
            seen = {}
            for a, b, src, tag in merged:
                n = seen[tag] = seen.get(tag, 0) + 1
                cid = f"{tag}" if n == 1 else f"{tag}_{n}"
                start, dur = P.fr(T + (a - pa)), round(P.fr(T + (b - pa)) - P.fr(T + (a - pa)), 6)
                if dur <= 0:
                    continue
                c = {"id": cid, "track": "v1", "shot": tag, "chapter": ch, "start": start, "dur": dur, "motion": "static",
                     "transition": "cut", "fit": "fill"}
                if src[0] == "video":
                    _, f, t0, sin, sp = src
                    c.update(kind="video", src=f, mute=True, **{"in": round(sin + (a - t0) * sp, 4)})
                    if sp != 1.0:
                        c["speed"] = sp
                    c["text"] = f"{tag} · {Path(f).stem}"
                elif src[0] == "image":
                    c.update(kind="image", src=src[1], motion=src[2], text=f"{tag} · {Path(src[1]).stem}")
                    if tag in MEMES:
                        c["transition"] = MEMES[tag][5]
                else:
                    c.update(kind="card", text=src[1])
                info = script.get(tag)
                if info and n == 1:
                    c["say"] = info["ru"]
                    c["say_en"] = en["lines"].get(tag, {}).get("tts", "")
                v1.append(c)
                # надписи [TEXT] — на первом куске реплики, не поверх Ника
                if info and n == 1 and info["texts"] and not tag.startswith("S"):
                    for k, tt in enumerate(info["texts"][:2]):
                        texts.append({"id": f"tx-{tag}-{k}", "track": "text", "start": P.fr(start + 0.4 + 1.3 * k),
                                      "dur": 2.2, "text": tt, "style": "keyword"})
                        au.append(P.aclip(f"sfx-tx-{tag}-{k}", "sfx1", "assets/sfx/pop.wav", start + 0.4 + 1.3 * k, 0.25,
                                          db=-18, tag="pop"))           # тихий «поп» на плашке
            # голос куска
            au.append(P.aclip(f"vo-{B}-{pi}", "voice", f"{VO}/block_{B}_master.wav", T, pb - pa, inp=pa))
            # музыка главы под голосом (кроме короткого первого куска B0): вырез частот голоса + приглушение на словах
            if B in CH_MUSIC and not (B == "B0" and pi == 0):
                f, m_in, db = CH_MUSIC[B]
                mdur = (pb - pa) + tail
                src = P.ducked(f"{MUS}/{f}", m_in, mdur, f"{VO}/block_{B}_master.wav", 0.0, f"ch_{B}_{pi}", key_ss=pa)
                # обрывы музыки под мемы (как у ТОПЛЕС: тишина 0,5–2,5 с под шутку), потом мягкий возврат
                drops = sorted((m0, m0 + min(2.0, m1 - m0)) for bb, m0, m1, f_, *_ in MEMES.values()
                               if bb == B and pa <= m0 < pb + tail and (ROOT / f_).exists())
                cuts, a0 = [], pa
                for d0, d1 in drops:
                    cuts.append((a0, d0))
                    a0 = d1
                cuts.append((a0, pa + mdur))
                for k, (sa, sb) in enumerate(cuts):
                    if sb - sa < 0.3:
                        continue
                    au.append(P.aclip(f"m-{B}-{pi}" + (f"-{k}" if k else ""), "music", src, T + (sa - pa), sb - sa, inp=sa - pa,
                                      db=db, fi=1.5 if k == 0 else 0.4, fo=0.6 if k == len(cuts) - 1 else 0.12))
            T = P.fr(T + (pb - pa) + tail)
            # 5) карточка главы
            if card:
                f = f"{SH}/cards/{card}.mp4"
                v1.append({"id": card, "track": "v1", "shot": card, "chapter": ch, "start": T, "dur": CARD_DUR,
                           "motion": "static", "transition": "cut", "fit": "fill", "kind": "video", "src": f, "in": 0.0,
                           "mute": True, "text": f"{card} [CARD 3D]"})
                au.append(P.aclip(f"sfx-{card}-w", "sfx1", f"{SFX}/whoosh_air_short.wav", T - 0.12, 0.55, db=-10, tag="whoosh"))
                au.append(P.aclip(f"sfx-{card}-h", "sfx2", f"{SFX}/impact_dark_low.wav", T, 2.0, db=-14, fo=0.8, tag="hit"))
                T = P.fr(T + CARD_DUR)
    # конечная заставка (как в ep02): место под конечные заставки YouTube + музыка
    v1.append({"id": "E2.1", "track": "v1", "shot": "E2.1", "chapter": "12. ФИНАЛ", "start": T, "dur": 5.0, "motion": "static",
               "transition": "cut", "fit": "fill", "kind": "video", "src": "assets/endblock/endcard_mini_469da229.mp4",
               "in": 0.0, "mute": True, "text": "E2.1 конечная заставка"})
    au.append(P.aclip("m-end", "music", "assets/music/outro_motivation.wav", T, 5.0, inp=10.0, db=-14, fi=0.4, fo=1.5))
    return v1, au, texts, T + 5.0


def main():
    v1, au, texts, total = build()
    clips = v1 + au + texts
    cards = [c for c in v1 if c.get("kind") == "card"]
    print(f"весь выпуск: {int(total // 60)}:{total % 60:04.1f}; кадров {len(v1)} (из них карточек-заглушек {len(cards)}), "
          f"звуков {len(au)}, надписей {len(texts)}")
    if "--apply" not in sys.argv:
        for c in v1[-40:]:
            print(f"  {c['start']:8.2f} +{c['dur']:6.2f}  {c['id']:16s} {c.get('kind')}  {str(c.get('text'))[:70]}")
        return
    proj = P.api(f"/projects/ep03")
    ops = [{"op": "remove", "id": c["id"], "fill": False} for c in proj["clips"]]
    ops += [{"op": "add", "clip": c, "restore": True} for c in clips]
    r = P.api("/projects/ep03/ops", {"ops": ops, "client": "claude", "base_revision": proj.get("revision")})
    print(f"проект ep03: ревизия {r['revision']}, клипов {len(r['project']['clips'])}")


if __name__ == "__main__":
    main()
