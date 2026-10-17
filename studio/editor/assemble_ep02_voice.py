"""Английская озвучка глав ep02 на таймлайн Cutlab: голос блоками (по главе), кадры — под слова, музыка — по главам.

Вход: export/ep02/tts_blocks.json (какие кадры в каком блоке и текст для озвучки),
      assets/voice/ep02/<блок>.mp3 + <блок>.words.json (python3 studio/whisper_dtw.py ep02/<блок>).
Каждая реплика (кадр) начинается за 0,12 с до своего первого слова; первый кадр после заставки — сразу после неё.
Музыка меняется только на границах глав (MUSIC). Одна пачка операций → ⌘Z; перед этим — версия.

  python3 studio/editor/assemble_ep02_voice.py [--dry]
"""
import difflib, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio/editor"))
import words as Wd   # noqa: E402

CLI = [sys.executable, str(ROOT / "studio/editor/cli.py"), "--project", "ep02"]
VO = ROOT / "assets/voice/ep02"
LEAD, GAP, TAIL = 0.12, 0.45, 1.5          # склейка до слова; пауза между главами; хвост после последней фразы
MUSIC_DB, FADE_IN, FADE_OUT = -21, 1.5, 2.0
# (первый кадр, последний кадр, трек) — смена музыки только на границах глав
MUSIC = [  # никогда: Volatile Reaction, Investigations, Sneaky Snitch, Sad Trio (пользователь, 29.09)
         ("D1", "1.19", "assets/music/macleod/thinking_music.mp3"),
         ("2.1", "3.20", "assets/music/macleod/clean_soul.mp3"),
         ("4.1", "4.10", "assets/music/macleod/floating_cities.mp3"),
         ("5.1", "5.20", "assets/music/macleod/meditation_impromptu_02.mp3"),
         ("6.1", "6.14", "assets/music/macleod/bossa_antigua.mp3"),
         ("7.1", "7.18", "assets/music/macleod/darkest_child.mp3"),
         ("8.1", "9.10", "assets/music/macleod/local_forecast.mp3"),
         ("9.11", "9.13", "assets/music/macleod/heroic_age.mp3")]


def cli(*args):
    r = subprocess.run([*CLI, *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"cli {args[0]}: {r.stdout[-800:]} {r.stderr[-800:]}")
    return r.stdout.strip()


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)


def line_starts(block, lines):
    """время начала каждой реплики внутри блока: слова текста ↔ слова whisper (difflib), без совпадения — интерполяция"""
    j = json.loads((VO / f"{block}.words.json").read_text())
    wt = [(w, t["offsets"]["from"] / 1000.0) for t in j["transcription"] for w in Wd.toks(t["text"])]
    toks, owner = [], []
    for i, ln in enumerate(lines):
        for w in Wd.toks(ln):
            toks.append(w); owner.append(i)
    m = {}
    for a, b, n in difflib.SequenceMatcher(None, toks, [w for w, _ in wt], autojunk=False).get_matching_blocks():
        for k in range(n):
            m[a + k] = wt[b + k][1]
    out = []
    for i in range(len(lines)):
        idx = [k for k, o in enumerate(owner) if o == i]
        hit = next(((k, m[k]) for k in idx if k in m), None)
        if hit:
            k, t = hit
            out.append(max(0.0, t - 0.28 * (k - idx[0])))       # первые слова реплики не нашлись — ≈0,28 с на слово
        else:
            out.append(None)
    for i, t in enumerate(out):                                    # дыры — между соседями
        if t is None:
            prev = next((out[k] for k in range(i - 1, -1, -1) if out[k] is not None), 0.0)
            nxt = next((out[k] for k in range(i + 1, len(out)) if out[k] is not None), prev + 3.0)
            out[i] = prev + (nxt - prev) / 2
    return out, len(m) / max(1, len(toks))


def main():
    dry = "--dry" in sys.argv
    proj = json.loads((ROOT / "projects/ep02/project.json").read_text())
    blocks = json.loads((ROOT / "export/ep02/tts_blocks.json").read_text())
    en = json.loads((ROOT / "script/ep02_en.json").read_text())
    by = {c["id"]: c for c in proj["clips"]}
    intro = by["INTRO"]
    cursor = intro["start"] + intro["dur"]
    starts, voice, report, first = {}, [], [], True
    for block, b in blocks.items():
        texts = [en[i].get("tts") or en[i]["en"] for i in b["ids"]]
        rel, cover = line_starts(block, texts)
        mp3 = VO / f"{block}.mp3"
        at = cursor + (0.25 if first else GAP)
        voice.append({"id": f"e2-vo-{block}", "track": "voice", "kind": "audio", "part": f"ep02/{block}", "src": str(mp3.relative_to(ROOT)),
                      "start": round(at, 4), "in": 0.0, "dur": round(dur(mp3), 4)})
        for k, (cid, t) in enumerate(zip(b["ids"], rel)):
            s = cursor if (first and k == 0) else at + t - LEAD
            if k == 0 and not first:
                s = min(s, at)                                        # глава начинается с картинки, не с паузы
            starts[cid] = round(s, 4)
        cursor = at + voice[-1]["dur"]
        report.append(f"{block}: {len(b['ids'])} реплик, {voice[-1]['dur']:.1f} с, совпало слов {cover:.0%}")
        first = False
    end_all = cursor + TAIL
    order = [c["id"] for c in sorted((c for c in proj["clips"] if c["track"] == "v1"), key=lambda c: c["start"]) if c["id"] in starts]
    ops = [{"op": "remove", "id": c["id"], "fill": False} for c in proj["clips"]
           if c["id"].startswith("e2-vo-ep02_") or c["id"].startswith("e2-mb-")]
    fields = {}
    for i, cid in enumerate(order):
        nxt = starts[order[i + 1]] if i + 1 < len(order) else end_all
        fields[cid] = {"start": starts[cid], "dur": round(max(0.5, nxt - starts[cid]), 4)}
    for cid, f in fields.items():
        ops.append({"op": "set", "id": cid, "fields": f})
    ops += [{"op": "add", "restore": True, "clip": v} for v in voice]
    for n, (a, b, src) in enumerate(MUSIC):
        t0, t1 = fields[a]["start"], fields[b]["start"] + fields[b]["dur"]
        L = dur(ROOT / src)
        ops.append({"op": "add", "clip": {"id": f"e2-mb-{n}", "track": "music", "src": src, "start": round(t0, 4), "dur": round(t1 - t0, 4),
                                          "in": 0.0, "loop": L < t1 - t0, "fade_in": FADE_IN, "fade_out": FADE_OUT, "volume_db": MUSIC_DB}})
    # слова для прилипания склеек и строк речи в «Правках»
    parts = [f"ep02/{b}" for b in blocks] + (["ep02/teaser"] if (VO / "teaser.words.json").exists() else [])
    words = Wd.build_words(parts)
    print("\n".join(report))
    print(f"голос до {int(cursor // 60)}:{cursor % 60:04.1f}, операций {len(ops)}")
    if dry:
        return
    (ROOT / "projects/ep02/words.json").write_text(json.dumps(words, ensure_ascii=False))
    teaser = next((c for c in proj["clips"] if c["track"] == "voice" and c.get("src", "").endswith("teaser.mp3")), None)
    if teaser:
        ops.append({"op": "set", "id": teaser["id"], "fields": {"part": "ep02/teaser"}})
    print(cli("version", "до английской озвучки глав (Claude)"))
    cli("op", json.dumps(ops, ensure_ascii=False))
    print(cli("validate"))


if __name__ == "__main__":
    main()
