import sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "capcut"))
import model as M, words as Wd, migrate as MG
import timeline as TL


class MigrateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proj, cls.words = MG.build_ep01()
        cls.tl = TL.build()

    def test_valid(self):
        self.assertEqual(M.validate(self.proj), [])

    def test_counts_and_length(self):
        v1 = M.on_track(self.proj, "v1")
        self.assertEqual(len(v1), 394)
        self.assertEqual(round(M.duration(self.proj) * 30), 35373)
        self.assertEqual(len([c for c in self.proj["clips"] if c["track"] in ("sfx1", "sfx2")]), 208)
        self.assertEqual(len(M.on_track(self.proj, "nick")), 36)

    def test_cuts_match_timeline_frame_exact(self):
        v1 = {c["id"]: c for c in M.on_track(self.proj, "v1")}
        for sh in self.tl["shots"]:
            self.assertEqual(round(v1[sh["id"]]["start"] * 30), sh["f0"], sh["id"])

    def test_anchors_consistent(self):
        n = 0
        for c in self.proj["clips"]:
            a = c.get("anchor")
            if not a:
                continue
            wt = Wd.word_time(self.proj, self.words, a["word"])
            self.assertIsNotNone(wt, c["id"])
            self.assertAlmostEqual(wt - a["lead"] - a.get("pre", 0.0), c["start"], delta=0.034, msg=c["id"])
            n += 1
        self.assertGreater(n, 300)

    def test_music_and_intro(self):
        mus = M.on_track(self.proj, "music")
        self.assertTrue(any(c["src"].endswith("intro_music.wav") and c["volume_db"] == 0 for c in mus))
        loops = [c for c in mus if c.get("loop")]
        self.assertTrue(loops and all(c["volume_db"] == -17 for c in loops))
        last = max(loops, key=lambda c: c["start"])
        self.assertTrue(last["src"].endswith("outro_motivation.wav"))          # концовка
        at_1110 = [c for c in loops if c["start"] <= 1110 < M.end(c)]
        self.assertTrue(at_1110 and at_1110[0]["src"].endswith("upbeat_hopeful.wav"))
        self.assertEqual(len(loops), 13)


if __name__ == "__main__":
    unittest.main()
