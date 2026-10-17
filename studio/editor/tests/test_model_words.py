import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model as M
import words as Wd


def tiny():
    """3 кадра по 2 с, голос из одной части 'p' тремя кусками, 6 слов."""
    p = M.empty_project("tst", "Тест")
    p["clips"] = [
        {"id": "A", "track": "v1", "kind": "image", "src": "a.png", "start": 0.0, "dur": 2.0},
        {"id": "B", "track": "v1", "kind": "image", "src": "b.png", "start": 2.0, "dur": 2.0, "anchor": {"word": "p:2", "lead": 0.12}},
        {"id": "C", "track": "v1", "kind": "image", "src": "c.png", "start": 4.0, "dur": 2.0},
        {"id": "vo-A", "track": "voice", "kind": "audio", "part": "p", "src": "p.mp3", "start": 0.0, "in": 0.0, "dur": 2.0},
        {"id": "vo-B", "track": "voice", "kind": "audio", "part": "p", "src": "p.mp3", "start": 2.0, "in": 2.0, "dur": 2.0},
        {"id": "vo-C", "track": "voice", "kind": "audio", "part": "p", "src": "p.mp3", "start": 4.0, "in": 4.0, "dur": 2.0},
    ]
    words = {"version": 1, "parts": {"p": [["one", 0.1, 0.4], ["two", 1.0, 1.3], ["forty", 2.12, 2.5],
                                           ["million", 2.6, 3.0], ["people", 4.12, 4.5], ["here", 5.0, 5.3]]}}
    return p, words


class ModelTest(unittest.TestCase):
    def test_frame_rounds_to_30fps(self):
        self.assertAlmostEqual(M.frame(1.0 / 30 * 10 + 0.004), 10 / 30, places=6)

    def test_validate_ok_and_errors(self):
        p, _ = tiny()
        self.assertEqual(M.validate(p), [])
        p["clips"][1]["start"] = 2.5          # дыра между A и B + перекрытие B и C
        errs = " ".join(M.validate(p))
        self.assertIn("дыра", errs)
        self.assertIn("перекрываются", errs)

    def test_save_load_roundtrip_and_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["NICK_PROJECTS"] = d
            import importlib; importlib.reload(M)
            p, _ = tiny()
            M.save_project("tst", p)
            self.assertEqual(M.load_project("tst")["clips"][1]["id"], "B")
            self.assertEqual([x.name for x in Path(d, "tst").iterdir() if x.name.endswith(".tmp")], [])
            Path(d, "tst", "project.json").write_text("{ broken", encoding="utf-8")
            with self.assertRaises(M.ProjectError) as e:
                M.load_project("tst")
            self.assertIn("строка", str(e.exception))
            del os.environ["NICK_PROJECTS"]; importlib.reload(M)

    def test_bad_pid(self):
        with self.assertRaises(M.ProjectError):
            M.pdir("../etc")

    def test_save_rejects_bad_clip_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["NICK_PROJECTS"] = d
            import importlib; importlib.reload(M)
            # Test 1: missing "dur" should raise ProjectError (not KeyError)
            p = M.empty_project("tst", "Тест")
            p["clips"] = [{"id": "A", "track": "v1", "kind": "image", "src": "a.png", "start": 0.0}]
            with self.assertRaises(M.ProjectError):
                M.save_project("tst", p)
            # Test 2: valid project with snapshot should not mutate original dur
            p, _ = tiny()
            p["clips"][1]["dur"] = 2.0123456
            p["clips"].append({"id": "D", "track": "v1", "kind": "image", "src": "d.png", "start": 6.0, "dur": 2.0})
            p["clips"].append({"id": "A", "track": "v1", "kind": "image", "src": "a2.png", "start": 8.0, "dur": 2.0})  # duplicate id
            original_dur = p["clips"][1]["dur"]
            with self.assertRaises(M.ProjectError):
                M.save_project("tst", p)
            self.assertEqual(p["clips"][1]["dur"], original_dur)  # original unchanged
            del os.environ["NICK_PROJECTS"]; importlib.reload(M)


class WordsTest(unittest.TestCase):
    def test_word_time_and_timeline_words(self):
        p, w = tiny()
        self.assertAlmostEqual(Wd.word_time(p, w, "p:2"), 2.12)
        tw = Wd.timeline_words(p, w)
        self.assertEqual([x[2] for x in tw], ["one", "two", "forty", "million", "people", "here"])

    def test_snap_uses_lead(self):
        p, w = tiny()
        tw = Wd.timeline_words(p, w)
        t, ref = Wd.snap(tw, 2.05)
        self.assertAlmostEqual(t, 2.0)
        self.assertEqual(ref, "p:2")
        self.assertIsNone(Wd.snap(tw, 3.6, max_dist=0.1))

    def test_words_between_find_anchor(self):
        p, w = tiny()
        tw = Wd.timeline_words(p, w)
        self.assertEqual(Wd.words_between(tw, 2.0, 4.0), "forty million")
        self.assertEqual(Wd.find_word(tw, "people")[1], "p:4")
        a = Wd.anchor_for(tw, 4.0)
        self.assertEqual(a["word"], "p:4")
        self.assertAlmostEqual(a["lead"], 0.12)

    def test_build_words_from_whisper_json(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "x.words.json").write_text('{"transcription": [{"offsets": {"from": 60, "to": 1030}, "text": " Manhattan,"},'
                                               '{"offsets": {"from": 1030, "to": 2460}, "text": " 21-26,"}]}', encoding="utf-8")
            w = Wd.build_words(["x"], Path(d))
            self.assertEqual(w["parts"]["x"], [["manhattan", 0.06, 1.03], ["21", 1.03, 2.46], ["26", 1.03, 2.46]])


if __name__ == "__main__":
    unittest.main()
