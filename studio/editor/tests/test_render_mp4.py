import importlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SR = 48000


def proj(clips):
    return {"version": 1, "id": "rt", "title": "t", "settings": {"levels_db": {"voice": 0, "sfx": -9, "music": -17, "video": -22}},
            "tracks": [{"id": t} for t in ("v1", "nick", "text", "voice", "music", "sfx1", "sfx2")], "clips": clips}


class RenderPlanTest(unittest.TestCase):
    def setUp(self):
        import render_mp4
        self.R = importlib.reload(render_mp4)
        self.cache = Path(tempfile.mkdtemp())

    def segs(self, p, fa, fb, total):
        return self.R.build_segments(p, fa, fb, total, self.cache, ["x"])

    def test_frames_cover_range_and_chunks(self):
        p = proj([{"id": "a", "track": "v1", "start": 0, "dur": 25.0, "kind": "card", "text": "A"},
                  {"id": "b", "track": "v1", "start": 25.0, "dur": 2.0, "kind": "card", "text": "B"},
                  {"id": "vo", "track": "voice", "start": 0, "dur": 30.0, "src": "x.wav"}])
        s = self.segs(p, 0, 900, 900)
        self.assertEqual(sum(x["g1"] - x["g0"] for x in s), 900)
        self.assertEqual([x["kind"] for x in s], ["card", "card", "card", "card", "gap"])   # 25 с → 10+10+5, хвост голоса — чёрный
        self.assertEqual([(x["j0"], x["j1"]) for x in s[:3]], [(0, 300), (300, 600), (600, 750)])
        part = self.segs(p, 310, 620, 900)                              # отрезок --from/--to режет по сетке клипа
        self.assertEqual([(x["j0"], x["j1"]) for x in part], [(310, 600), (600, 620)])

    def test_cache_key_ignores_position_but_not_params(self):
        c = {"id": "a", "track": "v1", "start": 0, "dur": 2.0, "kind": "card", "text": "A"}
        k1 = self.segs(proj([c]), 0, 60, 60)[0]["key"]
        k2 = self.segs(proj([dict(c, start=5.0)]), 150, 210, 210)[-1]["key"]
        k3 = self.segs(proj([dict(c, text="B")]), 0, 60, 60)[0]["key"]
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)

    def test_missing_file_flagged(self):
        s = self.segs(proj([{"id": "a", "track": "v1", "start": 0, "dur": 1.0, "kind": "image", "src": "assets/__nope__.png"}]), 0, 30, 30)
        self.assertTrue(s[0]["missing"])


class RenderAudioTest(unittest.TestCase):
    def setUp(self):
        import render_mp4
        self.R = importlib.reload(render_mp4)

    def test_loop_crossfade_keeps_level(self):
        R = self.R
        buf = np.zeros((SR * 10, 2), np.float32)
        aud = np.ones((SR * 4, 2), np.float32)          # «трек» 4 с из единиц
        L, step = 4.0, max(1.0, 4.0 - R.XF)
        k = 0
        while k * step < 10:
            at = k * step; d = min(L, 10 - at); last = at + d >= 10 - 1e-3
            R.place(buf, 0, aud, at, 0.0, d, 1.0, 0.0 if k == 0 else R.XF, 0.0 if last else R.XF)
            k += 1
        mid = buf[int(0.2 * SR): int(9.8 * SR), 0]
        self.assertLess(np.abs(mid - 1).max(), 1e-3)     # линейная перекрёстная склейка — ровный уровень

    def test_cues_follow_mixplan(self):
        p = proj([{"id": "v", "track": "v1", "start": 0, "dur": 2, "kind": "video", "src": "a.mp4"},
                  {"id": "vm", "track": "v1", "start": 2, "dur": 2, "kind": "video", "src": "a.mp4", "mute": True},
                  {"id": "i", "track": "v1", "start": 4, "dur": 2, "kind": "image", "src": "a.png"},
                  {"id": "m", "track": "music", "start": 0, "dur": 6, "src": "m.mp3", "loop": True, "volume_db": -20},
                  {"id": "p", "track": "voice", "start": 0, "dur": 1, "kind": "pause", "src": "x.wav"}])
        cues = {c["id"]: c for c in self.R.build_cues(p)}
        self.assertEqual(set(cues), {"v", "m"})
        self.assertTrue(cues["v"]["element"] and cues["m"]["loop"])
        self.assertEqual(cues["m"]["gain_db"], -20)


class RenderEndToEndTest(unittest.TestCase):
    def test_short_render(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "projects" / "rt").mkdir(parents=True)
        media = tmp / "media"; media.mkdir()
        t = np.arange(SR * 2) / SR
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", str(media / "vo.wav")],
                       input=(0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32).tobytes(), check=True)
        from PIL import Image
        Image.new("RGB", (800, 600), (40, 120, 200)).save(media / "img.png")
        p = proj([{"id": "a", "track": "v1", "start": 0, "dur": 0.5, "kind": "card", "text": "THEY SPIN", "transition": "glitch"},
                  {"id": "b", "track": "v1", "start": 0.5, "dur": 1.0, "kind": "image", "src": str(media / "img.png"), "motion": "zoom_in"},
                  {"id": "t", "track": "text", "start": 0.5, "dur": 1.0, "text": "264 hours", "words": [["264", 0], ["hours", 0.3]]},
                  {"id": "vo", "track": "voice", "start": 0.1, "dur": 1.5, "src": str(media / "vo.wav")}])
        (tmp / "projects" / "rt" / "project.json").write_text(json.dumps(p))
        env = dict(os.environ, NICK_PROJECTS=str(tmp / "projects"), NICK_EXPORT=str(tmp / "export"))
        out = tmp / "out.mp4"
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "render_mp4.py"), "--project", "rt",
                            "--jobs", "2", "--out", str(out)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        info = json.loads(out.with_suffix(".render.json").read_text())
        self.assertEqual(info["frames"], 48)                     # 1,6 с × 30 (конец голоса)
        self.assertLess(abs(info["lufs"] + 14), 1.0)
        self.assertLessEqual(info["true_peak"], -1.0)


if __name__ == "__main__":
    unittest.main()
