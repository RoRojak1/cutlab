#!/usr/bin/env python3
"""Дубляж (этап 2): план перевода по кадрам → блоки озвучки → полная дорожка по таймингу черновика CapCut.

  dub.py plan   --project ep01 --lang es     план и список «кадр | бюджет | EN» для перевода
  dub.py blocks --project ep01 --lang es     проверка text.json, блоки для озвучки и оценка кредитов
  dub.py build  --project ep01 --lang es     подгонка, сборка голоса, сведение с подложкой → <id>_<lang>.mp3
  dub.py status --project ep01               что готово по языкам

Черновик CapCut только читается. Спецификация: docs/superpowers/specs/2026-09-27-nick-editor-stage2-dub.md
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model as M

SR = 48000
GAP = 0.12            # тишина перед следующим блоком
FIT_MAX = 1.15        # на сколько можно ускорить блок, чтобы влез
BLOCK_MAX = 20.0      # длина блока озвучки, с
CR_PER_CHAR = 0.003   # get_cost: 0,9 кр за ~300 символов (elevenlabs, Mark)
VOICE_ID = "27c04473-84a9-4b60-a41f-c8e8458bd4f1"
REF_VOICE = M.ROOT / "assets" / "voice" / "voice_track.wav"   # английский голос — эталон громкости
# язык → (название, символов в секунду речи Mark)
LANGS = {"es": ("испанский (Лат. Америка)", 16.5), "pt": ("португальский (Бразилия)", 16.0), "de": ("немецкий", 15.5),
         "fr": ("французский", 16.0), "it": ("итальянский", 16.5), "hi": ("хинди", 14.0), "id": ("индонезийский", 16.0),
         "ja": ("японский", 8.0), "ko": ("корейский", 8.0), "ru": ("русский", 15.0), "tr": ("турецкий", 15.5),
         "ar": ("арабский", 13.0), "pl": ("польский", 15.0)}
SENT_END = re.compile(r"[.!?…。！？»\"”]\s*$")


class DubError(Exception):
    pass


def ddir(pid, lang=None):
    d = M.pdir(pid) / "dubs"
    return d / lang if lang else d


def lang_ok(lang):
    lang = (lang or "").split("-")[0].lower()             # es-419, pt-BR из диалога → es, pt
    if lang not in LANGS:
        raise DubError(f"язык {lang}: нет в списке {', '.join(LANGS)}")
    return lang


# ---------------------------------------------------------------- черновик CapCut (только чтение)
def read_draft(folder):
    p = Path(folder).expanduser() / "draft_info.json"
    if not p.exists():
        raise DubError(f"нет черновика CapCut: {p}")
    d = json.loads(p.read_text(encoding="utf-8"))
    mats = {m["id"]: m for m in d["materials"].get("audios", [])}
    voice, bed = [], []
    for tr in d["tracks"]:
        if tr.get("type") != "audio":
            continue
        for s in tr.get("segments", []):
            m = mats.get(s.get("material_id"))
            if not m:
                continue
            if abs((s.get("speed") or 1.0) - 1.0) > 1e-6:
                raise DubError(f"в черновике ускоренный звук ({Path(m['path']).name}) — так не умею")
            st, sr = s["target_timerange"], s.get("source_timerange") or {"start": 0}
            seg = {"path": m["path"], "at": st["start"] / 1e6, "dur": st["duration"] / 1e6, "src": sr["start"] / 1e6,
                   "gain": float(s.get("volume", 1.0)), "track": tr.get("name", "")}
            (voice if Path(m["path"]).name == "voice_track.wav" else bed).append(seg)
    if not voice:
        raise DubError("в черновике не нашёл дорожку голоса (voice_track.wav)")
    voice.sort(key=lambda v: v["at"])
    return {"duration": d["duration"] / 1e6, "voice": voice, "bed": bed, "mtime": p.stat().st_mtime}


def to_target(voice, s):
    """Время в voice_track.wav → время на таймлайне черновика (голос там порезан на куски со сдвигами)."""
    for v in voice:
        if v["src"] - 1e-6 <= s < v["src"] + v["dur"]:
            return v["at"] + s - v["src"]
    later = [v for v in voice if v["src"] > s]
    return later[0]["at"] if later else None          # слово попало в вырезанный кусок — на начало следующего


def draft_for(proj):
    f = (proj.get("settings") or {}).get("capcut_draft")
    if not f:
        raise DubError("в настройках проекта нет capcut_draft — дубляж без черновика CapCut будет после этапа 3 (рендер)")
    return f


# ---------------------------------------------------------------- план перевода
def plan(draft, alignment, script, lang):
    cps = LANGS[lang_ok(lang)][1]
    sc = {s["id"]: s for s in script["shots"]}
    rows = []
    for a in alignment["shots"]:
        s = sc.get(a["id"]) or {}
        if not a.get("voiced") or not a.get("words") or not (s.get("en") or "").strip():
            continue
        src0 = a["t_in"] + a["words"][0][1]
        t0 = to_target(draft["voice"], src0)
        if t0 is None:
            continue
        rows.append({"id": a["id"], "chapter": s.get("chapter", ""), "en": s["en"].strip(), "t0": round(t0, 3)})
    for i, r in enumerate(rows):
        nxt = rows[i + 1]["t0"] if i + 1 < len(rows) else draft["duration"]
        r["slot"] = round(max(0.3, nxt - r["t0"] - GAP), 3)
        r["budget"] = max(8, int(r["slot"] * cps))
    return {"lang": lang, "cps": cps, "duration": draft["duration"], "shots": rows, "draft_mtime": draft["mtime"]}


def blocks(pl, text):
    miss = [r["id"] for r in pl["shots"] if not (text.get(r["id"]) or "").strip()]
    if miss:
        raise DubError(f"нет перевода для {len(miss)} кадров: {', '.join(miss[:12])}{'…' if len(miss) > 12 else ''}")
    out, cur = [], None
    for r in pl["shots"]:
        tr = text[r["id"]].strip()
        ended = cur and (SENT_END.search(cur["_last_en"]) or SENT_END.search(cur["_last_tr"]))
        long_ = cur and r["t0"] + r["slot"] - cur["t0"] > BLOCK_MAX
        if not cur or r["chapter"] != cur["chapter"] or (long_ and ended) or (cur and r["t0"] + r["slot"] - cur["t0"] > BLOCK_MAX * 1.6):
            cur = {"id": f"b{len(out) + 1:03d}", "chapter": r["chapter"], "t0": r["t0"], "shots": [], "parts": []}
            out.append(cur)
        cur["shots"].append(r["id"]); cur["parts"].append(tr)
        cur["_last_en"], cur["_last_tr"] = r["en"], tr
    for i, b in enumerate(out):
        b["end"] = round((out[i + 1]["t0"] - GAP) if i + 1 < len(out) else pl["duration"], 3)
        b["text"] = " ".join(b.pop("parts"))
        b.pop("_last_en"); b.pop("_last_tr")
    over = [(r["id"], len(text[r["id"]]), r["budget"]) for r in pl["shots"] if len(text[r["id"]].strip()) > r["budget"] * 1.1]
    chars = sum(len(b["text"]) for b in out)
    return {"lang": pl["lang"], "blocks": out, "chars": chars, "cost": round(chars * CR_PER_CHAR, 1), "long_shots": over}


# ---------------------------------------------------------------- звук
def ff_decode(path, ch=1, af=None):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)] + (["-af", af] if af else []) + ["-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise DubError(f"ffmpeg не прочитал {path}: {r.stderr.decode()[-300:]}")
    a = np.frombuffer(r.stdout, dtype=np.float32)
    return a.reshape(-1, ch) if ch > 1 else a


def ff_filter(a, af):
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-af", af, "-f", "f32le", "-"],
                       input=a.astype(np.float32).tobytes(), capture_output=True)
    if r.returncode:
        raise DubError(f"ffmpeg {af}: {r.stderr.decode()[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.float32)


def loudness(a, ch=1):
    """Интегральная громкость (LUFS) через loudnorm; тишина → None."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-f", "f32le", "-ar", str(SR), "-ac", str(ch), "-i", "-",
                        "-af", "loudnorm=print_format=json", "-f", "null", "-"], input=np.ascontiguousarray(a, dtype=np.float32).tobytes(), capture_output=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr.decode())
    if not m:
        raise DubError("не смог измерить громкость")
    v = float(json.loads(m.group(0))["input_i"])
    return None if v < -70 else v


def trim_silence(a, thr_db=-45.0, pad=0.02):
    idx = np.flatnonzero(np.abs(a) > 10 ** (thr_db / 20))
    if not len(idx):
        return a[:0]
    p = int(pad * SR)
    return a[max(0, idx[0] - p): idx[-1] + p]


def bed_path(pid, draft):
    """Подложка (всё, кроме голоса) одна на все языки: собирается один раз на версию черновика."""
    key = hashlib.sha1(json.dumps([draft["duration"], draft["bed"], draft["mtime"]], sort_keys=True).encode()).hexdigest()[:12]
    d = ddir(pid) / "_bed"
    return d / f"bed-{key}.f32", d


def build_bed(pid, draft):
    out, d = bed_path(pid, draft)
    if out.exists():
        return out
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("bed-*.f32"):
        old.unlink()
    n = int(round(draft["duration"] * SR))
    tmp = out.with_suffix(".part")
    buf = np.lib.format.open_memmap(tmp, mode="w+", dtype=np.float32, shape=(n, 2))
    cache = {}
    for s in draft["bed"]:
        if s["path"] not in cache:
            cache.clear()                                  # стемы по 450 МБ — держим в памяти один файл
            cache[s["path"]] = ff_decode(s["path"], ch=2)
        a = cache[s["path"]]
        i0, j0 = int(round(s["at"] * SR)), int(round(s["src"] * SR))
        k = min(int(round(s["dur"] * SR)), len(a) - j0, n - i0)
        if k > 0:
            buf[i0:i0 + k] += a[j0:j0 + k] * s["gain"]
    buf.flush(); del buf
    os.replace(tmp, out)
    return out


def ref_loudness(pid):
    p = ddir(pid) / "_bed" / "voice_ref.json"
    if p.exists():
        return json.loads(p.read_text())["lufs"]
    v = loudness(ff_decode(REF_VOICE))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"lufs": v}))
    return v


def fit_blocks(bl, tts_dir):
    """Каждый блок: обрезать тишину, при нужде ускорить до FIT_MAX. Возвращает [(блок, сэмплы, отчёт)]."""
    res = []
    for b in bl["blocks"]:
        f = next((p for p in (tts_dir / f"{b['id']}.mp3", tts_dir / f"{b['id']}.wav") if p.exists()), None)
        if not f:
            raise DubError(f"нет озвучки блока {b['id']} ({tts_dir.name}/{b['id']}.mp3)")
        a = trim_silence(ff_decode(f))
        room = max(0.3, b["end"] - b["t0"])
        ratio = len(a) / SR / room
        tempo = 1.0
        if ratio > 1.0:
            tempo = min(ratio, FIT_MAX)
            a = ff_filter(a, f"atempo={tempo:.4f}")
        rep = {"id": b["id"], "t0": b["t0"], "room": round(room, 2), "len": round(len(a) / SR, 2), "tempo": round(tempo, 3),
               "overflow": round(len(a) / SR - room, 2) if len(a) / SR > room + 0.05 else 0}
        res.append((b, a, rep))
    return res


def build(pid, lang, draft, bl, bitrate="320k"):
    d = ddir(pid, lang)
    fitted = fit_blocks(bl, d / "tts")
    n = int(round(draft["duration"] * SR))
    voice = np.zeros(n, dtype=np.float32)
    for b, a, _ in fitted:
        i0 = int(round(b["t0"] * SR)); k = min(len(a), n - i0)
        voice[i0:i0 + k] += a[:k]
    ref, cur = ref_loudness(pid), loudness(voice)
    gain = 10 ** ((ref - cur) / 20) if ref is not None and cur is not None else 1.0
    voice *= gain
    bed = np.load(build_bed(pid, draft), mmap_mode="r")
    wav, mp3 = d / f"voice_{lang}.wav", d / f"{pid}_{lang}.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", str(wav)],
                   input=voice.tobytes(), check=True)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                            "-af", "alimiter=limit=0.891:level=false", "-c:a", "libmp3lame", "-b:a", bitrate, "-t", f"{draft['duration']:.3f}", str(mp3)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    step = SR * 10
    for i in range(0, n, step):
        chunk = np.array(bed[i:i + step], dtype=np.float32)
        chunk += voice[i:i + step, None]
        enc.stdin.write(chunk.tobytes())
    enc.stdin.close()
    if enc.wait():
        raise DubError(f"ffmpeg mp3: {enc.stderr.read().decode()[-300:]}")
    reps = [r for _, _, r in fitted]
    report = {"lang": lang, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "file": mp3.name, "duration": draft["duration"],
              "voice_gain_db": round(20 * np.log10(gain), 2), "blocks": reps,
              "overflow": [r for r in reps if r["overflow"]], "sped_up": sum(1 for r in reps if r["tempo"] > 1.0)}
    M.write_json_atomic(d / "report.json", report)
    return report


# ---------------------------------------------------------------- состояние по языкам (для монтажки)
def status(pid):
    out = []
    root = ddir(pid)
    for lang in LANGS:
        d = root / lang
        if not d.is_dir():
            continue
        rep = M.read_json(d / "report.json") if (d / "report.json").exists() else None
        st = "done" if rep and (d / rep["file"]).exists() else ("tts" if (d / "blocks.json").exists() else ("text" if (d / "plan.json").exists() else "none"))
        out.append({"lang": lang, "name": LANGS[lang][0], "status": st, "file": rep["file"] if rep else None,
                    "at": rep["at"] if rep else None, "overflow": len(rep["overflow"]) if rep else 0,
                    "meta": (d / "meta.txt").exists()})
    return out


# ---------------------------------------------------------------- CLI
def _inputs(pid):
    proj = M.load_project(pid)
    draft = read_draft(draft_for(proj))
    al = M.read_json(M.ROOT / "assets" / "voice" / "alignment.json")
    sc = M.read_json(M.ROOT / "script" / "script.json")
    return proj, draft, al, sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dub.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "blocks", "build", "status"])
    ap.add_argument("--project", default=os.environ.get("NICK_PROJECT", "ep01"))
    ap.add_argument("--lang")
    ap.add_argument("--force", action="store_true", help="build: собрать даже с переполнениями")
    a = ap.parse_args(argv)
    pid = a.project
    try:
        if a.cmd == "status":
            for s in status(pid):
                print(f"{s['lang']}  {s['name']:26} {s['status']:5} {s['file'] or ''} {'переполнений ' + str(s['overflow']) if s['overflow'] else ''}")
            return 0
        lang = lang_ok(a.lang or "")
        d = ddir(pid, lang)
        d.mkdir(parents=True, exist_ok=True)
        if a.cmd == "plan":
            _, draft, al, sc = _inputs(pid)
            pl = plan(draft, al, sc, lang)
            M.write_json_atomic(d / "plan.json", pl)
            print(f"# {LANGS[lang][0]}: {len(pl['shots'])} кадров, бюджет — символов перевода (≈{pl['cps']} симв/с). Перевод → {d / 'text.json'}")
            for r in pl["shots"]:
                print(f"{r['id']} | {r['budget']} | {r['en']}")
            return 0
        pl = M.read_json(d / "plan.json")
        text = M.read_json(d / "text.json") if (d / "text.json").exists() else {}
        if a.cmd == "blocks":
            bl = blocks(pl, text)
            M.write_json_atomic(d / "blocks.json", bl)
            print(f"# {len(bl['blocks'])} блоков, {bl['chars']} символов ≈ {bl['cost']} кр. Озвучка: text2speech_v2 elevenlabs, voice {VOICE_ID} (preset) → {d / 'tts'}/<блок>.mp3")
            for sid, n, b in bl["long_shots"]:
                print(f"! {sid}: {n} символов при бюджете {b} — лучше сократить")
            for b in bl["blocks"]:
                print(f"{b['id']} | {b['t0']:.2f}–{b['end']:.2f} | {b['text']}")
            return 0
        _, draft, _, _ = _inputs(pid)
        if abs(pl.get("draft_mtime", 0) - draft["mtime"]) > 1:
            print("! черновик CapCut менялся после plan — тайминг мог сдвинуться; при сомнениях пересоберите plan", file=sys.stderr)
        bl = M.read_json(d / "blocks.json")
        rep = build(pid, lang, draft, bl)
        print(f"{d / rep['file']}: ускорено блоков {rep['sped_up']}, громкость голоса {rep['voice_gain_db']:+.1f} дБ")
        for r in rep["overflow"]:
            print(f"! {r['id']} ({r['t0']:.1f} с) длиннее места на {r['overflow']} с даже при ×{FIT_MAX} — сократить перевод и переозвучить")
        return 1 if rep["overflow"] and not a.force else 0
    except (DubError, M.ProjectError) as e:
        print(f"ошибка: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
