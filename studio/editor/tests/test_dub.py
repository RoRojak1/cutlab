import importlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SR = 48000


def tone(path, dur, freq=440.0, amp=0.3, ch=1, lead=0.0):
    t = np.arange(int(dur * SR)) / SR
    a = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    a[: int(lead * SR)] = 0
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-ac", str(ch), str(path)],
                   input=a.tobytes(), check=True)


class DubTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["NICK_PROJECTS"] = str(root / "projects")
        import model, dub
        importlib.reload(model); importlib.reload(dub)
        self.M, self.D = model, dub
        media = root / "media"; media.mkdir()
        tone(media / "voice_track.wav", 12)
        tone(media / "music.wav", 12, 220, 0.1, ch=2)
        tone(media / "hit.wav", 0.5, 880, 0.2, ch=2)
        dub.REF_VOICE = media / "voice_track.wav"
        seg = lambda mid, at, dur, src=0.0, vol=1.0: {"material_id": mid, "target_timerange": {"start": int(at * 1e6), "duration": int(dur * 1e6)},
                                                    "source_timerange": {"start": int(src * 1e6), "duration": int(dur * 1e6)}, "volume": vol, "speed": 1.0}
        self.draft_dir = root / "draft"; self.draft_dir.mkdir()
        (self.draft_dir / "draft_info.json").write_text(json.dumps({
            "duration": int(10e6),
            "materials": {"audios": [{"id": "v", "path": str(media / "voice_track.wav")}, {"id": "m", "path": str(media / "music.wav")},
                                     {"id": "h", "path": str(media / "hit.wav")}]},
            "tracks": [{"type": "audio", "name": "Голос", "segments": [seg("v", 0, 5), seg("v", 5, 5, 5.5)]},   # вырезано 0,5 с на 5 с
                       {"type": "audio", "name": "Музыка", "segments": [seg("m", 0, 10)]},
                       {"type": "audio", "name": "Эффекты 1", "segments": [seg("h", 2, 0.5, vol=0.3548)]},
                       {"type": "video", "segments": []}]}))
        self.al = {"shots": [{"id": "A", "voiced": True, "t_in": 0.0, "words": [["one", 0.2]]},
                             {"id": "B", "voiced": True, "t_in": 3.0, "words": [["two", 0.1]]},
                             {"id": "X", "voiced": False, "t_in": 4.0, "words": []},
                             {"id": "C", "voiced": True, "t_in": 6.0, "words": [["three", 0.0]]}]}
        self.sc = {"shots": [{"id": "A", "chapter": "hook", "en": "One."}, {"id": "B", "chapter": "hook", "en": "Two"},
                             {"id": "X", "chapter": "hook", "en": ""}, {"id": "C", "chapter": "rules", "en": "Three."}]}

    def tearDown(self):
        del os.environ["NICK_PROJECTS"]
        self.tmp.cleanup()

    def test_draft_mapping_and_plan(self):
        dr = self.D.read_draft(self.draft_dir)
        self.assertEqual((len(dr["voice"]), len(dr["bed"]), dr["duration"]), (2, 2, 10.0))
        self.assertAlmostEqual(self.D.to_target(dr["voice"], 6.0), 5.5)        # после выреза — на 0,5 с раньше
        self.assertAlmostEqual(self.D.to_target(dr["voice"], 5.2), 5.0)        # в вырезанном куске — начало следующего
        pl = self.D.plan(dr, self.al, self.sc, "es")
        self.assertEqual([r["id"] for r in pl["shots"]], ["A", "B", "C"])       # X без речи пропущен
        self.assertEqual([r["t0"] for r in pl["shots"]], [0.2, 3.1, 5.5])
        self.assertEqual(pl["shots"][0]["budget"], int((3.1 - 0.2 - 0.12) * 16.5))
        with self.assertRaises(self.D.DubError):
            self.D.plan(dr, self.al, self.sc, "xx")
        self.assertEqual(self.D.lang_ok("es-419"), "es"); self.assertEqual(self.D.lang_ok("pt-BR"), "pt")

    def test_blocks_split_by_chapter_and_require_text(self):
        pl = self.D.plan(self.D.read_draft(self.draft_dir), self.al, self.sc, "es")
        with self.assertRaises(self.D.DubError):
            self.D.blocks(pl, {"A": "Uno."})
        bl = self.D.blocks(pl, {"A": "Uno.", "B": "Dos", "C": "Tres."})
        self.assertEqual([b["shots"] for b in bl["blocks"]], [["A", "B"], ["C"]])
        self.assertEqual(bl["blocks"][0]["text"], "Uno. Dos")
        self.assertAlmostEqual(bl["blocks"][0]["end"], 5.5 - 0.12)
        self.assertEqual(bl["blocks"][1]["end"], 10.0)

    def test_build_fits_mixes_and_reports_overflow(self):
        dr = self.D.read_draft(self.draft_dir)
        pl = self.D.plan(dr, self.al, self.sc, "es")
        bl = self.D.blocks(pl, {"A": "Uno.", "B": "Dos", "C": "Tres."})
        tts = self.D.ddir("ep", "es") / "tts"; tts.mkdir(parents=True)
        tone(tts / "b001.mp3", 5.8, 330, lead=0.3)       # место 5,18 с: речь 5,8 → ×1,12 — влезает
        tone(tts / "b002.mp3", 7.0, 330)                 # место 4,5 с: даже ×1,15 не влезет
        rep = self.D.build("ep", "es", dr, bl, bitrate="128k")
        b1, b2 = rep["blocks"]
        self.assertGreater(b1["tempo"], 1.0); self.assertEqual(b1["overflow"], 0)
        self.assertEqual(b2["tempo"], 1.15); self.assertGreater(b2["overflow"], 1.0)
        self.assertEqual([r["id"] for r in rep["overflow"]], ["b002"])
        mp3 = self.D.ddir("ep", "es") / "ep_es.mp3"
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
                                   capture_output=True, text=True).stdout)
        self.assertAlmostEqual(dur, 10.0, delta=0.06)
        self.assertEqual(self.D.status("ep")[0]["status"], "done")
        bed_files = list((self.D.ddir("ep") / "_bed").glob("bed-*.f32"))
        self.assertEqual(len(bed_files), 1)                                     # подложка одна на все языки
        bed = np.load(bed_files[0], mmap_mode="r")
        rms = lambda a, b: float(np.sqrt(np.mean(np.square(bed[int(a * SR):int(b * SR)]))))
        self.assertGreater(rms(1.0, 1.4), 0.03)                                  # музыка
        self.assertGreater(rms(2.0, 2.4), rms(1.0, 1.4) * 1.2)                   # + эффект на 2 с


if __name__ == "__main__":
    unittest.main()
