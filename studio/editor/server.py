#!/usr/bin/env python3
"""Nick Editor — сервер монтажки. Запуск из корня проекта: python3 studio/editor/server.py (порт 8777).
Порты 8765/8766 не трогает. Проект меняется только операциями (ops.py); изменения рассылаются в окна через SSE."""
import importlib.util, json, mimetypes, os, queue, re, subprocess, sys, threading, time, traceback, urllib.parse
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model as M
import ops as O
import review as R
import history as H
import library as L
import dub as D
import words as Wd

PORT = int(os.environ.get("NICK_EDITOR_PORT", "8777"))
WEB = HERE / "web"
LOCKS = defaultdict(threading.Lock)
INDEX_LOCK = threading.Lock()
_old = None


_old_lock = threading.Lock()


def old_studio():
    """studio/server.py загружаем под другим именем — ради make_thumb (превью).
    Под замком и с присваиванием после загрузки: иначе параллельный запрос превью получал недогруженный модуль."""
    global _old
    with _old_lock:
        if _old is None:
            spec = importlib.util.spec_from_file_location("studio_old_server", HERE.parent / "server.py")
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            _old = m
    return _old



def with_mtimes(proj):
    """копия проекта + _mtimes {src: mtime} для файлов клипов: плеер добавляет ?v= к адресу, перерендер под тем же именем не берётся из кэша"""
    mt = {}
    for c in proj.get("clips", []):
        s = c.get("src")
        if isinstance(s, str) and s and s not in mt:
            try:
                mt[s] = int((M.ROOT / s).stat().st_mtime)
            except OSError:
                pass
    out = dict(proj)
    out["_mtimes"] = mt
    return out

class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class Bus:
    def __init__(self):
        self.subs, self.lock = [], threading.Lock()

    def sub(self, pid):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.subs.append((pid, q))
        return q

    def unsub(self, q):
        with self.lock:
            self.subs = [s for s in self.subs if s[1] is not q]

    def pids(self):
        with self.lock:
            return {p for p, _ in self.subs}

    def pub(self, pid, ev):
        with self.lock:
            targets = [q for p, q in self.subs if p == pid]
        for q in targets:
            try:
                q.put_nowait(ev)
            except queue.Full:
                pass


BUS = Bus()


def load_words(pid):
    p = M.pdir(pid) / "words.json"
    return M.read_json(p) if p.exists() else {"version": 1, "parts": {}}


def index():
    p = M.PROJECTS / "index.json"
    return M.read_json(p) if p.exists() else {"version": 1, "projects": []}


def touch_index(pid, **fields):
    with INDEX_LOCK:
        idx = index()
        for x in idx["projects"]:
            if x["id"] == pid:
                x.update(fields)
        M.write_json_atomic(M.PROJECTS / "index.json", idx)


SEEN = {}          # (pid, файл) → mtime, который сервер уже разослал сам


def remember(pid, *names):
    for name in names:
        f = M.pdir(pid) / name
        if f.exists():
            SEEN[(pid, name)] = f.stat().st_mtime_ns


def watcher():
    """Файлы проекта могли поменять мимо сервера (Claude в прямом режиме) — сообщаем окнам."""
    seen, pres = SEEN, {}
    while True:
        for pid in BUS.pids():
            try:
                d = M.pdir(pid)
                for name, typ in (("project.json", "project"), ("review.json", "review")):
                    f = d / name
                    m = f.stat().st_mtime_ns if f.exists() else 0
                    k = (pid, name)
                    if k in seen and seen[k] != m:
                        ev = {"type": typ}
                        if typ == "project":
                            try:
                                ev.update(revision=M.load_project(pid).get("revision"), changed=[], by="file")
                            except M.ProjectError as e:
                                ev = {"type": "error", "error": str(e)}
                        BUS.pub(pid, ev)
                    seen[k] = m
                st = R.read_presence(pid)
                if pres.get(pid) != st:
                    pres[pid] = st
                    BUS.pub(pid, {"type": "claude", "state": st})
            except Exception:
                traceback.print_exc()
        time.sleep(0.5)


def autosaver():
    last = {}
    while True:
        time.sleep(600)
        for x in index()["projects"]:
            try:
                rev = M.load_project(x["id"]).get("revision")
                if x["id"] not in last:                           # после запуска — от последней сохранённой версии
                    vs = H.list_versions(x["id"])
                    last[x["id"]] = vs[0]["revision"] if vs else None
                if last.get(x["id"]) != rev:
                    H.snapshot(x["id"], "авто")
                last[x["id"]] = rev
            except Exception:
                traceback.print_exc()


class Handler(BaseHTTPRequestHandler):
    server_version = "NickEditor/1"

    def log_message(self, fmt, *a):
        if os.environ.get("NICK_EDITOR_LOG"):
            super().log_message(fmt, *a)

    # ---------- ответы
    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def jbody(self):
        raw = self.body()
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise ApiError(400, "тело — не JSON")

    def serve_file(self, p):
        p = Path(p)
        if not p.is_file():
            raise ApiError(404, "нет файла")
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix == ".mjs" or p.suffix == ".js":
            ctype = "text/javascript"
        start, end_, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m and size:
            g1, g2 = m.group(1), m.group(2)
            unsatisfiable = False
            if g1:
                start = int(g1)
                end_ = min(int(g2), size - 1) if g2 else size - 1
            elif g2 and int(g2) > 0:
                start = max(0, size - int(g2))
                end_ = size - 1
            else:
                unsatisfiable = True  # "bytes=-" (нет чисел) или "bytes=-0" (нулевой суффикс)
            if unsatisfiable or start >= size or start > end_:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end_ - start + 1))
        self.send_header("Cache-Control", "no-cache" if p.is_relative_to(WEB) else "max-age=300")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end_}/{size}")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            left = end_ - start + 1
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    # ---------- маршрутизация
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        u = urllib.parse.urlparse(self.path)
        path, q = urllib.parse.unquote(u.path), dict(urllib.parse.parse_qsl(u.query))
        try:
            if path.startswith("/api/"):
                return self.api(method, path[5:].rstrip("/").split("/"), q)
            if method != "GET":
                raise ApiError(405, "нельзя")
            if path in ("/", "/index.html"):
                return self.serve_file(WEB / "index.html")
            for prefix, root in (("/web/", WEB), ("/assets/", M.ROOT / "assets")):
                if path.startswith(prefix):
                    p = (root / path[len(prefix):]).resolve()
                    if root.resolve() not in p.parents:
                        raise ApiError(403, "вне папки")
                    return self.serve_file(p)
            m = re.match(r"^/projects/([a-z0-9_-]+)/review/([^/]+)$", path)
            if m:
                return self.serve_file(M.pdir(m.group(1)) / "review" / m.group(2))
            m = re.match(r"^/projects/([a-z0-9_-]+)/dubs/([a-z]{2})/([^/]+\.(?:mp3|wav|txt))$", path)
            if m:
                return self.serve_file(M.pdir(m.group(1)) / "dubs" / m.group(2) / m.group(3))
            raise ApiError(404, "нет такой страницы")
        except ApiError as e:
            self.send_json({"error": str(e)}, e.code)
        except (O.OpError, R.ReviewError) as e:
            self.send_json({"error": str(e)}, 400)
        except M.ProjectError as e:
            self.send_json({"error": str(e)}, 409)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def api(self, method, seg, q):
        key = (method, seg[0] if seg else "")
        if key == ("GET", "ping"):
            return self.send_json({"ok": True})
        if key == ("GET", "events"):
            return self.events(q.get("project") or "ep01")
        if key == ("GET", "thumb"):
            return self.thumb(q)
        if key == ("GET", "peaks"):
            return self.send_json(L.peaks(q.get("src", "")))
        if key == ("POST", "upload"):
            return self.upload(q)
        if seg[:2] == ["library", "sounds"]:
            return self.send_json({"sounds": L.sounds()})
        if seg[:2] == ["library", "music"]:
            return self.send_json({"music": L.music()})
        if seg[0] == "projects":
            if len(seg) == 1:
                if method == "GET":
                    return self.send_json(index())
                return self.create_project(self.jbody())
            return self.project_api(method, seg[1], seg[2:])
        raise ApiError(404, f"нет метода {method} {'/'.join(seg)}")

    def create_project(self, b):
        title = (b.get("title") or "Новый выпуск").strip()
        with INDEX_LOCK:
            ids = {x["id"] for x in index()["projects"]}
            n = 2
            while f"ep{n:02d}" in ids or M.pdir(f"ep{n:02d}").exists():
                n += 1
            pid = f"ep{n:02d}"
            p = M.empty_project(pid, title)
            M.pdir(pid).mkdir(parents=True, exist_ok=True)
            M.write_json_atomic(M.pdir(pid) / "project.json", p)
            R.save(pid, R.empty())
            idx = index()
            idx["projects"].append({"id": pid, "title": title, "duration": 0, "opened": time.time(), "ui": {}})
            M.write_json_atomic(M.PROJECTS / "index.json", idx)
        return self.send_json({"id": pid})

    def project_api(self, method, pid, rest):
        M.pdir(pid)
        head = rest[0] if rest else ""
        if method == "GET" and not rest:
            return self.send_json(with_mtimes(M.load_project(pid)))
        if method == "GET" and head == "words":
            return self.send_json({"words": Wd.timeline_words(M.load_project(pid), load_words(pid))})
        if method == "GET" and head == "review":
            r = R.load(pid)
            r["presence"] = R.read_presence(pid)
            return self.send_json(r)
        if method == "GET" and head == "history":
            return self.send_json({"versions": H.list_versions(pid)})
        if method == "GET" and head == "media":
            return self.send_json({"media": L.media_tree(M.load_project(pid), R.fresh_media(R.load(pid)))})
        if method == "GET" and head == "dubs":
            return self.send_json({"dubs": D.status(pid), "langs": {k: v[0] for k, v in D.LANGS.items()}})
        if method == "GET" and head == "dub-estimate":
            w = load_words(pid)
            chars = int(sum(len(t[0]) + 1 for lst in w["parts"].values() for t in lst) * 1.2)
            return self.send_json({"chars": chars, "per_lang": round(chars * D.CR_PER_CHAR * 1.15, 1)})   # +15 % на переозвучку длинных кусков
        if method == "GET" and head == "script":
            sp = M.pdir(pid) / "script.json"
            if not sp.exists() and pid == "ep01":
                sp = M.ROOT / "script" / "script.json"
            shots = M.read_json(sp)["shots"] if sp.exists() else []
            return self.send_json({"shots": [{"id": s["id"], "chapter": s.get("chapter"), "type": s.get("type"), "en": s.get("en") or ""} for s in shots]})
        if method == "GET" and head == "problems":
            out = []
            for c in M.load_project(pid)["clips"]:
                if c.get("src") and not (M.ROOT / c["src"]).exists():
                    out.append({"id": c["id"], "track": c["track"], "start": c["start"], "problem": f"нет файла {c['src']}"})
            return self.send_json({"problems": out})
        if method != "POST":
            raise ApiError(404, "нет метода")
        with LOCKS[pid]:
            return self.project_post(pid, head, rest[1:])

    def project_post(self, pid, head, rest):
        if head == "ops":
            b = self.jbody()
            proj = M.load_project(pid)
            new, inv, changed = O.apply(proj, b.get("ops") or [])
            M.save_project(pid, new)
            remember(pid, "project.json")
            by = b.get("client") or "ui"
            BUS.pub(pid, {"type": "project", "revision": new["revision"], "changed": changed, "by": by})
            touch_index(pid, duration=M.duration(new))
            return self.send_json({"revision": new["revision"], "inverse": inv, "changed": changed,
                                   "rebased": b.get("base_revision") != proj.get("revision"), "project": new})
        if head == "settings":
            b = self.jbody()
            proj = M.load_project(pid)
            if b.get("title"):
                proj["title"] = b["title"].strip()
                touch_index(pid, title=proj["title"])
            if isinstance(b.get("settings"), dict):
                proj["settings"].update(b["settings"])
            proj["revision"] = proj.get("revision", 0) + 1
            M.save_project(pid, proj)
            remember(pid, "project.json")
            BUS.pub(pid, {"type": "project", "revision": proj["revision"], "changed": [], "by": "ui"})
            return self.send_json(proj)
        if head == "ui":
            touch_index(pid, ui=self.jbody().get("ui") or {}, opened=time.time())
            return self.send_json({"ok": True})
        if head == "reveal":
            b = self.jbody()
            base = (M.ROOT if b.get("asset") else M.pdir(pid)).resolve()          # asset — файл кадра/звука из assets/
            p = (base / (b.get("asset") or b.get("path") or "project.json")).resolve()
            if base not in p.parents or not p.exists():
                raise ApiError(404, "нет такого файла")
            subprocess.run(["open", "-R", str(p)])
            return self.send_json({"ok": True})
        if head == "presence":
            R.write_presence(pid, self.jbody().get("state") or "watching")
            return self.send_json({"ok": True})
        if head == "history":
            if rest and rest[-1] == "restore":
                H.restore(pid, rest[0])
                remember(pid, "project.json")
                BUS.pub(pid, {"type": "project", "revision": M.load_project(pid)["revision"], "changed": [], "by": "restore"})
                return self.send_json({"ok": True})
            return self.send_json({"id": H.snapshot(pid, self.jbody().get("label") or "вручную")})
        r = R.load(pid)
        out = self.review_post(pid, r, head, rest)
        R.save(pid, r)
        remember(pid, "review.json")
        BUS.pub(pid, {"type": "review"})
        return self.send_json(out)

    def review_post(self, pid, r, head, rest):
        if head == "review" and rest[:1] == ["propose"]:
            b = self.jbody()
            if b.get("comment") and not any(x["id"] == b["comment"] for x in r["comments"]):
                raise ApiError(404, f"нет правки {b['comment']}")
            proj = M.load_project(pid)
            c = R.propose(r, proj, b.get("clip") or "", b.get("files") or [], b.get("comment"), b.get("text") or "", b.get("notes") or [])
            n = len(c["variants"])
            clip = M.by_id(proj)[c["variant_clip"]]
            note = R.notify(r, "question", f"{n} {'вариант' if n == 1 else 'варианта' if n < 5 else 'вариантов'} для {clip['id']} — выбрать",
                            [{"t": clip["start"], "clip": clip["id"], "text": "выберите в «Правках»", "comment": c["id"]}])
            BUS.pub(pid, {"type": "notify", "notification": note})
            return c
        if head == "review" and rest[:1] == ["settle"]:
            return R.settle_placed(r, M.load_project(pid))
        if head == "review" and rest[:1] == ["comments"]:
            if len(rest) == 1:
                b = self.jbody()
                proj = M.load_project(pid)
                rng = b.get("range")
                words = b.get("words")
                if words is None and rng:
                    words = Wd.words_between(Wd.timeline_words(proj, load_words(pid)), rng[0], rng[1])
                return R.add_comment(r, b.get("text") or "", clips=b.get("clips") or [], range=rng, words=words or "",
                                     type=b.get("type"), higgsfield=b.get("higgsfield"), attachments=b.get("attachments") or [])
            cid, action = rest[1], rest[2] if len(rest) > 2 else ""
            if action == "reply":
                b = self.jbody()
                return R.reply(r, cid, b.get("who") or "user", b.get("text") or "", b.get("status"))
            if action == "status":
                return R.set_status(r, cid, self.jbody().get("status"))
            if action in ("choose", "revert"):
                if not any(x["id"] == cid for x in r["comments"]):
                    raise ApiError(404, f"нет правки {cid}")
                if action == "revert":
                    return R.revert(r, cid)
                b = self.jbody()
                return R.choose(r, cid, b.get("idx"), b.get("prev"))
            if action == "higgsfield":
                c = next((x for x in r["comments"] if x["id"] == cid), None)
                if c is None:
                    raise ApiError(404, f"нет правки {cid}")
                if not c.get("higgsfield"):
                    raise ApiError(400, "в правке нет генерации")
                c["higgsfield"]["approved"] = bool(self.jbody().get("approved"))
                return c
            if action == "snapshot":
                data = self.body()
                c = next((x for x in r["comments"] if x["id"] == cid), None)
                if c is None:
                    raise ApiError(404, f"нет правки {cid}")
                d = M.pdir(pid) / "review"
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{cid}.jpg").write_bytes(data)
                c["snapshot"] = f"review/{cid}.jpg"
                return c
        if head == "fix":
            if not [c for c in R.pending(r) if c.get("batch") is None]:
                raise ApiError(400, "нет новых правок")      # без лишней версии «до правок Claude»
            vid = H.snapshot(pid, "до правок Claude")
            b = R.make_batch(pid, r, vid)
            if not b:
                raise ApiError(400, "нет новых правок")
            return b
        if head == "batches" and len(rest) == 2 and rest[1] == "done":
            b = next((x for x in r["batches"] if x["id"] == rest[0]), None)
            if b is None:
                raise ApiError(404, f"нет пачки {rest[0]}")
            b["status"], b["version_after"] = "done", H.snapshot(pid, "после правок Claude")
            return b
        if head == "jobs":
            b = self.jbody()
            if not rest:
                return R.add_job(pid, r, b.get("type"), b.get("params") or {}, float(b.get("cost") or 0), b.get("approved"))
            return R.set_job(r, rest[0], b.get("status"), b.get("note") or "")
        if head == "notify":
            b = self.jbody()
            n = R.notify(r, b.get("kind") or "done", b.get("title") or "", b.get("items") or [], b.get("batch"))
            BUS.pub(pid, {"type": "notify", "notification": n})
            return n
        if head == "notifications" and rest[:1] == ["read"]:
            R.mark_read(r, self.jbody().get("ids"))
            return {"ok": True}
        raise ApiError(404, f"нет метода {head}")

    def events(self, pid):
        M.pdir(pid)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = BUS.sub(pid)
        try:
            self.wfile.write(b": hi\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(b"data: " + json.dumps(ev, ensure_ascii=False).encode() + b"\n\n")
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            BUS.unsub(q)

    def thumb(self, q):
        p = (M.ROOT / q.get("path", "")).resolve()
        if M.ROOT not in p.parents or not p.is_file():
            raise ApiError(404, "нет файла")
        kind = "video" if p.suffix.lower() in L.VID else "image"
        t = old_studio().make_thumb(p, kind, max(32, min(1280, int(q.get("w") or 240))))
        if not t:
            raise ApiError(500, "превью не получилось")
        self.serve_file(t)

    def upload(self, q):
        shot = re.sub(r"[^A-Za-z0-9._-]", "", q.get("shot") or "")
        name = re.sub(r"[^\w.\- ]", "_", os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename") or "")))
        ext = Path(name).suffix.lower()
        if not shot or ext not in L.IMG | L.VID:
            raise ApiError(400, "нужен кадр и картинка/видео")
        d = M.ROOT / "assets" / "shots" / shot
        d.mkdir(parents=True, exist_ok=True)
        dst = d / name
        k = 2
        while dst.exists():
            dst = d / f"{Path(name).stem}_{k}{ext}"
            k += 1
        dst.write_bytes(self.body())
        return self.send_json({"src": L.rel(dst), "kind": "video" if ext in L.VID else "image"})


def make_server(port=PORT, host="127.0.0.1"):
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=watcher, daemon=True).start()
    return httpd


if __name__ == "__main__":
    if PORT in (8765, 8766):
        sys.exit("порты 8765/8766 заняты другими инструментами — выберите другой NICK_EDITOR_PORT")
    httpd = make_server()
    threading.Thread(target=autosaver, daemon=True).start()
    print(f"Nick Editor: http://127.0.0.1:{httpd.server_address[1]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
