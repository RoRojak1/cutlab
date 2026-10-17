"""Правки пользователя, пачки для Claude, сигнал, задачи (дубляж), уведомления, присутствие Claude."""
import datetime, json, os, re, time
import library as L
import model as M
import words as Wd

TYPES = ("timing", "image", "higgsfield", "sound", "text", "other")
STATUSES = ("new", "working", "done", "question", "accepted", "reopened")
FLOW = {"new": {"working"}, "reopened": {"working"}, "working": {"done", "question", "new"},
        "question": {"working", "new"}, "done": {"accepted", "reopened"}, "accepted": {"reopened"}}
GUESS = [("higgsfield", r"сгенер|higgsfield|хиксфилд|хигсфилд|нейросет"),
         ("sound", r"звук|громк|тише|громче|эффект|музык|всплеск|шум"),
         ("text", r"надпис|текст|шрифт|титр"),
         ("timing", r"переход|раньше|позже|склейк|тайминг|успева|слов|синхрон|длин"),
         ("image", r"картин|фото|видео|кадр|качеств|изображ")]


class ReviewError(Exception):
    pass


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def empty():
    return {"version": 1, "comments": [], "batches": [], "jobs": [], "notifications": []}


def path(pid):
    return M.pdir(pid) / "review.json"


def load(pid):
    p = path(pid)
    return M.read_json(p) if p.exists() else empty()


def save(pid, r):
    M.write_json_atomic(path(pid), r)


def guess_type(text):
    low = (text or "").lower()
    for t, rx in GUESS:
        if re.search(rx, low):
            return t
    return "other"


def _find(r, cid):
    for c in r["comments"]:
        if c["id"] == cid:
            return c
    raise ReviewError(f"нет правки {cid}")


def add_comment(r, text, clips=(), range=None, words="", type=None, snapshot=None, higgsfield=None, attachments=()):
    if higgsfield is not None:
        need = {"count", "model", "cost", "approved"}
        if not need <= set(higgsfield):
            raise ReviewError("для Higgsfield нужны count, model, cost, approved")
    t = type or ("higgsfield" if higgsfield else guess_type(text))
    if t not in TYPES:
        raise ReviewError(f"неизвестный тип {t}")
    c = {"id": M.new_id("r"), "created": now(), "status": "new", "type": t, "text": text.strip(), "clips": list(clips),
         "range": list(range) if range else None, "words": words, "snapshot": snapshot, "attachments": list(attachments),
         "higgsfield": higgsfield, "thread": [{"who": "user", "at": now(), "text": text.strip()}], "batch": None}
    r["comments"].append(c)
    return c


def set_status(r, cid, status):
    c = _find(r, cid)
    if status not in STATUSES:
        raise ReviewError(f"неизвестный статус {status}")
    if status != c["status"] and status not in FLOW.get(c["status"], set()):
        raise ReviewError(f"{c['status']} → {status} нельзя")
    c["status"] = status
    if status in ("reopened", "new"):
        c["batch"] = None
    return c


def reply(r, cid, who, text, status=None):
    c = _find(r, cid)
    if status in ("done", "question") and c["status"] in ("new", "reopened"):
        set_status(r, cid, "working")        # Claude ответил, не поставив «в работе», — проходим этот шаг сами
    c["thread"].append({"who": who, "at": now(), "text": text.strip()})
    if status:
        set_status(r, cid, status)
    elif who == "user" and c["status"] == "question":
        c["status"] = "new"
        c["batch"] = None
    return c


def _variant(f):
    p = (M.ROOT / f).resolve()
    if M.ROOT not in p.parents or not p.is_file():
        raise ReviewError(f"нет файла {f}")
    ext = p.suffix.lower()
    if ext not in L.IMG | L.VID:
        raise ReviewError(f"{f}: не картинка и не видео")
    return {"src": p.relative_to(M.ROOT).as_posix(), "kind": "video" if ext in L.VID else "image"}


def propose(r, proj, clip, files, cid=None, text="", notes=()):
    """Варианты для клипа: к правке cid или новой карточкой от Claude. В монтаж ставит пользователь (choose)."""
    c0 = M.by_id(proj).get(clip)
    if c0 is None or c0.get("kind") not in ("image", "video", "card"):   # card — заглушка кадра без файла
        raise ReviewError(f"{clip}: нет такого кадра")
    if not files:
        raise ReviewError("нужен хотя бы один файл")
    vs = [dict(_variant(f), note=(list(notes)[i] if i < len(notes) else "")) for i, f in enumerate(files)]
    text = (text or f"{len(vs)} {'вариант' if len(vs) == 1 else 'варианта' if len(vs) < 5 else 'вариантов'} для {clip} — выберите").strip()
    if cid:
        c = _find(r, cid)
        if c.get("chosen") is None:                        # новые варианты по правке — прежние (отвергнутые) сворачиваются
            for v in c.get("variants") or []:
                v["old"] = True
        c.setdefault("variants", []).extend(vs)
        if clip not in c["clips"]:
            c["clips"].append(clip)
        c["thread"].append({"who": "claude", "at": now(), "text": text})
    else:
        c = {"id": M.new_id("r"), "created": now(), "status": "question", "type": "image", "author": "claude", "text": text,
             "clips": [clip], "range": [c0["start"], M.end(c0)], "words": "", "snapshot": None, "attachments": [],
             "higgsfield": None, "thread": [{"who": "claude", "at": now(), "text": text}], "batch": None, "variants": vs}
        r["comments"].append(c)
    c["status"], c["chosen"], c["variant_clip"] = "question", None, clip
    return c


def choose(r, cid, idx, prev=None):
    """Отметка выбора; саму замену клипа делает интерфейс операцией set (её отменяет ⌘Z)."""
    c = _find(r, cid)
    vs = c.get("variants") or []
    if not isinstance(idx, int) or not 0 <= idx < len(vs):
        raise ReviewError("нет такого варианта")
    if prev and not c.get("prev_src"):
        c["prev_src"] = {k: prev.get(k) for k in ("src", "kind", "in")}
    c["chosen"], c["status"], c["batch"] = idx, "done", None
    c["thread"].append({"who": "user", "at": now(), "text": f"поставлен вариант {idx + 1}"})
    # кадр выбран — остальные карточки Claude с вариантами для него больше не спрашивают «выберите»
    clip = c.get("variant_clip") or (c.get("clips") or [None])[0]
    for o in r["comments"]:
        if o is c or o.get("author") != "claude" or o.get("status") != "question" or o.get("chosen") is not None or not o.get("variants"):
            continue
        if (o.get("variant_clip") or (o.get("clips") or [None])[0]) == clip:
            o["status"], o["batch"] = "accepted", None
            o["thread"].append({"who": "user", "at": now(), "text": f"кадр выбран в другой карточке ({c['id']})"})
    return c


FULL_ANIM = re.compile(r"/(3D_[A-Z]+/|3d_|gfx_|nick_anim)")


def settle_placed(r, proj):
    """Карточки «выберите», чей вариант уже стоит в монтаже (автосборка кладёт их в подкадры X~2…) или чей кадр
    занят анимацией (3D, графика, Ник), больше не спрашивают. chosen не трогаем — порядок вариантов для автосборки прежний."""
    where = {}
    for c in proj["clips"]:
        if c.get("track") == "v1" and c.get("src"):
            where.setdefault(c["src"], []).append(c["id"])
    by = M.by_id(proj)
    out = []
    for c in r["comments"]:
        if c.get("status") != "question" or c.get("chosen") is not None or not c.get("variants"):
            continue
        ids = [x for v in c["variants"] if not v.get("old") for x in where.get(v["src"], [])]
        clip = by.get(c.get("variant_clip") or (c.get("clips") or [None])[0]) or {}
        if ids:
            text = f"уже в монтаже: {', '.join(ids)}"
        elif FULL_ANIM.search(clip.get("src") or ""):
            text = f"в кадре анимация ({clip['src'].rsplit('/', 1)[-1]}) — варианты остались в «Медиа»"
        else:
            continue
        c["status"], c["batch"], c["placed"] = "accepted", None, ids
        c["thread"].append({"who": "claude", "at": now(), "text": text})
        out.append(c["id"])
    return out


def revert(r, cid):
    c = _find(r, cid)
    if not c.get("prev_src"):
        raise ReviewError("старого кадра нет — вариант ещё не ставили")
    c["chosen"], c["status"] = None, "question"
    c["thread"].append({"who": "user", "at": now(), "text": "вернул старый кадр"})
    return c


def fresh_media(r):
    """Файлы вариантов, которые ещё не выбраны, — в «Медиа» с меткой «✦ новое»."""
    out = set()
    for c in r["comments"]:
        for i, v in enumerate(c.get("variants") or []):
            if c.get("chosen") != i:
                out.add(v["src"])
    return out


def pending(r):
    return [c for c in r["comments"] if c["status"] in ("new", "reopened")]


def _signal(pid, **kw):
    d = M.pdir(pid) / "review"
    d.mkdir(parents=True, exist_ok=True)
    M.write_json_atomic(d / "SIGNAL", dict(kw, project=pid, at=time.time()))


def make_batch(pid, r, version_before):
    todo = [c for c in pending(r) if c.get("batch") is None]
    if not todo:
        return None
    b = {"id": f"b-{len(r['batches']) + 1:04d}", "at": now(), "comments": [c["id"] for c in todo], "status": "sent",
         "version_before": version_before, "version_after": None}
    for c in todo:
        c["batch"] = b["id"]
    r["batches"].append(b)
    _signal(pid, batch=b["id"], jobs=[j["id"] for j in r["jobs"] if j["status"] == "new"])
    return b


def add_job(pid, r, type, params, cost, approved):
    j = {"id": M.new_id("j"), "type": type, "params": params, "cost": cost, "approved": bool(approved),
         "status": "new", "at": now(), "note": ""}
    r["jobs"].append(j)
    _signal(pid, batch=None, jobs=[x["id"] for x in r["jobs"] if x["status"] == "new"])
    return j


def set_job(r, jid, status, note=""):
    for j in r["jobs"]:
        if j["id"] == jid:
            j["status"], j["note"] = status, note
            return j
    raise ReviewError(f"нет задачи {jid}")


def notify(r, kind, title, items, batch=None):
    n = {"id": M.new_id("n"), "at": now(), "kind": kind, "title": title, "items": list(items), "batch": batch, "read": False}
    r["notifications"].append(n)
    r["notifications"] = r["notifications"][-300:]
    return n


def mark_read(r, ids=None):
    for n in r["notifications"]:
        if ids is None or n["id"] in ids:
            n["read"] = True


def inbox(proj, words, r, batch=None):
    tw = Wd.timeline_words(proj, words)
    byid = M.by_id(proj)
    out = []
    for c in r["comments"]:
        if batch and c.get("batch") != batch:
            continue
        if not batch and c["status"] not in ("new", "reopened", "working"):
            continue
        rng = c.get("range")
        if not rng and c["clips"]:
            cl = [byid[x] for x in c["clips"] if x in byid]
            rng = [min(x["start"] for x in cl), max(M.end(x) for x in cl)] if cl else None
        out.append({"id": c["id"], "status": c["status"], "type": c["type"], "text": c["text"], "thread": c["thread"],
                    "range": rng, "words": c.get("words") or (Wd.words_between(tw, *rng) if rng else ""),
                    "clips": [byid[x] for x in c["clips"] if x in byid], "snapshot": c.get("snapshot"),
                    "attachments": c.get("attachments") or [], "higgsfield": c.get("higgsfield"),
                    "author": c.get("author", "user"), "variants": c.get("variants") or [], "chosen": c.get("chosen")})
    return out


def write_presence(pid, state):
    d = M.pdir(pid) / "review"
    d.mkdir(parents=True, exist_ok=True)
    (d / "CLAUDE").write_text(json.dumps({"state": state, "at": time.time()}), encoding="utf-8")


STALE = {"working": 600}                  # «работает» живёт дольше: между командами Claude бывают долгие паузы


def read_presence(pid):
    p = M.pdir(pid) / "review" / "CLAUDE"
    if not p.exists():
        return "offline"
    try:
        st = json.loads(p.read_text(encoding="utf-8")).get("state", "offline")
    except ValueError:
        return "offline"
    return st if time.time() - p.stat().st_mtime <= STALE.get(st, 90) else "offline"


def touch_presence(pid):
    """Любая команда Claude во время пачки продлевает «работает»."""
    p = M.pdir(pid) / "review" / "CLAUDE"
    try:
        if json.loads(p.read_text(encoding="utf-8")).get("state") == "working":
            write_presence(pid, "working")
    except (OSError, ValueError):
        pass
