"""Каркас проекта ep02 в Cutlab из русского черновика script/ep02_sleep_narration.md.

Каждая реплика → карточка-заглушка на дорожке «Кадры» (id = номер реплики, текст = метка + начало фразы).
Длина — прикидка по числу слов (≈0,42 с на русское слово). Потом карточки заменяются материалами
через `cli.py --project ep02 propose <id> …`.

  python3 studio/editor/build_ep02.py            # печатает план
  python3 studio/editor/build_ep02.py --apply    # создаёт ep02 (если нет) и заливает карточки через сервер
  python3 studio/editor/build_ep02.py --say      # дописывает кадрам полную речь (поле say — её показывают карточки «Правок»)
"""
import json, re, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MD = ROOT / "script" / "ep02_sleep_narration.md"
URL = "http://127.0.0.1:8777/api"
FIXED = {"H1": 5.0, "H2": 5.0, "H3": 6.0, "INTRO": 7.0}
SKIP = {"T0"}


def parse():
    lines = MD.read_text().splitlines()
    items, chapter = [], "hook"
    head = re.compile(r"^\*\*([A-Z]?\d*(?:\.\d+)?|[A-Z]\d+)\s*\[([^\]]+)\]\**\s*(.*)")
    for i, ln in enumerate(lines):
        if ln.startswith("## "):
            chapter = ln[3:].split("(")[0].strip()
        if ln.startswith("**[INTRO]**"):
            items.append({"id": "INTRO", "tag": "INTRO", "text": "заставка канала", "chapter": chapter})
            continue
        m = head.match(ln)
        if not m or m.group(1) in SKIP or not m.group(1):
            continue
        sid, tag, text = m.group(1), m.group(2), re.sub(r"\*+", "", m.group(3))
        if sid == "H4":   # 3D-блок: подпункты-строки «- … RU: …»
            k = 0
            for sub in lines[i + 1:]:
                if not sub.startswith("- "):
                    if sub.strip():
                        break
                    continue
                k += 1
                ru = re.search(r"RU:\s*(.*?)\s*/\s*EN:", sub)
                items.append({"id": f"H4.{k}", "tag": "3D", "text": ru.group(1) if ru else sub[2:], "chapter": chapter})
            continue
        if sid in ("H2", "H3"):
            nxt = next((x for x in lines[i + 1:i + 4] if x.startswith("RU:")), "")
            text = nxt[3:].strip() or text
        items.append({"id": sid, "tag": tag, "text": re.sub(r"\{[^}]*\}", "", text).strip(), "chapter": chapter})
    # перевод часов в файле стоит после хука, а в монтаже — в начале главы «Сутки» (после заставки)
    d = [x for x in items if re.fullmatch(r"D\d", x["id"])]
    rest = [x for x in items if x not in d]
    at = next(i for i, x in enumerate(rest) if x["id"] == "INTRO") + 1
    return rest[:at] + d + rest[at:]


def say_en():
    """Что реально звучит по-английски: хук — строки «EN:» сценария, тизер — слова самой дорожки teaser.mp3 (whisper_dtw)."""
    lines, out = MD.read_text().splitlines(), {}
    for i, ln in enumerate(lines):
        m = re.match(r"^\*\*(H2|H3)\b", ln)
        if m:
            out[m.group(1)] = next((x[3:].strip() for x in lines[i + 1:i + 6] if x.startswith("EN:")), None)
        if ln.startswith("**H4"):
            k = 0
            for sub in lines[i + 1:]:
                if not sub.startswith("- "):
                    if sub.strip():
                        break
                    continue
                k += 1
                e = re.search(r"EN:\s*(.*?)\s*(?:\{|—\s*подпись|$)", sub)
                if e:
                    out[f"H4.{k}"] = e.group(1).strip()
    sys.path.insert(0, str(ROOT / "studio"))
    import ep02_roughcut as RC
    j = json.loads((RC.VO / "teaser.words.json").read_text())
    toks = [(w["offsets"]["from"] / 1000, w["text"]) for w in j["transcription"] if w["text"].strip() and not w["text"].strip().startswith("[")]
    cuts, end = RC.teaser_cuts()
    ids = [a[0] for a in RC.TEASER_ANCHORS]
    for n, sid in enumerate(ids):
        a, b = cuts[sid], cuts[ids[n + 1]] if n + 1 < len(ids) else end + 1
        out[sid] = "".join(t for at, t in toks if a - 1e-3 <= at < b - 1e-3).strip()
    enf = ROOT / "script" / "ep02_en.json"          # английская адаптация глав (D1…9.13)
    if enf.exists():
        for k, v in json.loads(enf.read_text()).items():
            if not k.startswith("_") and v.get("en"):
                out[k] = v["en"]
    return {k: v for k, v in out.items() if v}


def dur(it):
    if it["id"] in FIXED:
        return FIXED[it["id"]]
    return round(max(1.8, len(it["text"].split()) * 0.42), 2)


def clips(items):
    t, out = 0.0, []
    for it in items:
        d = dur(it)
        out.append({"id": it["id"], "track": "v1", "shot": it["id"], "chapter": it["chapter"], "start": round(t, 4),
                    "dur": d, "motion": "static", "transition": "cut", "fit": "fill", "kind": "card",
                    "text": f"{it['id']} [{it['tag']}] {it['text'][:90]}", "say": it["text"]})
        t += d
    return out, t


def api(path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=10))


def main():
    cl, total = clips(parse())
    print(f"{len(cl)} карточек, ≈{int(total // 60)}:{total % 60:04.1f}")
    if "--say" in sys.argv:          # только речь, монтаж не трогаем; одна операция — отменяется ⌘Z
        proj = api("/projects/ep02")
        say, en = {it["id"]: it["text"] for it in parse()}, say_en()
        ops = []
        for c in proj["clips"]:
            if c["track"] != "v1" or c["id"] not in say:
                continue
            f = {"say": say[c["id"]], "say_en": en.get(c["id"])}
            f = {k: v for k, v in f.items() if c.get(k) != v}
            if f:
                ops.append({"op": "set", "id": c["id"], "fields": f})
        if ops:
            r = subprocess.run([sys.executable, str(ROOT / "studio/editor/cli.py"), "--project", "ep02", "op", json.dumps(ops, ensure_ascii=False)],
                               capture_output=True, text=True)
            print(r.stdout.strip()[-300:], r.stderr.strip()[-300:])
        print(f"речь дописана: {len(ops)} кадров")
        return
    if "--apply" not in sys.argv:
        for c in cl[:25]:
            print(f"{c['start']:7.1f} {c['dur']:5.2f}  {c['text']}")
        return
    ids = {p["id"]: p for p in api("/projects")["projects"]}
    pid = next((k for k, v in ids.items() if v["title"].startswith("What If You Stopped Sleeping")), None)
    if not pid:
        pid = api("/projects", {"title": "What If You Stopped Sleeping?"})["id"]
    proj = api(f"/projects/{pid}")
    have = {c["id"] for c in proj["clips"]}
    ops = [{"op": "add", "clip": c, "restore": True} for c in cl if c["id"] not in have]
    if ops:
        r = subprocess.run([sys.executable, str(ROOT / "studio/editor/cli.py"), "--project", pid, "op", json.dumps(ops, ensure_ascii=False)],
                           capture_output=True, text=True)
        print(r.stdout.strip()[-400:], r.stderr.strip()[-400:])
    print("проект:", pid)


if __name__ == "__main__":
    main()
