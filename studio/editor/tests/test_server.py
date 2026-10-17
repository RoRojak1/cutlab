import importlib, json, os, sys, tempfile, threading, time, unittest, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_model_words import tiny


def call(base, method, path, body=None, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def raw_call(base, method, path, headers=None):
    """Для не-JSON ответов (Range 206/416): возвращает (код, заголовки, тело)."""
    req = urllib.request.Request(base + path, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["NICK_PROJECTS"] = cls.tmp.name
        import model, review, history, server
        for m in (model, review, history, server):
            importlib.reload(m)
        cls.M, cls.S = model, server
        p, w = tiny()
        model.save_project("tst", p)
        model.write_json_atomic(Path(cls.tmp.name, "tst", "words.json"), w)
        model.write_json_atomic(Path(cls.tmp.name, "index.json"), {"version": 1, "projects": [{"id": "tst", "title": "Тест", "duration": 6, "opened": 0, "ui": {}}]})
        cls.httpd = server.make_server(port=0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        del os.environ["NICK_PROJECTS"]
        cls.tmp.cleanup()

    def test_ping_projects_project_words(self):
        self.assertEqual(call(self.base, "GET", "/api/ping")[1], {"ok": True})
        self.assertEqual(call(self.base, "GET", "/api/projects")[1]["projects"][0]["id"], "tst")
        st, p = call(self.base, "GET", "/api/projects/tst")
        self.assertEqual((st, len(p["clips"])), (200, 6))
        self.assertEqual(call(self.base, "GET", "/api/projects/tst/words")[1]["words"][2][2], "forty")

    def test_ops_roundtrip_and_errors(self):
        rev = call(self.base, "GET", "/api/projects/tst")[1]["revision"]
        st, r = call(self.base, "POST", "/api/projects/tst/ops", {"base_revision": rev, "client": "t",
                     "ops": [{"op": "set", "id": "A", "fields": {"motion": "zoom_in"}}]})
        self.assertEqual((st, r["revision"], r["changed"]), (200, rev + 1, ["A"]))
        self.assertEqual(self.M.load_project("tst")["clips"][0]["motion"], "zoom_in")
        st, r2 = call(self.base, "POST", "/api/projects/tst/ops", {"base_revision": rev + 1, "ops": r["inverse"]})
        self.assertEqual(st, 200)
        st, e = call(self.base, "POST", "/api/projects/tst/ops", {"base_revision": 0, "ops": [{"op": "nope"}]})
        self.assertEqual(st, 400)
        self.assertIn("неизвестная", e["error"])

    def test_review_fix_signal(self):
        st, c = call(self.base, "POST", "/api/projects/tst/review/comments", {"text": "сдвинь раньше", "clips": ["B"], "range": [2, 4]})
        self.assertEqual((st, c["words"]), (200, "forty million"))
        st, b = call(self.base, "POST", "/api/projects/tst/fix")
        self.assertEqual(st, 200)
        self.assertTrue(Path(self.tmp.name, "tst", "review", "SIGNAL").exists())
        n = len(call(self.base, "GET", "/api/projects/tst/history")[1]["versions"])
        self.assertEqual(call(self.base, "POST", "/api/projects/tst/fix")[0], 400)
        st, h = call(self.base, "GET", "/api/projects/tst/history")
        self.assertEqual(h["versions"][0]["label"], "до правок Claude")
        self.assertEqual(len(h["versions"]), n)                  # пустое «Исправить» не плодит версий

    def test_snapshot_upload(self):
        _, c = call(self.base, "POST", "/api/projects/tst/review/comments", {"text": "картинка плохая", "clips": ["A"]})
        st, c2 = call(self.base, "POST", f"/api/projects/tst/review/comments/{c['id']}/snapshot", raw=b"\xff\xd8\xff\xd9",
                      headers={"Content-Type": "image/jpeg"})
        self.assertEqual((st, c2["snapshot"]), (200, f"review/{c['id']}.jpg"))

    def test_sse_gets_project_event(self):
        got = []

        def listen():
            with urllib.request.urlopen(self.base + "/api/events?project=tst", timeout=10) as r:
                for line in r:
                    if line.startswith(b"data:"):
                        ev = json.loads(line[5:])
                        if ev.get("type") == "project":
                            got.append(ev)
                            return
        th = threading.Thread(target=listen, daemon=True)
        th.start()
        time.sleep(0.3)
        rev = call(self.base, "GET", "/api/projects/tst")[1]["revision"]
        call(self.base, "POST", "/api/projects/tst/ops", {"base_revision": rev, "client": "claude",
             "ops": [{"op": "set", "id": "C", "fields": {"motion": "shake"}}]})
        th.join(5)
        self.assertTrue(got and got[0]["by"] == "claude" and got[0]["changed"] == ["C"])

    def test_broken_project_reports_line(self):
        Path(self.tmp.name, "brk").mkdir()
        Path(self.tmp.name, "brk", "project.json").write_text("{\n oops", encoding="utf-8")
        st, e = call(self.base, "GET", "/api/projects/brk")
        self.assertEqual(st, 409)
        self.assertIn("строка 2", e["error"])

    def test_propose_choose_notifies(self):
        files = ["studio/editor/web/icon-32.png", "studio/editor/web/icon-180.png"]
        st, c = call(self.base, "POST", "/api/projects/tst/review/propose", {"clip": "C", "files": files})
        self.assertEqual((st, c["status"], len(c["variants"])), (200, "question", 2))
        r = call(self.base, "GET", "/api/projects/tst/review")[1]
        self.assertEqual(r["notifications"][-1]["items"][0]["comment"], c["id"])
        self.assertEqual(call(self.base, "GET", "/api/projects/tst/media")[0], 200)
        self.assertEqual(call(self.base, "POST", f"/api/projects/tst/review/comments/{c['id']}/choose", {"idx": 0, "prev": {"src": "c.png", "kind": "image"}})[1]["status"], "done")
        self.assertEqual(call(self.base, "POST", "/api/projects/tst/review/comments/r-nope/choose", {"idx": 0})[0], 404)
        self.assertEqual(call(self.base, "POST", "/api/projects/tst/review/propose", {"clip": "C", "files": ["nope.png"]})[0], 400)

    def test_dubs_status_and_files(self):
        st, d = call(self.base, "GET", "/api/projects/tst/dubs")
        self.assertEqual((st, d["dubs"]), (200, []))
        self.assertIn("es", d["langs"])
        p = Path(self.tmp.name, "tst", "dubs", "es"); p.mkdir(parents=True)
        (p / "meta.txt").write_text("Título")
        st, _, body = raw_call(self.base, "GET", "/projects/tst/dubs/es/meta.txt")
        self.assertEqual((st, body.decode()), (200, "Título"))
        self.assertEqual(raw_call(self.base, "GET", "/projects/tst/dubs/es/plan.json")[0], 404)     # отдаются только звук и meta

    def test_unknown_comment_and_batch_ids_404(self):
        st, e = call(self.base, "POST", "/api/projects/tst/review/comments/NOPE/higgsfield", {"approved": True})
        self.assertEqual(st, 404)
        self.assertIn("нет правки", e["error"])
        st, e = call(self.base, "POST", "/api/projects/tst/review/comments/NOPE/snapshot", raw=b"\xff\xd8\xff\xd9",
                     headers={"Content-Type": "image/jpeg"})
        self.assertEqual(st, 404)
        self.assertIn("нет правки", e["error"])
        st, e = call(self.base, "POST", "/api/projects/tst/batches/NOPE/done")
        self.assertEqual(st, 404)
        self.assertIn("нет пачки", e["error"])

    def test_problems_lists_missing_files(self):
        st, r = call(self.base, "GET", "/api/projects/tst/problems")
        self.assertEqual(st, 200)
        self.assertIn("A", [p["id"] for p in r["problems"]])          # a.png в тестовом проекте не существует

    def test_range_requests(self):
        d = Path(self.tmp.name, "tst", "review")
        d.mkdir(parents=True, exist_ok=True)
        (d / "x.jpg").write_bytes(b"01234567")
        st, hdrs, body = raw_call(self.base, "GET", "/projects/tst/review/x.jpg", {"Range": "bytes=1000000000-"})
        self.assertEqual(st, 416)
        self.assertEqual(hdrs.get("Content-Range"), "bytes */8")
        self.assertEqual(body, b"")
        st, hdrs, body = raw_call(self.base, "GET", "/projects/tst/review/x.jpg", {"Range": "bytes=2-5"})
        self.assertEqual(st, 206)
        self.assertEqual(hdrs.get("Content-Length"), "4")
        self.assertEqual(body, b"2345")


if __name__ == "__main__":
    unittest.main()
