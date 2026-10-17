#!/usr/bin/env python3
"""Применить план замен «динамика» (assets/stock/ep03/DYNAMICS_PLAN.json) к проекту Cutlab операциями.

План: участки → клипы v1 → сегменты {t0, t1, kind video|image|gfx_idea, src, in, speed}. Сегменты сводятся в один
сплошной список по участку: gfx_idea → остаётся то, что сейчас в кадре; одинаковое подряд склеивается; обрезки
короче MIN_SEG отдаются соседу. Затем число клипов участка подгоняется (split), склейки двигаются (move_cut:
сначала влево слева направо, потом вправо справа налево — чтобы склейка не выходила за соседний клип), содержимое
ставится через set. Участок пропускается, если его клипы в проекте уже не те, что в плане (правил пользователь).
  python3 studio/editor/apply_dynamics_plan.py --project ep03 [--range "5:16–5:52" ...] [--min-seg 0.4] [--dry]
"""
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "assets/stock/ep03/DYNAMICS_PLAN.json"
MIN_SEG = 0.5
EPS = 0.02


def load_project(pid):
    return json.loads((ROOT / f"projects/{pid}/project.json").read_text())


def op(pid, o, dry):
    if dry:
        print("   op", json.dumps(o, ensure_ascii=False))
        return True
    r = subprocess.run([sys.executable, str(ROOT / "studio/editor/cli.py"), "--project", pid, "op", json.dumps(o)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print("  ", out.splitlines()[-1] if out else r.returncode)
    return r.returncode == 0 and "ошибка" not in out


def content_of(clip, t):
    """содержимое клипа в момент t (для «оставить как есть»)"""
    if clip.get("kind") == "video":
        return {"kind": "video", "src": clip["src"], "in": (clip.get("in") or 0) + (t - clip["start"]) * (clip.get("speed") or 1),
                "speed": clip.get("speed") or 1.0}
    return {"kind": clip.get("kind"), "src": clip.get("src"), "motion": clip.get("motion") or "zoom_in"}


def flatten(r, clips_by_id):
    segs = []
    for c in r["clips"]:
        orig = clips_by_id[c["clip"]]
        for s in c["segments"]:
            if s["kind"] == "gfx_idea" or not s.get("src"):
                ct = content_of(orig, s["t0"])
            elif s["kind"] == "video":
                ct = {"kind": "video", "src": s["src"], "in": float(s.get("in") or 0), "speed": float(s.get("speed") or 1)}
            else:
                ct = {"kind": "image", "src": s["src"], "motion": orig.get("motion") if orig.get("src") == s["src"] else "zoom_in"}
            segs.append({"t0": s["t0"], "t1": s["t1"], **ct, "note": s.get("note") or s.get("phrase") or ""})
    out = []
    for s in segs:                                                  # склеить одинаковое подряд
        if out and out[-1]["src"] == s["src"] and out[-1]["kind"] == s["kind"]:
            p = out[-1]
            cont = s["kind"] != "video" or abs(p["in"] + (s["t0"] - p["t0"]) * p["speed"] - s["in"]) < 0.08
            if cont:
                p["t1"] = s["t1"]
                continue
        out.append(dict(s))
    k = 0                                                           # обрезки — соседу
    while k < len(out):
        s = out[k]
        if s["t1"] - s["t0"] < MIN_SEG and len(out) > 1:
            if k > 0:
                out[k - 1]["t1"] = s["t1"]
            else:
                nx = out[k + 1]
                if nx["kind"] == "video":
                    nx["in"] = max(0.0, nx["in"] - (nx["t0"] - s["t0"]) * nx["speed"])
                nx["t0"] = s["t0"]
            out.pop(k)
            continue
        k += 1
    return out


def apply_range(pid, r, dry):
    proj = load_project(pid)
    v1 = sorted([c for c in proj["clips"] if c["track"] == "v1"], key=lambda c: c["start"])
    by_id = {c["id"]: c for c in v1}
    ids = [c["clip"] for c in r["clips"]]
    for c in r["clips"]:
        x = by_id.get(c["clip"])
        if not x or abs(x["start"] - c["start"]) > 0.05 or abs(x["dur"] - c["dur"]) > 0.05:
            print(f"!! {r['range']}: клип {c['clip']} изменился в проекте — участок пропущен")
            return False
    segs = flatten(r, by_id)
    t_start, t_end = by_id[ids[0]]["start"], by_id[ids[-1]]["start"] + by_id[ids[-1]]["dur"]
    print(f"== {r['range']}: {len(ids)} клипов → {len(segs)} кусков")
    for s in segs:
        print(f"   {s['t0']:.2f}-{s['t1']:.2f} {s['kind']:5s} {Path(s['src']).name}")
    cur = list(ids)
    n_new = 0
    while len(cur) < len(segs):                                     # не хватает клипов — делим самый длинный
        proj = load_project(pid) if not dry else proj
        lens = {c["id"]: c for c in proj["clips"] if c["id"] in cur}
        if dry:
            longest = cur[-1]
            nid = f"{longest}_d{n_new}"
            cur.insert(cur.index(longest) + 1, nid)
            n_new += 1
            print(f"   op split {longest} → {nid}")
            continue
        longest = max(cur, key=lambda i: lens[i]["dur"])
        c = lens[longest]
        nid = f"{longest}_d{n_new}"
        n_new += 1
        if not op(pid, {"op": "split", "id": longest, "t": round(c["start"] + c["dur"] / 2, 4), "new_id": nid}, dry):
            return False
        cur.insert(cur.index(longest) + 1, nid)
    while len(cur) > len(segs):                                     # лишние клипы — убрать с заполнением соседом
        extra = cur.pop()
        if not op(pid, {"op": "remove", "id": extra, "fill": True}, dry):
            return False
    targets = [s["t1"] for s in segs[:-1]]                          # склейки
    proj = load_project(pid) if not dry else proj
    pos = {c["id"]: c for c in proj["clips"] if c["id"] in cur}
    cuts = [] if dry else [pos[cur[i]]["start"] + pos[cur[i]]["dur"] for i in range(len(cur) - 1)]
    order = list(range(len(targets)))
    left = [i for i in order if dry or targets[i] < cuts[i] - EPS]
    right = [i for i in reversed(order) if not dry and targets[i] > cuts[i] + EPS]
    for i in left + right:
        if not op(pid, {"op": "move_cut", "left": cur[i], "right": cur[i + 1], "t": round(targets[i], 4)}, dry):
            return False
    for cid, s in zip(cur, segs):                                   # содержимое
        if s["kind"] == "video":
            f = {"kind": "video", "src": s["src"], "in": round(s["in"], 4), "mute": True, "motion": "static",
                 "speed": s["speed"], "text": f"{cid} · {Path(s['src']).stem}"}
        else:
            f = {"kind": "image", "src": s["src"], "motion": s.get("motion") or "zoom_in", "in": None,
                 "text": f"{cid} · {Path(s['src']).stem}"}
        if not op(pid, {"op": "set", "id": cid, "fields": f}, dry):
            return False
    return True


def main():
    global MIN_SEG
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="ep03")
    ap.add_argument("--range", action="append")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--min-seg", type=float, default=MIN_SEG, help="короче — отдать соседу (с)")
    a = ap.parse_args()
    MIN_SEG = a.min_seg
    plan = json.loads(PLAN.read_text())
    for r in plan:
        if a.range and r["range"] not in a.range:
            continue
        apply_range(a.project, r, a.dry)


if __name__ == "__main__":
    main()
