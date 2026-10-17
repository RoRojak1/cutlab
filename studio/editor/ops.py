"""Операции над проектом. apply() не меняет исходник и возвращает обратные операции для отмены."""
import copy
import model as M

CONTENT = ("kind", "src", "in", "speed", "reverse", "fit", "text", "volume_db", "mute", "motion", "transition")
F = 1.0 / M.FPS


class OpError(Exception):
    pass


def _get(p, cid):
    for c in p["clips"]:
        if c["id"] == cid:
            return c
    raise OpError(f"нет клипа {cid}")


def _kind(p, track):
    for t in p["tracks"]:
        if t["id"] == track:
            return t["kind"]
    raise OpError(f"нет дорожки {track}")


def _setf(c, fields):
    for k, v in fields.items():
        if v is None:
            c.pop(k, None)
        else:
            c[k] = v


def op_set(p, op):
    c = _get(p, op["id"])
    if "id" in op["fields"] or "track" in op["fields"]:
        raise OpError("id и дорожку так не меняют")
    old = {k: copy.deepcopy(c.get(k)) for k in op["fields"]}
    _setf(c, copy.deepcopy(op["fields"]))
    return [{"op": "set", "id": c["id"], "fields": old}], {c["id"]}


def op_move_cut(p, op):
    a, b = _get(p, op["left"]), _get(p, op["right"])
    if a["track"] != "v1" or b["track"] != "v1" or abs(M.end(a) - b["start"]) > M.EPS:
        raise OpError("склейка — только между соседними кадрами")
    t = M.frame(op["t"])
    if not (a["start"] + F - M.EPS <= t <= M.end(b) - F + M.EPS):
        raise OpError("склейка вне соседних клипов")
    old_t, old_anchor, bend = b["start"], copy.deepcopy(b.get("anchor")), M.end(b)
    old_in = b.get("in")
    is_video = b.get("kind") == "video"
    if is_video:
        b["in"] = max(0.0, round(b.get("in", 0.0) + (t - old_t) * b.get("speed", 1.0), 4))
    a["dur"] = t - a["start"]
    b["start"], b["dur"] = t, bend - t
    if "anchor" in op:
        _setf(b, {"anchor": op["anchor"]})
    inv = [{"op": "move_cut", "left": a["id"], "right": b["id"], "t": old_t, "anchor": old_anchor}]
    if is_video:
        inv.append({"op": "set", "id": b["id"], "fields": {"in": old_in}})
    return inv, {a["id"], b["id"]}


def _split_at(p, c, t, new_id=None):
    r = copy.deepcopy(c)
    r["id"] = new_id or M.new_id(c["id"].split("-")[0] if c["track"] != "v1" else c["id"])
    cut = t - c["start"]
    r["start"], r["dur"] = t, M.end(c) - t
    if "in" in r:
        r["in"] = round(c.get("in", 0.0) + cut * c.get("speed", 1.0), 4)
    r.pop("anchor", None)
    if "words" in c:
        r["words"] = [[w, round(x - cut, 3)] for w, x in c["words"] if x >= cut]
        c["words"] = [[w, x] for w, x in c["words"] if x < cut]
    c["dur"] = cut
    p["clips"].append(r)
    return r


def _shift(p, t0, d, x, only=None, keep=None):
    """Сдвиг всего, что начинается в t0 и позже; подложки через точку и оверлеи этого кадра растягиваются.
    only — список id для растяжки (из обратной операции: ровно те, что растянула прямая), keep — не трогать.
    Возвращает id растянутых клипов."""
    grown = []
    for c in p["clips"]:
        if c is x or c is keep:
            continue
        if c["start"] >= t0 - M.EPS:
            c["start"] += d
        elif (c["id"] in only) if only is not None else (
                (M.end(c) > t0 + M.EPS and c["track"] == "music")
                or (abs(M.end(c) - t0) <= M.EPS and c.get("shot") == x.get("shot") and c["track"] in ("nick", "text"))):
            c["dur"] += d
            grown.append(c["id"])
    return grown


def _pause_at(p, t0, want=None):
    """Пауза голоса, которой принадлежит точка t0 (включая края); при нескольких — с id want."""
    cand = [v for v in M.on_track(p, "voice") if v.get("kind") == "pause" and v["start"] - M.EPS <= t0 <= M.end(v) + M.EPS]
    return next((v for v in cand if v["id"] == want), cand[0] if cand else None)


def op_ripple(p, op):
    x = _get(p, op["id"])
    if x["track"] != "v1":
        raise OpError("сдвиг с паузой — только для кадров")
    d, t0 = M.frame(op["delta"]), M.end(x)
    if abs(d) < M.EPS:
        return [], set()
    changed = {x["id"]}
    vsplit = None
    only, want = op.get("stretch"), op.get("pause_id")
    if d > 0:
        # точка в паузе или на её краю — удлиняем эту паузу (отмена укорачивания вернёт ту же паузу, без осколков)
        pz = _pause_at(p, t0, want)
        if pz is not None and want and pz["id"] != want and want not in {c["id"] for c in p["clips"]}:
            pz = None                  # отмена: паузу want прямая операция убрала целиком — вернуть её же
        if pz is None:
            for v in M.on_track(p, "voice"):
                if v["start"] + M.EPS < t0 < M.end(v) - M.EPS:
                    old_vdur = v["dur"]
                    r = _split_at(p, v, t0)
                    changed.add(r["id"])
                    vsplit = (v["id"], old_vdur, r["id"])
                    break
        grown = _shift(p, t0, d, x, only, keep=pz)
        x["dur"] += d
        if pz is not None:
            pz["dur"] += d
        else:
            ids = {c["id"] for c in p["clips"]}
            pz = {"id": want if want and want not in ids else M.new_id("pause"), "track": "voice", "kind": "pause",
                  "start": t0, "dur": d}
            p["clips"].append(pz)
        changed.add(pz["id"])
    else:
        n = -d
        pz = next((v for v in M.on_track(p, "voice") if v.get("kind") == "pause"
                   and v["start"] <= t0 - n + M.EPS and M.end(v) >= t0 - M.EPS), None)
        if pz is None or x["dur"] - n < F - M.EPS:
            raise OpError("укоротить так можно только вставленную паузу, речь не режется")
        pz["dur"] -= n
        if pz["dur"] < F - M.EPS:
            p["clips"].remove(pz)
        x["dur"] -= n
        grown = _shift(p, t0, -n, x, only)
        if any(c["dur"] < F - M.EPS for c in p["clips"] if c["id"] in grown):
            raise OpError("надпись или Ник этого кадра короче убираемой паузы — сначала укоротите их")
        changed.add(pz["id"])
    changed |= set(grown)
    inv = [{"op": "ripple", "id": x["id"], "delta": -d, "stretch": grown, "pause_id": pz["id"]}]
    if vsplit:
        v_id, old_vdur, r_id = vsplit
        inv.append({"op": "remove", "id": r_id, "fill": False})
        inv.append({"op": "set", "id": v_id, "fields": {"dur": old_vdur}})
    return inv, changed


def op_move(p, op):
    c = _get(p, op["id"])
    if c["track"] == "v1" or (c["track"] == "voice" and c.get("kind") != "audio"):
        raise OpError("кадры и паузы голоса двигаются склейками")
    if c["track"] == "voice" and op.get("track") and op["track"] != "voice":
        raise OpError("голос — только на дорожке голоса")
    old = {"op": "move", "id": c["id"], "start": c["start"], "track": c["track"], "anchor": copy.deepcopy(c.get("anchor"))}
    if op.get("track") and op["track"] != c["track"]:
        if _kind(p, op["track"]) != _kind(p, c["track"]):
            raise OpError("на эту дорожку такой клип нельзя")
        c["track"] = op["track"]
    c["start"] = max(0.0, float(op["start"]))
    if "anchor" in op:
        _setf(c, {"anchor": op["anchor"]})
    return [old], {c["id"]}


def _clear_range(p, track, a, b):
    inv = []
    for c in list(M.on_track(p, track)):
        s, e = c["start"], M.end(c)
        if e <= a + M.EPS or s >= b - M.EPS:
            continue
        if s >= a - M.EPS and e <= b + M.EPS:
            p["clips"].remove(c)
            inv.append({"op": "add", "clip": copy.deepcopy(c), "restore": True})
        elif s < a and e > b:
            old = {"dur": c["dur"]}
            r = _split_at(p, c, b)
            c["dur"] = a - s
            inv += [{"op": "remove", "id": r["id"], "fill": False}, {"op": "set", "id": c["id"], "fields": old}]
        elif s < a:
            inv.append({"op": "set", "id": c["id"], "fields": {"dur": c["dur"]}})
            c["dur"] = a - s
        else:
            inv.append({"op": "set", "id": c["id"], "fields": {"start": s, "dur": c["dur"], "in": c.get("in")}})
            if "in" in c:
                c["in"] = round(c["in"] + (b - s) * c.get("speed", 1.0), 4)
            c["start"], c["dur"] = b, e - b
    return inv


def op_add(p, op):
    c = copy.deepcopy(op["clip"])
    c.setdefault("id", M.new_id(c.get("track", "clip")))
    if c["id"] in {x["id"] for x in p["clips"]}:
        raise OpError(f"id {c['id']} уже есть")
    _kind(p, c.get("track"))
    if c["track"] in ("v1", "voice") and not op.get("restore"):
        raise OpError("в кадры и голос не добавляют — меняйте содержимое кадра")
    inv = _clear_range(p, c["track"], c["start"], c["start"] + c["dur"]) if op.get("replace") else []
    p["clips"].append(c)
    return [{"op": "remove", "id": c["id"], "fill": False}] + inv, {c["id"]}


def op_remove(p, op):
    c = _get(p, op["id"])
    if c["track"] == "voice" and op.get("fill") is not False:
        raise OpError("голос и паузы так не удаляют — паузу убирает ⌥ + край кадра")
    inv = []
    p["clips"].remove(c)
    if c["track"] == "v1" and op.get("fill", True):
        cl = M.on_track(p, "v1")
        if not cl:
            raise OpError("нельзя удалить последний кадр")
        prev = next((x for x in reversed(cl) if M.end(x) <= c["start"] + M.EPS), None)
        nxt = next((x for x in cl if x["start"] >= M.end(c) - M.EPS), None)
        if prev:
            inv.append({"op": "set", "id": prev["id"], "fields": {"dur": prev["dur"]}})
            prev["dur"] += c["dur"]
        elif nxt:
            inv.append({"op": "set", "id": nxt["id"], "fields": {"start": nxt["start"], "dur": nxt["dur"], "in": nxt.get("in")}})
            if nxt.get("kind") == "video":
                nxt["in"] = max(0.0, round(nxt.get("in", 0.0) - c["dur"] * nxt.get("speed", 1.0), 4))
            nxt["start"], nxt["dur"] = c["start"], nxt["dur"] + c["dur"]
    return inv + [{"op": "add", "clip": copy.deepcopy(c), "restore": True}], {c["id"]}


def op_split(p, op):
    c = _get(p, op["id"])
    if c["track"] == "voice":
        raise OpError("голос не режем")
    t = M.frame(op["t"])
    if not (c["start"] + F - M.EPS <= t <= M.end(c) - F + M.EPS):
        raise OpError("резать можно только внутри клипа")
    old = {"dur": c["dur"], "words": copy.deepcopy(c.get("words"))}
    r = _split_at(p, c, t, op.get("new_id"))
    return [{"op": "remove", "id": r["id"], "fill": False}, {"op": "set", "id": c["id"], "fields": old}], {c["id"], r["id"]}


def op_swap(p, op):
    a, b = _get(p, op["a"]), _get(p, op["b"])
    if a["track"] != "v1" or b["track"] != "v1":
        raise OpError("местами меняются только кадры")
    ca = {k: copy.deepcopy(a.get(k)) for k in CONTENT}
    cb = {k: copy.deepcopy(b.get(k)) for k in CONTENT}
    _setf(a, cb)
    _setf(b, ca)
    return [{"op": "swap", "a": a["id"], "b": b["id"]}], {a["id"], b["id"]}


OPS = {"set": op_set, "move_cut": op_move_cut, "ripple": op_ripple, "move": op_move, "add": op_add,
       "remove": op_remove, "split": op_split, "swap": op_swap}


def apply(proj, ops):
    p = copy.deepcopy(proj)
    inv, changed = [], set()
    for op in ops:
        fn = OPS.get(op.get("op"))
        if not fn:
            raise OpError(f"неизвестная операция {op.get('op')!r}")
        try:
            i, ch = fn(p, op)
        except KeyError as e:
            raise OpError(f"{op.get('op')}: нет поля {e}")
        except (TypeError, ValueError) as e:
            raise OpError(f"{op.get('op')}: неверные поля ({e})")
        inv[:0] = i
        changed |= ch
    M.snap_clips(p)
    errs = M.validate(p)
    if errs:
        raise OpError("; ".join(errs[:3]))
    p["revision"] = proj.get("revision", 0) + 1
    return p, inv, sorted(changed)
