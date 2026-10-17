"""Общие функции бумажных заставок канала (стиль новой шапки: мятный фон, растровые вырезки с кремовой каймой,
Avenir Next Heavy). Кадр собирается в PIL: каждый спрайт ставится одним аффинным преобразованием с субпикселем
(предварительное уменьшение LANCZOS — без муара на растре), тень — размытая альфа. Звук — numpy, 48 кГц стерео.
Используют intro_A.py и intro_C.py."""
import io
import math
import os
import subprocess
import wave
import multiprocessing

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CUT = os.path.join(ROOT, "assets/shots/ep06/intro/cutouts")
OUTDIR = os.path.join(ROOT, "assets/shots/ep06/intro")
SFX = os.path.join(ROOT, "assets/sfx")
AVN = "/System/Library/Fonts/Avenir Next.ttc"
W, H, FPS, SR = 1920, 1080, 30, 48000
MINT = (120, 220, 190)
INK = (18, 18, 18)
PAPER = (240, 235, 222)
SHADOW = tuple(int(v * .25) for v in MINT)


# ───────── движение ─────────
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def spring(t, freq=2.0, damp=.38):
    """0→1 с перелётом (затухающая пружина); t в секундах от старта, freq — колебаний в секунду"""
    if t <= 0:
        return 0.0
    w = 2 * math.pi * freq
    wd = w * math.sqrt(1 - damp * damp)
    return 1 - math.exp(-damp * w * t) * (math.cos(wd * t) + damp * w / wd * math.sin(wd * t))


def ease_out(t, p=3):
    t = clamp(t)
    return 1 - (1 - t) ** p


def ease_in(t, p=3):
    t = clamp(t)
    return t ** p


def ease_io(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def back_out(t, k=1.9):
    t = clamp(t) - 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


# ───────── камера и фон ─────────
class Cam:
    def __init__(self):
        self.cx, self.cy, self.zoom, self.sx, self.sy, self.rot = W / 2, H / 2, 1.0, 0.0, 0.0, 0.0

    def to_screen(self, x, y):
        dx, dy = (x - self.cx) * self.zoom, (y - self.cy) * self.zoom
        if self.rot:
            a = math.radians(self.rot)
            dx, dy = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
        return dx + W / 2 + self.sx, dy + H / 2 + self.sy


BG_MARGIN = 1.3


def make_bg(color=MINT, seed=7):
    """бумажный мятный фон (как canvas() шапки), с запасом под наезд и тряску"""
    w, h = int(W * BG_MARGIN), int(H * BG_MARGIN)
    rng = np.random.default_rng(seed)
    a = np.zeros((h, w, 3), np.float32) + np.array(color, np.float32)
    n = rng.normal(0, 1.0, (h // 4, w // 4)).astype(np.float32)
    n = np.array(Image.fromarray(((n + 4) * 32).clip(0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 32 - 4
    big = ndi_blur(rng.normal(0, 1, (h // 16, w // 16)), 3)
    big = np.array(Image.fromarray(((big / (np.abs(big).max() + 1e-6) + 1) * 127).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 127 - 1
    a += n[..., None] * 2.2 + rng.normal(0, 1.4, (h, w))[..., None] + big[..., None] * 3.0
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def ndi_blur(a, s):
    from scipy import ndimage
    return ndimage.gaussian_filter(a, s)


def bg_frame(bg, cam):
    """кусок фона под текущую камеру"""
    ox, oy = (bg.width - W) / 2, (bg.height - H) / 2
    hw, hh = W / 2 / cam.zoom, H / 2 / cam.zoom
    cx, cy = cam.cx + ox - cam.sx / cam.zoom, cam.cy + oy - cam.sy / cam.zoom
    if cam.rot:
        big = bg.crop((int(cx - hw * 1.1), int(cy - hh * 1.1), int(cx + hw * 1.1), int(cy + hh * 1.1)))
        big = big.rotate(-cam.rot, Image.BILINEAR)
        m = (big.width - 2 * hw) / 2, (big.height - 2 * hh) / 2
        return big.resize((W, H), Image.BILINEAR, box=(m[0], m[1], m[0] + 2 * hw, m[1] + 2 * hh))
    return bg.resize((W, H), Image.BILINEAR, box=(cx - hw, cy - hh, cx + hw, cy + hh))


# ───────── спрайты ─────────
def fix_rgb(im, color):
    """под прозрачными пикселями — цвет края (иначе при пересчёте вылезает бирюза/чёрная кайма)"""
    a = np.array(im.convert("RGBA"))
    t = a[..., 3] < 8
    a[t, :3] = color
    return Image.fromarray(a)


def load(name, color=PAPER):
    return fix_rgb(Image.open(os.path.join(CUT, name)), color)


_cache = {}


def _prescaled(spr, s):
    q = round(math.log(max(s, 1e-3)) / math.log(1.015))      # шаги 1,5 % — кэш
    sq = 1.015 ** q
    if abs(sq - 1) < .008:
        return spr, 1.0
    key = (id(spr), q)
    if key not in _cache:
        if len(_cache) > 400:
            _cache.clear()
        w, h = max(1, round(spr.width * sq)), max(1, round(spr.height * sq))
        _cache[key] = spr.resize((w, h), Image.LANCZOS)
    im = _cache[key]
    return im, im.width / spr.width


def place(dst, cam, spr, x, y, s=1.0, rot=0.0, alpha=1.0, shadow=(5, 9, 9, .42), sq=(1.0, 1.0)):
    """спрайт центром в мировую точку (x, y), масштаб s, поворот rot° против часовой; sq — сплющивание (sx, sy)"""
    if alpha <= .003 or s <= .003:
        return
    sx, sy = cam.to_screen(x, y)
    se = s * cam.zoom
    im, sp = _prescaled(spr, se * max(sq))
    r = se / sp
    rx, ry = r * sq[0], r * sq[1]
    a = math.radians(rot + cam.rot)
    ca, sa = math.cos(a), math.sin(a)
    w, h = im.size
    hw, hh = w * rx / 2, h * ry / 2
    bw = abs(hw * ca) + abs(hh * sa)
    bh = abs(hw * sa) + abs(hh * ca)
    X0, Y0 = int(math.floor(sx - bw - 2)), int(math.floor(sy - bh - 2))
    X1, Y1 = int(math.ceil(sx + bw + 2)), int(math.ceil(sy + bh + 2))
    if X1 < -200 or Y1 < -200 or X0 > W + 200 or Y0 > H + 200:
        return
    ow, oh = X1 - X0, Y1 - Y0
    dx0, dy0 = X0 + .5 - sx, Y0 + .5 - sy
    data = (ca / rx, -sa / rx, (ca * dx0 - sa * dy0) / rx + w / 2,
            sa / ry, ca / ry, (sa * dx0 + ca * dy0) / ry + h / 2)
    tr = im.transform((ow, oh), Image.AFFINE, data, Image.BICUBIC)
    m = tr.getchannel("A")
    if alpha < 1:
        m = m.point(lambda v: int(v * alpha))
    if shadow:
        sdx, sdy, blur, op = shadow
        op *= alpha
        if op > .01:
            k = 4
            sm = m.resize((max(1, ow // k), max(1, oh // k)), Image.BILINEAR)
            pad = int(blur * cam.zoom / k * 2.5) + 2
            big = Image.new("L", (sm.width + 2 * pad, sm.height + 2 * pad), 0)
            big.paste(sm, (pad, pad))
            big = big.filter(ImageFilter.GaussianBlur(max(.5, blur * cam.zoom / k)))
            big = big.resize((big.width * k, big.height * k), Image.BILINEAR).point(lambda v: int(v * op))
            dst.paste(SHADOW, (int(X0 - pad * k + sdx * cam.zoom), int(Y0 - pad * k + sdy * cam.zoom)), big)
    dst.paste(tr, (X0, Y0), m)


def local_to_world(px, py, x, y, s, rot):
    """точка спрайта (смещение от его центра, в пикселях спрайта) → мир, при центре (x, y), масштабе s, повороте rot"""
    a = math.radians(rot)
    dx, dy = px * s, py * s
    return x + dx * math.cos(a) + dy * math.sin(a), y - dx * math.sin(a) + dy * math.cos(a)


# ───────── текст и бумага ─────────
def font_for_cap(cap_h, index=8):
    f0 = ImageFont.truetype(AVN, 200, index=index)
    c = f0.getbbox("H")
    return ImageFont.truetype(AVN, int(200 * cap_h / (c[3] - c[1])), index=index)


def text_sprite(text, font, color=INK):
    """слово/буква: спрайт по габариту глифов + смещение (ox, oy) левого верха спрайта от точки пера (x, baseline-cap)"""
    l, t, r, b = font.getbbox(text)
    pad = 4
    im = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), color + (0,))
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=font, fill=color + (255,))
    return im, (l - pad, t - pad)


def torn_rim(mask, rim, seed=1, jag=.35):
    """маска → маска с рваной каймой шириной rim (бумага вокруг глифа)"""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    m = np.array(mask) > 127
    d = ndimage.distance_transform_edt(~m)
    n = ndimage.gaussian_filter(rng.normal(0, 1, m.shape), 2.2)
    n = n / (np.abs(n).max() + 1e-6)
    fine = ndimage.gaussian_filter(rng.normal(0, 1, m.shape), .8)
    fine = fine / (np.abs(fine).max() + 1e-6)
    return d <= rim * (1 + jag * n + .12 * fine)


def sticker_glyph(ch, font, rim=None, seed=3, fill=None, outline=0):
    """глиф-наклейка: чёрный знак (или текстура fill с чёрным контуром outline px) на кремовой рваной кайме"""
    from scipy import ndimage
    l, t, r, b = font.getbbox(ch)
    rim = rim or max(6, int((b - t) * .075))
    pad = rim * 2 + 6
    w, h = r - l + 2 * pad, b - t + 2 * pad
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text((pad - l, pad - t), ch, font=font, fill=255)
    paper = torn_rim(m, rim + outline, seed)
    rng = np.random.default_rng(seed)
    a = np.zeros((h, w, 4), np.float32)
    a[..., :3] = np.array(PAPER, np.float32) + rng.normal(0, 3, (h, w, 1))
    a[..., 3] = paper * 255
    g = np.array(m, np.float32) / 255
    if fill is not None:
        ring = ndimage.distance_transform_edt(g < .5) <= outline
        gr = np.clip(ndimage.gaussian_filter(ring.astype(np.float32), .7), 0, 1)
        gi = np.clip(ndimage.gaussian_filter((ndimage.distance_transform_edt(g >= .5) > 1).astype(np.float32), .7), 0, 1)
        fz = np.array(fill.convert("RGB").resize((w, h), Image.LANCZOS), np.float32)
        a[..., :3] = a[..., :3] * (1 - gr[..., None]) + np.array(INK, np.float32) * gr[..., None]
        a[..., :3] = a[..., :3] * (1 - gi[..., None]) + fz * gi[..., None]
    else:
        a[..., :3] = a[..., :3] * (1 - g[..., None]) + np.array(INK, np.float32) * g[..., None]
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    return im, (l - pad, t - pad)


def paper_strip_sprite(text, size, angle=-1.2, seed=5):
    """подзаголовок на рваной полоске бумаги (как paper_strip шапки v3), отдельным спрайтом"""
    f = ImageFont.truetype(AVN, size, index=7)
    tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f)
    pw, ph = int(tw + size * 1.6), int(size * 1.9)
    rng = np.random.default_rng(seed)
    m = Image.new("L", (pw + 40, ph + 40), 0)
    pts = [(20 + x, 20 + rng.uniform(-3, 3)) for x in np.linspace(0, pw, 60)] + \
          [(20 + pw + rng.uniform(-4, 4), 20 + y) for y in np.linspace(0, ph, 8)] + \
          [(20 + x, 20 + ph + rng.uniform(-3, 3)) for x in np.linspace(pw, 0, 60)] + \
          [(20 + rng.uniform(-4, 4), 20 + y) for y in np.linspace(ph, 0, 8)]
    ImageDraw.Draw(m).polygon(pts, fill=255)
    paper = Image.new("RGBA", m.size, PAPER + (0,))
    paper.putalpha(m)
    ImageDraw.Draw(paper).text((20 + (pw - tw) / 2, 20 + (ph - size * 1.02) / 2 - size * .18), text, font=f, fill=INK)
    paper = paper.rotate(angle, resample=Image.BICUBIC, expand=True)
    return fix_rgb(paper, PAPER)


def tear(spr, n, seed=2, amp=14, rim=3):
    """разрезать вырезку на n рваных кусков (Вороной с шумом на границах); у кусков на разрывах — кремовая кромка.
    → [(кусок RGBA, смещение центра куска от центра спрайта (dx, dy))]"""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    a = np.array(spr, np.float32)
    al = a[..., 3] > 127
    h, w = al.shape
    ys, xs = np.where(al)
    pick = rng.choice(len(xs), 4000)
    pts = np.c_[xs[pick], ys[pick]].astype(np.float32)
    cent = pts[rng.choice(len(pts), n, replace=False)]
    for _ in range(12):                                         # k-средних: куски примерно равные
        lab = np.argmin(((pts[:, None] - cent[None]) ** 2).sum(-1), 1)
        cent = np.array([pts[lab == k].mean(0) if (lab == k).any() else cent[k] for k in range(n)])
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    d = np.stack([np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) +
                  amp * ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 6) * 6 +
                  2.5 * ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 1) for cx, cy in cent])
    lab = np.argmin(d, 0)
    out = []
    for k in range(n):
        m = (lab == k) & al
        if m.sum() < 50:
            continue
        cut = m & ndimage.binary_dilation((lab != k) & al, iterations=rim)
        rgb = a[..., :3].copy()
        rgb[cut] = np.array(PAPER, np.float32) + rng.normal(0, 4, (int(cut.sum()), 1))
        alpha = a[..., 3] * m
        yk, xk = np.where(m)
        y0, y1, x0, x1 = yk.min(), yk.max() + 1, xk.min(), xk.max() + 1
        im = Image.fromarray(np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8)).crop((x0, y0, x1, y1))
        out.append((fix_rgb(im, PAPER), ((x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - h / 2)))
    return out


# ───────── вывод видео ─────────
_render = None


def _init(fn):
    global _render
    _render = fn


def _job(fi):
    im = _render(fi)
    return im.convert("RGB").tobytes()


def write_video(render, n_frames, out_mp4, jobs=6, crf=16, frames_dir=None, only=None):
    """кадры → H.264 (без звука; звук подмешивается в mux)"""
    if only is not None:                                        # только выбранные кадры в PNG (черновой просмотр)
        os.makedirs(frames_dir, exist_ok=True)
        for fi in only:
            render(fi).save(os.path.join(frames_dir, f"f{fi:04d}.png"))
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
           "-pix_fmt", "yuv420p",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out_mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with multiprocessing.get_context("fork").Pool(jobs, initializer=_init, initargs=(render,)) as pool:
        for buf in pool.imap(_job, range(n_frames), chunksize=2):
            p.stdin.write(buf)
    p.stdin.close()
    p.wait()


def mux(video, audio_wav, out_mp4, send_mp4=None):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio_wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                    out_mp4], check=True)
    if send_mp4:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out_mp4, "-c:v", "h264_videotoolbox", "-b:v", "6M",
                        "-maxrate", "8M", "-bufsize", "12M", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", send_mp4], check=True)


# ───────── звук ─────────
_sfx = {}


def sfx(rel):
    """звук из assets/sfx → float32 (n, 2), 48 кГц"""
    if rel not in _sfx:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", os.path.join(SFX, rel), "-f", "f32le", "-ac", "2",
                              "-ar", str(SR), "-"], capture_output=True, check=True).stdout
        _sfx[rel] = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    return _sfx[rel]


class Mix:
    def __init__(self, dur):
        self.buf = np.zeros((int(dur * SR) + SR, 2), np.float32)
        self.dur = dur

    def add(self, sig, t, gain_db=0.0, pan=0.0, start=0.0, length=None, fade_in=0.0, fade_out=0.01, rate=1.0, at_peak=False):
        """сигнал (n,2) или (n,) в момент t; start/length — кусок исходника (с), rate — скорость (высота тона);
        at_peak — t означает момент пика звука (удар, хлопок), а не его начало"""
        s = np.asarray(sig, np.float32)
        if s.ndim == 1:
            s = np.c_[s, s]
        s = s[int(start * SR):]
        if rate != 1.0:
            idx = np.arange(0, len(s) - 1, rate)
            s = np.c_[np.interp(idx, np.arange(len(s)), s[:, 0]), np.interp(idx, np.arange(len(s)), s[:, 1])].astype(np.float32)
        if length is not None:
            s = s[:int(length * SR)]
        s = s.copy()
        n = len(s)
        if n == 0:
            return
        if at_peak:
            t -= int(np.abs(s).max(1).argmax()) / SR
        fi, fo = int(fade_in * SR), min(n, int(fade_out * SR))
        if fi:
            s[:fi] *= np.linspace(0, 1, fi)[:, None]
        if fo:
            s[-fo:] *= np.linspace(1, 0, fo)[:, None]
        g = 10 ** (gain_db / 20)
        lg, rg = g * math.sqrt((1 - pan) / 2) * 1.414, g * math.sqrt((1 + pan) / 2) * 1.414
        i0 = int(t * SR)
        if i0 < 0:
            s = s[-i0:]; i0 = 0
        i1 = min(len(self.buf), i0 + len(s))
        self.buf[i0:i1, 0] += s[:i1 - i0, 0] * lg
        self.buf[i0:i1, 1] += s[:i1 - i0, 1] * rg

    def cut_after(self, t, fade=0.004):
        i = int(t * SR)
        f = int(fade * SR)
        self.buf[i:i + f] *= np.linspace(1, 0, f)[:, None]
        self.buf[i + f:] = 0

    def save(self, path, target_lufs=-15.0):
        x = self.buf[:int(self.dur * SR)].copy()
        tmp = path + ".tmp.wav"
        _write_wav(tmp, x)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", tmp, "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        lufs = float([ln for ln in r.splitlines() if ln.strip().startswith("I:")][-1].split()[1])
        g = 10 ** ((target_lufs - lufs) / 20)
        x *= g
        lim = 10 ** (-3.0 / 20)                                  # мягкий предел пиков −3 дБ (AAC добавляет до 2 дБ)
        over = np.abs(x) > lim * .8
        x[over] = np.sign(x[over]) * (lim * .8 + (lim * .2) * np.tanh((np.abs(x[over]) - lim * .8) / (lim * .2)))
        _write_wav(path, x)
        os.remove(tmp)
        return lufs


def _write_wav(path, x):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


# синтез: короткие «музыкальные» звуки для джингла
def tsec(d):
    return np.arange(int(d * SR)) / SR


def kick(d=.45, f0=150, f1=48, g=1.0):
    t = tsec(d)
    f = f1 + (f0 - f1) * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t * 7.5) + .25 * np.random.default_rng(1).normal(0, 1, len(t)) * np.exp(-t * 180)
    return (np.tanh(x * 1.6) * g).astype(np.float32)


def snare(d=.3, seed=2, tone=190, g=.8):
    t = tsec(d)
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, len(t))
    n = n - np.convolve(n, np.ones(6) / 6, "same")               # без низа
    x = n * np.exp(-t * 16) * .8 + np.sin(2 * np.pi * tone * t) * np.exp(-t * 22) * .6
    return (x * g).astype(np.float32)


def clap(d=.28, seed=4, g=.7):
    t = tsec(d)
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, len(t))
    n = n - np.convolve(n, np.ones(10) / 10, "same")
    env = np.zeros(len(t))
    for k, o in enumerate((0, .011, .022)):
        i = int(o * SR)
        env[i:] += np.exp(-(t[i:] - o) * (140 if k < 2 else 18))
    return (n * env * g).astype(np.float32)


def hat(d=.08, seed=5, g=.35):
    t = tsec(d)
    n = np.random.default_rng(seed).normal(0, 1, len(t))
    n = n - np.convolve(n, np.ones(3) / 3, "same")
    return (n * np.exp(-t * 60) * g).astype(np.float32)


def pluck(freq, d=.5, bright=1.0, g=.5):
    t = tsec(d)
    x = sum((1 / k ** (1.3 / bright)) * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (5 + 4 * k)) for k in range(1, 9))
    att = np.minimum(1, t / .003)
    return (x * att * g).astype(np.float32)


def bell(freq, d=1.2, g=.35):
    t = tsec(d)
    mod = np.sin(2 * np.pi * freq * 3.5 * t) * 2.2 * np.exp(-t * 6)
    x = np.sin(2 * np.pi * freq * t + mod) * np.exp(-t * 3.2) + .3 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 5)
    return (x * np.minimum(1, t / .002) * g).astype(np.float32)


def bass(freq, d=.6, g=.5):
    t = tsec(d)
    x = sum(((-1) ** (k + 1)) / k * np.sin(2 * np.pi * freq * k * t) for k in range(1, 12))
    lp = np.exp(-t * 7)
    x = np.tanh(x * 1.2) * (lp * .9 + .1) * np.exp(-t * 2.5)
    return (x * np.minimum(1, t / .004) * g).astype(np.float32)


def note(name):
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    n, o = name[:-1], int(name[-1])
    return 440 * 2 ** ((names[n] + 12 * (o + 1) - 69) / 12)


def reverse(sig):
    return np.asarray(sig)[::-1].copy()
