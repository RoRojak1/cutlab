"""Собирает начало ep02 (холодное начало → 3D → тизер → заставка) прямо на таймлайне Cutlab.

Берёт план из черновика `studio/ep02_roughcut.py` (export/ep02/ep02_roughcut_intro.plan.json — те же файлы,
длины, «начало видео» и скорость): кадры H1…INTRO получают материалы и длины, остальные карточки сдвигаются;
на «Голос» — реплики (у говорящих планов — со сдвигом под губы, тизер — одной дорожкой), на «Музыку» — подложки,
на «Эффекты» — whoosh/нарастание/удар. Одна пачка операций через сервер → отменяется ⌘Z. Перед этим — версия.

  python3 studio/ep02_roughcut.py && python3 studio/editor/assemble_ep02_intro.py
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio"))
import ep02_roughcut as RC   # noqa: E402

CLI = [sys.executable, str(ROOT / "studio/editor/cli.py"), "--project", "ep02"]
DROP = {"T10"}                      # убраны пользователем 28.09


def cli(*args):
    r = subprocess.run([*CLI, *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"cli {args[0]}: {r.stdout[-800:]} {r.stderr[-800:]}")
    return r.stdout.strip()


def main():
    proj = json.loads((ROOT / "projects/ep02/project.json").read_text())
    plan = json.loads((RC.OUT / "ep02_roughcut_intro.plan.json").read_text())
    shots = {s["id"]: s for s in plan["shots"]}
    ops = []
    for c in proj["clips"]:
        if (c["track"] == "v1" and c["id"] in DROP) or (c["track"] != "v1" and c["id"].startswith("e2-")):
            ops.append({"op": "remove", "id": c["id"], "fill": False})

    v1 = sorted((c for c in proj["clips"] if c["track"] == "v1" and c["id"] not in DROP), key=lambda c: c["start"])
    t = 0.0
    for i, c in enumerate(v1):
        f = {"start": round(t, 6)}
        s = shots.get(c["id"])
        if s:
            f.update(dur=s["d"], kind=s["kind"], src=s["src"], fit="fill")
            if s["kind"] == "image":
                f.update(motion="zoom_in" if i % 2 else "zoom_out", **{"in": None}, speed=None)
            else:
                f.update(motion="static", mute=True, **{"in": s["in"]}, speed=s["speed"] if s["speed"] != 1 else None)
            f["transition"] = "flash" if c["id"] == "H4.1" else "cut"
        ops.append({"op": "set", "id": c["id"], "fields": f})
        t += f.get("dur", c["dur"])

    for n, v in enumerate(plan["voice"]):
        ops.append({"op": "add", "restore": True, "clip": {"id": f"e2-vo-{n:02d}", "track": "voice", "kind": "audio", "part": "ep02",
                    "src": v["src"], "start": v["at"], "in": 0.0, "dur": v["dur"]}})
    for s in plan["shots"]:
        if s["id"].startswith("T") or s["id"] in ("H2", "H3"):
            ops.append({"op": "add", "clip": {"id": f"e2-sfx-{s['id']}", "track": "sfx1", "tag": "whoosh", "src": "assets/sfx/whoosh.wav",
                        "start": round(max(0, s["t"] - 0.15), 6), "dur": 0.6, "volume_db": -12}})
    h41, intro = shots["H4.1"]["t"], shots["INTRO"]
    ops += [
        {"op": "add", "clip": {"id": "e2-sfx-riser", "track": "sfx2", "tag": "riser", "src": "assets/sfx/riser.wav", "start": round(max(0, h41 - 1.2), 6), "dur": 1.2, "volume_db": -16}},
        {"op": "add", "clip": {"id": "e2-sfx-hit", "track": "sfx1", "tag": "hit", "src": "assets/sfx/hit.wav", "start": h41, "dur": 0.8, "volume_db": -12}},
        {"op": "add", "clip": {"id": "e2-m-intro", "track": "music", "src": "assets/intro/intro_music.wav", "start": intro["t"], "dur": intro["d"], "loop": False, "volume_db": 0}},
    ]
    span = {s["id"]: (s["t"], s["t"] + s["d"]) for s in plan["shots"]}
    for n, (f, a, b, db, off, fi, fo) in enumerate(RC.music_plan(span)):
        t0, t1 = span[a][0], span[b][1]
        ops.append({"op": "add", "clip": {"id": f"e2-m-{n}", "track": "music", "src": f, "start": round(t0, 6), "dur": round(t1 - t0, 6),
                                          "in": off, "loop": False, "fade_in": fi, "fade_out": fo, "volume_db": db}})
    print(cli("version", "до сборки начала (Claude)"))
    cli("op", json.dumps(ops, ensure_ascii=False))
    print(cli("validate"))
    print(f"собрано: {len(shots)} кадров начала, до конца заставки {intro['t'] + intro['d']:.1f} с")


if __name__ == "__main__":
    main()
