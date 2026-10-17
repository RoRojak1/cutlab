"""Библиотеки и медиа: звуки, музыка, дерево медиа выпуска, пики волны для таймлайна."""
import hashlib, subprocess
from pathlib import Path
import numpy as np
import model as M

IMG = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}
VID = {".mp4", ".mov", ".m4v", ".webm"}
SFX = M.ROOT / "assets" / "sfx"
MUSIC = M.ROOT / "assets" / "music"
PEAKS = M.ROOT / "studio" / ".peaks"
_DUR = {}


def rel(p):
    return str(Path(p).resolve().relative_to(M.ROOT))


def dur(p):
    p = Path(p)
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _DUR:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                             capture_output=True, text=True).stdout.strip()
        _DUR[key] = round(float(out or 0), 3)
    return _DUR[key]


def sounds():
    return [{"name": p.stem, "src": rel(p), "dur": dur(p)} for p in sorted(SFX.glob("*.wav"))]


def music():
    lib = MUSIC / "library.json"
    items = [dict(x) for x in (M.read_json(lib)["tracks"] if lib.exists() else [])]
    known = {x["src"] for x in items}
    for p in sorted(list(MUSIC.glob("*.wav")) + list(MUSIC.glob("*.mp3")) + list(MUSIC.glob("*/*.mp3"))):
        if rel(p) not in known:
            items.append({"name": p.stem, "src": rel(p), "mood": "", "license": "свой синтез"})
    for x in items:
        if (M.ROOT / x["src"]).exists():
            x["dur"] = dur(M.ROOT / x["src"])
    return [x for x in items if "dur" in x]


def media_tree(proj, fresh=frozenset()):
    stp = M.ROOT / "studio" / "state.json"
    st = M.read_json(stp)["shots"] if stp.exists() else {}
    chapters = []
    for c in M.on_track(proj, "v1"):
        sid = c.get("shot") or c["id"]
        if not chapters or chapters[-1]["chapter"] != (c.get("chapter") or ""):
            chapters.append({"chapter": c.get("chapter") or "", "shots": []})
        files = [{"name": f["name"], "src": f["path"], "kind": f["kind"]} for f in (st.get(sid, {}).get("files") or [])]
        have = {f["src"] for f in files}
        d = M.ROOT / "assets" / "shots" / sid
        if d.is_dir():
            for p in sorted(d.iterdir()):
                ext = p.suffix.lower()
                if p.is_file() and ext in IMG | VID and rel(p) not in have:
                    files.append({"name": p.name, "src": rel(p), "kind": "video" if ext in VID else "image"})
        for f in files:
            if f["src"] in fresh and f["src"] != c.get("src"):
                f["new"] = True
        chapters[-1]["shots"].append({"shot": sid, "clip": c["id"], "start": c["start"], "files": files, "used": c.get("src")})
    return chapters


def peaks(src, per_sec=100):
    p = (M.ROOT / src).resolve()
    if M.ROOT not in p.parents or not p.is_file():
        raise M.ProjectError(f"нет файла {src}")
    key = hashlib.sha1(f"{p}|{p.stat().st_mtime_ns}|{per_sec}".encode()).hexdigest()[:20]
    out = PEAKS / f"{key}.json"
    if out.exists():
        return M.read_json(out)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, dtype="<i2").astype(np.int32)
    step = 8000 // per_sec
    n = len(a) // step
    vals = (np.abs(a[: n * step]).reshape(n, step).max(axis=1) // 256).clip(0, 127).astype(int).tolist() if n else []
    res = {"per_sec": per_sec, "peaks": vals}
    M.write_json_atomic(out, res)
    return res
