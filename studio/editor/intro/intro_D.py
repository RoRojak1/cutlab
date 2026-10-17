"""Заставка D «Пролёт сквозь коллаж» (ep06+, без Ника), ≈10 с, 1920×1080/30. Улучшенная C «как у ТОПЛЕС, но в нашем стиле»:
тёмный кадр рвётся как бумага → камера летит сквозь глубокий мятный бумажный мир (вырезки на разной глубине, тени, DOF,
крен), темы проносятся мимо на сильные доли → выход к центру, темы схлопываются → БУМ: большой бумажный «?» с коллажем →
«?» садится последним знаком NICK: WHAT IF?, слова — штампами, полоска, астронавт с «козой» выглядывает → щелчок в чёрное
на последнем ударе трека.

3D — Blender Eevee (studio/blender/ep06/intro_D_scene.py, план — intro_D_plan.py), финал (надпись, «?», стопки тем,
полоска, астронавт) — PIL поверх кадров Blender (paperkit), звук — музыка + assets/sfx (+epidemic).

  /usr/bin/python3 studio/editor/intro/intro_D.py --music <wav>             → intro_D_flythrough.mp4 + _send.mp4
  /usr/bin/python3 studio/editor/intro/intro_D.py --draft                   → немой черновик 960×540 drafts_D/D_draft.mp4
  … --skip-render   (кадры Blender уже есть)   --frames 40,200   (PNG финала в drafts_D/comp/)   --bpm 104 (без музыки)
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paperkit as pk  # noqa: E402
import intro_D_plan as PL  # noqa: E402
from paperkit import H, W, clamp, ease_in, ease_io, ease_out, lerp, spring  # noqa: E402

ROOT = pk.ROOT
INTRO = os.path.join(ROOT, "assets/shots/ep06/intro")
TEXD = os.path.join(INTRO, "tex_D")
WORK = os.path.join(INTRO, "drafts_D")
SCENE = os.path.join(ROOT, "studio/blender/ep06/intro_D_scene.py")
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"

ap = argparse.ArgumentParser()
ap.add_argument("--music", default="")
ap.add_argument("--bpm", type=float, default=0.0, help="подсказка темпа (с музыкой) или темп (без музыки, по умолчанию 104)")
ap.add_argument("--draft", action="store_true")
ap.add_argument("--skip-render", action="store_true")
ap.add_argument("--frames", default="")
ap.add_argument("--slots", type=int, default=3)
ap.add_argument("--audio-only", action="store_true")
args = ap.parse_args()
os.makedirs(WORK, exist_ok=True)

# ───────── сетка и план ─────────
if args.music:
    GRID = PL.grid_from_music(os.path.abspath(args.music), args.bpm or None)
else:
    bpm = args.bpm or 104.0
    E8 = 30 / bpm
    GRID = dict(E8=E8, PH=.6175, bpm=bpm, t_last=.6175 + 26.4 * E8, t_end=.6175 + 27 * E8, dur=.6175 + 27 * E8 + .9, t_drop=.6175 + E8)
GRID_PATH = os.path.join(WORK, "grid.json")
json.dump(GRID, open(GRID_PATH, "w"), indent=1)
META = json.load(open(os.path.join(TEXD, "meta.json")))
P = PL.Plan(GRID, META)
T = P.T
DUR = GRID["dur"]
NF = int(round(DUR * pk.FPS))
F_BLACK = int(round(T["BLACK"] * pk.FPS))                     # первый чёрный кадр
QUALITY = "draft" if args.draft else "final"
FRAMES_DIR = os.path.join(WORK, f"frames_{QUALITY}")

# ───────── финал: спрайты ─────────
def load_tex(name):
    return pk.fix_rgb(Image.open(os.path.join(TEXD, name + ".png")), pk.PAPER)


NAMES = ["earth", "brain", "runner", "rosette", "chimp", "atom", "finger", "moon"]
SPR = {n: load_tex(n) for n in NAMES}
for n in NAMES:                                                # ~2× от размера на экране (≤ 300 px) — хватает с запасом
    s = SPR[n]
    k = 640 / max(s.size)
    if k < 1:
        SPR[n] = s.resize((int(s.width * k), int(s.height * k)), Image.LANCZOS)
SPR["bulb"] = load_tex("bulb")
ASTRO = pk.fix_rgb(Image.open(os.path.join(pk.CUT, "astronaut.png")), pk.PAPER)

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


def word(text, x0, top, line_text, idx):
    spr, (ox, oy) = pk.text_sprite(text, FONT)
    px = x0 + _d.textlength(line_text[:idx], font=FONT)
    return spr, (px + ox + spr.width / 2, top - CAP_OFF + oy + spr.height / 2)


WORDS = [word("NICK:", L1X, T1, "NICK:", 0), word("WHAT", L2X, T2, "WHAT IF?", 0), word("IF", L2X, T2, "WHAT IF?", 5)]
WORD_T = [T["STAMP1"], T["STAMP2"], T["STAMP3"]]

QCAP = 560
QFONT = pk.font_for_cap(QCAP)


def collage(w, h, seed=3):
    rng = np.random.default_rng(seed)
    c = Image.new("RGB", (w, h), (214, 207, 190))
    cols, rows = 3, 9
    cells = [(cx, cy) for cy in range(rows) for cx in range(cols)]
    names = (NAMES + ["bulb"]) * 4
    names = names[:len(cells)]
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
QBIG, (qox, qoy) = pk.sticker_glyph("?", QFONT, seed=12, fill=collage(_r - _l + 200, _b - _t + 200), outline=14)
QBLK, _ = pk.sticker_glyph("?", QFONT, seed=12, fill=Image.new("RGB", (8, 8), pk.INK), outline=14)
QBIG, QBLK = pk.fix_rgb(QBIG, pk.PAPER), pk.fix_rgb(QBLK, pk.PAPER)
QK = CAP / QCAP
QM_TITLE = (L2X + _d.textlength("WHAT IF", font=FONT) + qox * QK + QBIG.width * QK / 2 - 14 * QK,
            T2 - CAP_OFF + qoy * QK + QBIG.height * QK / 2)
Q_MID = (W / 2, H / 2)
Q_S = .92
T_QIN = T["QMOVE"] + .26                                       # «?» на месте в надписи

STRIP = pk.paper_strip_sprite("WILD QUESTIONS. REAL SCIENCE.", 40, angle=-1.0, seed=6)
STRIP_POS = (W / 2, T2 + CAP + 70)
ASTRO_H = 430
ASTRO_POS = (1268, 1080 + ASTRO_H * .5 - 262)                  # выглядывает снизу под «?»: видны шлем и рука с «козой»


def finale(img, t):
    """всё, что поверх кадра Blender после удара (в координатах 1920×1080)"""
    cam = pk.Cam()
    # ── стопки тем по бокам ──
    if t >= T["QMOVE"]:
        order = sorted(FINAL, key=lambda n: (FINAL[n][0][1] > 500, FINAL[n][0][0]))
        for j, n in enumerate(order):
            (fx, fy), hh, rot = FINAL[n]
            u = t - (T["QMOVE"] + .02 + j * .022)
            if u < 0:
                continue
            k = spring(u, 2.1, .5)
            s1 = hh / SPR[n].height
            x = lerp(Q_MID[0], fx, k) + 3 * math.sin(t * 2.2 + j) * clamp(u / .6)
            y = lerp(Q_MID[1], fy, k) + 4 * math.cos(t * 1.8 + j * 1.7) * clamp(u / .6)
            rr = lerp((1 if j % 2 else -1) * 120, rot, k) + 1.2 * math.sin(t * 1.5 + j)
            sc = s1 * lerp(.2, 1, clamp(k * 1.3))
            pk.place(img, cam, SPR[n], x, y, sc, rr, 1.0, (6, 10, 10, .42))
    # ── большой «?» ──
    if t >= T["BOOM"] - .5 / pk.FPS:
        u = t - T["BOOM"]
        k = spring(u + .02, 2.4, .34)
        qs = Q_S * max(.05, k) * (1 + .025 * math.sin(max(0, u) * 5))
        qr = -22 * math.exp(-max(0, u) * 4.5) * math.cos(max(0, u) * 2 * math.pi * 1.8)
        qx, qy = Q_MID
        blk = 0.0
        if t >= T["QMOVE"]:
            v = clamp((t - T["QMOVE"]) / (T_QIN - T["QMOVE"]))
            e = ease_io(v)
            qx = lerp(Q_MID[0], QM_TITLE[0], e)
            qy = lerp(Q_MID[1], QM_TITLE[1], e) - 70 * math.sin(math.pi * v)
            qs = lerp(qs, QK, ease_out(v, 2.2))
            qr = lerp(qr, 0, e) + 18 * math.sin(math.pi * v)
            blk = clamp((v - .35) / .45)
            if v >= 1:
                w_ = t - T_QIN
                qs = QK * (1 + .16 * math.exp(-w_ * 14) * math.cos(w_ * 40))
                h_ = t - T["HOP"]
                if h_ > 0:
                    qy -= 24 * math.sin(math.pi * clamp(h_ / .2))
                    qr += 14 * math.exp(-h_ * 5) * math.sin(h_ * 2 * math.pi * 2.6)
        lift = clamp(1 - (t - T["QMOVE"] - .15) / .15) if t >= T["QMOVE"] else 1
        sh = (6 + 16 * lift, 10 + 26 * lift, 10 + 14 * lift, .42)
        if blk < 1:
            pk.place(img, cam, QBIG, qx, qy, qs, qr, 1.0, sh)
        if blk > 0:
            pk.place(img, cam, QBLK, qx, qy, qs, qr, blk, sh if blk >= 1 else None)
    # ── слова штампами ──
    for (spr, (lx, ly)), t0 in zip(WORDS, WORD_T):
        u = t - (t0 - .055)                                     # штамп опускается 55 мс и бьёт ровно в долю
        if u < 0:
            continue
        if u < .055:
            kk = ease_in(u / .055, 2)
            sc, lift, al = lerp(1.45, .97, kk), 1 - kk, clamp(u / .02)
        else:
            w_ = u - .055
            sc, lift, al = 1 - .03 * math.exp(-w_ * 18) * math.cos(w_ * 40), 0.0, 1.0
        pk.place(img, cam, spr, lx, ly, sc, 0, al, (CAP * (.03 + .10 * lift), CAP * (.05 + .16 * lift), CAP * (.05 + .1 * lift), .55 * al))
    # ── полоска ──
    if t >= T["STRIP"] - .06:
        u = t - (T["STRIP"] - .06)
        if u < .06:
            kk = ease_in(u / .06, 2)
            sc, al = lerp(1.6, .96, kk), clamp(u / .03)
        else:
            w_ = u - .06
            sc, al = 1 - .04 * math.exp(-w_ * 16) * math.cos(w_ * 36), 1.0
        pk.place(img, cam, STRIP, STRIP_POS[0], STRIP_POS[1], sc, 0, al, (4, 7, 8, .4 * al))
    # ── астронавт выглядывает снизу ──
    if t >= T["ASTRO"] - .12:
        u = t - (T["ASTRO"] - .12)
        k = spring(u, 2.6, .42)
        x = ASTRO_POS[0]
        y = lerp(H + ASTRO_H * .55, ASTRO_POS[1], k)
        rr = lerp(-14, -4, k)
        h_ = t - T["HOP"]
        if h_ > 0:                                            # «коза» в такт
            rr += 7 * math.exp(-h_ * 6) * math.sin(h_ * 2 * math.pi * 3)
            y -= 14 * math.sin(math.pi * clamp(h_ / .16))
        pk.place(img, cam, ASTRO, x, y, ASTRO_H / ASTRO.height, rr, 1.0, (6, 10, 10, .42))
    return img


def post(img, t):
    """камера поверх всего кадра: тряска на ударах, наезд перед щелчком"""
    sh = 0.0
    for ts, amp in ((T["DROP"], 10), (T["BOOM"], 16), (T["STAMP1"], 5), (T["STAMP2"], 5), (T["STAMP3"], 12), (T["STRIP"], 4)):
        u = t - ts
        if 0 <= u < .35:
            sh += amp * math.exp(-u * 12)
    z = 1.0
    if t >= T["BOOM"]:
        z += .035 * ease_io((t - T["BOOM"]) / 1.6)
        z += .05 * math.exp(-(t - T["BOOM"]) * 7)
    z += .14 * ease_in((t - (T["BLACK"] - .26)) / .26, 2.4)
    rot = .7 * ease_in((t - (T["BLACK"] - .26)) / .26, 2)
    if sh < .2 and abs(z - 1) < 1e-4 and not rot:
        return img
    r = np.random.default_rng(int(t * 1000) + 3)
    dx, dy = (r.uniform(-1, 1) * sh, r.uniform(-1, 1) * sh) if sh >= .2 else (0, 0)
    # аффинно: масштаб z вокруг центра, поворот, сдвиг
    a = math.radians(rot)
    ca, sa = math.cos(a) / z, math.sin(a) / z
    cx, cy = W / 2, H / 2
    data = (ca, sa, cx - ca * (cx + dx) - sa * (cy + dy), -sa, ca, cy + sa * (cx + dx) - ca * (cy + dy))
    return img.transform((W, H), Image.AFFINE, data, Image.BICUBIC)


_plate_cache = {}


def render(fi):
    t = fi / pk.FPS
    if fi >= F_BLACK:
        return Image.new("RGB", (W, H), (0, 0, 0))
    path = os.path.join(FRAMES_DIR, f"{fi + 1:04d}.png")
    img = Image.open(path).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.BICUBIC)
    if t >= T["BOOM"] - 1 / pk.FPS:
        img = finale(img, t)
    return post(img, t)


# ───────── звук ─────────
def audio(path, music):
    """музыка + эффекты; громкость каждого эффекта задаётся относительно музыки в его момент (мастер трека очень
    громкий — фиксированные дБ тонули на 20–30 дБ). В брейках опора не тише −22 дБFS, чтобы эффект не пропал."""
    m = pk.Mix(DUR)
    sx = pk.sfx
    mus = None
    if music:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", music, "-f", "f32le", "-ac", "2", "-ar", str(pk.SR), "-"],
                             capture_output=True, check=True).stdout
        mus = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
        m.add(mus, 0.0, 0.0, fade_out=.02)

    def db_rms(x):
        return 20 * math.log10(math.sqrt(float((np.asarray(x, np.float64) ** 2).mean())) + 1e-9)

    def rel(sig, t, target, start=0.0, length=None, rate=1.0, at_peak=False, **kw):
        s_ = np.asarray(sig, np.float32)
        if s_.ndim == 1:
            s_ = np.c_[s_, s_]
        s_ = s_[int(start * pk.SR):]
        if length is not None:
            s_ = s_[:int(length * rate * pk.SR)]                 # столько исходника уйдёт в микс
        win = max(1, int(.05 * pk.SR * rate))                  # громкость — по самым громким 50 мс (удары короткие)
        en = np.convolve((s_ ** 2).mean(1), np.ones(win) / win, "valid") if len(s_) > win else [(s_ ** 2).mean()]
        s_db = 10 * math.log10(float(np.max(en)) + 1e-12)
        pk_db = 20 * math.log10(float(np.abs(s_).max()) + 1e-9)
        if mus is not None:
            a, b = int(max(0, t - .03) * pk.SR), int((t + .08) * pk.SR)
            w2 = int(.05 * pk.SR)
            e2 = np.convolve((mus[a:b] ** 2).mean(1), np.ones(w2) / w2, "valid")
            ref = max(10 * math.log10(float(e2.max()) + 1e-12), -24.0)
        else:
            ref = -16.0
        gain = min(target + ref - s_db, -1.5 - pk_db)          # пик эффекта не выше −1,5 дБFS
        m.add(sig, t, gain, start=start, length=length, rate=rate, at_peak=at_peak, **kw)

    # разрыв
    rel(sx("epidemic/ep05/paper_sheet_fold.wav"), T["STAB"] + .01, -10, length=.35, fade_out=.1)
    rel(sx("epidemic/ep05/tape_sticky_rip.wav"), T["PICK"], -8, at_peak=True, rate=1.15, fade_out=.08)
    rel(sx("epidemic/ep05/tape_sticky_rip.wav"), T["DROP"], -4, at_peak=True, rate=.82, fade_out=.1)
    rel(sx("epidemic/ep05/paper_flutter_photo.wav"), T["DROP"] + .03, -10)
    rel(sx("epidemic/ep03/whoosh_mids_2.wav"), T["DROP"] - .05, -9)
    # пролёты
    for i, p in enumerate(P.passes):
        pan = clamp(math.cos(math.radians(p["dir"])) * .75, -.75, .75)
        if p["name"] == "earth":
            rel(sx("epidemic/ep03/whoosh_mids_1.wav"), p["t"] + .02, -6, pan=pan, at_peak=True)
            rel(sx("epidemic/ep05/paper_flutter_photo.wav"), p["t"] + .05, -12, pan=pan)
        else:
            rel(sx("epidemic/ep03/whoosh_air_short.wav"), p["t"] + .02, -11, pan=pan, rate=.92 + .05 * (i % 5), at_peak=True)
    rel(pk.reverse(sx("epidemic/ep03/whoosh_mids.wav")), P.tk(7) - .62, -12, length=.6, fade_out=.03)
    # схлопывание и удар
    rel(pk.reverse(sx("epidemic/ep03/whoosh_mids.wav")), T["BOOM"] - .44, -8, length=.43, fade_out=.02)
    rel(sx("epidemic/ep03/impact_dark_low.wav"), T["BOOM"], -3, at_peak=True, length=1.4, fade_out=.5)
    rel(sx("boom.wav"), T["BOOM"], -8, at_peak=True)
    rel(sx("epidemic/ep05/paper_flutter_photo.wav"), T["BOOM"] + .02, -10)
    # «?» в надпись, штампы, полоска, астронавт
    rel(sx("epidemic/ep03/whoosh_mids_2.wav"), T["QMOVE"] - .03, -8, pan=.3)
    for i, ts in enumerate(WORD_T):
        rel(sx("epidemic/ep03/stamp_rubber.wav"), ts, (-4, -4, -3)[i], at_peak=True, pan=(-.25, -.1, .15)[i])
    rel(sx("epidemic/ep04/cardboard_squash.wav"), WORD_T[2], -10, at_peak=True, length=.3, fade_out=.1)
    rel(sx("epidemic/ep05/paper_letter_drop.wav"), T["STRIP"], -6, at_peak=True)
    rel(sx("epidemic/ep05/paper_pad_set_down.wav"), T["ASTRO"], -7, at_peak=True, pan=.3)
    rel(sx("pop.wav"), T["ASTRO"] + .02, -11, rate=1.2, pan=.3)
    rel(sx("epidemic/ep04/ui_pop_glass.wav"), T["HOP"], -10, at_peak=True, pan=.25)
    rel(sx("epidemic/ep03/button_click.wav"), T["BLACK"] - .005, -5)
    return m.save(path)


# ───────── сборка ─────────
def blender_render():
    res = ["--quality", QUALITY]
    cmd = ["caffeinate", "-i", "/usr/bin/python3", os.path.join(ROOT, "studio/blender/gpu_slot.py"), "--slots", str(args.slots), "--",
           BLENDER, "-b", "-P", SCENE, "--", "--out", FRAMES_DIR, "--grid", GRID_PATH] + res
    print(" ".join(cmd), flush=True)
    log = open(os.path.join(WORK, f"render_{QUALITY}.log"), "w")
    r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode:
        sys.exit(f"Blender упал, см. {log.name}")


def write_draft(out):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W // 2}x{H // 2}", "-r", str(pk.FPS),
           "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    import multiprocessing
    with multiprocessing.get_context("fork").Pool(6) as pool:
        for im in pool.imap(_draft_job, range(NF), chunksize=2):
            p.stdin.write(im)
    p.stdin.close()
    p.wait()


def _draft_job(fi):
    return render(fi).resize((W // 2, H // 2), Image.LANCZOS).tobytes()


if __name__ == "__main__":
    print("сетка:", {k: round(v, 4) for k, v in GRID.items()}, flush=True)
    print("тайминг:", {k: round(v, 3) for k, v in T.items()}, flush=True)
    if args.frames:
        od = os.path.join(WORK, "comp")
        os.makedirs(od, exist_ok=True)
        for fi in [int(v) for v in args.frames.split(",")]:
            render(fi).save(os.path.join(od, f"c{fi:04d}.png"))
        print("ok", od)
        sys.exit(0)
    if not args.skip_render and not args.audio_only:
        blender_render()
    if args.draft:
        out = os.path.join(WORK, "D_draft.mp4")
        write_draft(out)
        print("ok", out)
        sys.exit(0)
    vid = os.path.join(WORK, "D_video.mp4")
    wav = os.path.join(WORK, "D_audio.wav")
    if not args.audio_only:
        pk.write_video(render, NF, vid)
    lufs = audio(wav, os.path.abspath(args.music) if args.music else "")
    out = os.path.join(INTRO, "intro_D_flythrough.mp4")
    pk.mux(vid, wav, out, out.replace(".mp4", "_send.mp4"))
    print("ok", out, f"{DUR:.2f} s", f"исходная громкость {lufs:.1f} LUFS")
