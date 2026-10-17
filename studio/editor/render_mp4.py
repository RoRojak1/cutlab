#!/usr/bin/env python3
"""Рендер проекта Cutlab в MP4 (этап 3 редактора).

Картинка повторяет плеер Cutlab (web/js/player/viewer.js): кадры v1 (видео / картинка / карточка) с наездами,
панорамами, тряской и переходами-входами, Ник с хромакеем поверх кадра (петлёй), надписи (a-kw / a-ost, слова
по c.words). Звук — как живое сведение (mixplan.js buildCues + mix.js): голос, музыка (петля с перекрёстной
склейкой 1,5 с), эффекты, звук роликов (−22 дБ по умолчанию), уровни project.settings.levels_db.
Выключенные/соло-дорожки интерфейса не учитываются — рендерится всё.

  python3 studio/editor/render_mp4.py --project ep02 [--from 0 --to 80] [--jobs 8] [--out export/ep02/ep02_cut.mp4]

Картинка рендерится сегментами (кадр v1, длинные — кусками по 10 с) параллельно, каждый сегмент кэшируется в
export/<pid>/render_cache/<хэш параметров>.mp4 — после правок перерисовываются только изменившиеся. Потом склейка
без перекодирования (concat) + звук AAC 192k 48 кГц, громкость ≈ −14 LUFS, пик ≤ −1 dBTP.
Нет файла / не читается — вместо кадра карточка «нет файла» и предупреждение (рендер не падает).
"""
import argparse, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model as M  # noqa: E402

ROOT = M.ROOT
W, H, FPS = 1920, 1080, 30
ZOOM = 0.06
K = 1.15                      # запас разрешения под наезд/сдвиг (как в studio/capcut/render.py)
SR = 48000
SPF = SR // FPS               # сэмплов звука на кадр (1600)
XF = 1.5                      # перекрёстная склейка петли музыки (mix.js)
CHUNK = 300                   # длинные клипы режем на куски по 10 с (сетка от начала клипа — кэш стабилен)
RENDER_VERSION = "r1"
TARGET_LUFS = -14.0
TARGET_TP = -1.5              # запас 0,5 дБ на AAC, итог ≤ −1 dBTP
ENC_TAIL = ["-pix_fmt", "yuv420p", "-g", "90", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-video_track_timescale", "15360", "-movflags", "+faststart", "-an"]


def enc_args(mode="x264", preset="fast", crf=20):
    """x264 (по умолчанию: CRF 20, preset fast, High) или vt — аппаратный VideoToolbox (в разы быстрее, чуть хуже)"""
    if mode == "vt":
        return ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-q:v", "72"] + ENC_TAIL
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-threads", "2"] + ENC_TAIL
FONT_MAIN = ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8)          # Heavy (800)
FONT_FALLBACK = [("/System/Library/Fonts/Supplemental/Impact.ttf", 0),       # кириллица (как Impact в CSS-цепочке)
                 ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0)]
LEVEL_BUS = {"voice": "voice", "music": "music", "sfx1": "sfx", "sfx2": "sfx", "v1": "video"}


def fr(t):
    """секунды → номер кадра (время в проекте кратно 1/30)"""
    return int(round(float(t) * FPS + 1e-9))


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def rel(p):
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def absp(src):
    p = Path(src)
    return p if p.is_absolute() else ROOT / p


def file_sig(src):
    p = absp(src)
    try:
        st = p.stat()
        return [st.st_size, st.st_mtime_ns] if p.is_file() else None
    except OSError:
        return None


# ------------------------------------------------------------------ геометрия (viewer.js motion / outer)
def motion(m, p, t):
    """→ (scale, tx_frac, ty_frac, rot_deg)"""
    if m == "zoom_in":
        return 1 + ZOOM * p, 0, 0, 0
    if m == "zoom_out":
        return 1 + ZOOM - ZOOM * p, 0, 0, 0
    if m == "pan_left":
        return 1 + ZOOM + 0.01, (-2.5 + 5 * p) / 100, 0, 0
    if m == "pan_right":
        return 1 + ZOOM + 0.01, (2.5 - 5 * p) / 100, 0, 0
    if m == "pan_up":
        return 1 + ZOOM + 0.01, 0, (-2.5 + 5 * p) / 100, 0
    if m == "pan_down":
        return 1 + ZOOM + 0.01, 0, (2.5 - 5 * p) / 100, 0
    if m == "shake":
        n = lambda k: math.sin(t * 37 * k) * 0.6 + math.sin(t * 91 * k + 1.3) * 0.4
        return 1.06, n(1) * 0.9 / 100, n(1.37) * 0.7 / 100, n(0.71) * 0.5
    return 1, 0, 0, 0


def outer(tr, lt):
    """переход-вход → (scale, tx_frac, ty_px, blur_px, veil_rgb, veil_alpha, glitch_k)"""
    s, tx, ty, blur, veil, va, gk = 1.0, 0.0, 0.0, 0.0, (0, 0, 0), 0.0, None
    if tr == "slide" and lt < 0.3:
        tx = 1 - ease(lt / 0.3)
    elif tr == "whoosh" and lt < 0.28:
        k = 1 - ease(lt / 0.28); tx = k * 0.35; blur = k * 28
    elif tr == "zoom_punch" and lt < 0.25:
        s = 1 + 0.22 * (1 - lt / 0.25) ** 2
    elif tr == "glitch" and lt < 0.35:
        gk = int(lt * 40); tx = (((gk * 37) % 13) - 6) * 2 / W; ty = (((gk * 17) % 7) - 3) * 2
    if tr == "flash" and lt < 0.3:
        veil, va = (255, 255, 255), 1 - lt / 0.3
    if tr == "dip_black" and lt < 0.4:
        veil, va = (0, 0, 0), 1 - lt / 0.4
    return s, tx, ty, blur, veil, va, gk


def affine_for(sm, txm, tym, rot, so, txo, tyo_px, k):
    """обратное аффинное: пиксель кадра → пиксель контента (контент нарисован в масштабе k).
    Canvas: translate(W/2+tx*W, H/2+ty) scale(s) rotate(r) translate(-W/2+txm*W, -H/2+tym*H)"""
    cx, cy = W / 2, H / 2
    tlx, tly = txm * W, tym * H
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    S = sm * so
    tox, toy = txo * W, tyo_px
    A_, B_, D_, E_ = ca / S, sa / S, -sa / S, ca / S
    C_ = cx - tlx - A_ * (cx + tox) - B_ * (cy + toy)
    F_ = cy - tly - D_ * (cx + tox) - E_ * (cy + toy)
    return (A_ * k, B_ * k, C_ * k, D_ * k, E_ * k, F_ * k)


def hue_glitch(im, gk):
    """≈ CSS hue-rotate(gk*97°) saturate(2.2) contrast(1.3)"""
    im = ImageEnhance.Color(im).enhance(2.2)
    im = ImageEnhance.Contrast(im).enhance(1.3)
    r, g, b = im.split()
    return Image.merge("RGB", [(r, g, b), (g, b, r), (b, r, g)][(gk * 97) % 3])


def compose_frame(content, k, mot, trans, lt, gt, p):
    sm, txm, tym, rot = motion(mot, p, gt)
    so, txo, tyo, blur, veil, va, gk = outer(trans, lt)
    if (sm, txm, tym, rot, so, txo, tyo) == (1, 0, 0, 0, 1.0, 0.0, 0.0) and content.size == (W, H):
        fr_ = content
    else:
        fr_ = None
        if rot == 0:
            # без поворота — масштаб+сдвиг: resize с дробной рамкой (плавно, со сглаживанием и в 3–4 раза быстрее transform)
            S = sm * so
            cw, ch = content.size
            x0 = ((-W / 2 - txo * W) / S + W / 2 - txm * W) * k
            x1 = ((W / 2 - txo * W) / S + W / 2 - txm * W) * k
            y0 = ((-H / 2 - tyo) / S + H / 2 - tym * H) * k
            y1 = ((H / 2 - tyo) / S + H / 2 - tym * H) * k
            if x0 >= -1e-3 and y0 >= -1e-3 and x1 <= cw + 1e-3 and y1 <= ch + 1e-3:
                fr_ = content.resize((W, H), Image.BICUBIC, box=(max(0.0, x0), max(0.0, y0), min(cw, x1), min(ch, y1)))
        if fr_ is None:
            fr_ = content.transform((W, H), Image.AFFINE, affine_for(sm, txm, tym, rot, so, txo, tyo, k),
                                    resample=Image.BICUBIC, fillcolor=(0, 0, 0))
    if blur > 0.5:
        fr_ = fr_.filter(ImageFilter.GaussianBlur(blur))
    if gk is not None:
        fr_ = hue_glitch(fr_, gk)
    if va > 0:
        fr_ = Image.blend(fr_, Image.new("RGB", (W, H), veil), min(1.0, va))
    return fr_


# ------------------------------------------------------------------ шрифты (Avenir Next Condensed → Impact → Arial Unicode)
_FONTS = {}
_NOTDEF = {}


def font(i, size):
    key = (i, int(size))
    if key not in _FONTS:
        path, idx = ([FONT_MAIN] + FONT_FALLBACK)[i]
        try:
            _FONTS[key] = ImageFont.truetype(path, max(1, int(size)), index=idx)
        except OSError:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _mask(f, ch):
    m = f.getmask(ch)
    return m.size, bytes(m)


_FONT_FOR = {}


def font_for(ch):
    """первый шрифт цепочки, в котором есть глиф (как подстановка шрифтов в браузере)"""
    if ch not in _FONT_FOR:
        _FONT_FOR[ch] = _font_for(ch)
    return _FONT_FOR[ch]


def _font_for(ch):
    if ch.isspace():
        return 0
    for i in range(len(FONT_FALLBACK)):
        f = font(i, 64)
        if i not in _NOTDEF:
            _NOTDEF[i] = _mask(f, "\ue000")
        if _mask(f, ch) != _NOTDEF[i]:
            return i
    return len(FONT_FALLBACK)


def runs(text):
    out = []
    for ch in text:
        i = font_for(ch)
        if out and out[-1][0] == i:
            out[-1][1] += ch
        else:
            out.append([i, ch])
    return out


def text_width(text, size):
    return sum(font(i, size).getlength(s) for i, s in runs(text))


def draw_text(dr, x, y_mid, text, size, fill, align="center"):
    """строка из нескольких шрифтов; y_mid — середина строки (как textBaseline='middle')"""
    asc, desc = font(0, size).getmetrics()
    base = y_mid + (asc - desc) / 2
    w = text_width(text, size)
    cx = x - w / 2 if align == "center" else x
    for i, s in runs(text):
        f = font(i, size)
        dr.text((cx, base), s, font=f, fill=fill, anchor="ls")
        cx += f.getlength(s)


# ------------------------------------------------------------------ карточка (viewer.js drawCard)
def card_image(text):
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt((xx - W * 0.5) ** 2 + (yy - H * 0.45) ** 2) / math.hypot(W * 0.5, H * 0.55)
    d = np.clip(d, 0, 1)[..., None]
    c0, c1 = np.array([0x1b, 0x1d, 0x22], np.float32), np.array([0x07, 0x08, 0x09], np.float32)
    im = Image.fromarray((c0 * (1 - d) + c1 * d + 0.5).astype("uint8"))
    dr = ImageDraw.Draw(im)
    size = 0.09 * W
    words = str(text or "").upper().split()
    while True:
        lines, cur = [], ""
        for w_ in words:
            tt = (cur + " " + w_).strip()
            if text_width(tt, size) <= W * 0.88 or not cur:
                cur = tt
            else:
                lines.append(cur); cur = w_
        if cur:
            lines.append(cur)
        lh = size * 0.98
        # в плеере длинный текст уходит за край; в рендере уменьшаем кегль, чтобы всё влезло
        if lh * len(lines) <= H * 0.92 or size < 0.03 * W:
            break
        size *= 0.92
    y0 = H / 2 - lh * len(lines) / 2
    for k, ln in enumerate(lines):
        draw_text(dr, W / 2, y0 + lh * k + lh / 2, ln, size, (0xff, 0xd2, 0x3f))
    return im


# ------------------------------------------------------------------ надписи (app.css .a-kw / .a-ost, viewer.js drawText)
def _hex(c, default):
    try:
        c = str(c).strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        if re.fullmatch(r"#[0-9a-fA-F]{3}", c):
            return tuple(int(ch * 2, 16) for ch in c[1:])
    except Exception:
        pass
    return default


def _word_img(text, size, color, lh, shadow=None):
    """RGBA-картинка слова: ширина = ширина текста, высота = line-height; базовая линия как в CSS (half-leading)"""
    asc, desc = font(0, size).getmetrics()
    w_ = max(1, int(math.ceil(text_width(text, size))))
    pad = int(size * 0.15)
    hh = int(math.ceil(lh))
    box = (w_ + 2 * pad, hh + 2 * pad)
    y_mid = pad + lh / 2
    mask = Image.new("L", box, 0)                      # маска отдельно — без тёмной каймы по краям букв
    draw_text(ImageDraw.Draw(mask), pad, y_mid, text, size, 255, align="left")
    im = Image.new("RGBA", box, tuple(color) + (0,))
    im.putalpha(mask)
    if shadow:
        dy, (sr, sg, sb, sa) = shadow
        sm = Image.new("L", box, 0)
        draw_text(ImageDraw.Draw(sm), pad, y_mid + dy, text, size, 255, align="left")
        sh = Image.new("RGBA", box, (sr, sg, sb, 0))
        sh.putalpha(sm.point(lambda v: v * sa // 255))
        im = Image.alpha_composite(sh, im)
    return im, pad, w_


class TextLayer:
    """одна надпись с дорожки text; рисуется поверх кадра (не двигается вместе с ним)"""

    def __init__(self, spec):
        self.s = spec
        self.style = spec.get("style")
        up = str(spec.get("text") or "").upper()
        col = _hex(spec.get("color"), (255, 255, 255))
        if self.style == "keyword":
            size = 0.086 * W
            self.img, self.pad, self.w = _word_img(up, size, col, size, shadow=(0.0035 * W, (0, 0, 0, 89)))
            self.cx, self.cy = W / 2, H * 0.83 - size / 2          # bottom: 17%, line-height 1
            self._cache = {}
        else:
            size, lh, gap = 0.12 * W, 0.12 * W * 0.95, 0.022 * W
            words = spec.get("words") or []
            if words:
                items = [(str(w_[0]).upper(), float(w_[1]) if len(w_) > 1 else 0.0) for w_ in words]
            else:
                items = [(w_, 0.0) for w_ in up.split()]
            self.words = []
            for wt, t0 in items:
                c = (0xff, 0xd2, 0x3f) if re.search(r"\d", wt) else col
                img, pad, ww = _word_img(wt, size, c, lh)
                self.words.append({"img": img, "pad": pad, "w": ww, "t0": t0})
            maxw = W - 2 * 0.05 * W
            lines, cur, curw = [], [], 0.0
            for wd in self.words:
                add = wd["w"] + (gap if cur else 0)
                if cur and curw + add > maxw:
                    lines.append((cur, curw)); cur, curw = [], 0.0; add = wd["w"]
                cur.append(wd); curw += add
            if cur:
                lines.append((cur, curw))
            top = H / 2 - lh * len(lines) / 2
            for li, (ln, lw) in enumerate(lines):
                x = W / 2 - lw / 2
                for wd in ln:
                    wd["x"], wd["y"] = x, top + li * lh
                    wd["ox"], wd["oy"] = x + wd["w"] * 0.5, top + li * lh + lh * 0.6   # transform-origin 50% 60%
                    x += wd["w"] + gap

    @staticmethod
    def _paste(frame, img, pad, x, y, scale, origin, alpha=1.0):
        if scale != 1.0:
            nw, nh = max(1, int(round(img.width * scale))), max(1, int(round(img.height * scale)))
            img = img.resize((nw, nh), Image.BICUBIC)
            ox, oy = origin
            x = ox + (x - pad - ox) * scale
            y = oy + (y - pad - oy) * scale
        else:
            x, y = x - pad, y - pad
        if alpha < 1.0:
            a = img.getchannel("A").point(lambda v: int(v * alpha))
            img = img.copy(); img.putalpha(a)
        frame.paste(img, (int(round(x)), int(round(y))), img)

    def draw(self, frame, lt):
        if self.style == "keyword":
            k = max(0.0, min(1.0, lt / 0.18))
            if k <= 0:
                return
            sc = 0.6 + 0.48 * ease(k)
            x, y = self.cx - self.w / 2, self.cy - self.img.height / 2 + self.pad
            self._paste(frame, self.img, self.pad, x, y, sc, (self.cx, self.cy), alpha=k)
            return
        for wd in self.words:
            d = lt - wd["t0"]
            if d < 0:
                continue
            q = max(0.0, min(1.0, d / 0.12))
            sc = 1.35 - 0.35 * ease(q)
            self._paste(frame, wd["img"], wd["pad"], wd["x"], wd["y"], sc, (wd["ox"], wd["oy"]))


# ------------------------------------------------------------------ источники кадров
_PROBE = {}


def probe(src):
    key = str(src)
    if key not in _PROBE:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=index,codec_type,width,height,pix_fmt,color_space,color_range,channels:format=duration",
                            "-of", "json", str(src)], capture_output=True, text=True)
        try:
            j = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            j = {}
        v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
        a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
        try:
            dur = float(j.get("format", {}).get("duration") or 0)
        except ValueError:
            dur = 0.0
        _PROBE[key] = {"v": v, "a": a, "dur": dur}
    return _PROBE[key]


def color_in(src):
    """матрица и диапазон источника для перевода в RGB/bt709 (без метки: HD → bt709, SD → bt601, как браузер)"""
    v = probe(src)["v"] or {}
    cs = v.get("color_space") or ""
    if cs in ("bt709",):
        m = "bt709"
    elif cs in ("smpte170m", "bt470bg", "bt601", "fcc"):
        m = "bt601"
    else:
        m = "bt709" if (v.get("height") or 0) >= 720 else "bt601"
    rng = "pc" if (str(v.get("pix_fmt", "")).startswith("yuvj") or v.get("color_range") == "pc") else "tv"
    return m, rng


def fit_filter(fit, cw, ch, src, out_rgb):
    m, rng = color_in(src)
    if out_rgb:
        sc = f"scale={cw}:{ch}:force_original_aspect_ratio=%s:flags=lanczos:in_color_matrix={m}:in_range={rng},format=rgb24"
    else:
        sc = (f"scale={cw}:{ch}:force_original_aspect_ratio=%s:flags=lanczos:in_color_matrix={m}:in_range={rng}"
              f":out_color_matrix=bt709:out_range=tv,format=yuv420p")
    if fit == "fit":
        return (sc % "decrease") + f",pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    return (sc % "increase") + f",crop={cw}:{ch},setsar=1"


def ffmpeg_frames(args, n, size, fallback=None):
    """сырые RGB-кадры из ffmpeg; источник кончился — держим последний кадр (как <video> в конце).
    Возвращает генератор; сколько реально прочитано — в gen.got (через список)"""
    cw, ch = size
    fsz = cw * ch * 3
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-threads", "2"] + args +
                         ["-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    got = 0
    last = None
    try:
        while got < n:
            buf = p.stdout.read(fsz)
            if len(buf) < fsz:
                break
            last = Image.frombytes("RGB", (cw, ch), buf)
            got += 1
            yield last
    finally:
        p.stdout.close(); p.wait()
    if last is None and fallback is not None:
        last = fallback()                       # начало за концом ролика — стоит последний кадр (как <video> в конце)
    if last is None:
        raise RuntimeError("не удалось прочитать ни одного кадра")
    for _ in range(n - got):
        yield last


def video_last_frame(src, vf, size):
    """последний кадр ролика (ffmpeg с −1 с до конца, берём последний прочитанный)"""
    cw, ch = size
    fsz = cw * ch * 3
    for back in ("-1.0", "-3.0"):
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-sseof", back, "-i", str(src), "-an", "-sn", "-dn", "-vf", vf,
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        k = len(r.stdout) // fsz
        if k:
            return Image.frombytes("RGB", (cw, ch), r.stdout[(k - 1) * fsz: k * fsz])
    return None


def video_source(seg, k):
    """кадры v1-видео (вперёд или назад) в масштабе k, с учётом in / speed / reverse"""
    cw, ch = int(W * k), int(H * k)
    src = absp(seg["src"])
    sp = float(seg.get("speed") or 1) or 1.0
    vin = float(seg.get("in") or 0)
    j0, n = seg["j0"], seg["j1"] - seg["j0"]
    vf = f"setpts=(PTS-STARTPTS)/{sp:.6f},fps={FPS}," + fit_filter(seg.get("fit"), cw, ch, src, True)
    tail = lambda: video_last_frame(src, fit_filter(seg.get("fit"), cw, ch, src, True), (cw, ch))
    if not seg.get("reverse"):
        ss = vin + j0 / FPS * sp
        yield from ffmpeg_frames(["-ss", f"{ss:.4f}", "-i", str(src), "-an", "-sn", "-dn", "-vf", vf], n, (cw, ch), tail)
        return
    # назад: want = in + (dur − lt)·speed; читаем блоками с конца, каждый блок разворачиваем
    cdur = seg["cdur"] / FPS
    sdur = probe(src)["dur"] or 1e9
    B = 45
    j = 0
    while j < n:
        b = min(B, n - j)
        jl = j0 + j + b - 1                                       # последний кадр блока = самый ранний момент
        ts = vin + (cdur - jl / FPS) * sp
        ts = max(0.0, min(ts, sdur - 1.0 / FPS))
        block = list(ffmpeg_frames(["-ss", f"{ts:.4f}", "-i", str(src), "-an", "-sn", "-dn", "-vf", vf], b, (cw, ch), tail))
        for im in reversed(block):
            yield im
        j += b


def image_content(src, fit, k):
    """картинка под кадр (как drawFit: cover / contain на чёрном), заранее уменьшенная"""
    cw, ch = int(W * k), int(H * k)
    im = Image.open(absp(src))
    try:
        im.draft("RGB", (cw, ch))          # JPEG: декодировать сразу в меньшем размере (4K → быстрее)
    except Exception:
        pass
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        bg.alpha_composite(im)
        im = bg
    im = im.convert("RGB")
    iw, ih = im.size
    sc = min(cw / iw, ch / ih) if fit == "fit" else max(cw / iw, ch / ih)
    nw, nh = max(1, round(iw * sc)), max(1, round(ih * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (cw, ch), (0, 0, 0))
    canvas.paste(im, ((cw - nw) // 2, (ch - nh) // 2))
    return canvas


def chroma_key(rgb):
    """порт viewer.js chromaKey: мягкий край + подавление зелёного → (rgb, alpha 0..1)"""
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = np.maximum(r, b)
    diff = g - m
    c0 = (diff > 70) & (g > 90)
    c1 = (~c0) & (diff > 22)
    c2 = (~c0) & (~c1) & (diff > 0)
    alpha = np.ones(diff.shape, np.float32)
    alpha[c1] = np.clip(1 - (diff[c1] - 22) / 48.0, 0, 1)
    alpha[c0] = 0
    g2 = g.astype(np.float32)
    g2[c1] = m[c1]
    g2[c2] = m[c2] + diff[c2] * 0.4
    out = np.stack([r, g2, b], -1).astype(np.float32)
    return out, alpha[..., None]


class NickSource:
    """Ник на хромакее: клип зациклен от начала своего клипа на дорожке"""

    def __init__(self, ov, k):
        self.a, self.b = ov["a"], ov["b"]
        cw, ch = int(W * k), int(H * k)
        src = absp(ov["src"])
        L = probe(src)["dur"] or 0
        off = ov["off"]
        if L > 0.15:
            off = off % max(0.1, L - 0.05)
        vf = f"fps={FPS}," + fit_filter("fill", cw, ch, src, True)
        self.gen = ffmpeg_frames(["-stream_loop", "-1", "-ss", f"{off:.4f}", "-i", str(src), "-an", "-sn", "-dn", "-vf", vf],
                                 self.b - self.a, (cw, ch))

    def over(self, content, j):
        if not (self.a <= j < self.b):
            return content
        fg = next(self.gen)
        f, al = chroma_key(np.asarray(fg))
        bg = np.asarray(content).astype(np.float32)
        return Image.fromarray((f * al + bg * (1 - al) + 0.5).astype(np.uint8))


# ------------------------------------------------------------------ рендер одного сегмента
def seg_needs_pil(seg):
    return bool(seg.get("nick") or seg.get("texts") or seg["kind"] != "video" or seg.get("reverse")
                or (seg.get("motion") or "static") != "static" or (seg.get("transition") or "cut") != "cut")


def encoder(out, enc):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"] + enc + ["-r", str(FPS), str(out)],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def count_frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    m = re.search(r"\d+", r.stdout)            # ffmpeg 9 печатает число ещё раз для «групп потоков»
    return int(m.group(0)) if m else -1


def render_fast_video(seg, out):
    """статичный кадр-видео без наложений — одним ffmpeg (декод + масштаб + кодирование)"""
    src = absp(seg["src"])
    sp = float(seg.get("speed") or 1) or 1.0
    n = seg["j1"] - seg["j0"]
    ss = float(seg.get("in") or 0) + seg["j0"] / FPS * sp
    sdur = probe(src)["dur"]
    if sdur and ss > sdur - 0.5:
        raise RuntimeError("начало у конца ролика")        # стоп-кадр последнего кадра — через PIL-путь
    vf = (f"setpts=(PTS-STARTPTS)/{sp:.6f},fps={FPS}," + fit_filter(seg.get("fit"), W, H, src, False) +
          f",tpad=stop_mode=clone:stop_duration={n / FPS + 1:.3f}")
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "2", "-ss", f"{ss:.4f}", "-i", str(src),
                        "-map", "0:v:0", "-map_metadata", "-1", "-an", "-sn", "-dn", "-vf", vf, "-frames:v", str(n)]
                       + seg["enc"] + ["-r", str(FPS), str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    got = count_frames(out)
    if got != n:
        raise RuntimeError(f"кадров {got} из {n}")


def render_pil(seg, out, warn):
    n = seg["j1"] - seg["j0"]
    mot = seg.get("motion") or "static"
    trans = seg.get("transition") or "cut"
    moving = mot != "static" or trans not in ("cut", "flash", "dip_black")
    k = K if moving else 1.0
    cw, ch = int(W * k), int(H * k)
    kind = seg["kind"]
    if kind == "video":
        src_frames = video_source(seg, k)
    elif kind == "image":
        c = image_content(seg["src"], seg.get("fit"), k)
        src_frames = (c for _ in range(n))
    elif kind == "card":
        c = card_image(seg.get("text") or "")
        if k != 1.0:
            c = c.resize((cw, ch), Image.LANCZOS)
        src_frames = (c for _ in range(n))
    else:                                           # дыра (gap) / клип без файла (blank) — чёрный
        c = Image.new("RGB", (cw, ch))
        src_frames = (c for _ in range(n))
    nicks = [NickSource(ov, k) for ov in seg.get("nick") or []]
    texts = [(TextLayer(t), t) for t in seg.get("texts") or []]
    cdur = max(1e-6, seg["cdur"] / FPS)
    enc = encoder(out, seg["enc"])
    cnt = 0
    last_obj, last_bytes = None, None
    try:
        for jj, content in enumerate(src_frames):
            j = seg["j0"] + jj                      # кадр от начала клипа
            lt = j / FPS
            gt = (seg["g0"] + jj) / FPS             # время проекта
            for ns in nicks:
                content = ns.over(content, jj)
            frame = compose_frame(content, k, mot, trans, lt, gt, min(1.0, lt / cdur)) if kind != "gap" else content
            if texts:
                frame = frame.copy() if frame is content else frame
                for tl, t in texts:
                    tlt = gt - t["start"]
                    if 0 <= tlt < t["dur"]:
                        tl.draw(frame, tlt)
            if frame is not last_obj:                # неподвижная картинка — байты одни и те же
                last_obj, last_bytes = frame, frame.tobytes()
            enc.stdin.write(last_bytes)
            cnt += 1
            if cnt >= n:
                break
    finally:
        try:
            enc.stdin.close()
        except BrokenPipeError:
            pass
        err = enc.stderr.read().decode(errors="replace")
        enc.wait()
    if enc.returncode != 0 or cnt != n:
        raise RuntimeError(f"кодирование: rc={enc.returncode} кадров {cnt}/{n} {err[-200:]}")


def render_segment(seg):
    """→ (key, warnings, seconds, путь). Пишет export/<pid>/render_cache/<key>.mp4.
    Файл не читается — карточка пишется в <key>.err.mp4 (не кэшируется: в следующий раз попробуем снова)."""
    t0 = time.time()
    out = Path(seg["out"])
    tmp = out.with_name(out.stem + f".part{os.getpid()}.mp4")
    warns = []
    try:
        if seg.get("missing"):
            warns.append(f"{seg['clip']}: нет файла {seg['src']} — карточка")
            seg = dict(seg, kind="card", text=f"{seg['clip']} · нет файла · {Path(seg['src']).name}",
                       motion="static", transition="cut")
        try:
            if seg_needs_pil(seg):
                render_pil(seg, tmp, warns)
            else:
                try:
                    render_fast_video(seg, tmp)
                except Exception:
                    render_pil(seg, tmp, warns)         # запасной путь: кадр за кадром (держит последний кадр)
        except Exception as e:  # файл не читается — карточка вместо кадра
            if seg["kind"] in ("video", "image"):
                warns.append(f"{seg['clip']}: не читается {seg.get('src')} ({str(e)[:120]}) — карточка")
                seg2 = dict(seg, kind="card", text=f"{seg['clip']} · файл не читается · {Path(seg['src']).name}",
                            motion="static", transition="cut", nick=[])
                render_pil(seg2, tmp, warns)
                out = out.with_name(out.stem + ".err.mp4")
            else:
                raise
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()
    return seg["key"], warns, time.time() - t0, str(out)


# ------------------------------------------------------------------ план сегментов
def build_segments(proj, fa, fb, total, cache, enc):
    clips = proj.get("clips", [])
    v1 = sorted((c for c in clips if c.get("track") == "v1"), key=lambda c: c["start"])
    nick = [c for c in clips if c.get("track") == "nick" and c.get("src")]
    texts = [c for c in clips if c.get("track") == "text"]
    spans, cur = [], 0
    for c in v1:
        a, b = fr(c["start"]), fr(c["start"] + c["dur"])
        if a > cur:
            spans.append((None, cur, a))
        a = max(a, cur)
        if b > a:
            spans.append((c, a, b))
        cur = max(cur, b)
    if cur < total:
        spans.append((None, cur, total))
    segs = []
    for c, a, b in spans:
        cstart = fr(c["start"]) if c else a
        cdur = (fr(c["start"] + c["dur"]) - cstart) if c else (b - a)
        base_j = a - cstart                          # сдвиг, если клип перекрыт предыдущим
        for q in range(0, b - a, CHUNK) if c else [0]:
            j0 = base_j + q
            j1 = min(base_j + (q + CHUNK if c else b - a), b - cstart)
            g0, g1 = cstart + j0, cstart + j1
            g0c, g1c = max(g0, fa), min(g1, fb)       # отрезок --from/--to
            if g1c <= g0c:
                continue
            j0c, j1c = j0 + (g0c - g0), j1 - (g1 - g1c)
            seg = {"g0": g0c, "g1": g1c, "j0": j0c, "j1": j1c, "cdur": cdur}
            if c:
                kind = c.get("kind") or ""
                seg.update(clip=c["id"], kind=kind, motion=c.get("motion") or "static",
                           transition=c.get("transition") or "cut", fit=c.get("fit") or "fill")
                if kind in ("video", "image"):
                    if c.get("src"):
                        seg["src"] = c["src"]
                        seg["sig"] = file_sig(c["src"])
                        seg["missing"] = seg["sig"] is None
                    else:
                        seg["kind"] = "blank"          # клип без файла — чёрный (Ник поверх рисуется), как в плеере
                if kind == "video":
                    seg.update({"in": float(c.get("in") or 0), "speed": float(c.get("speed") or 1),
                                "reverse": bool(c.get("reverse"))})
                elif kind == "card":
                    seg["text"] = c.get("text") or ""
                elif kind not in ("image",):
                    seg["kind"] = "blank"
                if seg["motion"] == "shake":
                    seg["gstart"] = cstart            # тряска зависит от времени проекта
            else:
                seg.update(clip=f"gap@{a / FPS:.2f}", kind="gap", motion="static", transition="cut")
            if seg["kind"] != "gap":
                ns = []
                for n in nick:
                    na, nb = fr(n["start"]), fr(n["start"] + n["dur"])
                    lo, hi = max(na, g0c), min(nb, g1c)
                    if hi > lo:
                        ns.append({"src": n["src"], "sig": file_sig(n["src"]), "a": lo - g0c, "b": hi - g0c,
                                   "off": (lo - na) / FPS})
                ns = [x for x in ns if x["sig"]]
                if ns:
                    seg["nick"] = ns
            ts = []
            for t in texts:
                ta, tb = fr(t["start"]), fr(t["start"] + t["dur"])
                if min(tb, g1c) > max(ta, g0c):
                    ts.append({"text": t.get("text") or "", "style": t.get("style"), "words": t.get("words") or [],
                               "color": t.get("color"), "font": t.get("font"), "start": ta / FPS, "dur": (tb - ta) / FPS})
            if ts:
                seg["texts"] = ts
            spec = {k: v for k, v in seg.items() if k not in ("g0", "g1", "clip")}
            if seg.get("missing"):
                spec["clip"] = seg["clip"]            # в карточке «нет файла» — имя кадра
            if not seg.get("nick") and not ts and seg.get("motion") != "shake":
                spec.pop("gstart", None)
            if ts:
                spec["tg0"] = g0c                     # надписи привязаны к времени проекта
            spec["v"] = RENDER_VERSION
            spec["enc"] = enc
            seg["enc"] = enc
            key = hashlib.sha1(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
            seg["key"] = key
            seg["out"] = str(cache / f"{key}.mp4")
            segs.append(seg)
    return segs


# ------------------------------------------------------------------ звук (mixplan.js buildCues + mix.js)
def build_cues(proj):
    out = []
    for c in proj.get("clips", []):
        tr = c.get("track")
        if tr not in LEVEL_BUS:
            continue
        if c.get("kind") == "pause" or c.get("mute") or not c.get("src"):
            continue
        if tr == "v1" and c.get("kind") != "video":
            continue
        if tr == "v1" and c.get("reverse"):
            continue                                  # в плеере ролик назад стоит на паузе — без звука
        out.append({"id": c["id"], "bus": LEVEL_BUS[tr], "src": c["src"], "at": fr(c["start"]) / FPS,
                    "offset": float(c.get("in") or 0), "dur": (fr(c["start"] + c["dur"]) - fr(c["start"])) / FPS,
                    "gain_db": c.get("volume_db"), "loop": bool(c.get("loop")), "fi": float(c.get("fade_in") or 0),
                    "fo": float(c.get("fade_out") or 0), "element": tr == "v1", "speed": float(c.get("speed") or 1)})
    return sorted(out, key=lambda c: c["at"])


def level_db(proj, bus):
    lv = (proj.get("settings") or {}).get("levels_db") or {}
    d = M.LEVELS.get(bus, 0)
    try:
        return float(lv.get(bus, d)) - d
    except (TypeError, ValueError):
        return 0.0


def decode_audio(src, ss=None, t=None, speed=1.0):
    """→ float32 (n, 2) 48 кГц; моно размножается на оба канала без ослабления (как Web Audio)"""
    info = probe(absp(src))
    a = info["a"]
    if not a:
        return None
    chn = 1 if (a.get("channels") or 2) == 1 else 2
    args = ["ffmpeg", "-v", "error", "-nostdin"]
    if ss:
        args += ["-ss", f"{ss:.4f}"]
    if t:
        args += ["-t", f"{t:.4f}"]
    args += ["-i", str(absp(src)), "-vn", "-sn", "-dn"]
    af = []
    s = speed
    while s > 2.0:
        af.append("atempo=2.0"); s /= 2.0
    while s < 0.5:
        af.append("atempo=0.5"); s /= 0.5
    if abs(s - 1) > 1e-6:
        af.append(f"atempo={s:.6f}")
    if af:
        args += ["-af", ",".join(af)]
    args += ["-ac", str(chn), "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(args, capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    if chn == 1:
        return np.repeat(x[:, None], 2, axis=1)
    return x[: len(x) // 2 * 2].reshape(-1, 2)


def place(buf, s0_buf, audio, at, off, dur, gain, fi, fo):
    """положить кусок audio[off : off+dur] (сек) с момента at, линейные фейды fi/fo, в буфер от сэмпла s0_buf"""
    if audio is None or dur <= 0.01:
        return
    a0 = int(round(off * SR))
    n = min(int(round(dur * SR)), len(audio) - a0)
    if n <= 0:
        return
    p0 = int(round(at * SR)) - s0_buf                 # позиция в буфере
    lo, hi = max(0, p0), min(len(buf), p0 + n)
    if hi <= lo:
        return
    seg = audio[a0 + (lo - p0): a0 + (hi - p0)]
    env = np.full(hi - lo, gain, np.float32)
    idx = np.arange(lo - p0, hi - p0, dtype=np.float32) / SR     # время от начала куска
    d = n / SR
    if fi > 0:
        env *= np.clip(idx / fi, 0, 1)
    if fo > 0:
        env *= np.clip((d - idx) / fo, 0, 1)
    buf[lo:hi] += seg * env[:, None]


def mix_audio(proj, fa, fb, warn):
    s0 = fa * SPF
    buf = np.zeros(((fb - fa) * SPF, 2), np.float32)
    t_lo, t_hi = fa / FPS, fb / FPS
    cues = [c for c in build_cues(proj) if c["at"] < t_hi and c["at"] + c["dur"] > t_lo]
    cache = {}
    for c in sorted(cues, key=lambda c: (c["src"], c["at"])):
        if not file_sig(c["src"]):
            warn.append(f"звук {c['id']}: нет файла {c['src']}")
            continue
        if c["element"]:                              # звук ролика: <video>.volume = min(1, 10^(dB/20)·уровень)
            gdb = min(0.0, float(c["gain_db"] if c["gain_db"] is not None else -22) + level_db(proj, "video"))
            if not probe(absp(c["src"]))["a"]:
                continue
            sp = c["speed"] or 1.0
            aud = decode_audio(c["src"], ss=c["offset"], t=c["dur"] * sp + 0.1, speed=sp)
            place(buf, s0, aud, c["at"], 0.0, c["dur"], 10 ** (gdb / 20), 0, 0)
            continue
        gdb = float(c["gain_db"] if c["gain_db"] is not None else 0) + level_db(proj, c["bus"])
        g = 10 ** (gdb / 20)
        if c["src"] not in cache:
            cache.clear()                             # по одному исходнику в памяти (сортировка по src)
            cache[c["src"]] = decode_audio(c["src"])
        aud = cache[c["src"]]
        if aud is None or not len(aud):
            warn.append(f"звук {c['id']}: не читается {c['src']}")
            continue
        L = len(aud) / SR
        if c["loop"]:
            step = max(1.0, L - XF)
            k = 0
            while c["at"] + k * step < c["at"] + c["dur"] - 1e-9:
                seg_at = c["at"] + k * step
                seg_dur = min(L, c["at"] + c["dur"] - seg_at)
                last = seg_at + seg_dur >= c["at"] + c["dur"] - 1e-3
                if seg_at < t_hi and seg_at + seg_dur > t_lo:
                    place(buf, s0, aud, seg_at, 0.0, seg_dur, g, c["fi"] if k == 0 else XF, c["fo"] if last else XF)
                k += 1
        else:
            place(buf, s0, aud, c["at"], c["offset"], min(c["dur"], L - c["offset"]), g, c["fi"], c["fo"])
    return buf, len(cues)


def write_wav_f32(path, x):
    """float32 WAV (стерео, 48 кГц) через ffmpeg"""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                          "-c:a", "pcm_f32le", str(path)], stdin=subprocess.PIPE)
    p.stdin.write(np.ascontiguousarray(x, np.float32).tobytes()); p.stdin.close(); p.wait()


def loudness(path, stream_args=()):
    """(I LUFS, true peak dBTP, LRA) по EBU R128 (ffmpeg ebur128)"""
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path), *stream_args, "-vn",
                        "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary:"):]
    def num(pat):
        m = re.search(pat, s, re.S)
        return float(m.group(1)) if m else float("nan")
    return num(r"I:\s+(-?[\d.]+|-inf) LUFS"), num(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf)"), num(r"LRA:\s+(-?[\d.]+) LU")


def limit_pass(src_wav, out_wav, gain_db, lim_db):
    """усиление + лимитер по «почти истинному» пику (×4 передискретизация) с компенсацией задержки"""
    lim = 10 ** (lim_db / 20)
    af = (f"volume={gain_db:.3f}dB,aresample={SR * 4},alimiter=limit={lim:.5f}:attack=1:release=80:level=0:latency=1,"
          f"aresample={SR}")
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src_wav), "-af", af, "-c:a", "pcm_f32le",
                        str(out_wav)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("лимитер: " + r.stderr[-300:])


def master_audio(raw_wav, work, log):
    """→ путь к wav с громкостью ≈ −14 LUFS и пиком ≤ −1,5 dBTP"""
    I0, TP0, _ = loudness(raw_wav)
    log(f"звук до мастеринга: {I0:.1f} LUFS, пик {TP0:.1f} dBTP")
    if not math.isfinite(I0):
        return raw_wav, I0, TP0
    gain, lim = TARGET_LUFS - I0, TARGET_TP
    out = work / "audio_master.wav"
    I1 = TP1 = float("nan")
    for _ in range(4):
        limit_pass(raw_wav, out, gain, lim)
        I1, TP1, _ = loudness(out)
        if not math.isfinite(I1):
            break
        ok_i = abs(I1 - TARGET_LUFS) <= 0.3
        ok_tp = TP1 <= TARGET_TP + 0.2
        if ok_i and ok_tp:
            break
        if not ok_tp:
            lim -= (TP1 - TARGET_TP) + 0.1
        gain += TARGET_LUFS - I1
    log(f"после мастеринга: {I1:.1f} LUFS, пик {TP1:.1f} dBTP (усиление {gain:+.1f} дБ)")
    return out, I1, TP1


# ------------------------------------------------------------------ журнал прогресса
class Progress:
    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        self.last = 0.0

    def set(self, lines, force=False):
        self.lines = lines
        if not force and time.time() - self.last < 5:
            return
        self.last = time.time()
        block = "<!-- live -->\n" + "\n".join(lines) + "\n<!-- /live -->"
        try:
            txt = self.path.read_text(encoding="utf-8") if self.path.exists() else "# Рендер Cutlab → MP4\n\n"
        except OSError:
            return
        if "<!-- live -->" in txt and "<!-- /live -->" in txt:
            txt = re.sub(r"<!-- live -->.*?<!-- /live -->", lambda _: block, txt, flags=re.S)
        else:
            txt = txt.rstrip() + "\n\n" + block + "\n"
        tmp = self.path.with_suffix(".md.tmp")
        tmp.write_text(txt, encoding="utf-8")
        os.replace(tmp, self.path)


def hms(t):
    t = max(0.0, t)
    return f"{int(t // 60)}:{t % 60:04.1f}"


def aac_codec():
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    return "aac_at" if re.search(r"\baac_at\b", r.stdout) else "aac"


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Рендер проекта Cutlab в MP4")
    ap.add_argument("--project", required=True)
    ap.add_argument("--from", dest="t_from", type=float, default=0.0, help="с какой секунды (по умолчанию 0)")
    ap.add_argument("--to", dest="t_to", type=float, default=None, help="до какой секунды (по умолчанию до конца)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default=None, help="по умолчанию export/<pid>/<pid>_cut.mp4 (отрезок — …_cut_<от>-<до>.mp4)")
    ap.add_argument("--force", action="store_true", help="перерисовать сегменты, не глядя в кэш")
    ap.add_argument("--gc", action="store_true", help="после рендера удалить из кэша сегменты, которых нет в этом проекте")
    ap.add_argument("--progress", default=None, help="файл журнала (по умолчанию export/<pid>/RENDER_PROGRESS.md)")
    ap.add_argument("--vt", action="store_true", help="кодировать аппаратно (VideoToolbox): в разы быстрее, качество чуть ниже")
    ap.add_argument("--preset", default="fast", help="preset x264 (по умолчанию fast)")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--abr", default="192k", help="битрейт AAC (по умолчанию 192k; мастер для YouTube — 320k)")
    a = ap.parse_args()

    t_start = time.time()
    pid = a.project
    pfile = M.pdir(pid) / "project.json"
    proj = json.loads(pfile.read_text(encoding="utf-8"))       # снимок: проект может меняться во время рендера
    errs = M.validate(proj)
    exp = Path(os.environ.get("NICK_EXPORT") or (ROOT / "export")) / pid
    cache = exp / "render_cache"
    cache.mkdir(parents=True, exist_ok=True)
    prog = Progress(a.progress or (exp / "RENDER_PROGRESS.md"))
    ends = [c["start"] + c["dur"] for c in proj.get("clips", []) if c.get("track") in ("v1", "voice")]
    total = fr(max(ends)) if ends else 0
    fa = max(0, min(total, fr(a.t_from)))
    fb = total if a.t_to is None else max(fa, min(total, fr(a.t_to)))
    if fb <= fa:
        sys.exit("пустой отрезок")
    if a.out:
        out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    elif fa == 0 and fb == total:
        out = exp / f"{pid}_cut.mp4"
    else:
        out = exp / f"{pid}_cut_{fa / FPS:g}-{fb / FPS:g}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    warns = [f"проект: {e}" for e in errs[:10]]

    def log(s):
        print(s, flush=True)

    log(f"{pid}: {proj.get('title', '')} · длина проекта {hms(total / FPS)} ({total} кадров) · рендер {hms(fa / FPS)}–{hms(fb / FPS)}")
    enc = enc_args("vt" if a.vt else "x264", a.preset, a.crf)
    segs = build_segments(proj, fa, fb, total, cache, enc)
    todo = [s for s in segs if a.force or not Path(s["out"]).exists()]
    uniq = {}
    for s in todo:
        uniq.setdefault(s["key"], s)
    todo = sorted(uniq.values(), key=lambda s: -(s["j1"] - s["j0"]) * (3 if seg_needs_pil(s) else 1))
    log(f"сегментов {len(segs)}, из кэша {len(segs) - len(todo)}, рисовать {len(todo)} · потоков {a.jobs}")
    started = time.strftime("%d.%m %H:%M")
    head = [f"**Рендер {pid}** ({started}) → `{rel(out)}` · отрезок {hms(fa / FPS)}–{hms(fb / FPS)}"]
    prog.set(head + [f"- сегменты: 0/{len(todo)} (из кэша {len(segs) - len(todo)})"], force=True)

    frames_todo = sum(s["j1"] - s["j0"] for s in todo)
    done_frames, done_n, failed, outs = 0, 0, [], {}
    t_v = time.time()
    if todo:
        with ProcessPoolExecutor(max_workers=max(1, a.jobs)) as ex:
            futs = {ex.submit(render_segment, s): s for s in todo}
            for f in as_completed(futs):
                s = futs[f]
                try:
                    key, w, dt, path = f.result()
                    warns.extend(w)
                    outs[key] = path
                except Exception as e:
                    failed.append(s)
                    warns.append(f"{s['clip']}: сегмент не отрисован: {str(e)[:200]}")
                done_n += 1
                done_frames += s["j1"] - s["j0"]
                el = time.time() - t_v
                eta = el / max(1, done_frames) * (frames_todo - done_frames)
                if done_n % 10 == 0 or done_n == len(todo):
                    log(f"  {done_n}/{len(todo)} сегментов · {done_frames}/{frames_todo} кадров · {el:.0f} с, осталось ~{eta:.0f} с")
                prog.set(head + [f"- сегменты: {done_n}/{len(todo)} · кадров {done_frames}/{frames_todo} · "
                                 f"прошло {el:.0f} с, осталось ~{eta:.0f} с"] + [f"- ⚠ {x}" for x in warns[-8:]])
    # не отрисованные сегменты — чёрная карточка, чтобы длина совпала
    for s in failed:
        s2 = dict(s, kind="card", text=f"{s['clip']} · ошибка рендера", motion="static", transition="cut", nick=[], texts=[],
                  missing=False, reverse=False)
        s2["key"] = s["key"] + "e"; s2["out"] = str(cache / f"{s2['key']}.err.mp4")
        outs[s["key"]] = render_segment(s2)[3]
    for s in segs:
        s["out"] = outs.get(s["key"], s["out"])
    t_video = time.time() - t_v
    log(f"картинка готова за {t_video:.0f} с")

    # звук
    work = Path(tempfile.mkdtemp(prefix="render_", dir=str(cache)))
    try:
        t_a = time.time()
        buf, ncues = mix_audio(proj, fa, fb, warns)
        raw = work / "audio_raw.wav"
        write_wav_f32(raw, buf)
        del buf
        log(f"сведение: {ncues} звуков, {time.time() - t_a:.0f} с")
        mastered, I1, TP1 = master_audio(raw, work, log)

        # склейка без перекодирования + звук
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{s['out']}'\n" for s in segs), encoding="utf-8")
        T = (fb - fa) / FPS
        acodec = aac_codec()
        tmp_out = out.with_name(out.stem + ".part.mp4")
        for attempt in range(3):
            r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                                "-i", str(mastered), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                                "-af", "apad", "-c:a", acodec, "-b:a", a.abr, "-ar", str(SR), "-ac", "2",
                                "-t", f"{T:.6f}", "-movflags", "+faststart", str(tmp_out)], capture_output=True, text=True)
            if r.returncode:
                sys.exit("склейка: " + r.stderr[-800:])
            I2, TP2, LRA2 = loudness(tmp_out)
            if not math.isfinite(TP2) or TP2 <= -1.0 or attempt == 2:
                break
            log(f"после AAC пик {TP2:.2f} dBTP > −1 — лимитер ниже")
            m2 = work / f"audio_master{attempt}.wav"
            limit_pass(mastered, m2, 0.0, TARGET_TP - (TP2 + 1.0) - 0.3)
            mastered = m2
        os.replace(tmp_out, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    nfr = count_frames(out)
    dur_s = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                                 capture_output=True, text=True).stdout.strip() or 0)
    el = time.time() - t_start
    info = {"project": pid, "out": rel(out), "from": fa / FPS, "to": fb / FPS, "frames": nfr, "frames_expected": fb - fa,
            "duration": dur_s, "lufs": I2, "true_peak": TP2, "lra": LRA2, "render_seconds": round(el, 1),
            "video_seconds": round(t_video, 1), "segments": len(segs), "rendered": len(todo), "warnings": warns,
            "revision": proj.get("revision")}
    out.with_suffix(".render.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = "✓" if nfr == fb - fa else "✗"
    log(f"готово: {rel(out)} · {hms(dur_s)} · кадров {nfr}/{fb - fa} {ok} · {I2:.1f} LUFS, пик {TP2:.1f} dBTP · {el:.0f} с")
    for w in warns:
        log("  ⚠ " + w)
    prog.set(head + [f"- готово за {el:.0f} с (картинка {t_video:.0f} с, нарисовано {len(todo)} из {len(segs)} сегментов)",
                     f"- длина {hms(dur_s)}, кадров {nfr}/{fb - fa} {ok}; звук {I2:.1f} LUFS, пик {TP2:.1f} dBTP, LRA {LRA2:.1f}",
                     f"- ревизия проекта: {proj.get('revision')}"] + [f"- ⚠ {x}" for x in warns[:30]], force=True)
    if a.gc:
        keep = {Path(s["out"]).name for s in build_segments(proj, 0, total, total, cache, enc)} | {Path(s["out"]).name for s in segs}
        gone = 0
        for p in cache.glob("*.mp4"):
            if p.name not in keep:
                p.unlink(); gone += 1
        log(f"кэш: удалено {gone} старых сегментов")


if __name__ == "__main__":
    main()
