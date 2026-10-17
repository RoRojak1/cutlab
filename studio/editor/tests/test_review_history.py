import importlib, json, os, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_model_words import tiny


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["NICK_PROJECTS"] = self.tmp.name
        import model, review, history
        for m in (model, review, history):
            importlib.reload(m)
        self.M, self.R, self.H = model, review, history
        self.p, self.w = tiny()
        self.M.save_project("tst", self.p)

    def tearDown(self):
        del os.environ["NICK_PROJECTS"]
        self.tmp.cleanup()


class ReviewTest(Base):
    def test_guess_type(self):
        g = self.R.guess_type
        self.assertEqual(g("сгенерируй другую картинку в хиксфилд"), "higgsfield")
        self.assertEqual(g("переход не попадает в слово, сдвинь раньше"), "timing")
        self.assertEqual(g("убери всплеск, громко"), "sound")
        self.assertEqual(g("надпись поздно появляется"), "text")
        self.assertEqual(g("плохое качество картинки"), "image")
        self.assertEqual(g("просто мысль"), "other")

    def test_lifecycle_and_batch_signal(self):
        r = self.R.empty()
        c = self.R.add_comment(r, "сдвинь раньше", clips=["A", "B"], range=[1.9, 4.0], words="forty million")
        self.assertEqual((c["status"], c["type"]), ("new", "timing"))
        b = self.R.make_batch("tst", r, "h-1")
        self.assertEqual(b["comments"], [c["id"]])
        sig = json.loads(Path(self.tmp.name, "tst", "review", "SIGNAL").read_text())
        self.assertEqual(sig["batch"], b["id"])
        self.assertIsNone(self.R.make_batch("tst", r, "h-2"))            # новых нет
        self.R.set_status(r, c["id"], "working")
        self.R.reply(r, c["id"], "claude", "сдвинул на 'forty'", status="done")
        self.assertEqual(r["comments"][0]["status"], "done")
        self.R.set_status(r, c["id"], "reopened")
        self.assertEqual(len(self.R.pending(r)), 1)
        with self.assertRaises(self.R.ReviewError):
            self.R.set_status(r, c["id"], "accepted")                     # reopened → accepted нельзя

    def test_question_answer_goes_back_to_new(self):
        r = self.R.empty()
        c = self.R.add_comment(r, "что-то не так")
        self.R.set_status(r, c["id"], "working")
        self.R.reply(r, c["id"], "claude", "какой именно кадр?", status="question")
        self.R.reply(r, c["id"], "user", "W24.1")
        self.assertEqual(r["comments"][0]["status"], "new")

    def test_higgsfield_needs_fields(self):
        r = self.R.empty()
        c = self.R.add_comment(r, "сгенерируй другую", higgsfield={"count": 4, "model": "gpt_image_2_5", "cost": 2.0, "approved": True})
        self.assertEqual(c["type"], "higgsfield")
        with self.assertRaises(self.R.ReviewError):
            self.R.add_comment(r, "x", higgsfield={"count": 4})

    def test_jobs_notifications_inbox(self):
        r = self.R.empty()
        j = self.R.add_job("tst", r, "dub", {"langs": ["es", "de"]}, 170.0, True)
        self.assertEqual(j["status"], "new")
        self.assertIn(j["id"], json.loads(Path(self.tmp.name, "tst", "review", "SIGNAL").read_text())["jobs"])
        n = self.R.notify(r, "done", "Готово 1 из 1", [{"text": "A — склейка", "t": 1.9, "clip": "A"}])
        self.assertFalse(n["read"])
        self.R.mark_read(r)
        self.assertTrue(r["notifications"][0]["read"])
        c = self.R.add_comment(r, "сдвинь", clips=["B"], range=[2.0, 4.0])
        d = self.R.inbox(self.p, self.w, r)
        self.assertEqual(d[0]["id"], c["id"])
        self.assertEqual(d[0]["words"], "forty million")
        self.assertEqual(d[0]["clips"][0]["id"], "B")

    def test_presence(self):
        self.assertEqual(self.R.read_presence("tst"), "offline")
        self.R.write_presence("tst", "watching")
        self.assertEqual(self.R.read_presence("tst"), "watching")
        pth = Path(self.tmp.name, "tst", "review", "CLAUDE")
        old = time.time() - 120
        os.utime(pth, (old, old))
        self.assertEqual(self.R.read_presence("tst"), "offline")

    def test_reopened_comment_in_next_batch(self):
        r = self.R.empty()
        c = self.R.add_comment(r, "сдвинь раньше", clips=["A", "B"], range=[1.9, 4.0], words="forty million")
        b1 = self.R.make_batch("tst", r, "h-1")
        self.assertEqual(b1["comments"], [c["id"]])
        self.R.set_status(r, c["id"], "working")
        self.R.reply(r, c["id"], "claude", "сдвинул на 'forty'", status="done")
        self.R.set_status(r, c["id"], "reopened")
        b2 = self.R.make_batch("tst", r, "h-2")
        self.assertIsNotNone(b2)
        self.assertEqual(b2["comments"], [c["id"]])

    def test_answered_question_in_next_batch(self):
        r = self.R.empty()
        c = self.R.add_comment(r, "что-то не так")
        b1 = self.R.make_batch("tst", r, "h-1")
        self.assertEqual(b1["comments"], [c["id"]])
        self.R.set_status(r, c["id"], "working")
        self.R.reply(r, c["id"], "claude", "какой именно кадр?", status="question")
        self.R.reply(r, c["id"], "user", "W24.1")
        self.assertEqual(r["comments"][0]["status"], "new")
        b2 = self.R.make_batch("tst", r, "h-2")
        self.assertIsNotNone(b2)
        self.assertEqual(b2["comments"], [c["id"]])


class HistoryTest(Base):
    def test_snapshot_list_restore(self):
        v1 = self.H.snapshot("tst", "до правок Claude")
        self.p["clips"][0]["motion"] = "shake"
        self.M.save_project("tst", self.p)
        vs = self.H.list_versions("tst")
        self.assertEqual(vs[0]["id"], v1)
        self.assertEqual(vs[0]["label"], "до правок Claude")
        self.H.restore("tst", v1)
        self.assertNotIn("motion", self.M.load_project("tst")["clips"][0])
        self.assertTrue(any(v["label"] == "перед откатом" for v in self.H.list_versions("tst")))


if __name__ == "__main__":
    unittest.main()


class VariantsTest(Base):
    FILES = ["studio/editor/web/icon-32.png", "studio/editor/web/icon-180.png"]

    def test_propose_new_card_choose_revert(self):
        r = self.R.empty()
        c = self.R.propose(r, self.p, "B", self.FILES)
        self.assertEqual((c["author"], c["status"], c["clips"], c["range"]), ("claude", "question", ["B"], [2.0, 4.0]))
        self.assertEqual([v["kind"] for v in c["variants"]], ["image", "image"])
        self.assertIn("2 варианта для B", c["text"])
        self.assertEqual(self.R.fresh_media(r), set(self.FILES))
        self.R.choose(r, c["id"], 1, {"src": "b.png", "kind": "image", "in": None})
        self.assertEqual((c["status"], c["chosen"], c["prev_src"]["src"]), ("done", 1, "b.png"))
        self.assertEqual(self.R.fresh_media(r), {self.FILES[0]})
        self.R.choose(r, c["id"], 0, {"src": self.FILES[1], "kind": "image"})
        self.assertEqual(c["prev_src"]["src"], "b.png")           # «было» — самый первый кадр, не промежуточный
        self.R.revert(r, c["id"])
        self.assertEqual((c["status"], c["chosen"]), ("question", None))
        self.R.reply(r, c["id"], "user", "ни один не подходит")
        self.assertEqual(self.R.pending(r), [c])                  # уходит Claude в следующую пачку

    def test_choose_closes_other_claude_cards_of_same_clip(self):
        r = self.R.empty()
        real = self.R.propose(r, self.p, "B", self.FILES[:1])
        ai = self.R.propose(r, self.p, "B", self.FILES[1:])
        other = self.R.propose(r, self.p, "C", self.FILES[:1])
        u = self.R.add_comment(r, "хочу 3D", clips=["B"])
        self.R.propose(r, self.p, "B", self.FILES[:1], cid=u["id"])
        self.R.choose(r, real["id"], 0)
        self.assertEqual((ai["status"], other["status"], u["status"]), ("accepted", "question", "question"))  # правку пользователя не трогаем
        self.assertIn(real["id"], ai["thread"][-1]["text"])

    def test_settle_placed_closes_cards_already_in_edit(self):
        r = self.R.empty()
        placed = self.R.propose(r, self.p, "B", self.FILES[:1])
        open_ = self.R.propose(r, self.p, "C", self.FILES[1:])
        clips = {c["id"]: c for c in self.p["clips"]}
        clips["C"]["src"] = self.FILES[:1][0]              # вариант карточки B автосборка положила в другой кадр
        self.assertEqual(self.R.settle_placed(r, self.p), [placed["id"]])
        self.assertEqual((placed["status"], placed["chosen"], placed["placed"]), ("accepted", None, ["C"]))
        self.assertIn("уже в монтаже: C", placed["thread"][-1]["text"])
        self.assertEqual(open_["status"], "question")      # его вариант нигде не стоит — ждёт выбора
        clips["C"]["src"] = "assets/shots/ep02/C/nick_anim.mp4"
        self.assertEqual(self.R.settle_placed(r, self.p), [open_["id"]])   # кадр занят анимацией
        self.assertEqual(open_["status"], "accepted")

    def test_propose_to_existing_comment_and_errors(self):
        r = self.R.empty()
        u = self.R.add_comment(r, "сгенерируй другую картинку", clips=["C"])
        c = self.R.propose(r, self.p, "C", self.FILES[:1], cid=u["id"], text="вот вариант")
        self.assertIs(c, u)
        self.assertEqual((c["status"], len(c["variants"]), c["thread"][-1]["who"]), ("question", 1, "claude"))
        self.R.reply(r, c["id"], "user", "не то, другое")
        self.R.propose(r, self.p, "C", self.FILES[1:], cid=u["id"], text="новый вариант")
        self.assertEqual([v.get("old", False) for v in c["variants"]], [True, False])   # прежний свёрнут, новый — к выбору
        with self.assertRaises(self.R.ReviewError):
            self.R.propose(r, self.p, "C", ["../../etc/passwd"])
        with self.assertRaises(self.R.ReviewError):
            self.R.propose(r, self.p, "vo-A", self.FILES)       # не кадр
        with self.assertRaises(self.R.ReviewError):
            self.R.choose(r, c["id"], 5)
        with self.assertRaises(self.R.ReviewError):
            self.R.revert(r, c["id"])                            # ещё ничего не ставили
