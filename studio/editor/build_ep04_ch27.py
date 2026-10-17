"""Cutlab ep04 · главы 2–7 по плану export/ep04/VISUAL_PLAN_ch2-7.json — дописывает к пилоту операциями (проект не пересоздаётся,
правки пилота не трогаются). Голос — файлы правки блоков (паузы и вырезы, export/ep04/voice_edits.json); a, b кусков — уже в их времени.

  python3 studio/editor/build_ep04_ch27.py            сводка: что есть, чего нет, длина
  python3 studio/editor/build_ep04_ch27.py --apply    снять прежнюю сборку глав 2–7 (ids из export/ep04/ch27_ids.json) и поставить заново

Материалы: реальное видео — MANIFEST_real_ch27_*.json (A, B, C, D); графика — MANIFEST_gfx.json + MANIFEST_gfx_ch*.json (по главам);
доска — MANIFEST_board.json; звуки — MANIFEST_sfx.json. Нет материала → жёлтая карточка с описанием (никаких заимствований).
Повторный --apply — только пока пользователь не правил главы 2–7 в Cutlab; после — правки операциями по месту.
"""
import glob, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
FPS = 30
E = "export/ep04"
PLAN = f"{E}/VISUAL_PLAN_ch2-7.json"
IDS = f"{E}/ch27_ids.json"
CHAP = {"ch2": "3. ГЛАВА 2 — LATENT PRINTS", "ch3": "4. ГЛАВА 3 — PROFILING", "ch4": "5. ГЛАВА 4 — GENETIC GENEALOGY",
        "ch5": "6. ГЛАВА 5 — DIGITAL FORENSICS", "ch6": "7. ГЛАВА 6 — FORENSIC LINGUISTICS", "ch7": "8. ФИНАЛ"}
SEAM = {"B1": 0.3, "B2": 0.1, "B3": 0.6, "B3b": 0.4, "B4": 1.2, "B5": 0.6, "B6": 0.3, "B6b": 0.3, "B6c": 0.4, "B7": 0.0}                     # B4 1,2: правка 110 — засвет телефоном Ника перед главой 5
# губы сцен Ника (LIPSYNC.md): k, L0, начало референса в мастере блока; реакции — с какого места брать
LIP = {"2.8": (1.0, 0.24, 147.40), "3.5": (1.0, -0.04, 79.40), "4.8": (1.02, 0.24, 176.68), "5.7": (1.02, 0.04, 171.28), "7.1": (1.0, 0.354, 25.55)}   # 03.10: по полоскам рта с голосом правки
REACT_IN = {"R2.6": 0.0, "R3.9": 1.0}                              # правка 100 (04.10): реакции целиком (пауза голоса 4,0 / 3,0 с)
BOARD_PIECE = {"7.0_1": "BD7a", "7.0_3": "BD7b"}                   # финал доски — два ролика на два слота (между ними V6)


def fr(t): return round(round(t * FPS) / FPS, 6)
def ex(p): return bool(p) and os.path.exists(p)
def jl(p): return json.load(open(p)) if os.path.exists(p) else {}


def merged(pattern, first=()):
    """манифесты помощников (по главам) в один словарь; служебные ключи «_…» и строки пропускаются"""
    d = {}
    for p in list(first) + sorted(glob.glob(f"{E}/{pattern}")):
        d.update({k: v for k, v in jl(p).items() if not k.startswith("_") and isinstance(v, dict)})
    return d


REAL = merged("MANIFEST_real_ch27_*.json")
GFX = merged("MANIFEST_gfx_ch*.json", first=[f"{E}/MANIFEST_gfx.json"])
BOARD = jl(f"{E}/MANIFEST_board.json")
SFX = jl(f"{E}/MANIFEST_sfx.json")
VED = jl(f"{E}/voice_edits.json")
sys.path.insert(0, "studio/ep04")
from voice_edits import map_time                                   # noqa: E402


# кусок плана = 3D + прозрачная плашка поверх: рендер Cutlab прозрачные .mov не накладывает — склеиваем заранее (видео и звук)
COMPOSITE = {"4.0_1": dict(base="assets/shots/ep04/3d/skin_to_dna/skin_to_dna_v1.mp4", over="assets/shots/ep04/gfx/TERM4/TERM4_alpha.mov",
                           at=2.865, dur=8.995, out="assets/shots/ep04/gfx/TERM4/TERM4_over_skin.mp4",
                           base_sfx="assets/sfx/ep04_stems/3d/skin_to_dna.wav", over_sfx="assets/sfx/ep04_stems/gfx/TERM4.wav",
                           out_sfx="assets/sfx/ep04_stems/gfx/TERM4_over_skin.wav")}


def composite(c):
    """3D до конца → стоп-кадр до dur; плашка с c["at"]; звук — стем 3D + стем плашки со сдвигом"""
    import numpy as np, wave
    src = [c["base"], c["over"]]
    if not ex(c["out"]) or os.path.getmtime(c["out"]) < max(map(os.path.getmtime, src)):
        fc = (f"[0:v]tpad=stop_mode=clone:stop_duration={c['dur']:.3f}[bg];[1:v]setpts=PTS-STARTPTS+{c['at']}/TB[ov];"
              f"[bg][ov]overlay=eof_action=pass,trim=duration={c['dur']:.3f},format=yuv420p[v]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", c["base"], "-i", c["over"], "-filter_complex", fc, "-map", "[v]", "-r", "30",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium", c["out"]], check=True)
    if all(map(ex, (c["base_sfx"], c["over_sfx"]))):
        rd = lambda f: np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-ac", "2", "-ar", "48000", "-f", "f32le", "-"],
                                                    capture_output=True).stdout, np.float32).reshape(-1, 2)
        tr = np.zeros((int(c["dur"] * 48000), 2), np.float32)
        for x, at in ((rd(c["base_sfx"]), 0.0), (rd(c["over_sfx"]), c["at"])):
            i = int(at * 48000); j = min(len(tr), i + len(x)); tr[i:j] += x[:j - i]
        tr *= min(1.0, 0.95 / max(1e-6, float(np.abs(tr).max())))
        with wave.open(c["out_sfx"], "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000); w.writeframes((tr * 32767).astype(np.int16).tobytes())
    return c["out"], (c["out_sfx"] if ex(c["out_sfx"]) else None)


def three_d(src):
    """3D: финал _v1, если уже есть, иначе черновик"""
    if src and src.endswith("_draft.mp4") and ex(src.replace("_draft.mp4", "_v1.mp4")): return src.replace("_draft.mp4", "_v1.mp4")
    return src if ex(src) else None


# ролик графики на конкретный кусок плана (поле "piece"): части одной нужды (G6.6a, G6.6b … на куски нужды G6.6),
# колбэки и оверлеи на реальном клипе ("override": true — вместо реального клипа куска)
_PG = [(g, v) for g, v in list(GFX.items()) + [(k, x) for k, x in BOARD.items() if isinstance(x, dict)]   # правка 88: вставки доски VD2–VD6
       if isinstance(v.get("piece"), str) and " " not in v["piece"]]                                     # (MANIFEST_board) поверх карточек V
PIECE_GFX = {v["piece"]: v for g, v in _PG}
PIECE_ID = {id(v): g for g, v in _PG}


def resolve(p, blk, use_override=True):
    """кусок плана → (kind, src, in, speed, motion, stem, note); kind None — карточка"""
    k, need, src = p["kind"], p.get("need"), p.get("src")
    o = PIECE_GFX.get(p["id"]) if use_override else None
    if o and k in ("REAL", "PD") and not ((REAL.get(need) and ex(REAL[need].get("file"))) or (k == "PD" and ex(src))): o = None   # оверлей на ещё не найденном клипе — заглушка (PD-фото с файлом — можно, правка 125)
    if o and ex(o.get("file")): return "video", o["file"], 0.0, 1.0, "static", (o["stem"] if ex(o.get("stem")) else SFX.get(PIECE_ID[id(o)])), f"{p['id']} · {o.get('note', '')[:120]} (оверлей)"
    if k == "REAL":
        r = REAL.get(need)
        if r and not r.get("missing") and ex(r.get("file")):                 # архив на плёнке (archive_shot.py) — со своим звуком круга/бирки
            return "video", r["file"], float(r.get("in", 0)), float(r.get("speed", 1) or 1), "static", r.get("sfx_stem"), f"{need} · {r.get('what', '')}"
        return None, None, 0, 1, "", None, f"[REAL {need}] {p.get('what', '')}"
    if k in ("GFX", "QUIZ", "DOSSIER", "WINDOW", "V", "TERM") or (k == "PD" and need in GFX):
        g = GFX.get(need) if need else None
        if g and ex(g.get("file")): return "video", g["file"], 0.0, 1.0, "static", SFX.get(need), f"{need} · {g.get('note', '')[:120]}"
        if src and ex(src) and src.endswith(".mp4"):
            gid = os.path.basename(os.path.dirname(src)); return "video", src, 0.0, 1.0, "static", SFX.get(gid), f"{gid}"
        return None, None, 0, 1, "", None, f"[{k} {need}] {p.get('what', '')}"
    if k == "BOARD":
        b = BOARD.get(BOARD_PIECE.get(p["id"], need))
        if b and ex(b.get("file")): return "video", b["file"], 0.0, 1.0, "static", SFX.get(need), f"{need} · {b.get('note', '')[:120]}"
        return None, None, 0, 1, "", None, f"[BOARD {need}] {p.get('what', '')}"
    if k == "3D" and p["id"] in COMPOSITE:
        f, st = composite(COMPOSITE[p["id"]]); return "video", f, 0.0, 1.0, "static", st, "3D skin_to_dna + плашка TERM4 (склеено заранее)"
    if k == "PD" and REAL.get(need, {}).get("file") and ex(REAL[need]["file"]):        # страницы аффидевита — из манифеста реального видео
        f = REAL[need]["file"]
        return ("video" if f.endswith((".mp4", ".mov")) else "image"), f, float(REAL[need].get("in", 0)), 1.0, "zoom_in", None, f"{need} · {REAL[need].get('what', '')}"
    if k == "3D":
        f = three_d(src); slug = os.path.basename(os.path.dirname(src or ""))
        if f: return "video", f, 0.0, 1.0, "static", SFX.get("3d:" + slug), f"3D {slug}" + (" (черновик)" if f.endswith("_draft.mp4") else "")
        return None, None, 0, 1, "", None, f"[3D {slug}] рендерится"
    if k == "NICK":
        sid = os.path.basename(src or "")[:-4]
        if not ex(src): return None, None, 0, 1, "", None, f"[NICK {sid}]"
        if sid in REACT_IN: return "video", src, REACT_IN[sid], 1.0, "static", None, f"Ник, реакция без речи {sid}"
        if sid in LIP:
            kk, L0, t0 = LIP[sid]; t0e = map_time(VED.get(blk, {}), t0)
            return "video", src, max(0.0, L0 + (p["a"] - t0e) * kk), kk, "static", None, f"Ник {sid} (губы: скорость {kk}, сдвиг {L0})"
        return "video", src, 0.0, 1.0, "static", None, f"Ник {sid}"
    if k in ("AI", "PD"):
        if ex(src): return "image", src, 0.0, 1.0, "zoom_in", None, f"{k} {os.path.basename(src)}"
        return None, None, 0, 1, "", None, f"[{k}] {p.get('what', '')}"
    return None, None, 0, 1, "", None, f"[{k} {need}] {p.get('what', '')}"


def build(proj):
    plan = json.load(open(PLAN))
    ours = set(jl(IDS).get("ids", []))
    v1_pilot = [c for c in proj["clips"] if c["track"] == "v1" and c["id"] not in ours]
    vo_pilot = [c for c in proj["clips"] if c["track"] == "voice" and c["id"] not in ours]
    t = max(c["start"] + c["dur"] for c in vo_pilot)              # конец голоса пилота (кадры могли быть продлены прошлой сборкой)
    last_pilot = max(v1_pilot, key=lambda c: c["start"] + c["dur"])
    clips, stats, prev_blk = [], {"есть": 0, "карточек": 0, "черновиков 3D": 0}, "B1"
    cards = []
    t += SEAM["B1"]
    for ch in plan["chapters"]:
        chapter = CHAP.get(ch["id"], ch["title"])
        for b in ch["blocks"]:
            blk, S = b["id"], fr(t)
            clips.append({"id": f"vo-{blk}", "track": "voice", "src": b["voice_file"], "start": S, "dur": round(b["dur"], 4), "in": 0.0,
                          "volume_db": 0.0, "loop": False, "chapter": chapter})
            pcs = [p for ln in b["lines"] if not ln.get("cut") for p in ln["pieces"]]
            first = {}                                          # один ролик на несколько кусков (вставка внутри) — продолжать с того же места
            for i, p in enumerate(pcs):
                a, e = S + p["a"], S + (pcs[i + 1]["a"] if i + 1 < len(pcs) else b["dur"] + SEAM.get(blk, 0))
                kind, src, inp, sp, motion, stem, note = resolve(p, blk)
                if p["id"] in PIECE_GFX:                         # кусок заменён (окно, плёнка…): якорь продолжения исходного файла не теряем —
                    k0, s0, i0, *_r = resolve(p, blk, use_override=False)   # иначе дальние куски того же ролика берут не тот отрезок (правки 132–133)
                    if k0 == "video" and s0 and s0 != src and s0 not in first: first[s0] = (p["a"], i0)
                key = src                                        # продолжение — только когда тот же файл идёт под несколькими кусками
                if kind == "video" and key:
                    if key in first: inp = first[key][1] + (p["a"] - first[key][0]) * sp; note += " (продолжение)"
                    else: first[key] = (p["a"], inp)
                c = {"id": p["id"], "track": "v1", "shot": p["line"], "chapter": chapter, "start": fr(a), "dur": round(fr(e) - fr(a), 6),
                     "motion": motion or "static", "transition": "cut", "fit": "fill", "text": f"{p['line']} · {note} — {p.get('what', '')}"[:600]}
                if kind == "video":
                    c.update(kind="video", src=src, mute=True, **{"in": round(inp, 4)})
                    if sp != 1.0: c["speed"] = sp
                    stats["есть"] += 1; stats["черновиков 3D"] += src.endswith("_draft.mp4")
                elif kind == "image":
                    c.update(kind="image", src=src); stats["есть"] += 1
                else:
                    c.update(kind="card"); stats["карточек"] += 1; cards.append(f"{p['id']:8s} {note[:100]}")
                clips.append(c)
                if stem and ex(stem):
                    db = float((GFX.get(p.get("need") or "") or BOARD.get(p.get("need") or "") or {}).get("sfx_db", 0.0))   # «тише» из манифеста
                    clips.append({"id": f"sfx-{p['id']}", "track": "sfx2", "src": stem, "start": fr(a), "dur": round(fr(e) - fr(a), 4),
                                  "in": round(inp, 4), "volume_db": db, "loop": False, "tag": "звуки ролика", "chapter": chapter})
            t = S + b["dur"] + SEAM.get(blk, 0); prev_blk = blk
    # стыки блоков: если первый кусок блока начинается не с 0 (план тянет хвост прошлой сцены), продлить предыдущий кадр
    v1 = sorted([c for c in clips if c["track"] == "v1"], key=lambda c: c["start"])
    stems = {c["id"][4:]: c for c in clips if c["id"].startswith("sfx-")}
    for a_, b_ in zip(v1, v1[1:]):
        gap = round(b_["start"] - (a_["start"] + a_["dur"]), 6)
        if abs(gap) > 1e-6:
            a_["dur"] = round(a_["dur"] + gap, 6)
            if a_["id"] in stems: stems[a_["id"]]["dur"] = round(stems[a_["id"]]["dur"] + gap, 4)
    # концовка канала (как в ep03): заставка 5 с — место под конечную заставку YouTube, музыка outro
    tend = fr(max(c["start"] + c["dur"] for c in clips if c["track"] == "v1"))
    tv = "assets/shots/ep04/gfx/TVOFF/TVOFF2.mp4"                  # правка 145: после CASE CLOSED — «выключение кинескопа → снег», потом заставка
    if ex(tv):
        clips.append({"id": "TVOFF2", "track": "v1", "shot": "TVOFF2", "chapter": CHAP["ch7"], "start": tend, "dur": fr(0.9), "kind": "video",
                      "src": tv, "in": 0.0, "mute": True, "motion": "static", "transition": "cut", "fit": "fill",
                      "text": "TVOFF2 · правка 145: CASE CLOSED выключается, как кинескоп, → «снег» → заставка (как TVOFF перед интро)"})
        clips.append({"id": "sfx-TVOFF2", "track": "sfx2", "src": "assets/sfx/ep04_stems/gfx/TVOFF2.wav", "start": tend, "dur": fr(0.9),
                      "in": 0.0, "volume_db": 0.0, "loop": False, "tag": "звуки ролика", "chapter": CHAP["ch7"]})
        tend = fr(tend + 0.9)
    clips.append({"id": "E2.1", "track": "v1", "shot": "E2.1", "chapter": CHAP["ch7"], "start": tend, "dur": 5.0, "kind": "video",
                  "src": "assets/endblock/endcard_mini_469da229.mp4", "in": 0.0, "mute": True, "motion": "static", "transition": "cut",
                  "fit": "fill", "text": "E2.1 · заставка канала 5 с — место под конечную заставку YouTube (общий финальный блок, assets/endblock/)"})
    clips.append({"id": "m-end", "track": "music", "src": "assets/music/outro_motivation.wav", "start": tend, "dur": 5.0, "in": 0.0,
                  "volume_db": -12.0, "loop": False, "tag": "музыка концовки"})
    S2 = fr(max(c["start"] for c in clips if c["id"] == "vo-B2"))
    clips.append({"id": "amb-ch27", "track": "sfx1", "src": "assets/sfx/epidemic/ep04/city_rain_night.wav", "start": S2, "dur": round(fr(t) - S2, 4),
                  "in": 0.0, "volume_db": -34.0, "loop": True, "tag": "фон: дождь за окном"})
    return clips, stats, cards, last_pilot, S2, t


def main():
    sys.path.insert(0, "studio/editor")
    import model as M                                                      # noqa: E402
    proj = M.load_project("ep04")
    clips, stats, cards, last_pilot, S2, end = build(proj)
    v1 = [c for c in clips if c["track"] == "v1"]
    print(f"главы 2–7: {len(v1)} кусков · с материалом {stats['есть']} · карточек {stats['карточек']} · черновиков 3D {stats['черновиков 3D']}")
    print(f"начало главы 2 {S2:.2f} с · конец выпуска {end:.2f} с ({int(end // 60)}:{end % 60:04.1f})")
    if cards: print("нет материала:\n  " + "\n  ".join(cards[:400]))
    if "--apply" not in sys.argv: return
    ours = jl(IDS).get("ids", [])
    ops = [{"op": "remove", "id": i, "fill": False} for i in ours if any(c["id"] == i for c in proj["clips"])]
    first = min((c for c in clips if c["track"] == "v1"), key=lambda c: c["start"])
    gap = round(first["start"] - (last_pilot["start"] + last_pilot["dur"]), 6)  # стык пилот → глава 2: хвост последнего кадра пилота
    if abs(gap) > 1e-6: ops.append({"op": "set", "id": last_pilot["id"], "fields": {"dur": round(last_pilot["dur"] + gap, 6)}})
    ops += [{"op": "add", "clip": c, "restore": True} for c in clips]
    size = len(json.dumps(ops, ensure_ascii=False).encode())
    step = len(ops) if size < 700_000 else 120                     # пересборка (снять + поставить) — одной ревизией, иначе на дорожке дыры
    for k in range(0, len(ops), step):
        r = subprocess.run(["python3", "studio/editor/cli.py", "--project", "ep04", "op", json.dumps(ops[k:k + step], ensure_ascii=False)],
                           capture_output=True, text=True)
        print((r.stdout or r.stderr).strip()[:200])
        if r.returncode: sys.exit("операции не прошли — остановился")
    json.dump({"ids": [c["id"] for c in clips], "note": "клипы глав 2–7, поставленные build_ep04_ch27.py"}, open(IDS, "w"), ensure_ascii=False, indent=0)
    print("поставлено клипов:", len(clips))


if __name__ == "__main__":
    main()
