"""Черновая автосборка ep02: материалы в кадры, длинные реплики — подкадрами ~4 с, видео каждые 4–5 кусков,
Ник (хромакей на фоне лаборатории, 5 анимаций Seedance на своих фразах), финальный блок.

Пользователь попросил собрать автоматически (28.09), дальше меняет сам в Cutlab; карточки «Правок» остаются —
в них видно «сейчас» и остальные варианты. Одна пачка операций (⌘Z), перед ней — версия.

  python3 studio/editor/autofill_ep02.py [--dry]
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = [sys.executable, str(ROOT / "studio/editor/cli.py"), "--project", "ep02"]
SH = ROOT / "assets/shots/ep02"
LEAD, TARGET, MINP = 0.12, 3.5, 2.3              # склейка до слова; длина куска; минимальный кусок
BLOCKED = {"assets/shots/ep02/3.14/vid_2_times_square_1956.mp4"}   # номер стока в углу — лицензия под вопросом
IMG, VID = {".png", ".jpg", ".jpeg", ".webp"}, {".mp4", ".mov", ".webm"}
NICK_CLIPS = {  # говорящие клипы на хромакее → подходящий фон лаборатории (PROJECT.md)
    "addf7572": "e566dc7b", "13139fae": "e566dc7b", "c68d59c9": "c3b64f2e", "f79353fc": "c3b64f2e",
    "2e30a2e3": "c3b64f2e", "e66cc4fe": "bc0fe9c8", "fa5d5599": "8ac75081"}
NICK_ANIM = json.loads((ROOT / "assets/voice/ep02/nick/spans.json").read_text())   # кадр → {block, t0, dur}
NICK_MAX = 4.5
END = ROOT / "assets/endblock"


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


def dur(p):
    try:
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ROOT / p)],
                                    capture_output=True, text=True).stdout)
    except ValueError:
        return 0.0


def cli(*args):
    r = subprocess.run([*CLI, *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"cli {args[0]}: {r.stdout[-800:]} {r.stderr[-800:]}")
    return r.stdout.strip()


def tag_of(c):
    m = re.match(r"^\S+\s+\[([^\]]+)\]", c.get("text", ""))
    return m.group(1) if m else ""


def timeline_words(proj):
    """(время на таймлайне, слово с пунктуацией) по всем репликам голоса"""
    out = []
    for c in proj["clips"]:
        if c["track"] != "voice" or not str(c.get("part", "")).startswith("ep02/"):
            continue
        f = ROOT / "assets/voice" / f"{c['part']}.words.json"
        if not f.exists():
            continue
        for t in json.loads(f.read_text())["transcription"]:
            w = t["text"].strip()
            a = t["offsets"]["from"] / 1000.0
            if w and not w.startswith("[") and c.get("in", 0) <= a < c.get("in", 0) + c["dur"]:
                out.append((c["start"] + a - c.get("in", 0), w))
    return sorted(out)


def pools(proj, review):
    """варианты по кадрам: не отвергнутые, выбранный — первым; + свои файлы (AI, графика, 3D) из папки кадра"""
    by = {}
    for c in review["comments"]:
        vs = c.get("variants") or []
        if not vs:
            continue
        clip = c.get("variant_clip") or (c.get("clips") or [None])[0]
        last = (c.get("thread") or [{}])[-1]
        waiting = c.get("chosen") is None and c["status"] in ("new", "working", "reopened") and last.get("who") == "user"
        for i, v in enumerate(vs):
            if v.get("old") or waiting or v["src"] in BLOCKED:
                continue
            by.setdefault(clip, []).append((0 if c.get("chosen") == i else 1, v["src"], v["kind"]))
    for d in SH.iterdir():
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            n = f.name
            if f.suffix.lower() in IMG | VID and re.match(r"^(ai_|gfx_|3d_)", n):
                by.setdefault(d.name, []).append((1, rel(f), "video" if f.suffix.lower() in VID else "image"))
    out = {}
    for clip, lst in by.items():
        seen, res = set(), []
        for _, src, kind in sorted(lst, key=lambda x: x[0]):
            if src not in seen and (ROOT / src).exists():
                seen.add(src); res.append({"src": src, "kind": kind})
        out[clip] = res
    return out


FULL = re.compile(r"/(3D_[A-Z]+/|3d_|gfx_|nick_anim)")


def is_full(src):
    """3D, графика и анимации Ника показываем только целиком (пользователь 29.09)"""
    return bool(FULL.search(src or ""))


def cuts(s, e, n, words):
    """n−1 склеек внутри [s, e) на началах слов, лучше — после знака препинания"""
    cand = [(t, prev.endswith((",", ".", "?", "!", ":", ";", "—"))) for (t, w), (_, prev) in zip(words[1:], words[:-1]) if s + MINP < t < e - MINP]
    res, last = [], s
    for k in range(1, n):
        target = s + (e - s) * k / n
        best = min((c for c in cand if c[0] - LEAD - last >= MINP and e - (c[0] - LEAD) >= MINP),
                   key=lambda c: abs(c[0] - target) - (0.8 if c[1] else 0), default=None)
        if best is None:
            break
        res.append(round(best[0] - LEAD, 4)); last = res[-1]
    return res


CARD = {"D6": "WHAT IF YOU STOPPED SLEEPING?", "3.9": "264 HOURS 25 MINUTES", "5.12": "IN MICE. HUMANS: STILL BEING STUDIED",
        "1.15": "ADENOSINE = “TIME TO SLEEP”", "1.16": "CAFFEINE: A FAKE KEY", "5.5": "A RAT RUNS THE MAZE…", "5.6": "…AND REPLAYS IT IN ITS SLEEP",
        "7.2": "BRAINSTEM: MUSCLES OFF", "7.3": "BARRIER BROKEN = ACTING OUT DREAMS", "7.4": "SLEEP PARALYSIS",
        "7.15": "6 OF 36 · 29 CORRECT ANSWERS", "8.6": "MELATONIN CALLS: +530%", "5.13": "SCIENCE HASN’T PROVED IT YET",
        "9.11": "1 DAY: DRUNK · 3 DAYS: HALLUCINATIONS · 11 DAYS: LOST AT MATH"}


def short(t):
    t = re.split(r"(?<=[.?!])\s", t.strip())[0] if t else ""
    return (t if len(t) <= 48 else t[:46].rsplit(" ", 1)[0] + "…").upper()


def main():
    dry = "--dry" in sys.argv
    en = json.loads((ROOT / "script/ep02_en.json").read_text())
    proj = json.loads((ROOT / "projects/ep02/project.json").read_text())
    review = json.loads((ROOT / "projects/ep02/review.json").read_text())
    words = timeline_words(proj)
    pool = pools(proj, review)
    v1 = sorted((c for c in proj["clips"] if c["track"] == "v1"), key=lambda c: c["start"])
    intro_end = next(c for c in v1 if c["id"] == "INTRO")
    body = [c for c in v1 if c["start"] >= intro_end["start"] + intro_end["dur"] - 1e-3 and "~" not in c["id"] and not c["id"].startswith("E")]
    voice = {c["part"]: c for c in proj["clips"] if c["track"] == "voice" and c.get("part")}
    ops = [{"op": "remove", "id": c["id"], "fill": False} for c in proj["clips"]
           if "~" in c["id"] or c["id"].startswith(("e2-nk-", "e2-end-", "E1", "E2"))]
    used, since_video, stats = set(), 0, {"pieces": 0, "video": 0, "nick": 0, "empty": []}
    nick_n, ids_bg = 0, {p.name.split("_")[3][:8]: rel(p) for p in (ROOT / "assets/backgrounds").glob("*.png")}
    nick_clips = {p.name.split("_")[3][:8]: rel(p) for p in (ROOT / "assets/nick_clips").glob("*.mp4")}
    nick_order = list(NICK_CLIPS)
    anim = {cid: rel(SH / cid / "nick_anim.mp4") for cid in NICK_ANIM if (SH / cid / "nick_anim.mp4").exists()}

    order_ids = [c["id"] for c in body]

    def fits(m, need):                               # видео чуть короче куска — замедлим (не ниже ×0,7)
        return m["kind"] != "video" or dur(m["src"]) >= 0.7 * need

    def take_from(clip_id, want_video, need, from_end=False):
        cands = [m for m in pool.get(clip_id, []) if m["src"] not in used and fits(m, need) and not is_full(m["src"])]
        if from_end:
            cands = cands[::-1]
        if want_video:
            vids = [m for m in cands if m["kind"] == "video"]
            if vids:
                return vids[0]
        non = [m for m in cands if m["kind"] == "image"] + [m for m in cands if m["kind"] == "video"]
        return non[0] if non else None

    def take(clip_id, want_video, need):
        m = take_from(clip_id, want_video, need)
        if m is None:                                # своего нет — неиспользованное у соседей по теме (другие файлы, без повторов)
            i = order_ids.index(clip_id)
            for j, end in ((i - 1, False), (i - 2, False), (i + 1, True), (i + 2, True)):
                if 0 <= j < len(order_ids) and body[j].get("chapter") == body[i].get("chapter"):
                    if end:                          # у следующих кадров берём только лишнее — своё им ещё понадобится
                        left = [x for x in pool.get(order_ids[j], []) if x["src"] not in used]
                        if len(left) <= max(1, round(body[j]["dur"] / TARGET)):
                            continue
                    m = take_from(order_ids[j], want_video, need, from_end=end)
                    if m:
                        break
        return m

    # то, что уже стоит первым куском реплики, резервируем сразу — чтобы соседи его не забрали
    for c in body:
        if c.get("kind") != "card" and c.get("src") and c["src"] not in BLOCKED and c["id"] not in anim:
            used.add(c["src"])
    # границы реплик: от начала реплики до начала следующей (после прошлой автосборки клип — только первый кусок)
    ends = {}
    for i, c in enumerate(body):
        if i + 1 < len(body):
            ends[c["id"]] = body[i + 1]["start"]
        else:
            tail = [x for x in v1 if x["id"].split("~")[0] == c["id"]]
            ends[c["id"]] = max(x["start"] + x["dur"] for x in tail)
    bounds = [c["start"] for c in body] + [ends[body[-1]["id"]]]

    def plan_end(a, D):
        """где закончится анимация длины D с момента a: целиком; если «хвост» в следующей реплике или остаток до конца
        реплики короче MINP — чуть ускорить/замедлить (±20 %), чтобы конец лёг на границу, но не обрезать"""
        t = a + D
        nb = next((b for b in bounds if b >= t - 1e-3), bounds[-1])
        pb = max([b for b in bounds if b < t - 1e-3 and b > a + 1e-3] or [a])
        if pb > a and t - pb < MINP and D / (pb - a) <= 1.2:
            return pb, D / (pb - a)
        if nb - t < MINP and D / (nb - a) >= 0.8:
            return nb, D / (nb - a)
        return t, 1.0

    carry, last_op, placed = None, None, set()                     # анимация, которая доигрывает под следующей репликой; последний кусок
    for c in body:
        s, e = c["start"], ends[c["id"]]
        segs, cur = [], s                            # [начало, конец, материал | ("full", src, a0, speed)]
        if carry and carry["end"] > s + 1e-3:
            ce = min(e, carry["end"])
            segs.append([s, ce, ("full", carry["src"], carry["a"], carry["speed"])])
            cur = ce
            if carry["end"] <= e + 1e-3:
                carry = None
        full, lips = None, False
        if cur < e - 0.5:
            if c["id"] in anim:                      # анимация Ника — строго на своей фразе и со своей скоростью (губы!)
                sp = NICK_ANIM[c["id"]]
                vc = voice.get(f"ep02/{sp['block']}")
                a0 = vc["start"] + sp["t0"] - vc.get("in", 0) if vc else cur
                full, lips = (anim[c["id"]], max(cur, a0)), True
            else:                                    # 3D/графика кадра — целиком
                cand = [m["src"] for m in pool.get(c["id"], []) if is_full(m["src"]) and m["src"] not in placed]   # только своя, один раз
                if cand:
                    full = (cand[0], cur)
        if full:
            src, a0 = full
            gap = a0 - cur
            if lips and 1e-3 < gap < 0.6 and last_op and not segs:   # крошечный зазор до фразы — продлить предыдущий кусок
                (last_op.get("fields") or last_op["clip"])["dur"] = round((last_op.get("fields") or last_op["clip"])["dur"] + gap, 4)
                s = cur = a0
            elif lips and gap >= 0.6:
                segs.append([cur, a0, None])
            elif gap > 1e-3 and gap < MINP:
                a0 = cur
            elif gap >= MINP:
                segs.append([cur, a0, None])
            if lips:
                t_end, speed = a0 + dur(src), 1.0
                nb = next((b for b in bounds if b >= t_end - 1e-3), None)
                if nb is not None and nb - t_end < 0.8:          # до конца реплики меньше 0,8 с — держим последний кадр
                    t_end = nb
            else:
                t_end, speed = plan_end(a0, dur(src))
            used.add(src); placed.add(src)
            last = c is body[-1]                     # последняя реплика — анимация доигрывает целиком, финальный блок после неё
            segs.append([a0, t_end if last else min(e, t_end), ("full", src, a0, speed)])
            if t_end > e + 1e-3 and not last:
                carry = {"src": src, "a": a0, "speed": speed, "end": t_end}
            cur = max(cur, min(e, t_end)) if not last else max(e, t_end)
        if e - cur > 1e-3:                           # обычные куски ~TARGET на словах
            n = max(1, round((e - cur) / TARGET))
            pts = [cur] + cuts(cur, e, n, words) + [e]
            segs += [[pts[i], pts[i + 1], None] for i in range(len(pts) - 1)]
        # материалы для обычных кусков
        first_kept = c.get("kind") != "card" and c.get("src") and c["src"] not in BLOCKED and not is_full(c["src"]) and c["id"] not in anim
        for k, sg in enumerate(segs):
            a, b, m = sg
            if m is not None:
                continue
            if k == 0 and first_kept:
                sg[2] = {"src": c["src"], "kind": c["kind"], "keep": True}; continue
            m = take(c["id"], since_video >= 3, b - a)
            if m is None:                            # материала нет — продлить предыдущий обычный кусок, иначе надпись
                j = next((i for i in range(k - 1, -1, -1) if segs[i][1] - segs[i][0] > 1e-3), None)
                if j is not None and not (isinstance(segs[j][2], tuple)):
                    segs[j][1] = b; sg[1] = sg[0]; continue
                sg[2] = "card"; continue
            used.add(m["src"])
            sg[2] = m
        segs = [sg for sg in segs if sg[1] - sg[0] > 1e-3]
        for k, (a, b, m) in enumerate(segs):
            cid = c["id"] if k == 0 else f"{c['id']}~{k + 1}"
            f = {"start": round(a, 4), "dur": round(b - a, 4), "transition": c.get("transition", "cut") if k == 0 else "cut"}
            if isinstance(m, tuple):                 # целая анимация (или её продолжение под следующей репликой)
                _, src, a0, speed = m
                f.update(kind="video", src=src, motion="static", fit="fill", mute=True, **{"in": round((a - a0) * speed, 4)},
                         speed=None if abs(speed - 1) < 1e-3 else round(speed, 4))
                since_video = 0; stats["video"] += 1
            elif m == "card":                        # материала нет — крупная надпись (как полноэкранные шутки ТОПЛЕС)
                stats["empty"].append(c["id"]); since_video += 1
                f.update(kind="card", text=CARD.get(c["id"]) or short(en.get(c["id"], {}).get("en", "")), motion="static")
            else:
                if m.get("keep"):
                    pass                              # то, что уже стоит — не трогаем
                elif m["kind"] == "video":
                    vd = dur(m["src"]); sp = round(vd / f["dur"], 3) if vd < f["dur"] else None
                    f.update(kind="video", src=m["src"], motion="static", fit="fill", mute=True, **{"in": 0.0}, speed=sp)
                else:
                    f.update(kind="image", src=m["src"], motion="zoom_in" if stats["pieces"] % 2 else "zoom_out", fit="fill", **{"in": None}, speed=None)
                if m["kind"] == "video":
                    since_video = 0; stats["video"] += 1
                else:
                    since_video += 1
            stats["pieces"] += 1
            if k == 0:
                ops.append({"op": "set", "id": cid, "fields": f})
            else:
                clip = {"id": cid, "track": "v1", "shot": c["id"], "chapter": c.get("chapter", ""), "text": f"{cid}", "fit": "fill", **f}
                clip.setdefault("kind", "card"); clip.setdefault("motion", "static")
                ops.append({"op": "add", "restore": True, "clip": clip})
            last_op = ops[-1]
    # финальный блок (assets/endblock): Ник говорит 10 с + заставка 5 с, свой голос и музыка
    t = max([c["start"] + c["dur"] for c in body] + [f["start"] + f["dur"] for f in (o["fields"] for o in ops if o["op"] == "set" and "start" in o.get("fields", {}))])
    nick_end, card = "assets/endblock/nick_talk_wan27_a22219b8.mp4", "assets/endblock/endcard_mini_469da229.mp4"
    ops += [
        {"op": "add", "restore": True, "clip": {"id": "E1.1", "track": "v1", "shot": "E1.1", "chapter": "endblock", "text": "E1.1 endblock", "kind": "video", "src": nick_end,
                                                "start": round(t, 4), "dur": 10.0, "in": 0.0, "mute": True, "motion": "static", "fit": "fill", "transition": "cut"}},
        {"op": "add", "restore": True, "clip": {"id": "E2.1", "track": "v1", "shot": "E2.1", "chapter": "endblock", "text": "E2.1 endcard", "kind": "video", "src": card,
                                                "start": round(t + 10.0, 4), "dur": 5.0, "in": 0.0, "mute": True, "motion": "static", "fit": "fill", "transition": "cut"}},
        {"op": "add", "restore": True, "clip": {"id": "e2-end-vo", "track": "voice", "kind": "audio", "part": "endblock", "src": "assets/endblock/endblock_voice.mp3",
                                                "start": round(t + 0.05, 4), "in": 0.0, "dur": round(dur("assets/endblock/endblock_voice.mp3"), 4)}},
        {"op": "add", "restore": True, "clip": {"id": "e2-end-music", "track": "music", "src": "assets/music/outro_motivation.wav", "start": round(t, 4), "dur": 15.0,
                                                "in": 0.0, "loop": False, "fade_in": 0.5, "fade_out": 1.5, "volume_db": -14}},
    ]
    vids = stats["video"] + len(anim)
    print(f"кусков {stats['pieces']}, из них видео {stats['video']} ({stats['pieces'] / max(1, stats['video']):.1f} куска на видео), анимаций Ника {len(anim)}")
    print(f"средний кусок {(t - body[0]['start']) / max(1, stats['pieces']):.1f} с; без материала: {len(stats['empty'])} → {stats['empty'][:40]}")
    mmss = lambda x: f"{int(x // 60)}:{x % 60:04.1f}"
    print(f"финальный блок с {mmss(t)}, конец {mmss(t + 15)}; операций {len(ops)}")
    if dry:
        return
    print(cli("version", "до автосборки (Claude)"))
    cli("op", json.dumps(ops, ensure_ascii=False))
    print(cli("validate"))
    print(cli("settle"))                 # карточки, чьи варианты автосборка уже поставила, не спрашивают «выберите»


if __name__ == "__main__":
    main()
