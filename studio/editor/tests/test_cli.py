import importlib, io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_model_words import tiny


class CliDirectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["NICK_PROJECTS"] = self.tmp.name
        os.environ["NICK_EDITOR_URL"] = "http://127.0.0.1:9"          # сервера нет → прямой режим
        import model, review, history, cli
        for m in (model, review, history, cli):
            importlib.reload(m)
        self.M, self.R, self.C = model, review, cli
        p, w = tiny()
        model.save_project("tst", p)
        model.write_json_atomic(Path(self.tmp.name, "tst", "words.json"), w)
        r = review.empty()
        self.cid = review.add_comment(r, "сдвинь склейку раньше", clips=["C"], range=[4, 6])["id"]
        review.save("tst", r)

    def tearDown(self):
        for k in ("NICK_PROJECTS", "NICK_EDITOR_URL"):
            del os.environ[k]
        self.tmp.cleanup()

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = self.C.main(["--project", "tst", *args])
        return code, buf.getvalue()

    def test_parse_time(self):
        self.assertAlmostEqual(self.C.parse_time("6:28.4"), 388.4)
        self.assertAlmostEqual(self.C.parse_time("12.5"), 12.5)

    def test_inbox_and_reply(self):
        code, out = self.run_cli("inbox")
        self.assertEqual(code, 0)
        self.assertIn("сдвинь склейку раньше", out)
        self.assertIn("people here", out)
        self.run_cli("status", self.cid, "working")
        self.run_cli("reply", self.cid, "сдвинул", "--done")
        self.assertEqual(self.R.load("tst")["comments"][0]["status"], "done")

    def test_cut_on_word(self):
        code, out = self.run_cli("cut", "C", "--word", "million")
        self.assertEqual(code, 0, out)
        c = self.M.by_id(self.M.load_project("tst"))["C"]
        self.assertAlmostEqual(c["start"], 2.4667, places=3)       # 2.6 − 0.12 = 2.48 → ближайший кадр 74/30
        self.assertEqual(c["anchor"]["word"], "p:3")

    def test_op_and_validate(self):
        code, _ = self.run_cli("op", json.dumps({"op": "set", "id": "A", "fields": {"motion": "zoom_out"}}))
        self.assertEqual(code, 0)
        self.assertEqual(self.M.by_id(self.M.load_project("tst"))["A"]["motion"], "zoom_out")
        self.assertEqual(self.run_cli("validate")[0], 0)

    def test_show_words_notify(self):
        self.assertIn("forty", self.run_cli("words", "2", "4")[1])
        self.assertIn("B", self.run_cli("show", "0:02.5")[1])
        self.run_cli("notify", "b-0001", "--title", "Готово 1 из 1", "--item", "4.0|C|склейка на 'million'")
        n = self.R.load("tst")["notifications"][-1]
        self.assertEqual(n["items"][0], {"t": 4.0, "clip": "C", "text": "склейка на 'million'"})

    def test_op_bad_json(self):
        code, out = self.run_cli("op", "{bad")
        self.assertEqual(code, 1)
        self.assertIn("ошибка", out)

    def test_show_nonexistent_clip(self):
        code, out = self.run_cli("show", "ZZZ")
        self.assertEqual(code, 1)
        self.assertIn("нет клипа", out)

    def test_cut_first_clip(self):
        code, out = self.run_cli("cut", "A", "--word", "forty")
        self.assertEqual(code, 1)
        self.assertIn("первого кадра", out)

    def test_cut_requires_word_or_t(self):
        try:
            code, out = self.run_cli("cut", "C")
            self.fail("Expected SystemExit with code 2")
        except SystemExit as e:
            self.assertEqual(e.code, 2)

    def test_http_dead_url(self):
        old_url = self.C.URL
        try:
            self.C.URL = "http://127.0.0.1:9"
            with self.assertRaises(SystemExit) as cm:
                self.C.http("GET", "/api/ping")
            self.assertIn("сервер недоступен", str(cm.exception))
        finally:
            self.C.URL = old_url

    def test_wait_signal_picks_up_sent_batch_and_batch_done_resets_presence(self):
        r = self.R.load("tst")
        b = self.R.make_batch("tst", r, "h-x")                   # «Исправить» нажали, пока ожидание не шло
        self.R.save("tst", r)
        code, out = self.run_cli("wait-signal", "--timeout", "1")
        self.assertEqual(code, 0)
        self.assertIn(b["id"], out)
        self.assertEqual(self.R.read_presence("tst"), "working")
        self.run_cli("reply", self.cid, "сдвинул", "--done")    # без status working — проходит сам
        self.assertEqual(self.R.load("tst")["comments"][0]["status"], "done")
        self.run_cli("batch-done", b["id"])
        self.assertEqual(self.R.read_presence("tst"), "watching")
        self.assertEqual(self.run_cli("wait-signal", "--timeout", "0.6")[0], 2)   # пачка закрыта — ждём дальше

    def test_working_presence_survives_long_work(self):
        self.run_cli("status", self.cid, "working")
        pth = Path(self.tmp.name, "tst", "review", "CLAUDE")
        old = __import__("time").time() - 300
        os.utime(pth, (old, old))
        self.assertEqual(self.R.read_presence("tst"), "working")
        self.run_cli("inbox")                                    # любая команда продлевает
        self.assertLess(__import__("time").time() - pth.stat().st_mtime, 5)


if __name__ == "__main__":
    unittest.main()
