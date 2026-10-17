"""Версии project.json: history/<id>.json + meta в history/index.json."""
import re, shutil, time
import model as M

KEEP = 200


def _dir(pid):
    d = M.pdir(pid) / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index(pid):
    p = _dir(pid) / "index.json"
    return M.read_json(p) if p.exists() else []


def snapshot(pid, label):
    proj = M.load_project(pid)
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:24] or "v"
    vid = f"h-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{slug}"
    shutil.copy2(M.pdir(pid) / "project.json", _dir(pid) / f"{vid}.json")
    idx = [{"id": vid, "at": time.time(), "label": label, "revision": proj.get("revision", 0),
            "duration": M.duration(proj)}] + _index(pid)
    for old in idx[KEEP:]:
        (_dir(pid) / f"{old['id']}.json").unlink(missing_ok=True)
    M.write_json_atomic(_dir(pid) / "index.json", idx[:KEEP])
    return vid


def list_versions(pid):
    return _index(pid)


def restore(pid, vid):
    src = _dir(pid) / f"{vid}.json"
    if not src.exists():
        raise M.ProjectError(f"нет версии {vid}")
    snapshot(pid, "перед откатом")
    proj = M.read_json(src)
    proj["revision"] = M.load_project(pid).get("revision", 0) + 1
    M.save_project(pid, proj)
    return vid
