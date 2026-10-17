#!/usr/bin/env python3
"""Время каждой реплики сценария ep03 в мастер-файлах блоков (block_<B>_master.wav).

Слова whisper (block_<B>.words.json, время сырой записи) сопоставляются с текстом реплик (script/ep03_en.json, tts)
через difflib: числа whisper пишет цифрами, TTS-текст — словами, поэтому сравнение по последовательности, а не по
каждому слову. Время мастера = время сырой записи − «разгон» (cut_t, как в ep03_voice_prep.py). Начало реплики
подтягивается к ближайшей паузе в самом мастере (whisper ошибается до ±0,5 с — урок ep03).

  python3 studio/editor/ep03_lines.py      → assets/voice/ep03/lines_timing.json
"""
import difflib, json, re, subprocess, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio"))
sys.path.insert(0, str(ROOT / "studio" / "editor"))
import voice_consistency as V  # noqa: E402
from ep03_voice_prep import LEADIN_END, norm  # noqa: E402

VO = ROOT / "assets/voice/ep03"
NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
       "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "twenty": "20", "thirty": "30",
       "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000", "million": "1000000"}


def toks(text):
    out = []
    for t in re.findall(r"[A-Za-z0-9'’.,%]+", text):
        n = norm(t)
        if n:
            out.append(NUM.get(n, n))
    return out


def cut_time(w, block):
    tk = [norm(t) for t, _, _ in w]
    le = LEADIN_END[block].split()
    k = next(i for i in range(len(le) - 1, 25) if tk[i - len(le) + 1:i + 1] == le)
    return (w[k][2] + w[k + 1][1]) / 2, k + 1


def pauses(master, thr=-40.0, min_len=0.07):
    """начала речи после пауз (с) в мастере — точки для склеек"""
    sr = 16000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(master), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-9)
    on, sil = [], 0
    for i, v in enumerate(db):
        if v < thr:
            sil += 1
        else:
            if sil * hop / sr >= min_len:
                on.append(i * hop / sr)
            sil = 0
    return on, len(x) / sr


def main():
    en = json.loads((ROOT / "script/ep03_en.json").read_text())
    out = {}
    for b in en["blocks"]:
        B = b["id"]
        w = V.words(str(VO / f"block_{B}.words.json"))
        cut, k0 = cut_time(w, B)
        wt = [(norm(t), s, e) for t, s, e in w[k0:]]
        wt = [(NUM.get(t, t), s, e) for t, s, e in wt if t]
        seq_w = [t for t, _, _ in wt]
        seq_s, owner = [], []
        for lid in b["ids"]:
            tt = toks(en["lines"][lid]["tts"])
            seq_s += tt
            owner += [lid] * len(tt)
        sm = difflib.SequenceMatcher(a=seq_s, b=seq_w, autojunk=False)
        first, last = {}, {}
        for blk in sm.get_matching_blocks():
            for j in range(blk.size):
                lid = owner[blk.a + j]
                ws, we = wt[blk.b + j][1], wt[blk.b + j][2]
                first.setdefault(lid, (blk.a + j, ws))
                last[lid] = (blk.a + j, we)
        on, mdur = pauses(VO / f"block_{B}_master.wav")
        ids = b["ids"]
        for i, lid in enumerate(ids):
            if lid not in first:
                print(f"  ! {B} {lid}: не нашлось слов", file=sys.stderr)
                continue
            # первое слово реплики могло не совпасть (числа) — сдвигаем начало назад на долю несовпавших токенов
            a_idx, ws = first[lid]
            lead_tokens = a_idx - owner.index(lid)
            s = ws - cut - 0.33 * lead_tokens
            near = [p for p in on if s - 0.6 <= p <= s + 0.35]
            if near:
                s = min(near, key=lambda p: abs(p - s))
            out[lid] = {"block": B, "start": round(max(0.0, s), 3), "end": round(last[lid][1] - cut, 3)}
        # конец реплики = начало следующей (без дыр); последняя — до конца файла
        for i, lid in enumerate(ids):
            if lid in out:
                nxt = next((out[x]["start"] for x in ids[i + 1:] if x in out), mdur)
                out[lid]["next"] = round(nxt, 3)
        out[f"_{B}"] = {"dur": round(mdur, 3), "cut": round(cut, 3)}
        print(f"{B}: {len(ids)} реплик, мастер {mdur:.1f} с")
    (VO / "lines_timing.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
