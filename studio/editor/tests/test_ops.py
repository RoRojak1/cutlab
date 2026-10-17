import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model as M, ops as O, words as Wd
from test_model_words import tiny


def ids(p, tr):
    return [(c["id"], round(c["start"], 3), round(c["dur"], 3)) for c in M.on_track(p, tr)]


class OpsTest(unittest.TestCase):
    def setUp(self):
        self.p, self.w = tiny()
        self.p["clips"].append({"id": "M", "track": "music", "src": "m.wav", "start": 0.0, "dur": 6.0, "loop": True})
        self.p["clips"].append({"id": "S", "track": "sfx1", "src": "s.wav", "start": 3.9, "dur": 0.5})

    def roundtrip(self, ops):
        p2, inv, ch = O.apply(self.p, ops)
        p3, _, _ = O.apply(p2, inv)
        for tr in ("v1", "voice", "music", "sfx1"):
            self.assertEqual([x[1:] for x in ids(p3, tr)], [x[1:] for x in ids(self.p, tr)], tr)
        return p2, ch

    def test_set_and_inverse(self):
        p2, ch = self.roundtrip([{"op": "set", "id": "A", "fields": {"motion": "zoom_in", "src": None}}])
        a = M.by_id(p2)["A"]
        self.assertEqual(a["motion"], "zoom_in"); self.assertNotIn("src", a); self.assertEqual(ch, ["A"])

    def test_move_cut_keeps_total_and_voice(self):
        p2, _ = self.roundtrip([{"op": "move_cut", "left": "A", "right": "B", "t": 1.5, "anchor": None}])
        self.assertEqual(ids(p2, "v1")[:2], [("A", 0.0, 1.5), ("B", 1.5, 2.5)])
        self.assertEqual(M.duration(p2), M.duration(self.p))
        self.assertEqual(ids(p2, "voice"), ids(self.p, "voice"))
        self.assertNotIn("anchor", M.by_id(p2)["B"])

    def test_move_cut_rejects_far(self):
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "move_cut", "left": "A", "right": "B", "t": 4.5}])
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "move_cut", "left": "A", "right": "C", "t": 3.0}])

    def test_move_cut_undo_restores_clamped_video_in(self):
        b = M.by_id(self.p)["B"]
        b["kind"] = "video"
        b["in"] = 0.1
        p2, inv, _ = O.apply(self.p, [{"op": "move_cut", "left": "A", "right": "B", "t": 1.5}])
        self.assertEqual(M.by_id(p2)["B"]["in"], 0.0)          # ушёл в упор в 0
        p3, _, _ = O.apply(p2, inv)
        self.assertAlmostEqual(M.by_id(p3)["B"]["in"], 0.1, places=4)   # а не пересчитан заново из 0
        self.assertEqual(ids(p3, "v1"), ids(self.p, "v1"))

    def test_ripple_inserts_pause_and_shifts(self):
        p2, _ = self.roundtrip([{"op": "ripple", "id": "A", "delta": 0.8}])
        self.assertEqual(ids(p2, "v1"), [("A", 0.0, 2.8), ("B", 2.8, 2.0), ("C", 4.8, 2.0)])
        pauses = [c for c in M.on_track(p2, "voice") if c.get("kind") == "pause"]
        self.assertEqual([(round(c["start"], 3), round(c["dur"], 3)) for c in pauses], [(2.0, 0.8)])
        self.assertAlmostEqual(M.by_id(p2)["S"]["start"], 4.7, places=3)
        self.assertAlmostEqual(M.by_id(p2)["M"]["dur"], 6.8, places=3)
        b = M.by_id(p2)["B"]            # якорь остаётся верным: слово сдвинулось вместе с голосом
        self.assertAlmostEqual(Wd.word_time(p2, self.w, b["anchor"]["word"]) - b["anchor"]["lead"], b["start"], places=3)

    def test_ripple_splits_voice_inside_speech(self):
        self.p["clips"] = [c for c in self.p["clips"] if c["id"] not in ("vo-A", "vo-B")]
        self.p["clips"].append({"id": "vo-AB", "track": "voice", "kind": "audio", "part": "p", "src": "p.mp3", "start": 0.0, "in": 0.0, "dur": 4.0})
        p2, _, _ = O.apply(self.p, [{"op": "ripple", "id": "A", "delta": 0.5}])
        v = [(round(c["start"], 3), round(c["dur"], 3), c.get("in")) for c in M.on_track(p2, "voice")]
        self.assertEqual(v[:3], [(0.0, 2.0, 0.0), (2.0, 0.5, None), (2.5, 2.0, 2.0)])

    def test_ripple_split_voice_remerges_on_undo(self):
        self.p["clips"] = [c for c in self.p["clips"] if c["id"] not in ("vo-A", "vo-B")]
        self.p["clips"].append({"id": "vo-AB", "track": "voice", "kind": "audio", "part": "p", "src": "p.mp3", "start": 0.0, "in": 0.0, "dur": 4.0})
        p2, inv, _ = O.apply(self.p, [{"op": "ripple", "id": "A", "delta": 0.5}])
        p3, _, _ = O.apply(p2, inv)
        voice = M.on_track(p3, "voice")
        self.assertEqual([c["id"] for c in voice], ["vo-AB", "vo-C"])          # склеенное обратно, без осколка
        ab = M.by_id(p3)["vo-AB"]
        self.assertAlmostEqual(ab["start"], 0.0, places=3)
        self.assertAlmostEqual(ab["dur"], 4.0, places=3)
        self.assertAlmostEqual(ab.get("in"), 0.0, places=3)
        vc = M.by_id(p3)["vo-C"]
        self.assertAlmostEqual(vc["start"], 4.0, places=3)
        self.assertAlmostEqual(vc["dur"], 2.0, places=3)

    def test_ripple_negative_only_removes_pause(self):
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "ripple", "id": "A", "delta": -0.5}])
        p2, _, _ = O.apply(self.p, [{"op": "ripple", "id": "A", "delta": 0.8}])
        p3, _, _ = O.apply(p2, [{"op": "ripple", "id": "A", "delta": -0.3}])
        pauses = [round(c["dur"], 3) for c in M.on_track(p3, "voice") if c.get("kind") == "pause"]
        self.assertEqual(pauses, [0.5])

    def test_ripple_undo_redo_exact(self):
        # надпись кадра A тянется дальше конца A; после ripple конец A совпадает с её концом — отмена не должна её укоротить
        self.p["clips"][0]["shot"] = "A"
        self.p["clips"].append({"id": "tA", "track": "text", "shot": "A", "text": "X", "start": 1.0, "dur": 1.8})
        p2, inv, _ = O.apply(self.p, [{"op": "ripple", "id": "A", "delta": 0.8}])
        p3, inv2, _ = O.apply(p2, inv)
        self.assertAlmostEqual(M.by_id(p3)["tA"]["dur"], 1.8, places=3)
        p4, _, _ = O.apply(p3, inv2)                                  # повтор — те же id паузы
        self.assertEqual(sorted(c["id"] for c in p4["clips"]), sorted(c["id"] for c in p2["clips"]))

    def test_ripple_negative_undo_keeps_one_pause(self):
        p2, _, _ = O.apply(self.p, [{"op": "ripple", "id": "A", "delta": 0.8}])
        p3, inv, _ = O.apply(p2, [{"op": "ripple", "id": "A", "delta": -0.3}])
        p4, _, _ = O.apply(p3, inv)
        pauses = [(c["id"], round(c["dur"], 3)) for c in M.on_track(p4, "voice") if c.get("kind") == "pause"]
        before = [(c["id"], round(c["dur"], 3)) for c in M.on_track(p2, "voice") if c.get("kind") == "pause"]
        self.assertEqual(pauses, before)                              # одна пауза 0,8 с, без осколков

    def test_move_voice_line(self):
        # отдельную реплику голоса можно сдвинуть (подогнать под губы), но не на другую дорожку и не внахлёст
        p2, _ = self.roundtrip([{"op": "move", "id": "vo-C", "start": 4.3}])
        self.assertAlmostEqual(M.by_id(p2)["vo-C"]["start"], 4.3)
        with self.assertRaises(Exception):
            O.apply(self.p, [{"op": "move", "id": "vo-B", "start": 2.5}])
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "move", "id": "vo-C", "start": 4.3, "track": "music"}])

    def test_move_and_track_kind(self):
        p2, _ = self.roundtrip([{"op": "move", "id": "S", "start": 1.0, "track": "sfx2"}])
        self.assertEqual(M.by_id(p2)["S"]["track"], "sfx2")
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "move", "id": "S", "start": 1.0, "track": "music"}])
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "move", "id": "A", "start": 1.0}])

    def test_add_replace_trims_music(self):
        p2, _ = self.roundtrip([{"op": "add", "replace": True,
                                 "clip": {"id": "M2", "track": "music", "src": "n.wav", "start": 2.0, "dur": 2.0, "loop": True}}])
        self.assertEqual(ids(p2, "music"), [("M", 0.0, 2.0), ("M2", 2.0, 2.0), (ids(p2, "music")[2][0], 4.0, 2.0)])

    def test_remove_fills_from_previous(self):
        p2, _ = self.roundtrip([{"op": "remove", "id": "B"}])
        self.assertEqual(ids(p2, "v1"), [("A", 0.0, 4.0), ("C", 4.0, 2.0)])
        p3, _, _ = O.apply(self.p, [{"op": "remove", "id": "A"}])
        self.assertEqual(ids(p3, "v1")[0], ("B", 0.0, 4.0))
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "remove", "id": "vo-A"}])

    def test_split_and_swap(self):
        p2, ch = self.roundtrip([{"op": "split", "id": "B", "t": 3.0, "new_id": "B-2"}])
        self.assertEqual(ids(p2, "v1")[1:3], [("B", 2.0, 1.0), ("B-2", 3.0, 1.0)])
        self.assertNotIn("anchor", M.by_id(p2)["B-2"])
        p3, _ = self.roundtrip([{"op": "swap", "a": "A", "b": "C"}])
        self.assertEqual((M.by_id(p3)["A"]["src"], M.by_id(p3)["C"]["src"]), ("c.png", "a.png"))
        self.assertEqual(M.by_id(p3)["A"]["start"], 0.0)

    def test_revision_and_validation(self):
        self.p["revision"] = 7
        p2, _, _ = O.apply(self.p, [{"op": "set", "id": "A", "fields": {"motion": "shake"}}])
        self.assertEqual(p2["revision"], 8)
        self.assertEqual(self.p["clips"][0].get("motion"), None)      # исходник не тронут
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "set", "id": "A", "fields": {"dur": 5.0}}])   # перекрытие с B
        with self.assertRaises(O.OpError):
            O.apply(self.p, [{"op": "nope"}])

    def test_malformed_fields_raise_operror(self):
        bad_ops = [
            {"op": "move_cut", "left": "A", "right": "B", "t": None},
            {"op": "ripple", "id": "A", "delta": "oops"},
            {"op": "split", "id": "B", "t": "x"},
            {"op": "set", "id": "A", "fields": None},
        ]
        for bad in bad_ops:
            with self.assertRaises(O.OpError):
                O.apply(self.p, [bad])


if __name__ == "__main__":
    unittest.main()
