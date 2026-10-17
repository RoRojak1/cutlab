"""Проект монтажки: пути, чтение, проверка, атомарная запись. Время — секунды, кратные 1/FPS."""
import copy, json, os, re, secrets, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = Path(os.environ.get("NICK_PROJECTS") or (ROOT / "projects"))
FPS = 30
EPS = 0.5 / FPS
TRACKS = [
    {"id": "v1", "kind": "video", "name": "Кадры"},
    {"id": "nick", "kind": "overlay", "name": "Ник"},
    {"id": "text", "kind": "text", "name": "Надписи"},
    {"id": "voice", "kind": "voice", "name": "Голос", "locked": True},
    {"id": "music", "kind": "music", "name": "Музыка"},
    {"id": "sfx1", "kind": "sfx", "name": "Эффекты 1"},
    {"id": "sfx2", "kind": "sfx", "name": "Эффекты 2"},
]
LEVELS = {"voice": 0, "sfx": -9, "music": -17, "video": -22}


class ProjectError(Exception):
    pass


def pdir(pid):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", str(pid)):
        raise ProjectError(f"плохой id проекта: {pid!r}")
    return PROJECTS / pid


def frame(t):
    return round(round(float(t) * FPS) / FPS, 6)


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def new_id(prefix):
    return f"{prefix}-{secrets.token_hex(3)}"


def end(c):
    return c["start"] + c["dur"]


def on_track(proj, track):
    return sorted((c for c in proj["clips"] if c["track"] == track), key=lambda c: c["start"])


def by_id(proj):
    return {c["id"]: c for c in proj["clips"]}


def duration(proj):
    ends = [end(c) for c in proj["clips"] if c["track"] in ("v1", "voice")]
    return frame(max(ends)) if ends else 0.0


def empty_project(pid, title):
    return {"version": 1, "id": pid, "title": title, "fps": FPS, "width": 1920, "height": 1080, "revision": 0,
            "settings": {"voice": "Mark", "levels_db": dict(LEVELS), "dub_langs": []},
            "tracks": [dict(t) for t in TRACKS], "clips": []}


def validate(proj):
    errs = []
    if proj.get("version") != 1:
        errs.append("version должна быть 1")
    tracks = {t["id"] for t in proj.get("tracks", [])}
    seen = set()
    for c in proj.get("clips", []):
        cid = c.get("id")
        if not cid or cid in seen:
            errs.append(f"повтор или пустой id клипа: {cid!r}")
        seen.add(cid)
        if c.get("track") not in tracks:
            errs.append(f"{cid}: нет дорожки {c.get('track')!r}")
        if not isinstance(c.get("start"), (int, float)) or c["start"] < -EPS:
            errs.append(f"{cid}: плохой start")
        if not isinstance(c.get("dur"), (int, float)) or c["dur"] <= 0:
            errs.append(f"{cid}: плохая dur")
    if errs:
        return errs
    for tr in ("v1", "voice"):
        cl = on_track(proj, tr)
        for a, b in zip(cl, cl[1:]):
            if b["start"] < end(a) - EPS:
                errs.append(f"{tr}: {a['id']} и {b['id']} перекрываются")
            elif tr == "v1" and b["start"] > end(a) + EPS:
                errs.append(f"v1: дыра между {a['id']} и {b['id']}")
    return errs


def load_project(pid):
    p = pdir(pid) / "project.json"
    if not p.exists():
        raise ProjectError(f"нет проекта {pid}")
    try:
        proj = read_json(p)
    except json.JSONDecodeError as e:
        raise ProjectError(f"project.json: строка {e.lineno}: {e.msg}")
    errs = validate(proj)
    if errs:
        raise ProjectError("; ".join(errs[:5]))
    return proj


def snap_clips(proj):
    """Начало и конец каждого клипа — к ближайшему кадру (длина = разность, без накопления ошибки)."""
    for c in proj["clips"]:
        e = frame(c["start"] + c["dur"])
        c["start"] = frame(c["start"])
        c["dur"] = round(max(1.0 / FPS, e - c["start"]), 6)


def save_project(pid, proj):
    """Проверяет, приводит к кадрам копию и пишет её. Исходный dict не меняется; возвращает записанную копию."""
    errs = validate(proj)
    if errs:
        raise ProjectError("; ".join(errs[:5]))
    p = copy.deepcopy(proj)
    snap_clips(p)
    errs = validate(p)
    if errs:
        raise ProjectError("; ".join(errs[:5]))
    write_json_atomic(pdir(pid) / "project.json", p)
    return p
