#!/usr/bin/env python3
"""Мягкий сигнал уведомления: две ноты (E6 → A6), колокольчик-«маримба», лёгкий хвост. → assets/ui/notify.wav"""
import wave
from pathlib import Path
import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parents[2] / "assets" / "ui" / "notify.wav"


def note(f, dur, t0, total):
    t = np.arange(int(total * SR)) / SR - t0
    on = t >= 0
    tt = np.where(on, t, 0)
    env = np.where(on, (1 - np.exp(-tt / 0.006)) * np.exp(-tt / dur), 0)
    tone = np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt / 0.08) + 0.08 * np.sin(2 * np.pi * 3.01 * f * tt)
    return tone * env


def main():
    total = 1.1
    x = note(1318.5, 0.32, 0.0, total) * 0.8 + note(1760.0, 0.45, 0.11, total)
    for d, g in ((0.045, 0.22), (0.09, 0.12), (0.15, 0.06)):          # «комната»
        k = int(d * SR)
        x[k:] += g * x[:-k]
    x *= 0.5 / np.max(np.abs(x))                                       # пик −6 dBFS
    fade = int(0.08 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    st = np.stack([x, np.roll(x, 90) * 0.96], axis=1)                  # чуть шире стерео
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(st, -1, 1) * 32767).astype("<i2").tobytes())
    print(OUT)


if __name__ == "__main__":
    main()
