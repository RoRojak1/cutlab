#!/usr/bin/env python3
"""Голос ep03: из блоков TTS (assets/voice/ep03/block_<B>.mp3 + .words.json) — отрезать «разгон», выровнять
(voice_consistency match → block_<B>_master.wav) и вырезать реплики Ника для анимаций губ (nick/<сцена>.mp3).
Таймкоды реплик в мастер-файле блока — в nick/_scenes.json.

  python3 studio/editor/ep03_voice_prep.py
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio"))
import voice_consistency as V  # noqa: E402

VO = ROOT / "assets/voice/ep03"
REF = ROOT / "assets/voice/ep02/ep02_ch1.mp3"
LEADIN_END = {"B0": "start", "B1": "superpowers", "B2": "hell", "B3": "hardware", "B4": "terrifying", "B5": "strength",
              "B6": "kills you", "B7": "glow", "B9": "faster", "B10": "it", "BF": "sign"}
SCENES = {   # сцена: (блок, первые 3 слова, последние 2 слова) — как их пишет whisper (числа цифрами)
    "S00": ("B0", "level zero lets", "a mutant"),
    "S09": ("B0", "but thats small", "actual superpowers"),
    "S115": ("B1", "but mutants were", "through hell"),
    "S218": ("B2", "level 2 verdict", "some hardware"),
    "S313": ("B3", "tech hands out", "are terrifying"),
    "S415": ("B4", "now enough nature", "super strength"),
    "S58": ("B5", "speed runs into", "kills you"),
    "S611": ("B6", "up there theres", "to glow"),
    "S77": ("B7", "11 kilometers per", "times faster"),
    "S99": ("B9", "light speed is", "for it"),
    "SF1": ("BF", "so how superhuman", "time work"),
    "SF3": ("BF", "you started this", "20 minutes"),
    "SF4": ("BF", "question for the", "see you"),
}


def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower().replace("’", "'"))


def main():
    out = {}
    blocks = sorted({b for b, _, _ in SCENES.values()} | set(LEADIN_END))
    for b in blocks:
        src, wj = VO / f"block_{b}.mp3", VO / f"block_{b}.words.json"
        w = V.words(str(wj))
        toks = [norm(t) for t, _, _ in w]
        le = LEADIN_END[b].split()
        k = next(i for i in range(len(le) - 1, 25) if toks[i - len(le) + 1:i + 1] == le)
        cut_t = (w[k][2] + w[k + 1][1]) / 2
        cut = VO / f"block_{b}_cut.wav"
        V.ffcut(str(src), cut_t, len(V.load(str(src))) / V.SR, str(cut))
        master = VO / f"block_{b}_master.wav"
        subprocess.run([sys.executable, str(ROOT / "studio/voice_consistency.py"), "match", "--ref", str(REF), str(cut), str(master)],
                       check=True, capture_output=True)
        print(f"{b}: разгон до {cut_t:.2f} с, первое слово «{w[k + 1][0]}»")
        for sc, (bb, first, last) in SCENES.items():
            if bb != b:
                continue
            f3, l2 = first.split(), last.split()
            s = [i for i in range(k + 1, len(toks) - 2) if toks[i:i + 3] == f3][-1]      # последнее вхождение
            e = next(i for i in range(s + 2, len(toks)) if toks[i - 1:i + 1] == l2)
            prev_end = w[s - 1][2] if s > 0 else 0
            nxt = w[e + 1][1] if e + 1 < len(w) else w[e][2] + 0.6
            a = max((prev_end + w[s][1]) / 2, w[s][1] - 0.15) - cut_t
            z = min((w[e][2] + nxt) / 2, w[e][2] + 0.25) - cut_t
            (VO / "nick").mkdir(exist_ok=True)
            wav, mp3 = VO / "nick" / f"{sc}.wav", VO / "nick" / f"{sc}.mp3"
            V.ffcut(str(master), max(0, a), z, str(wav))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "44100", "-b:a", "192k", str(mp3)], check=True)
            out[sc] = {"block": b, "start": round(max(0, a), 3), "end": round(z, 3), "dur": round(z - max(0, a), 2),
                       "text": " ".join(t for t, _, _ in w[s:e + 1])}
            print(f"  {sc} {out[sc]['dur']:.2f} с: {out[sc]['text'][:90]}")
    json.dump(out, open(VO / "nick" / "_scenes.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
