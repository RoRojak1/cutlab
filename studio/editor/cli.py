#!/usr/bin/env python3
"""Команды Claude для Nick Editor. Работает через сервер (NICK_EDITOR_URL, по умолчанию http://127.0.0.1:8777);
если сервер выключен — напрямую с файлами проекта (с той же проверкой).

  inbox [--batch B] [--json]                   сводка правок (текст, таймкод, клипы, слова, стоп-кадр)
  show <clip|shot|m:ss.s|sec>                  клип(ы) и слова
  words <from> <to>                            слова с таймкодами
  op '<json>'                                  операция или список операций
  cut <clip> (--word W [--nth N] | --t SEC)    склейка перед клипом: на слово (−0,12 с) или на время
  propose <clip> <file…> [--comment r-…] [--text T] [--note N …]  варианты кадра — пользователь выберет и поставит сам
  settle                                       закрыть «выберите», чей вариант уже в монтаже (после автосборки)
  status <comment> <status>
  reply <comment> "<текст>" [--done|--question]
  notify <batch|-> --title T --item "sec|clip|текст" [--item ...] [--kind done|question]
  batch-done <batch>
  job <job> <status> [--note N]
  version "<метка>"
  validate
  wait-signal [--timeout SEC]                  ждать «Исправить» (держит статус «Claude следит»)
Общее: --project ep01 (или NICK_PROJECT)."""
import argparse, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model as M
import ops as O
import review as R
import history as H
import words as Wd

URL = os.environ.get("NICK_EDITOR_URL", "http://127.0.0.1:8777")


def parse_time(s):
    s = str(s).strip()
    if ":" in s:
        m, sec = s.rsplit(":", 1)
        return round(int(m) * 60 + float(sec), 4)
    return float(s)


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            error_text = json.loads(e.read() or b'{}').get('error')
        except (json.JSONDecodeError, ValueError):
            error_text = e.reason
        raise SystemExit(f"ошибка сервера: {error_text}")
    except urllib.error.URLError as e:
        raise SystemExit(f"сервер недоступен: {e.reason}")


def online():
    try:
        with urllib.request.urlopen(URL + "/api/ping", timeout=0.5):
            return True
    except Exception:
        return False


class Ctx:
    def __init__(self, pid):
        self.pid, self.online = pid, online()

    def project(self):
        return http("GET", f"/api/projects/{self.pid}") if self.online else M.load_project(self.pid)

    def words(self):
        p = M.pdir(self.pid) / "words.json"
        return M.read_json(p) if p.exists() else {"version": 1, "parts": {}}

    def tw(self, proj=None):
        return Wd.timeline_words(proj or self.project(), self.words())

    def apply(self, ops):
        if self.online:
            proj = self.project()
            return http("POST", f"/api/projects/{self.pid}/ops", {"base_revision": proj.get("revision"), "ops": ops, "client": "claude"})
        proj = M.load_project(self.pid)
        new, inv, ch = O.apply(proj, ops)
        M.save_project(self.pid, new)
        return {"revision": new["revision"], "inverse": inv, "changed": ch}

    def review_call(self, path, body, local):
        if self.online:
            return http("POST", f"/api/projects/{self.pid}/{path}", body)
        r = R.load(self.pid)
        out = local(r)
        R.save(self.pid, r)
        return out


def clip_line(c):
    bits = [c["id"], c["track"], fmt(c["start"]), f"{c['dur']:.2f}s"]
    for k in ("kind", "src", "text", "motion", "transition", "tag", "volume_db"):
        if c.get(k) not in (None, ""):
            bits.append(f"{k}={c[k]}")
    if c.get("anchor"):
        bits.append(f"anchor={c['anchor']['word']}")
    return "  ".join(str(b) for b in bits)


def cmd_inbox(ctx, a):
    proj = ctx.project()
    r = http("GET", f"/api/projects/{ctx.pid}/review") if ctx.online else R.load(ctx.pid)
    items = R.inbox(proj, ctx.words(), r, a.batch)
    if a.json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return 0
    jobs = [j for j in r.get("jobs", []) if j["status"] in ("new", "working")]
    print(f"{ctx.pid}: правок {len(items)}, задач {len(jobs)}")
    for it in items:
        rng = it["range"]
        print(f"\n● {it['id']} [{it['type']}/{it['status']}] {fmt(rng[0]) + '–' + fmt(rng[1]) if rng else ''}")
        for m in it["thread"]:
            print(f"   {m['who']}: {m['text']}")
        if it["words"]:
            print(f"   слова: «{it['words']}»")
        for c in it["clips"]:
            print("   " + clip_line(c))
        if it["snapshot"]:
            print(f"   стоп-кадр: projects/{ctx.pid}/{it['snapshot']}")
        for i, v in enumerate(it.get("variants") or []):
            mark = "  ← поставлен" if it.get("chosen") == i else ""
            print(f"   вариант {i + 1}: {v['src']}{'  ' + v['note'] if v.get('note') else ''}{mark}")
        if it["higgsfield"]:
            h = it["higgsfield"]
            print(f"   Higgsfield: {h['count']} × {h['model']} = {h['cost']} кр, разрешено: {'да' if h['approved'] else 'НЕТ — спросить в чате'}")
    for j in jobs:
        print(f"\n■ задача {j['id']} {j['type']} {j['params']} {j['cost']} кр, разрешено: {'да' if j['approved'] else 'НЕТ'}")
    return 0


def cmd_show(ctx, a):
    proj = ctx.project()
    byid = M.by_id(proj)
    if a.what in byid:
        cl = [byid[a.what]]
    else:
        shot = [c for c in proj["clips"] if c.get("shot") == a.what]
        if shot:
            cl = shot
        else:
            try:
                t = parse_time(a.what)
                cl = [c for c in proj["clips"] if c["start"] - 1e-6 <= t < M.end(c)]
            except ValueError:
                print(f"ошибка: нет клипа или кадра {a.what}")
                return 1
    tw = ctx.tw(proj)
    for c in sorted(cl, key=lambda c: (c["track"], c["start"])):
        print(clip_line(c))
    if cl:
        a0, b0 = min(c["start"] for c in cl), max(M.end(c) for c in cl)
        print(f"слова {fmt(a0)}–{fmt(b0)}: «{Wd.words_between(tw, a0, b0)}»")
    return 0 if cl else 1


def cmd_words(ctx, a):
    t0, t1 = parse_time(a.a), parse_time(a.b)
    for t, ref, w in ctx.tw():
        if t0 <= t < t1:
            print(f"{fmt(t)}  {w}  ({ref})")
    return 0


def cmd_op(ctx, a):
    ops = json.loads(a.json)
    res = ctx.apply(ops if isinstance(ops, list) else [ops])
    print(f"ревизия {res['revision']}, изменены: {', '.join(res['changed'])}")
    return 0


def cmd_cut(ctx, a):
    proj = ctx.project()
    v1 = M.on_track(proj, "v1")
    i = next((k for k, c in enumerate(v1) if c["id"] == a.clip), None)
    if i is None:
        print(f"ошибка: нет кадра {a.clip} на дорожке «Кадры»")
        return 1
    if i == 0:
        print("ошибка: у первого кадра нет склейки слева")
        return 1
    tw = ctx.tw(proj)
    anchor = None
    if a.word:
        f = Wd.find_word(tw, a.word, after=v1[i - 1]["start"], nth=a.nth)
        if not f:
            print(f"ошибка: нет слова {a.word!r} после {fmt(v1[i - 1]['start'])}")
            return 1
        t = f[0] - Wd.LEAD
        anchor = {"word": f[1], "lead": Wd.LEAD}
    else:
        t = parse_time(a.t)
    res = ctx.apply([{"op": "move_cut", "left": v1[i - 1]["id"], "right": a.clip, "t": t, "anchor": anchor}])
    print(f"склейка {v1[i - 1]['id']} | {a.clip} → {fmt(M.frame(t))}, ревизия {res['revision']}")
    return 0


def cmd_status(ctx, a):
    ctx.review_call(f"review/comments/{a.id}/status", {"status": a.status}, lambda r: R.set_status(r, a.id, a.status))
    if a.status == "working":
        R.write_presence(ctx.pid, "working")
    return 0


def cmd_reply(ctx, a):
    st = "done" if a.done else ("question" if a.question else None)
    ctx.review_call(f"review/comments/{a.id}/reply", {"who": "claude", "text": a.text, "status": st},
                    lambda r: R.reply(r, a.id, "claude", a.text, st))
    return 0


def cmd_propose(ctx, a):
    body = {"clip": a.clip, "files": a.files, "comment": a.comment, "text": a.text or "", "notes": a.note or []}
    c = ctx.review_call("review/propose", body, lambda r: R.propose(r, ctx.project(), a.clip, a.files, a.comment, a.text or "", a.note or []))
    print(f"{c['id']}: {len(c['variants'])} вар. для {a.clip} — ждут выбора в «Правках»")
    return 0


def cmd_settle(ctx, a):
    ids = ctx.review_call("review/settle", {}, lambda r: R.settle_placed(r, ctx.project()))
    print(f"закрыто карточек: {len(ids)}" + (f" ({', '.join(ids)})" if ids else ""))
    return 0


def cmd_notify(ctx, a):
    items = []
    for s in a.item or []:
        t, clip, text = s.split("|", 2)
        items.append({"t": parse_time(t), "clip": clip, "text": text})
    batch = None if a.batch == "-" else a.batch
    body = {"kind": a.kind, "title": a.title, "items": items, "batch": batch}
    ctx.review_call("notify", body, lambda r: R.notify(r, a.kind, a.title, items, batch))
    return 0


def cmd_batch_done(ctx, a):
    def local(r):
        b = next(x for x in r["batches"] if x["id"] == a.batch)
        b["status"], b["version_after"] = "done", H.snapshot(ctx.pid, "после правок Claude")
        return b
    ctx.review_call(f"batches/{a.batch}/done", {}, local)
    R.write_presence(ctx.pid, "watching")     # пачка закрыта; дальше — снова wait-signal (иначе через 90 с «не подключён»)
    return 0


def cmd_job(ctx, a):
    ctx.review_call(f"jobs/{a.id}", {"status": a.status, "note": a.note or ""}, lambda r: R.set_job(r, a.id, a.status, a.note or ""))
    return 0


def cmd_version(ctx, a):
    vid = http("POST", f"/api/projects/{ctx.pid}/history", {"label": a.label})["id"] if ctx.online else H.snapshot(ctx.pid, a.label)
    print(vid)
    return 0


def cmd_validate(ctx, a):
    errs = M.validate(M.read_json(M.pdir(ctx.pid) / "project.json"))
    print("\n".join(errs) or "ok")
    return 1 if errs else 0


def cmd_wait(ctx, a):
    sig = M.pdir(ctx.pid) / "review" / "SIGNAL"
    base = sig.stat().st_mtime_ns if sig.exists() else 0
    # «Исправить» могли нажать, пока ожидание не было запущено (Claude доделывал прошлую пачку) — не терять такие пачки
    sent = [b["id"] for b in R.load(ctx.pid).get("batches", []) if b.get("status") == "sent"]
    if sent:
        R.write_presence(ctx.pid, "working")
        print("СИГНАЛ:", json.dumps({"batch": sent[-1], "waiting": sent, "project": ctx.pid}, ensure_ascii=False))
        print(f"(незакрытые пачки: {', '.join(sent)} — после работы cli.py batch-done <пачка>)")
        return 0
    t_end, beat = time.time() + a.timeout, 0.0
    while time.time() < t_end:
        if time.time() - beat > 20:
            R.write_presence(ctx.pid, "watching")
            beat = time.time()
        if sig.exists() and sig.stat().st_mtime_ns != base:
            R.write_presence(ctx.pid, "working")
            print("СИГНАЛ:", sig.read_text(encoding="utf-8"))
            return 0
        time.sleep(0.5)
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cli.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("NICK_PROJECT", "ep01"))
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("inbox"); p.add_argument("--batch"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_inbox)
    p = sp.add_parser("show"); p.add_argument("what"); p.set_defaults(fn=cmd_show)
    p = sp.add_parser("words"); p.add_argument("a"); p.add_argument("b"); p.set_defaults(fn=cmd_words)
    p = sp.add_parser("op"); p.add_argument("json"); p.set_defaults(fn=cmd_op)
    p = sp.add_parser("cut"); p.add_argument("clip"); g = p.add_mutually_exclusive_group(required=True); g.add_argument("--word"); g.add_argument("--t"); p.add_argument("--nth", type=int, default=1); p.set_defaults(fn=cmd_cut)
    p = sp.add_parser("propose"); p.add_argument("clip"); p.add_argument("files", nargs="+"); p.add_argument("--comment"); p.add_argument("--text"); p.add_argument("--note", action="append"); p.set_defaults(fn=cmd_propose)
    p = sp.add_parser("settle"); p.set_defaults(fn=cmd_settle)
    p = sp.add_parser("status"); p.add_argument("id"); p.add_argument("status"); p.set_defaults(fn=cmd_status)
    p = sp.add_parser("reply"); p.add_argument("id"); p.add_argument("text"); p.add_argument("--done", action="store_true"); p.add_argument("--question", action="store_true"); p.set_defaults(fn=cmd_reply)
    p = sp.add_parser("notify"); p.add_argument("batch"); p.add_argument("--title", required=True); p.add_argument("--item", action="append"); p.add_argument("--kind", default="done"); p.set_defaults(fn=cmd_notify)
    p = sp.add_parser("batch-done"); p.add_argument("batch"); p.set_defaults(fn=cmd_batch_done)
    p = sp.add_parser("job"); p.add_argument("id"); p.add_argument("status"); p.add_argument("--note"); p.set_defaults(fn=cmd_job)
    p = sp.add_parser("version"); p.add_argument("label"); p.set_defaults(fn=cmd_version)
    p = sp.add_parser("validate"); p.set_defaults(fn=cmd_validate)
    p = sp.add_parser("wait-signal"); p.add_argument("--timeout", type=float, default=3500); p.set_defaults(fn=cmd_wait)
    a = ap.parse_args(argv)
    try:
        if a.cmd not in ("wait-signal", "batch-done"):
            R.touch_presence(a.project)
        return a.fn(Ctx(a.project), a)
    except (O.OpError, R.ReviewError, M.ProjectError, json.JSONDecodeError, ValueError) as e:
        print(f"ошибка: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
