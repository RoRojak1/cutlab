#!/usr/bin/env python3
"""ep01 из текущих данных студии → projects/ep01/ (project.json, words.json, review.json).
Источники только читаются: script/script.json, studio/state.json, assets/voice/alignment.json + <part>.words.json.
Запуск: python3 studio/editor/migrate.py ep01 [--force]"""
import glob, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "capcut"))
import model as M
import words as Wd
import timeline as TL

PARTS = ["hook", "learn", "rules", "water_a", "water_b", "travel", "food", "disease", "solutions", "outro", "endblock"]
PRE = {"whoosh": 0.15, "riser": 1.2, "swipe": 0.1}
_DUR = {}


def rel(p):
    return os.path.relpath(str(p), str(M.ROOT)) if p else None


def probe_dur(p):
    if p not in _DUR:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                             capture_output=True, text=True).stdout.strip()
        _DUR[p] = float(out or 0)
    return _DUR[p]


def has_audio(p):
    return bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(p)],
                               capture_output=True, text=True).stdout.strip())


def find_asset(sub, ident):
    for p in sorted(glob.glob(str(M.ROOT / "assets" / sub / "*"))):
        if ident and str(ident) in os.path.basename(p):
            return p
    return None


def build_ep01():
    tl = TL.build()
    al = {x["id"]: x for x in M.read_json(M.ROOT / "assets" / "voice" / "alignment.json")["shots"]}
    words = Wd.build_words(PARTS)
    proj = M.empty_project("ep01", (tl["meta"] or {}).get("title") or "ep01")
    clips = proj["clips"]
    firsts = {}                       # shot → глобальное время первого слова (по alignment)
    for sh in tl["shots"]:
        sid, ef = sh["id"], sh["ef"]
        t0, t1 = M.frame(sh["t_in"]), M.frame(sh["t_out"])
        a = al.get(sid) or {}
        segs = a.get("src") or []
        off = t0
        raw_pos = sh["t_in"]                # позиция в «сырых» секундах ролика (не привязана к кадрам)
        for j, (part, sin, sout) in enumerate(segs):
            raw_pos += sout - sin
            # последний кусок всегда доводим ровно до t1 клипа v1 — иначе независимое
            # округление t0/t1 кадра и суммы длительностей alignment даёт наплыв на
            # соседний кадр на дорожке voice (наблюдалось на стыке H3.2/H4.1)
            seg_end = t1 if j == len(segs) - 1 else M.frame(raw_pos)
            dur = round(seg_end - off, 6)
            if part == "_pause":
                clips.append({"id": f"pause-{sid}", "track": "voice", "kind": "pause", "start": off, "dur": dur})
            else:
                clips.append({"id": f"vo-{sid}-{j}", "track": "voice", "kind": "audio", "part": part,
                              "src": f"assets/voice/{part}.mp3", "start": off, "in": sin, "dur": dur})
            off = seg_end
        if a.get("words"):
            firsts[sid] = t0 + a["words"][0][1]
        base = {"id": sid, "track": "v1", "shot": sid, "chapter": sh["chapter"], "start": t0, "dur": round(t1 - t0, 6),
                "motion": ef["motion"], "transition": ef["transition"], "fit": ef["fit"]}
        if sh["type"] == "NICK" and sh.get("nick") and not sh["file"]:
            bg = find_asset("backgrounds", sh["nick"].get("bg"))
            clips.append(dict(base, kind="image" if bg else "black", **({"src": rel(bg)} if bg else {})))
            nc = find_asset("nick_clips", sh["nick"].get("clip"))
            if nc:
                clips.append({"id": f"nick-{sid}", "track": "nick", "shot": sid, "kind": "keyed", "src": rel(nc),
                              "start": t0, "dur": base["dur"], "loop": True})
            if ef.get("kw"):
                clips.append({"id": f"kw-{sid}", "track": "text", "shot": sid, "style": "keyword", "text": ef["kw"],
                              "start": t0, "dur": base["dur"], "words": []})
        elif sh["type"] == "TEXT":
            clips.append(dict(base, kind="card", text=ef["ost"] or sh["en"]))
        elif sh["file"] and sh["kind"] == "video":
            v = dict(base, kind="video", src=rel(sh["file"]), **{"in": float(ef["video_in"] or 0)},
                     speed=float(ef["speed"] or 1), reverse=False)
            if sh["type"] == "INTRO" or ef["vaudio"] is False or v["speed"] != 1 or not has_audio(sh["file"]):
                v["mute"] = True
            else:
                v["volume_db"] = M.LEVELS["video"]
            clips.append(v)
        elif sh["file"]:
            clips.append(dict(base, kind="image", src=rel(sh["file"])))
        else:
            clips.append(dict(base, kind="black"))
        if sh.get("ost_words"):
            w0 = sh["ost_words"][0][1]
            st = M.frame(t0 + w0)
            clips.append({"id": f"txt-{sid}", "track": "text", "shot": sid, "style": "kinetic", "text": ef["ost"],
                          "start": st, "dur": round(max(1 / 30, t1 - st), 6),
                          "words": [[w, round(t - w0, 3)] for w, t in sh["ost_words"]]})
        for k, tag in enumerate((ef["sfx"] or [])[:2] if sh["type"] != "INTRO" else []):
            p = M.ROOT / "assets" / "sfx" / f"{tag}.wav"
            if p.exists():
                clips.append({"id": f"s-{sid}-{k}", "track": f"sfx{k + 1}", "shot": sid, "tag": tag, "src": rel(p),
                              "start": M.frame(max(0.0, t0 - PRE.get(tag, 0.0))), "dur": round(probe_dur(p), 4),
                              "volume_db": M.LEVELS["sfx"], "pre": PRE.get(tag, 0.0)})
    _music(proj, tl)
    _anchors(proj, words, firsts)
    M.snap_clips(proj)
    proj["revision"] = 1
    return proj, words


def _music(proj, tl):
    runs = []
    for sh in tl["shots"]:
        ef = sh["ef"]
        if sh["type"] == "INTRO":
            if ef["music"]:
                p = M.ROOT / "assets" / "intro" / "intro_music.wav"
                proj["clips"].append({"id": "m-intro", "track": "music", "src": rel(p), "start": M.frame(sh["t_in"]),
                                      "dur": round(probe_dur(p), 4), "loop": False, "volume_db": 0})
            continue
        mood = ef["music"]
        if mood and not mood.startswith("intro"):
            if runs and runs[-1]["mood"] == mood and abs(runs[-1]["end"] - sh["t_in"]) < 0.05:
                runs[-1]["end"] = sh["t_out"]
            else:
                runs.append({"mood": mood, "start": sh["t_in"], "end": sh["t_out"]})
    for n, r in enumerate(runs):
        p = M.ROOT / "assets" / "music" / f"{r['mood']}.wav"
        if p.exists():
            proj["clips"].append({"id": f"m-{n}", "track": "music", "src": rel(p), "start": M.frame(r["start"]),
                                  "dur": round(min(tl["total"], r["end"] + 0.6) - r["start"], 4), "loop": True,
                                  "fade_in": 0.5, "fade_out": 0.8, "volume_db": M.LEVELS["music"]})


def _anchors(proj, words, firsts):
    tw = Wd.timeline_words(proj, words)
    for c in proj["clips"]:
        if c["track"] == "v1" and c["id"] in firsts:
            a = Wd.anchor_for(tw, firsts[c["id"]])
            if a:
                c["anchor"] = {"word": a["word"], "lead": round(a["lead"] + firsts[c["id"]] - c["start"], 4)}
        elif c["track"] in ("text", "sfx1", "sfx2"):
            t = c["start"] + c.get("pre", 0.0)
            a = Wd.anchor_for(tw, t if c["track"] == "text" else firsts.get(c.get("shot"), t))
            if a:
                wt = Wd.word_time(proj, words, a["word"])
                c["anchor"] = {"word": a["word"], "lead": round(wt - c["start"] - c.get("pre", 0.0), 4)}
                if c.get("pre"):
                    c["anchor"]["pre"] = c.pop("pre")
        c.pop("pre", None)


def write_project(pid, proj, words, force=False):
    d = M.pdir(pid)
    pj = d / "project.json"
    if pj.exists() and not force:
        raise M.ProjectError(f"{pj} уже есть — запустите с --force (старый уйдёт в history/)")
    if pj.exists():
        (d / "history").mkdir(parents=True, exist_ok=True)
        shutil.copy2(pj, d / "history" / f"h-{time.strftime('%Y%m%d-%H%M%S')}-before-migrate.json")
    M.save_project(pid, proj)
    M.write_json_atomic(d / "words.json", words)
    if not (d / "review.json").exists():
        M.write_json_atomic(d / "review.json", {"version": 1, "comments": [], "batches": [], "jobs": [], "notifications": []})
    (d / "review").mkdir(exist_ok=True)
    idx_p = M.PROJECTS / "index.json"
    idx = M.read_json(idx_p) if idx_p.exists() else {"version": 1, "projects": []}
    idx["projects"] = [x for x in idx["projects"] if x["id"] != pid] + [
        {"id": pid, "title": proj["title"], "duration": M.duration(proj), "opened": time.time(), "ui": {}}]
    M.write_json_atomic(idx_p, idx)


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "ep01"
    if pid != "ep01":
        sys.exit("пока умею переносить только ep01")
    proj, words = build_ep01()
    write_project(pid, proj, words, force="--force" in sys.argv)
    print(f"{pid}: {len(proj['clips'])} клипов, {M.duration(proj):.2f} с, {round(M.duration(proj) * 30)} кадров")
