"""Заставка C «Взрыв тем канала» (ep06+, без Ника), 5,6 с, 1920×1080/30.
Вырезки тем канала шлёпаются на мятный фон одна на другую (3–6 кадров каждая, с поворотом и масштабом) → все
схлопываются в центр → БУМ: большой бумажный «?», внутри — коллаж тех же тем → «?» уезжает в конец надписи, из него
выскакивают буквы NICK: WHAT IF, темы разлетаются по бокам двумя стопками → полоска подзаголовка → наезд → щелчок в чёрное.
Звук — только assets/sfx (+epidemic) и свой синтез (каждый шлепок — нота пентатоники, удар на сборке «?»).

  python3 studio/editor/intro/intro_C.py              → intro_C_themes.mp4 + _send.mp4
  python3 studio/editor/intro/intro_C.py --frames 0,30,60  → PNG выбранных кадров (frames/C/)
  python3 studio/editor/intro/intro_C.py --sheet      → контактный лист drafts/C_sheet.jpg"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperkit as pk  # noqa: E402
from paperkit import H, W, clamp, ease_in, ease_io, ease_out, lerp, spring  # noqa: E402

DUR = 5.6
NF = int(round(DUR * pk.FPS))
T_BLACK = 5.267
T_BOOM = 2.10
T_OPEN = 2.85
T_STRIP = 3.45
T_HOP = 4.25

BG = pk.make_bg(seed=9)
NAMES = ["earth", "brain", "runner", "rosette", "chimp", "atom", "finger", "moon", "astronaut"]
SPR = {n: pk.load(f"theme_{n}.png") for n in NAMES[:-1]}
SPR["astronaut"] = pk.load("astronaut.png")

# шлепки: кадр, центр, высота, поворот (в порядке NAMES)
SLAP_F = [3, 9, 14, 19, 24, 28, 32, 36, 40]
SLAP = [((640, 400), 430, -9), ((1270, 610), 400, 7), ((860, 690), 470, -4), ((1220, 330), 420, 10),
        ((560, 690), 430, 6), ((1400, 430), 430, -8), ((1010, 420), 400, 5), ((760, 330), 420, -6),
        ((960, 560), 600, -3)]
# финал: две стопки тем по бокам надписи (центр, высота, поворот, порядок)
FINAL = {"earth": ((215, 370), 265, -6), "moon": ((405, 345), 250, 6), "runner": ((225, 680), 290, 4),
         "finger": ((400, 700), 250, -5), "chimp": ((1590, 385), 240, 5), "rosette": ((1770, 345), 245, -5),
         "atom": ((1575, 690), 265, -4), "brain": ((1755, 690), 215, 6)}

CAP = 132
FONT = pk.font_for_cap(CAP)
CAP_OFF = FONT.getbbox("H")[1]
_d = ImageDraw.Draw(Image.new("L", (1, 1)))
T1 = 340
T2 = T1 + CAP * 1.28
L1X = W / 2 - _d.textlength("NICK:", font=FONT) / 2
L2X = W / 2 - _d.textlength("WHAT IF?", font=FONT) / 2


def letters(line, x0, top):
    out = []
    for i, ch in enumerate(line):
        if ch == " ":
            continue
        spr, (ox, oy) = pk.text_sprite(ch, FONT)
        px = x0 + _d.textlength(line[:i], font=FONT)
        out.append((spr, (px + ox + spr.width / 2, top - CAP_OFF + oy + spr.height / 2)))
    return out


LET = letters("WHAT IF", L2X, T2)[::-1] + letters("NICK:", L1X, T1)[::-1]   # вылетают справа налево
LET_T0 = [T_OPEN + .03 + i * .03 for i in range(len(LET))]

# большой «?»: внутри коллаж тем, чёрный контур, кремовая рваная кайма; второй — чёрный (для надписи)
QCAP = 560
QFONT = pk.font_for_cap(QCAP)


def collage(w, h, seed=3):
    """плотный коллаж тем (как стопка вырезок) — заливка большого «?»"""
    rng = np.random.default_rng(seed)
    c = Image.new("RGB", (w, h), (214, 207, 190))              # фон чуть темнее каймы — знак читается
    cols, rows = 3, 9
    cells = [(cx, cy) for cy in range(rows) for cx in range(cols)]
    names = (list(NAMES) * 4)[:len(cells)]
    rng.shuffle(names)
    for (cx, cy), n in zip(cells, names):
        spr = SPR[n]
        hh = int(h * rng.uniform(.19, .26))
        s = spr.resize((max(1, int(spr.width * hh / spr.height)), hh), Image.LANCZOS)
        s = s.rotate(rng.uniform(-25, 25), Image.BICUBIC, expand=True)
        x = int((cx + .5) / cols * w + rng.uniform(-.1, .1) * w - s.width / 2)
        y = int((cy + .5) / rows * h + rng.uniform(-.03, .03) * h - s.height / 2)
        c.paste(s, (x, y), s)
    return c


_l, _t, _r, _b = QFONT.getbbox("?")
_fill = collage(_r - _l + 200, _b - _t + 200)
QBIG, (qox, qoy) = pk.sticker_glyph("?", QFONT, seed=12, fill=_fill, outline=14)
QBLK, _ = pk.sticker_glyph("?", QFONT, seed=12, fill=Image.new("RGB", (8, 8), pk.INK), outline=14)
QBIG, QBLK = pk.fix_rgb(QBIG, pk.PAPER), pk.fix_rgb(QBLK, pk.PAPER)
QK = CAP / QCAP                                                # масштаб «?» в надписи
QM_TITLE = (L2X + _d.textlength("WHAT IF", font=FONT) + qox * QK + QBIG.width * QK / 2 - 14 * QK,
            T2 - CAP_OFF + qoy * QK + QBIG.height * QK / 2)
Q_MID = (960, 560)
Q_S = 1.0

STRIP = pk.paper_strip_sprite("WILD QUESTIONS. REAL SCIENCE.", 40, angle=-1.0, seed=6)
STRIP_POS = (W / 2, T2 + CAP + 70)

# конфетти: рваные клочки бумаги (кремовые и тёмно-мятные)
_rng = np.random.default_rng(5)


def _bit(seed):
    r = np.random.default_rng(seed)
    n = r.integers(5, 8)
    R = r.uniform(18, 34)
    pts = [(40 + math.cos(a) * R * r.uniform(.5, 1.2), 40 + math.sin(a) * R * r.uniform(.5, 1.2))
           for a in np.sort(r.uniform(0, 2 * math.pi, n))]
    im = Image.new("RGBA", (80, 80), pk.PAPER + (0,))
    col = pk.PAPER if seed % 3 else (60, 150, 125)
    ImageDraw.Draw(im).polygon(pts, fill=col + (255,))
    return pk.fix_rgb(im, col)


BITS = [dict(spr=_bit(i), ang=_rng.uniform(0, 2 * math.pi), v=_rng.uniform(700, 1500), spin=_rng.uniform(-720, 720),
             s=_rng.uniform(.7, 1.5)) for i in range(18)]


def slap_state(i, t):
    """шлепок i: центр, масштаб, поворот, тень (до схлопывания)"""
    (x, y), hh, rot = SLAP[i]
    s0 = hh / SPR[NAMES[i]].height
    u = t - SLAP_F[i] / pk.FPS
    if u < 0:
        return None
    if u < 2 / pk.FPS:                                         # летит в камеру → шлёп
        k = ease_in(u / (2 / pk.FPS), 2)
        sc = lerp(1.75, .95, k)
        sh = (lerp(26, 6, k), lerp(42, 10, k), lerp(24, 10, k), .45)
        rr = rot + lerp(-14 if i % 2 else 14, 0, k)
    else:
        w = u - 2 / pk.FPS
        sc = 1 + -.05 * math.exp(-w * 18) * math.cos(w * 45)
        sh = (6, 10, 10, .45)
        rr = rot
    sc *= s0
    # лёгкий дрейф, пока лежит
    x += 3 * math.sin(t * 3 + i)
    y += 3 * math.cos(t * 2.4 + i * 2)
    return x, y, sc, rr, sh


def cam_state(t):
    c = pk.Cam()
    z = 1.0 + .03 * ease_io(t / 1.5)                           # подкрадываемся во время шлепков
    z -= .03 * ease_io((t - 1.5) / .5)
    z += .05 * math.exp(-(t - T_BOOM) * 6) * (t >= T_BOOM)     # удар
    z += .045 * ease_io((t - 3.5) / 1.5)
    z += .17 * ease_in((t - 4.98) / (T_BLACK - 4.98), 2.4)
    c.zoom = z
    sh = 0.0
    for f in SLAP_F:
        u = t - (f + 2) / pk.FPS
        if 0 <= u < .15:
            sh += 5 * math.exp(-u * 25)
    for ts, amp in ((T_BOOM, 16), (T_STRIP, 4)):
        u = t - ts
        if 0 <= u < .35:
            sh += amp * math.exp(-u * 12)
    if sh:
        r = np.random.default_rng(int(t * 1000) + 3)
        c.sx, c.sy = r.uniform(-1, 1) * sh, r.uniform(-1, 1) * sh
    c.rot = .8 * ease_in((t - 4.98) / (T_BLACK - 4.98), 2)
    return c


T_COLL = 1.53                                                  # начало схлопывания


def render(fi):
    t = fi / pk.FPS
    if t >= T_BLACK:
        return Image.new("RGB", (W, H), (0, 0, 0))
    cam = cam_state(t)
    img = pk.bg_frame(BG, cam)

    # ── шлепки и схлопывание ──
    if t < T_BOOM:
        for i, n in enumerate(NAMES):
            st = slap_state(i, t)
            if st is None:
                continue
            x, y, sc, rr, sh = st
            if t >= T_COLL:
                a = (t - T_COLL) / .12                          # замах: чуть наружу и крупнее
                k_out = math.sin(math.pi * clamp(a)) * (a < 1)
                dx, dy = x - Q_MID[0], y - Q_MID[1]
                x += dx * .05 * k_out
                y += dy * .05 * k_out
                sc *= 1 + .05 * k_out
                t0 = T_COLL + .1 + (len(NAMES) - 1 - i) * .012
                v = clamp((t - t0) / (T_BOOM - .02 - t0))
                e = ease_in(v, 2.6)
                x, y = lerp(x, Q_MID[0], e), lerp(y, Q_MID[1], e)
                sc *= lerp(1, .12, e)
                rr += (1 if i % 2 else -1) * 260 * e
                sh = (6, 10, 10, .45 * (1 - e))
            pk.place(img, cam, SPR[n], x, y, sc, rr, 1.0, sh)

    # ── финал: темы по бокам ──
    if t >= T_OPEN:
        order = sorted(FINAL, key=lambda n: (FINAL[n][0][1] > 500, FINAL[n][0][0]))
        for j, n in enumerate(order):
            (fx, fy), hh, rot = FINAL[n]
            u = t - (T_OPEN + .04 + j * .025)
            if u < 0:
                continue
            k = spring(u, 1.9, .5)
            s1 = hh / SPR[n].height
            x = lerp(Q_MID[0], fx, k) + 3 * math.sin(t * 2.2 + j) * clamp(u / .6)
            y = lerp(Q_MID[1], fy, k) + 4 * math.cos(t * 1.8 + j * 1.7) * clamp(u / .6)
            rr = lerp((1 if j % 2 else -1) * 120, rot, k) + 1.2 * math.sin(t * 1.5 + j)
            sc = s1 * lerp(.2, 1, clamp(k * 1.3))
            pk.place(img, cam, SPR[n], x, y, sc, rr, 1.0, (6, 10, 10, .42))

    # ── конфетти на ударе ──
    u = t - T_BOOM
    if 0 <= u < .9:
        for b in BITS:
            d = b["v"] * u * math.exp(-u * 2.2)
            x = Q_MID[0] + math.cos(b["ang"]) * d
            y = Q_MID[1] + math.sin(b["ang"]) * d + 400 * u * u
            pk.place(img, cam, b["spr"], x, y, b["s"] * (1 - ease_in(u / .9, 3)), b["spin"] * u, 1.0, (3, 6, 5, .35))

    # ── большой «?» ──
    if t >= T_BOOM - 1 / pk.FPS:
        u = t - T_BOOM
        k = spring(u + .02, 2.3, .33)
        qs = Q_S * max(.05, k) * (1 + .025 * math.sin(max(0, u) * 4))
        qr = -24 * math.exp(-max(0, u) * 4.5) * math.cos(max(0, u) * 2 * math.pi * 1.7)
        qx, qy = Q_MID
        blk = 0.0
        if t >= T_OPEN:
            v = clamp((t - T_OPEN) / .42)
            e = ease_io(v)
            qx = lerp(Q_MID[0], QM_TITLE[0], e)
            qy = lerp(Q_MID[1], QM_TITLE[1], e) - 70 * math.sin(math.pi * v)
            qs = lerp(qs, QK, ease_out(v, 2.2))
            qr = lerp(qr, 0, e) + 18 * math.sin(math.pi * v)
            blk = clamp((v - .35) / .45)
            if v >= 1:
                w = t - T_OPEN - .42
                qs = QK * (1 + .16 * math.exp(-w * 14) * math.cos(w * 40))
                h_ = t - T_HOP                                  # «?» подпрыгивает на удержании
                if h_ > 0:
                    qy -= 26 * math.sin(math.pi * clamp(h_ / .26))
                    qr += 14 * math.exp(-h_ * 5) * math.sin(h_ * 2 * math.pi * 2.6)
                    qs *= 1 + .1 * math.exp(-max(0, h_ - .26) * 12) * (h_ > .26) * math.cos((h_ - .26) * 40)
        lift = clamp(1 - (t - T_OPEN - .3) / .2) if t >= T_OPEN else 1
        sh = (6 + 16 * lift, 10 + 26 * lift, 10 + 14 * lift, .42)
        if blk < 1:
            pk.place(img, cam, QBIG, qx, qy, qs, qr, 1.0, sh)
        if blk > 0:
            pk.place(img, cam, QBLK, qx, qy, qs, qr, blk, sh if blk >= 1 else None)

    # ── буквы вылетают из «?» ──
    for (spr, (lx, ly)), t0 in zip(LET, LET_T0):
        u = t - t0
        if u < 0:
            continue
        v = clamp((t0 - T_OPEN) / .42)
        e = ease_io(v)
        ox = lerp(Q_MID[0], QM_TITLE[0], e)
        oy = lerp(Q_MID[1], QM_TITLE[1], e) - 70 * math.sin(math.pi * v)
        k = spring(u, 2.3, .48)
        x, y = lerp(ox, lx, k), lerp(oy, ly, k)
        sc = lerp(.25, 1, clamp(spring(u, 2.8, .45)))
        rr = lerp(35 if int(t0 * 100) % 2 else -35, 0, k)
        pk.place(img, cam, spr, x, y, sc, rr, clamp(u / .04), (CAP * .03, CAP * .05, CAP * .05, .55 * clamp(u / .15)))

    # ── полоска ──
    if t >= T_STRIP:
        u = t - T_STRIP
        if u < .08:
            k = ease_in(u / .08, 2)
            sc, al = lerp(1.6, .96, k), clamp(u / .04)
        else:
            w = u - .08
            sc, al = 1 - .04 * math.exp(-w * 16) * math.cos(w * 36), 1.0
        pk.place(img, cam, STRIP, STRIP_POS[0], STRIP_POS[1], sc, 0, al, (4, 7, 8, .4 * al))
    return img


# ───────── звук ─────────
PENTA = ["E4", "F#4", "G#4", "B4", "C#5", "E5", "F#5", "G#5", "B5"]


def audio(path):
    m = pk.Mix(DUR)
    sx = pk.sfx
    slaps = ["epidemic/ep05/paper_letter_drop.wav", "epidemic/ep05/paper_pad_set_down.wav", "epidemic/ep04/cardboard_squash.wav"]
    for i, f in enumerate(SLAP_F):
        ts = (f + 2) / pk.FPS
        pan = (SLAP[i][0][0] - 960) / 960 * .7
        m.add(sx(slaps[i % 3]), ts, -6 if i % 3 < 2 else -10, pan=pan, rate=1.0 + .05 * (i % 4), at_peak=True,
              length=.35 if i % 3 == 2 else None, fade_out=.08)
        m.add(sx("epidemic/ep03/whoosh_air_short.wav"), ts - .09, -20, pan=pan, rate=1.4)
        m.add(pk.pluck(pk.note(PENTA[i]), .45, 1.3, .5), ts, -11, pan=pan * .5)
        m.add(pk.hat(seed=i), ts, -16)
        if i in (0, 4, 8):
            m.add(pk.kick(.35, 130, 55), ts, -10)
    # подъём к удару
    m.add(sx("riser.wav"), T_BOOM - 1.4, -19, length=1.36, fade_in=.3, fade_out=.04)
    m.add(pk.reverse(sx("epidemic/ep03/whoosh_mids.wav")), T_BOOM - 1.75, -14, start=0, length=1.71, fade_out=.04)
    for k in range(6):                                          # дробь при схлопывании
        m.add(pk.snare(.15, seed=10 + k, g=.6), T_COLL + .1 + k * .075, -16 + k * 1.2)
    # БУМ: «?»
    m.add(sx("boom.wav"), T_BOOM, -6, at_peak=True)
    m.add(sx("hit.wav"), T_BOOM, -6, at_peak=True)
    m.add(sx("epidemic/ep03/impact_dark_low.wav"), T_BOOM, -8, at_peak=True, length=1.6, fade_out=.6)
    m.add(pk.kick(.6, 160, 42), T_BOOM, -5)
    m.add(pk.bass(pk.note("E2"), 1.0), T_BOOM, -9)
    for j, nt in enumerate(["E3", "B3", "E4", "G#4"]):
        m.add(pk.pluck(pk.note(nt), 1.0, 1.1, .35), T_BOOM + j * .012, -12)
    m.add(sx("epidemic/ep05/paper_flutter_photo.wav"), T_BOOM + .02, -12)
    # раскрытие: темы разлетаются, буквы выскакивают
    m.add(sx("epidemic/ep03/whoosh_mids_2.wav"), T_OPEN - .05, -12)
    m.add(sx("epidemic/ep05/paper_flutter_photo.wav"), T_OPEN + .05, -11, rate=1.2)
    for i, t0 in enumerate(LET_T0):
        m.add(sx("pop.wav"), t0 + .02, -10, rate=1.0 + i * .06, pan=((i % 5) - 2) * .2)
    for j, nt in enumerate(["B5", "E6", "G#6", "B6"]):
        m.add(pk.bell(pk.note(nt), .7, .25), T_OPEN + .05 + j * .09, -20)
    # «?» садится в надпись
    m.add(sx("epidemic/ep03/stamp_rubber.wav"), T_OPEN + .42, -6, at_peak=True)
    # полоска + финальный аккорд
    m.add(sx("epidemic/ep05/paper_letter_drop.wav"), T_STRIP + .08, -8, at_peak=True)
    m.add(sx("epidemic/ep03/stamp_rubber.wav"), T_STRIP + .08, -4, at_peak=True)
    m.add(pk.kick(.5, 140, 48), T_STRIP + .08, -7)
    m.add(pk.clap(), T_STRIP + .08, -11)
    m.add(pk.bass(pk.note("E2"), 1.6), T_STRIP + .08, -10)
    for j, nt in enumerate(["E4", "G#4", "B4", "E5"]):
        m.add(pk.pluck(pk.note(nt), 1.6, 1.2, .3), T_STRIP + .08 + j * .02, -13)
    m.add(pk.bell(pk.note("E6"), 1.6, .3), T_STRIP + .1, -19)
    for b in range(4):                                         # тихий пульс на удержании
        tb = T_STRIP + .08 + .4 * (b + 1)
        m.add(pk.hat(seed=30 + b), tb, -21)
        m.add(pk.kick(.25, 100, 50), tb, -19)
    m.add(sx("epidemic/ep04/ui_pop_glass.wav"), T_HOP + .26, -9, at_peak=True)    # «?» подпрыгнул
    m.add(pk.bell(pk.note("G#6"), .6, .25), T_HOP + .26, -20)
    m.add(sx("epidemic/ep03/whoosh_mids.wav"), T_BLACK - 1.0, -17, length=1.0, fade_in=.4)
    m.cut_after(T_BLACK)
    m.add(sx("epidemic/ep03/button_click.wav"), T_BLACK - .01, -4)
    m.add(pk.kick(.2, 90, 50), T_BLACK, -14)
    return m.save(path)


if __name__ == "__main__":
    args = sys.argv[1:]
    drafts = os.path.join(pk.OUTDIR, "drafts")
    os.makedirs(drafts, exist_ok=True)
    if args[:1] == ["--frames"]:
        fr = [int(v) for v in args[1].split(",")]
        pk.write_video(render, NF, None, frames_dir=os.path.join(pk.OUTDIR, "frames/C"), only=fr)
    elif args[:1] == ["--sheet"]:
        fr = [int(v) for v in args[1].split(",")] if len(args) > 1 else list(range(0, NF, 6))
        thumbs = [render(f).resize((480, 270), Image.LANCZOS) for f in fr]
        cols = 6
        sh = Image.new("RGB", (cols * 484, ((len(thumbs) + cols - 1) // cols) * 290), (20, 20, 20))
        d = ImageDraw.Draw(sh)
        for i, (f, im) in enumerate(zip(fr, thumbs)):
            sh.paste(im, ((i % cols) * 484, (i // cols) * 290 + 18))
            d.text(((i % cols) * 484 + 4, (i // cols) * 290 + 2), f"{f}  {f / pk.FPS:.2f}s", fill=(230, 230, 230))
        sh.save(os.path.join(drafts, "C_sheet.jpg"), quality=85)
    else:
        vid = os.path.join(drafts, "C_video.mp4")
        wav = os.path.join(drafts, "C_audio.wav")
        if "--audio-only" not in args:
            pk.write_video(render, NF, vid)
        lufs = audio(wav)
        out = os.path.join(pk.OUTDIR, "intro_C_themes.mp4")
        pk.mux(vid, wav, out, out.replace(".mp4", "_send.mp4"))
        print("ok", out, f"{DUR} s", f"исходная громкость {lufs:.1f} LUFS")
