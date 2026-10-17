"""Заставка A «Астронавт с шапки» (ep06+, без Ника), 5,6 с, 1920×1080/30.
Рваные куски бумаги слетаются в астронавта-вырезку → он «прилипает» с отскоком → «коза» (рука — отдельный кусок,
качается вокруг манжеты, как бумажная марионетка) → над шлемом выскакивает бумажный «?» → астронавт уезжает вправо,
NICK: / WHAT / IF штампуются, «?» перелетает с головы в конец надписи → полоска подзаголовка → наезд → щелчок в чёрное.
Звук — только assets/sfx (+epidemic) и свой синтез (рок-джингл 150 BPM: гитарный риф guitar_riff.wav + барабаны).

  python3 studio/editor/intro/intro_A.py              → intro_A_astronaut.mp4 + _send.mp4
  python3 studio/editor/intro/intro_A.py --frames 0,30,60  → PNG выбранных кадров (frames/A/)
  python3 studio/editor/intro/intro_A.py --sheet      → контактный лист drafts/A_sheet.jpg"""
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
T_BLACK = 5.267                                                # «щелчок» в чёрное

# ───────── ассеты ─────────
BG = pk.make_bg()
ASTRO = pk.load("astronaut.png")
AW0, AH0 = ASTRO.size
PIECES = pk.tear(ASTRO, 9, seed=4, amp=10)

# рука-«коза» отдельно: выше манжеты (y < 392), с нахлёстом 30 px на тело; ось — центр манжеты
HAND_POLY = [(0, 120), (204, 120), (204, 330), (186, 392), (170, 392), (30, 392), (0, 392)]
PIVOT = (100, 398)


def _split_hand():
    a = np.array(ASTRO)
    m_body = Image.new("L", ASTRO.size, 0)
    ImageDraw.Draw(m_body).polygon(HAND_POLY, fill=255)
    m_hand = Image.new("L", ASTRO.size, 0)
    ImageDraw.Draw(m_hand).polygon([(x, y + 30 if y >= 392 else y) for x, y in HAND_POLY], fill=255)
    body = a.copy()
    body[np.array(m_body) > 0, 3] = 0
    hand = a.copy()
    hand[np.array(m_hand) == 0, 3] = 0
    ys, xs = np.where(hand[..., 3] > 0)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    hand_im = Image.fromarray(hand).crop((x0, y0, x1, y1))
    hc = ((x0 + x1) / 2 - AW0 / 2, (y0 + y1) / 2 - AH0 / 2)        # центр руки от центра спрайта
    return pk.fix_rgb(Image.fromarray(body), pk.PAPER), pk.fix_rgb(hand_im, pk.PAPER), hc


BODY, HAND, HAND_C = _split_hand()
PIV = (PIVOT[0] - AW0 / 2, PIVOT[1] - AH0 / 2)

CAP = 150
FONT = pk.font_for_cap(CAP)
CAP_OFF = FONT.getbbox("H")[1]
_d = ImageDraw.Draw(Image.new("L", (1, 1)))
TW = max(_d.textlength("NICK:", font=FONT), _d.textlength("WHAT IF?", font=FONT))
S_FIN = 560 / AH0
GAP = 105
X0 = (W - (TW + GAP + AW0 * S_FIN)) / 2
T1 = 292
T2 = T1 + CAP * 1.28
WORDS = []                                                     # (спрайт, мировой центр, время штампа)
for text, px, top, t in (("NICK:", X0, T1, 2.80), ("WHAT", X0, T2, 3.00),
                         ("IF", X0 + _d.textlength("WHAT ", font=FONT), T2, 3.20)):
    spr, (ox, oy) = pk.text_sprite(text, FONT)
    WORDS.append((spr, (px + ox + spr.width / 2, top - CAP_OFF + oy + spr.height / 2), t))
QM, (qox, qoy) = pk.sticker_glyph("?", FONT, seed=8)
QM = pk.fix_rgb(QM, pk.PAPER)
QM_TITLE = (X0 + _d.textlength("WHAT IF", font=FONT) + qox + QM.width / 2, T2 - CAP_OFF + qoy + QM.height / 2)
STRIP = pk.paper_strip_sprite("WILD QUESTIONS. REAL SCIENCE.", 44, angle=-1.2)
STRIP_POS = (X0 - 8 + STRIP.width / 2, T2 + CAP + 74)
A_FIN = (X0 + TW + GAP + AW0 * S_FIN / 2, STRIP_POS[1] + 40 - AH0 * S_FIN / 2)
A_MID, S_MID = (960, 625), 700 / AH0

# «штрихи» вокруг поднятой руки (бумажные полоски)
def _dash(L=70, th=16):
    im = Image.new("RGBA", (L + 20, th + 20), pk.PAPER + (0,))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, L + 19, th + 19], radius=(th + 20) // 2, fill=pk.PAPER + (255,))
    d.rounded_rectangle([10, 10, L + 9, th + 9], radius=th // 2, fill=pk.INK + (255,))
    return im


DASH = _dash()

# куски: откуда летят (направление, поворот), когда
_rng = np.random.default_rng(21)
FLY = []
dirs = [(-1, -.3), (1, -.5), (-.4, -1), (.6, 1), (-1, .6), (1, .2), (.2, -1), (-.7, 1), (1, -1)]
for i, (spr, off) in enumerate(PIECES):
    dx, dy = dirs[i % len(dirs)]
    n = math.hypot(dx, dy)
    FLY.append(dict(spr=spr, off=off, dir=(dx / n, dy / n), rot0=float(_rng.choice([-1, 1]) * _rng.uniform(70, 200)),
                    t0=0.06 + i * 0.075, dur=0.40 + _rng.uniform(-.04, .05)))
T_LAND = max(f["t0"] + f["dur"] for f in FLY)                    # ≈1,1 с
T_STICK = T_LAND + 0.02


def astro_state(t):
    """центр, масштаб, наклон тела, угол руки, подъём руки (px спрайта)"""
    k = spring(t - 2.50, 1.7, .55)                             # переезд вправо
    x = lerp(A_MID[0], A_FIN[0], k)
    y = lerp(A_MID[1], A_FIN[1], k)
    s = lerp(S_MID, S_FIN, k)
    # прилип: отскок масштаба
    st = t - T_STICK
    bump = .055 * math.exp(-st * 6) * math.sin(st * 2 * math.pi * 2.6) if st > 0 else 0
    s *= 1 + bump
    tilt, hang, lift = 0.0, 0.0, 0.0
    # «коза»: 4 качка на восьмых (150 BPM) с 1,6 с, затем ещё пара на 4,4 с
    for t0, n in ((1.6, 4), (4.4, 2)):
        u = t - t0
        if -0.2 < u < n * 0.2 + .5:
            env = clamp((u + .2) / .2) * clamp((n * 0.2 + .5 - u) / .5)
            hang += env * 12 * math.sin(2 * math.pi * u / 0.4)
            lift += env * 18 * max(0, math.sin(2 * math.pi * u / 0.2)) * (1 if u >= 0 else 0)
            tilt += env * 2.6 * math.sin(2 * math.pi * u / 0.8)
    if 1.2 < t < 1.6:                                          # замах перед аккордом
        hang += -7 * ease_io((t - 1.2) / .4)
    tilt += 1.0 * math.sin(t * 2.1) * clamp((t - 3.6) / .5)    # «дыхание» на удержании
    tilt += -6 * (spring(t - 2.5, 1.7, .55) - spring(t - 2.62, 1.7, .55))   # инерция при переезде
    return x, y, s, tilt, hang, lift


def head_point(t):
    x, y, s, tilt, _, _ = astro_state(t)
    return pk.local_to_world(30, -AH0 / 2 - 230 / s * 0 - 40, x, y, s, tilt), s, tilt


def cam_state(t):
    c = pk.Cam()
    z = 1.0 + .035 * ease_io((t - 1.1) / 1.35) - .035 * ease_io((t - 2.45) / .45)   # медленный наезд на «козу»
    z += .045 * ease_io((t - 3.7) / 1.3)
    z += .17 * ease_in((t - 4.98) / (T_BLACK - 4.98), 2.4)
    c.zoom = z
    c.cx, c.cy = 960, 540 + 10 * ease_io((t - 3.7) / 1.3)
    sh = 0.0
    for ts, amp in ((T_STICK, 5), (2.80, 7), (3.00, 6), (3.20, 6), (3.45, 10), (3.65, 3)):
        u = t - ts
        if 0 <= u < .2:
            sh += amp * math.exp(-u * 22)
    if sh:
        r = np.random.default_rng(int(t * 1000))
        c.sx, c.sy = r.uniform(-1, 1) * sh, r.uniform(-1, 1) * sh
    c.rot = -.8 * ease_in((t - 4.98) / (T_BLACK - 4.98), 2)
    return c


def render(fi):
    t = fi / pk.FPS
    if t >= T_BLACK:
        return Image.new("RGB", (W, H), (0, 0, 0))
    cam = cam_state(t)
    img = pk.bg_frame(BG, cam)
    x, y, s, tilt, hang, lift = astro_state(t)

    # ── астронавт ──
    if t < T_STICK + 0.08:
        for f in FLY:
            u = (t - f["t0"]) / f["dur"]
            if u <= 0:
                continue
            tx, ty = A_MID[0] + f["off"][0] * S_MID, A_MID[1] + f["off"][1] * S_MID
            k = pk.back_out(u, 1.4) if u < 1 else 1.0
            dist = 1350
            px = tx + f["dir"][0] * dist * (1 - k)
            py = ty + f["dir"][1] * dist * (1 - k)
            rot = f["rot0"] * (1 - ease_out(u, 3)) if u < 1 else 0
            air = 1 - clamp(u)                                  # «в воздухе» — крупнее, тень дальше
            land = max(0.0, 1 - (t - f["t0"] - f["dur"]) / .12) if u >= 1 else 0
            sc = S_MID * (1 + .22 * air - .03 * land * (u >= 1))
            sh = (5 + 30 * air, 9 + 40 * air, 9 + 18 * air, .42 - .1 * air)
            place_alpha = 1.0
            if t > T_STICK:                                     # куски → цельная наклейка (шов заживает)
                place_alpha = 1 - clamp((t - T_STICK) / .08)
            pk.place(img, cam, f["spr"], px, py, sc, rot, place_alpha, sh)
    if t >= T_STICK:
        al = clamp((t - T_STICK) / .08)
        pk.place(img, cam, BODY, x, y, s, tilt, al, (6, 11, 11, .45))
        # рука: поворот вокруг манжеты + подъём
        px_, py_ = PIV
        hx, hy = HAND_C
        a = math.radians(hang)
        rx = px_ + (hx - px_) * math.cos(a) + (hy - py_) * math.sin(a)
        ry = py_ - (hx - px_) * math.sin(a) + (hy - py_) * math.cos(a) - lift
        wx, wy = pk.local_to_world(rx, ry, x, y, s, tilt)
        pk.place(img, cam, HAND, wx, wy, s, tilt + hang, al, (6, 11, 11, .45))

    # ── штрихи у руки на аккорде ──
    for t0 in (1.6, 4.4):
        u = t - t0
        if 0 <= u < .42:
            hx, hy = pk.local_to_world(HAND_C[0] - 10, HAND_C[1] - 150, x, y, s, tilt + hang)
            for j, ang in enumerate((150, 112, 72)):
                k = spring(u, 3.2, .5)
                r = (90 + 45 * k) * s / S_MID
                aa = math.radians(ang + tilt)
                ox, oy = math.cos(aa) * r, -math.sin(aa) * r
                pk.place(img, cam, DASH, hx + ox, hy + oy, .9 * k * (1 - ease_in((u - .25) / .17)) * s / S_MID,
                         ang + tilt, 1.0, (3, 5, 4, .35))

    # ── «?» над шлемом → в надпись ──
    if t >= 2.2:
        u = t - 2.2
        hx, hy = pk.local_to_world(40, -AH0 / 2 - 145, x, y, s, tilt)
        qs_head = 1.15 * s / S_MID
        k = spring(u, 2.6, .35)
        wob = 22 * math.exp(-u * 5) * math.cos(u * 2 * math.pi * 2.2) + 8 + 3 * math.sin(t * 3)
        qx, qy, qs, qr = hx, hy, qs_head * k, wob
        if t >= 3.2:                                            # прыжок дугой в конец надписи
            v = clamp((t - 3.2) / .25)
            e = ease_io(v)
            qx = lerp(hx, QM_TITLE[0], e)
            qy = lerp(hy, QM_TITLE[1], e) - 160 * math.sin(math.pi * v)
            qs = lerp(qs_head, 1.0, e)
            qr = lerp(wob, -360, e)
            if v >= 1:
                w = t - 3.45
                qs = 1.0 * (1 + .18 * math.exp(-w * 14) * math.cos(w * 40))
                qr = 0
        lift_sh = 1 if t < 3.45 else 0
        pk.place(img, cam, QM, qx, qy, qs, qr, 1.0, (6 + 14 * lift_sh, 10 + 22 * lift_sh, 9 + 8 * lift_sh, .42))

    # ── надпись штампами ──
    for spr, (wx, wy), ts in WORDS:
        u = t - ts
        if u < 0:
            continue
        if u < .1:                                              # падает сверху-сзади
            k = ease_in(u / .1, 2)
            sc, al = lerp(1.9, .94, k), clamp(u / .05)
        else:
            w = u - .1
            sc, al = 1 - .06 * math.exp(-w * 16) * math.cos(w * 34), 1.0
        sha = (CAP * .03, CAP * .05, CAP * .05, .59 * clamp(u / .1))
        pk.place(img, cam, spr, wx, wy, sc, 0, al, sha)

    # ── полоска подзаголовка: разворачивается слева направо ──
    if t >= 3.62:
        u = t - 3.62
        rev = ease_out(u / .22, 2)
        cw = max(2, int(STRIP.width * rev))
        part = STRIP.crop((0, 0, cw, STRIP.height))
        k = spring(u, 2.4, .45)
        rot = lerp(-7, 0, k)
        pk.place(img, cam, part, STRIP_POS[0] - STRIP.width / 2 + cw / 2, STRIP_POS[1] + 18 * (1 - k), 1.0, rot, 1.0,
                 (4, 7, 8, .4))
    return img


# ───────── звук ─────────
def audio(path):
    m = pk.Mix(DUR)
    sx = pk.sfx
    # шорох и разлёт кусков
    m.add(sx("epidemic/ep05/tape_sticky_rip.wav"), 0.0, -12, rate=1.3)
    m.add(sx("epidemic/ep05/paper_flutter_photo.wav"), 0.04, -9)
    m.add(sx("epidemic/ep03/whoosh_mids.wav"), 0.0, -16, length=1.1, fade_in=.05, fade_out=.3)
    for i, f in enumerate(FLY):
        m.add(sx("epidemic/ep03/whoosh_air_short.wav"), f["t0"], -18 + (i % 3), pan=f["dir"][0] * .6, rate=1.1 + .07 * (i % 4))
        m.add(sx("epidemic/ep05/paper_pad_set_down.wav" if i % 2 else "epidemic/ep05/paper_letter_drop.wav"),
              f["t0"] + f["dur"], -8 - (i % 3), pan=f["dir"][0] * .4, rate=.95 + .06 * (i % 5), at_peak=True)
    # прилип
    m.add(sx("epidemic/ep05/tape_sticky_rip.wav"), T_STICK, -16, rate=1.15, at_peak=True)
    m.add(sx("pop.wav"), T_STICK, -8)
    m.add(pk.pluck(pk.note("E4"), .4, 1.2, .4), T_STICK, -10)
    # гитара: «чак-чак-чак → АККОРД» (риф 1,2–2,5 с файла: аккорд E5 ровно на 1,6 с)
    gt = sx("guitar_riff.wav")
    m.add(gt, 1.2, -7, start=1.2, length=1.3, fade_out=.3)
    # барабаны с аккорда
    for b in range(9):
        tb = 1.6 + b * 0.4
        if tb > 4.9:
            break
        m.add(pk.kick(), tb, -9)
        if b % 2 == 1:
            m.add(pk.snare(), tb, -9)
        m.add(pk.hat(seed=b), tb + .2, -17)
        m.add(pk.hat(seed=b + 50), tb, -20)
    m.add(pk.clap(), 1.6, -11)
    # «?» выскакивает
    m.add(sx("epidemic/ep04/ui_pop_glass.wav"), 2.22, -4, at_peak=True)
    m.add(sx("pop.wav"), 2.2, -12, rate=1.3)
    m.add(pk.bell(pk.note("B5"), .9), 2.2, -15)
    # переезд
    m.add(sx("epidemic/ep03/whoosh_mids_1.wav"), 2.47, -15, rate=1.1)
    # штампы
    for ts, nt in ((2.8, "E3"), (3.0, "G3"), (3.2, "A3")):
        m.add(sx("epidemic/ep03/stamp_rubber.wav"), ts + .1, -5, at_peak=True)
        m.add(pk.kick(.25, 120, 60), ts + .09, -10)
        m.add(pk.bass(pk.note(nt), .22), ts + .09, -12)
    m.add(sx("epidemic/ep03/whoosh_air_short.wav"), 3.2, -15, rate=1.3)
    # «?» в надписи — главный удар + аккорд
    m.add(sx("epidemic/ep03/stamp_rubber.wav"), 3.45, -3, at_peak=True)
    m.add(sx("hit.wav"), 3.45, -6, at_peak=True)
    m.add(gt, 3.45, -8, start=1.6, length=.95, fade_out=.35)
    m.add(pk.bass(pk.note("E2"), .9), 3.45, -9)
    m.add(pk.bell(pk.note("E6"), 1.2), 3.45, -18)
    # полоска
    m.add(sx("epidemic/ep05/tape_masking_pull.wav"), 3.62, -12, start=.3, length=.4, fade_in=.03, fade_out=.12, rate=1.2)
    # финальная «коза» на 4,4 и подъём к щелчку
    m.add(gt, 4.4, -12, start=1.6, length=.6, fade_out=.3)
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
        pk.write_video(render, NF, None, frames_dir=os.path.join(pk.OUTDIR, "frames/A"), only=fr)
    elif args[:1] == ["--sheet"]:
        fr = [int(v) for v in args[1].split(",")] if len(args) > 1 else list(range(0, NF, 6))
        thumbs = [render(f).resize((480, 270), Image.LANCZOS) for f in fr]
        cols = 6
        sh = Image.new("RGB", (cols * 484, ((len(thumbs) + cols - 1) // cols) * 290), (20, 20, 20))
        d = ImageDraw.Draw(sh)
        for i, (f, im) in enumerate(zip(fr, thumbs)):
            sh.paste(im, ((i % cols) * 484, (i // cols) * 290 + 18))
            d.text(((i % cols) * 484 + 4, (i // cols) * 290 + 2), f"{f}  {f / pk.FPS:.2f}s", fill=(230, 230, 230))
        sh.save(os.path.join(drafts, "A_sheet.jpg"), quality=85)
    else:
        vid = os.path.join(drafts, "A_video.mp4")
        wav = os.path.join(drafts, "A_audio.wav")
        if "--audio-only" not in args:
            pk.write_video(render, NF, vid)
        lufs = audio(wav)
        out = os.path.join(pk.OUTDIR, "intro_A_astronaut.mp4")
        pk.mux(vid, wav, out, out.replace(".mp4", "_send.mp4"))
        print("ok", out, f"{DUR} s", f"исходная громкость {lufs:.1f} LUFS")
