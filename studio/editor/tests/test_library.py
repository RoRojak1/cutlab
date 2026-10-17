import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import library as L


class LibraryTest(unittest.TestCase):
    def test_music_has_20_with_license_and_duration(self):
        m = L.music()
        self.assertGreaterEqual(len(m), 20)
        for x in m:
            self.assertTrue(x.get("license"), x["name"])
            self.assertGreater(x["dur"], 1, x["name"])        # outro_sting — 4-секундный акцент

    def test_sounds(self):
        s = L.sounds()
        self.assertGreaterEqual(len(s), 24)
        self.assertIn("whoosh", [x["name"] for x in s])


if __name__ == "__main__":
    unittest.main()
