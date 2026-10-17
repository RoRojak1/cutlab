"""Заставка D «Пролёт сквозь коллаж» — текстуры: вырезки тем из чётких листов 2688×1520, «живые» части, слои-туннель,
тёмная бумага разрыва, обрывки. Альфа — по насыщенности (фон и тень эскиза бирюзовые, вырезка почти серая), как hero()
шапки v4. Всё → assets/shots/ep06/intro/tex_D/ + meta.json (размеры, точки опоры, эллипсы орбит атома).

  /usr/bin/python3 studio/editor/intro/intro_D_tex.py            # всё
  /usr/bin/python3 studio/editor/intro/intro_D_tex.py --check    # + контактный лист tex_D/_check.jpg
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
INTRO = os.path.join(ROOT, "assets/shots/ep06/intro")
SRC = os.path.join(INTRO, "src_hq")
OUT = os.path.join(INTRO, "tex_D")
PAPER = (238, 232, 218)
MINT = (120, 220, 190)

# предметы листов: имя → примерный центр в координатах листа (для опознания компонент)
SHEETS = {
    "sheet1_13d61e11.png": {"earth": (437, 415), "moon": (1333, 453), "runner": (2307, 548), "finger": (795, 1111), "qmark": (1776, 1104)},
    "sheet2_ed1da411.png": {"chimp": (464, 453), "rosette": (1345, 438), "atom": (2234, 450), "brain": (879, 1121), "bulb": (1829, 1081)},
}


def alpha_chroma(a):
    chroma = a.max(-1) - a.min(-1)
    return np.clip((95 - chroma) / 45, 0, 1)


def cut_sheets():
    """→ {имя: RGBA (обрезано по альфе, поля 6 px)}"""
    out = {}
    for fn, names in SHEETS.items():
        a = np.array(Image.open(os.path.join(SRC, fn)).convert("RGB"), np.float32)
        al = alpha_chroma(a)
        lab, n = ndi.label(al > .5)
        for name, (cx, cy) in names.items():
            k = lab[cy, cx]
            if k == 0:                                          # центр попал в дырку рисунка — ближайшая крупная компонента
                d, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
                k = lab[iy[cy, cx], ix[cy, cx]]
            m = lab == k
            holes = ndi.binary_fill_holes(m) & ~m                # мелкие дырки внутри (цветные крапинки) — заделать
            hl, hn = ndi.label(holes)
            if hn:
                sizes = ndi.sum(np.ones_like(al), hl, range(1, hn + 1))
                small = np.isin(hl, np.where(sizes < 400)[0] + 1)
                m |= small
            alpha = np.where(m, np.maximum(al, small.astype(np.float32) if hn else 0), 0) if hn else np.where(m, al, 0)
            # край как в hero(): альфа ужимается на 3 px, полупрозрачная кромка — цвет бумаги
            am = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(7))
            am = np.array(am.point(lambda v: 0 if v < 60 else min(255, int((v - 60) * 1.4))), np.float32) / 255
            rgb = a.copy()
            edge = (am > 0) & (am < .98)
            rgb[edge] = PAPER
            rgb[am <= 0] = PAPER                                 # под прозрачным — бумага (без бирюзы при фильтрации)
            ys, xs = np.where(am > .5)
            y0, y1, x0, x1 = max(0, ys.min() - 6), ys.max() + 7, max(0, xs.min() - 6), xs.max() + 7
            im = np.dstack([rgb, am * 255])[y0:y1, x0:x1]
            out[name] = Image.fromarray(im.clip(0, 255).astype(np.uint8))
            ORIGIN[name] = (x0, y0)
    return out


ORIGIN = {}


# ───────── атом: орбиты (эллипсы) и электроны отдельно ─────────
def fit_conic(P):
    """A x² + B xy + C y² = 1 по точкам P (n,2) — МНК (эллипс с центром в начале координат)"""
    M = np.c_[P[:, 0] ** 2, P[:, 0] * P[:, 1], P[:, 1] ** 2]
    sol, *_ = np.linalg.lstsq(M, np.ones(len(P)), rcond=None)
    return sol


def conic_f(c, P):
    return c[0] * P[:, 0] ** 2 + c[1] * P[:, 0] * P[:, 1] + c[2] * P[:, 1] ** 2


def is_ellipse(c):
    return c[0] > 0 and c[2] > 0 and c[1] ** 2 - 4 * c[0] * c[2] < 0


def conic_axes(c):
    M = np.array([[c[0], c[1] / 2], [c[1] / 2, c[2]]])
    w, v = np.linalg.eigh(M)
    return 1 / math.sqrt(w[0]), 1 / math.sqrt(w[1]), math.atan2(v[1, 0], v[0, 0])


def gconic_fit(P):
    """общая коника A x²+B xy+C y²+D x+E y+F=0 (наименьший сингулярный вектор)"""
    x, y = P[:, 0], P[:, 1]
    Z = np.c_[x * x, x * y, y * y, x, y, np.ones_like(x)]
    return np.linalg.svd(Z, full_matrices=False)[2][-1]


def sampson(w, x, y):
    A, B, C, D, E, F = w
    f = A * x * x + B * x * y + C * y * y + D * x + E * y + F
    gx, gy = 2 * A * x + B * y + D, B * x + 2 * C * y + E
    return f / np.maximum(np.hypot(gx, gy), 1e-9)


def gconic_params(w):
    A, B, C, D, E, F = w
    x0, y0 = np.linalg.solve([[2 * A, B], [B, 2 * C]], [-D, -E])
    Fc = F + (D * x0 + E * y0) / 2
    M = np.array([[A, B / 2], [B / 2, C]])
    lam, v = np.linalg.eigh(M)
    a, b = math.sqrt(-Fc / lam[0]), math.sqrt(-Fc / lam[1])
    return dict(cx=float(x0), cy=float(y0), a=float(a), b=float(b), phi=float(math.atan2(v[1, 0], v[0, 0])))


def ell_coords(e, x, y):
    """→ θ, ρ точки в «полярных» координатах эллипса e"""
    c, s_ = math.cos(e["phi"]), math.sin(e["phi"])
    u = (x - e["cx"]) * c + (y - e["cy"]) * s_
    v = -(x - e["cx"]) * s_ + (y - e["cy"]) * c
    return np.arctan2(v / e["b"], u / e["a"]), np.hypot(u / e["a"], v / e["b"])


def ell_point(e, th, rho=1.0):
    c, s_ = math.cos(e["phi"]), math.sin(e["phi"])
    u, v = rho * e["a"] * np.cos(th), rho * e["b"] * np.sin(th)
    return e["cx"] + u * c - v * s_, e["cy"] + u * s_ + v * c


def atom_parts(im):
    from scipy.ndimage import map_coordinates
    a = np.array(im, np.float32)
    rgb, al = a[..., :3], a[..., 3] / 255
    g = rgb.mean(-1)
    dark = (g < 110) & (al > .5)
    yy, xx = np.mgrid[:dark.shape[0], :dark.shape[1]]
    D = lambda r: np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r
    blobs = ndi.binary_opening(ndi.binary_closing(dark, structure=D(3)), structure=D(14))   # шары: ядро и электроны
    lab, n = ndi.label(blobs)
    sizes = ndi.sum(np.ones_like(g), lab, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    cy, cx = ndi.center_of_mass(lab == order[0] + 1)
    E = []
    for k in order[1:7]:
        ey, ex = ndi.center_of_mass(lab == k + 1)
        E.append((ex, ey, math.sqrt(sizes[k] / math.pi) + 2.5))
    linepx = dark & ~ndi.binary_dilation(blobs, iterations=4)
    ll, ln = ndi.label(linepx)
    ls = ndi.sum(np.ones_like(g), ll, range(1, ln + 1))
    linepx &= np.isin(ll, np.where(ls > 150)[0] + 1)
    P = np.c_[xx[linepx] - cx, yy[linepx] - cy].astype(np.float64)
    # 1) грубо: эллипсы с центром в ядре (RANSAC по 3 точкам), 2) уточнение — общая коника по Сэмпсону
    rng = np.random.default_rng(4)
    rough, rest = [], P.copy()
    for _ in range(3):
        best = (0, None)
        for _ in range(3000):
            s3 = rest[rng.choice(len(rest), 3, replace=False)]
            try:
                c = np.linalg.solve(np.c_[s3[:, 0] ** 2, s3[:, 0] * s3[:, 1], s3[:, 1] ** 2], np.ones(3))
            except np.linalg.LinAlgError:
                continue
            if not is_ellipse(c):
                continue
            ax = conic_axes(c)
            if ax[0] > 400 or ax[1] < 40:
                continue
            inl = (np.abs(conic_f(c, rest) - 1) < .07).sum()
            if inl > best[0]:
                best = (inl, c)
        c = best[1]
        for _ in range(3):
            c = fit_conic(rest[np.abs(conic_f(c, rest) - 1) < .07])
        rough.append(c)
        rest = rest[np.abs(conic_f(c, rest) - 1) > .10]
    X, Y = P[:, 0] + cx, P[:, 1] + cy
    ells = []
    for c in rough:
        A, B, C = c
        w = np.array([A, B, C, -2 * A * cx - B * cy, -B * cx - 2 * C * cy, A * cx * cx + B * cx * cy + C * cy * cy - 1])
        for tol in (9, 7, 6, 5, 5):
            inl = np.abs(sampson(w, X, Y)) < tol
            w = gconic_fit(np.c_[X[inl], Y[inl]])
        ells.append(gconic_params(w))
    # стереть электроны: содержимое под шаром «протягивается» вдоль своей орбиты с двух сторон
    base = rgb.copy()
    el = []
    for i, (ex, ey, r) in enumerate(E):
        j = int(np.argmin([abs(ell_coords(e, np.array([ex]), np.array([ey]))[1][0] - 1) for e in ells]))
        e = ells[j]
        th_e = float(ell_coords(e, np.array([ex]), np.array([ey]))[0][0])
        dist = np.hypot(xx - ex, yy - ey)
        onany = np.zeros_like(dark)
        for e2 in ells:
            th2, rho2 = ell_coords(e2, xx, yy)
            onany |= np.abs(rho2 - 1) * min(e2["a"], e2["b"]) < 9
        debris = dark & (dist > r) & (dist < r + 18) & ~onany
        M = (dist <= r + 3) | ndi.binary_dilation(debris, iterations=3)
        # для пикселей зоны: ближайшая точка орбиты (Ньютон), знаковое расстояние по нормали; источник —
        # та же нормаль в точке, сдвинутой по дуге на ±L (за пределы шара)
        Mz = ndi.binary_dilation(M, iterations=3)
        px_, py_ = xx[Mz].astype(np.float64), yy[Mz].astype(np.float64)
        cph, sph = math.cos(e["phi"]), math.sin(e["phi"])
        EA, EB = e["a"], e["b"]

        def Ept(t):
            u, v = EA * np.cos(t), EB * np.sin(t)
            return e["cx"] + u * cph - v * sph, e["cy"] + u * sph + v * cph

        def Ed(t):
            u, v = -EA * np.sin(t), EB * np.cos(t)
            return u * cph - v * sph, u * sph + v * cph

        def Edd(t):
            u, v = -EA * np.cos(t), -EB * np.sin(t)
            return u * cph - v * sph, u * sph + v * cph

        def project(px_, py_):
            t, _ = ell_coords(e, px_, py_)
            for _ in range(8):
                ex_, ey_ = Ept(t)
                dx_, dy_ = Ed(t)
                ddx, ddy = Edd(t)
                f = (ex_ - px_) * dx_ + (ey_ - py_) * dy_
                fp = dx_ * dx_ + dy_ * dy_ + (ex_ - px_) * ddx + (ey_ - py_) * ddy
                t = t - f / np.where(np.abs(fp) < 1e-6, 1e-6, fp)
            return t

        th_e = float(project(np.array([ex], np.float64), np.array([ey], np.float64))[0])
        t, _ = ell_coords(e, px_, py_)
        for _ in range(8):
            ex_, ey_ = Ept(t)
            dx_, dy_ = Ed(t)
            ddx, ddy = Edd(t)
            f = (ex_ - px_) * dx_ + (ey_ - py_) * dy_
            fp = dx_ * dx_ + dy_ * dy_ + (ex_ - px_) * ddx + (ey_ - py_) * ddy
            t = t - f / np.where(np.abs(fp) < 1e-6, 1e-6, fp)
        ex_, ey_ = Ept(t)
        dx_, dy_ = Ed(t)
        sp_ = np.hypot(dx_, dy_)
        nx_, ny_ = -dy_ / sp_, dx_ / sp_
        dn = (px_ - ex_) * nx_ + (py_ - ey_) * ny_
        sarc = np.angle(np.exp(1j * (t - th_e))) * sp_                # знаковая дуга от центра шара (приближённо)
        R0 = r + 6
        other = np.zeros_like(dark)                               # полосы других орбит (их не копировать)
        for jj, e2 in enumerate(ells):
            if jj != j:
                th2, rho2 = ell_coords(e2, xx, yy)
                other |= np.abs(rho2 - 1) * min(e2["a"], e2["b"]) < 12
        other_f = ndi.gaussian_filter(other.astype(np.float32), 2)
        acc = np.zeros((len(px_), 3))
        wsum = np.zeros(len(px_))
        for sgn in (-1, 1):
            shift = sgn * 2 * R0 - 2 * sarc                         # зеркально относительно края шара
            ts = t + shift / sp_
            for _ in range(2):
                dmx, dmy = Ed((t + ts) / 2)
                ts = t + shift / np.hypot(dmx, dmy)
            sx_, sy_ = Ept(ts)
            dx2, dy2 = Ed(ts)
            s2 = np.hypot(dx2, dy2)
            qx, qy = sx_ + dn * (-dy2 / s2), sy_ + dn * (dx2 / s2)
            src = np.stack([map_coordinates(rgb[..., c], [qy, qx], order=1, mode="nearest") for c in range(3)], -1)
            clean = 1 - np.clip(map_coordinates(other_f, [qy, qx], order=1, mode="nearest") * 1.5, 0, 1)
            wgt = np.clip(.5 + sgn * sarc / (2 * R0), 0, 1) * (clean + 1e-3)
            acc += src * wgt[:, None]
            wsum += wgt
        acc /= wsum[:, None]
        acc_full = base.copy()
        acc_full[Mz] = acc
        acc = acc_full
        m = np.clip(ndi.gaussian_filter(M.astype(np.float32), 1.6) * 1.4, 0, 1)
        base = base * (1 - m[..., None]) + acc * m[..., None]
        el.append(dict(orbit=j, theta=th_e, r=r, sprite=f"atom_e{i}.png"))
    base_im = Image.fromarray(np.dstack([base, al * 255]).clip(0, 255).astype(np.uint8))
    sprites = []
    for i, (ex, ey, r) in enumerate(E):
        R = int(r + 4)
        crop = rgb[int(ey) - R:int(ey) + R + 1, int(ex) - R:int(ex) + R + 1]
        hh, ww = crop.shape[:2]
        my, mx = np.mgrid[:hh, :ww]
        m = np.clip((r + 1.5 - np.hypot(mx - (ex - int(ex) + R), my - (ey - int(ey) + R))) / 1.5, 0, 1)
        sprites.append(Image.fromarray(np.dstack([crop, m * 255]).clip(0, 255).astype(np.uint8)))
    return base_im, sprites, dict(nucleus=[cx, cy], orbits=ells, electrons=el)


# ───────── луна на подушке: луна отдельно (качается), подушка с заделанной дыркой ─────────
MOON_POLY = [(0, 0), (900, 0), (900, 330), (720, 330), (695, 320), (675, 400), (650, 430), (600, 457), (550, 475), (500, 490),
             (450, 500), (400, 490), (350, 485), (300, 475), (250, 445), (200, 380), (150, 385), (0, 385)]
PILLOW_TOP = [(0, 392), (150, 388), (250, 428), (400, 452), (550, 447), (650, 418), (720, 425), (900, 425)]


def moon_parts(im, off):
    """off — сдвиг координат вырезки относительно кадрирования moon.png (x914, y72 листа)"""
    a = np.array(im, np.float32)
    h, w = a.shape[:2]
    sh = lambda pts: [(x - off[0], y - off[1]) for x, y in pts]
    mm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mm).polygon(sh(MOON_POLY), fill=255)
    moon_m = (np.array(mm) > 127) & (a[..., 3] > 0)
    pm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(pm).polygon(sh(PILLOW_TOP) + [(w + 50, h + 50), (-50, h + 50)], fill=255)
    below = np.array(pm) > 127
    moon = a.copy()
    moon[..., 3] *= moon_m
    pillow = a.copy()
    pil_m = (a[..., 3] > 127) & ~moon_m
    hole = moon_m & below                                       # спрятанная под луной часть подушки
    _, (iy, ix) = ndi.distance_transform_edt(~pil_m, return_indices=True)
    nn = a[iy, ix, :3]
    sm = np.dstack([ndi.gaussian_filter(nn[..., c], 7) for c in range(3)])
    pillow[hole, :3] = sm[hole] + np.random.default_rng(2).normal(0, 10, (int(hole.sum()), 1))
    pillow[hole, 3] = 255
    pillow[moon_m & ~below, 3] = 0
    pillow[..., :3] = np.where(pillow[..., 3:] < 8, PAPER, pillow[..., :3])
    moon[..., :3] = np.where(moon[..., 3:] < 8, PAPER, moon[..., :3])
    pivot = (430 - off[0], 492 - off[1])                        # точка касания луны и подушки
    return Image.fromarray(moon.clip(0, 255).astype(np.uint8)), Image.fromarray(pillow.clip(0, 255).astype(np.uint8)), pivot


# ───────── лампочка: «включённое» состояние ─────────
def bulb_on(im):
    a = np.array(im, np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    g = a[..., :3].mean(-1)
    # колба: эллипс над цоколем (по кадрированию вырезки)
    cx, cy, rx, ry = w * .50, h * .40, w * .30, h * .27
    glass = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1
    glass = ndi.gaussian_filter(glass.astype(np.float32), 6)
    light = np.clip((g - 90) / 120, 0, 1) * glass
    warm = np.array([255, 214, 92], np.float32)
    rgb = a[..., :3] * (1 - light[..., None] * .75) + warm * light[..., None] * .75
    # лучи вокруг колбы — тёплые
    rays = (g < 110) & (((xx - cx) / (rx * 1.25)) ** 2 + ((yy - cy) / (ry * 1.25)) ** 2 > 1) & (yy < h * .62)
    rays = ndi.gaussian_filter(rays.astype(np.float32), .8)
    rgb = rgb * (1 - rays[..., None] * .8) + np.array([235, 150, 30], np.float32) * rays[..., None] * .8
    on = Image.fromarray(np.dstack([rgb, a[..., 3]]).clip(0, 255).astype(np.uint8))
    # мягкий ореол (для аддитивного свечения позади)
    s = 512
    yy, xx = np.mgrid[:s, :s]
    r = np.hypot(xx - s / 2, yy - s / 2) / (s / 2)
    glow = np.clip(1 - r, 0, 1) ** 2.2
    halo = Image.fromarray(np.dstack([np.full((s, s, 3), (255, 226, 140), np.float32), glow * 255]).astype(np.uint8))
    return on, halo, (cx / w, cy / h)


# ───────── тёмная бумага: две половинки по рваной линии ─────────
def tear_halves(w=2400, h=1400, seed=11):
    rng = np.random.default_rng(seed)
    ys = np.arange(h)
    base = w / 2 + np.cumsum(rng.normal(0, 2.2, h))
    base -= np.linspace(base[0], base[-1], h) - w / 2
    big = ndi.gaussian_filter1d(rng.normal(0, 1, h), 40) * 900
    zig = ndi.gaussian_filter1d(rng.normal(0, 1, h), 6) * 60
    edge = base + big + zig                                   # x разрыва для каждой строки
    xx = np.arange(w)[None, :]
    fib = ndi.gaussian_filter(rng.normal(0, 1, (h, w)), 1.2)
    fib = fib / np.abs(fib).max()
    # бумага: графит с волокном и лёгкой неровностью
    tone = np.array([24, 26, 28], np.float32)
    grain = ndi.gaussian_filter(rng.normal(0, 1, (h // 2, w // 2)), 1.0)
    grain = np.array(Image.fromarray(((grain / np.abs(grain).max() + 1) * 127).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 127 - 1
    blot = np.array(Image.fromarray(((ndi.gaussian_filter(rng.normal(0, 1, (h // 20, w // 20)), 3) * 40 + 128).clip(0, 255)).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 128 - 1
    col = tone + grain[..., None] * 5 + blot[..., None] * 4
    d = xx - edge[:, None]                                     # <0 левая половинка, >0 правая
    out = []
    for side in (-1, 1):
        dist = d * side                                        # расстояние внутрь своей половинки от линии (L: слева)
        rim_w = 7 + 9 * (fib * .5 + .5) + 6 * ndi.gaussian_filter1d(rng.normal(0, 1, h), 3)[:, None]
        # белые волокна на кромке: у одной половинки кайма шире (верхний слой бумаги отслоился)
        rim_w *= 1.6 if side < 0 else .8
        alpha = np.clip(dist + 1.5 * fib + 1, 0, 1)
        rim = np.clip((rim_w - dist) / 3, 0, 1) * (dist > -1)
        rgb = col * (1 - rim[..., None]) + np.array([226, 222, 210], np.float32) * rim[..., None]
        # тонкие волоски за край
        hair = (np.abs(ndi.gaussian_filter(rng.normal(0, 1, (h, w)), (6, .6))) > .045) & (dist > -6) & (dist < 0)
        alpha = np.maximum(alpha, hair * .8)
        rgb[hair] = (232, 228, 218)
        out.append(Image.fromarray(np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8)))
    return out


# ───────── слой-туннель: мятный лист с рваной дырой и кремовой кромкой ─────────
def layer_tex(rx, rz, tone, seed, size=(3072, 2048), span=(6.0, 4.0), lobes=None):
    """лист span (ширина × высота, в единицах сцены) вокруг дыры; дыра — эллипс rx × rz с шумом.
    За пределами текстуры лист продолжается краевыми пикселями (EXTEND)."""
    rng = np.random.default_rng(seed)
    W, H = size
    xx, yy = np.meshgrid((np.arange(W) + .5) / W * span[0] - span[0] / 2, span[1] / 2 - (np.arange(H) + .5) / H * span[1])
    ang = np.arctan2(yy / rz, xx / rx)
    rr = np.hypot(xx / rx, yy / rz)
    # неровный край: гармоники + мелкий шум по углу
    k = np.arange(2, 9)
    amp = rng.normal(0, 1, len(k)) * .07 / np.sqrt(k)
    ph = rng.uniform(0, 2 * np.pi, len(k))
    wob = sum(a_ * np.cos(k_ * ang + p_) for a_, k_, p_ in zip(amp, k, ph))
    fine_n = 2048
    fine = ndi.gaussian_filter1d(rng.normal(0, 1, fine_n), 3, mode="wrap")
    fine = fine / np.abs(fine).max()
    fine_v = fine[((ang + np.pi) / (2 * np.pi) * fine_n).astype(int) % fine_n]
    micro = ndi.gaussian_filter(rng.normal(0, 1, (H, W)), 1.0)
    micro = micro / np.abs(micro).max()
    edge = 1 + wob + .018 * fine_v
    d = (rr - edge) * np.minimum(rx, rz)                       # >0 — бумага; единицы сцены
    px = span[0] / W                                           # размер пикселя в единицах
    alpha = np.clip(d / px + 1.2 * micro + .5, 0, 1)
    rim_w = (.010 + .008 * (fine_v * .5 + .5)) * (1 + .4 * micro)
    rim = np.clip((rim_w - d) / (px * 2), 0, 1)
    col = np.array(tone, np.float32)
    grain = ndi.gaussian_filter(rng.normal(0, 1, (H // 3, W // 3)), .8)
    grain = np.array(Image.fromarray(((grain / np.abs(grain).max() + 1) * 127).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 127 - 1
    rgb = col + grain[..., None] * 2.5 + rng.normal(0, 1.2, (H, W, 1))
    # волокна кромки чуть темнее у самого разрыва, кремовые внутри
    rgb = rgb * (1 - rim[..., None]) + (np.array(PAPER, np.float32) - 6 * np.clip(-d / rim_w, 0, 1)[..., None]) * rim[..., None]
    return Image.fromarray(np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8))


# ───────── плоскости-декорации: крыло (рваный внутренний край слева), холм (рваный верх), облако (волнистый низ) ─────────
TONES = [(124, 222, 193), (108, 208, 178), (130, 227, 199), (114, 213, 183), (102, 202, 172), (126, 224, 195)]


def flat_tex(kind, tone, seed, span, ppu):
    rng = np.random.default_rng(seed)
    W, H = int(span[0] * ppu), int(span[1] * ppu)
    px = 1 / ppu
    u = (np.arange(W) + .5) * px                                # 0 … ширина (единицы сцены), слева направо
    v = span[1] - (np.arange(H) + .5) * px                      # 0 … высота, снизу вверх
    if kind == "wing":                                          # бумага справа от рваной линии x = e(z)
        n = H
        prof = .07 + ndi.gaussian_filter1d(rng.normal(0, 1, n), 60) * 1.2 + ndi.gaussian_filter1d(rng.normal(0, 1, n), 9) * .10
        prof = .16 + (prof - prof.mean()) * .13 / (np.abs(prof - prof.mean()).max() + 1e-6)
        jag = ndi.gaussian_filter1d(rng.normal(0, 1, n), 1.5)
        prof = prof + .006 * jag / np.abs(jag).max()
        d = u[None, :] - prof[:, None]
    else:                                                       # холм: бумага ниже линии z = e(x); облако: выше
        n = W
        x = u
        if kind == "hill":
            k = rng.uniform(.9, 1.6)
            base = span[1] - .22 - .10 * np.sin(2 * np.pi * x / span[0] * k + rng.uniform(0, 6)) \
                - .05 * np.sin(2 * np.pi * x / span[0] * 3.1 + rng.uniform(0, 6))
            base -= .05 * (1 - np.sin(np.pi * x / span[0])) * 0
        else:
            lob = rng.uniform(.28, .42)
            ph = (x / lob) % 1
            base = .22 + .09 * np.sqrt(np.clip(1 - (2 * ph - 1) ** 2, 0, 1)) * -1 + .09
            base = base + .03 * np.sin(2 * np.pi * x / span[0] * 1.3 + rng.uniform(0, 6))
        jag = ndi.gaussian_filter1d(rng.normal(0, 1, n), 1.5)
        mid = ndi.gaussian_filter1d(rng.normal(0, 1, n), 10)
        base = base + .006 * jag / np.abs(jag).max() + .012 * mid / np.abs(mid).max()
        if kind == "hill":
            d = base[None, :] - v[:, None]
        else:
            d = v[:, None] - base[None, :]
    micro = ndi.gaussian_filter(rng.normal(0, 1, (H, W)), 1.0)
    micro /= np.abs(micro).max()
    alpha = np.clip(d / px + 1.2 * micro + .5, 0, 1)
    fine = ndi.gaussian_filter(rng.normal(0, 1, (H, W)), (6, 6))
    fine /= np.abs(fine).max()
    rim_w = .011 + .006 * fine
    rim = np.clip((rim_w - d) / (px * 2), 0, 1)
    grain = ndi.gaussian_filter(rng.normal(0, 1, (H // 3 + 1, W // 3 + 1)), .8)
    grain = np.array(Image.fromarray(((grain / np.abs(grain).max() + 1) * 127).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 127 - 1
    blot = ndi.gaussian_filter(rng.normal(0, 1, (H // 24 + 1, W // 24 + 1)), 2)
    blot = np.array(Image.fromarray(((blot / (np.abs(blot).max() + 1e-6) + 1) * 127).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 127 - 1
    rgb = np.array(tone, np.float32) + grain[..., None] * 2.2 + blot[..., None] * 2.5 + rng.normal(0, 1.0, (H, W, 1))
    rgb = rgb * (1 - rim[..., None]) + (np.array(PAPER, np.float32) - 8 * np.clip(-d / .012, 0, 1)[..., None]) * rim[..., None]
    rgb[alpha <= 0] = PAPER
    return Image.fromarray(np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8))


def sky_tex():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paperkit as pk
    return pk.make_bg(MINT, seed=21)


# ───────── обрывки бумаги ─────────
def scrap(seed, kind):
    r = np.random.default_rng(seed)
    S = 256
    n = r.integers(5, 9)
    R = r.uniform(70, 110)
    pts = [(S / 2 + math.cos(a) * R * r.uniform(.45, 1.15), S / 2 + math.sin(a) * R * r.uniform(.45, 1.15))
           for a in np.sort(r.uniform(0, 2 * math.pi, n))]
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    m = np.array(m.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    micro = ndi.gaussian_filter(r.normal(0, 1, (S, S)), 1.0)
    m = np.clip((m - .5) * 6 + micro * 1.5 + .5, 0, 1)
    if kind == "cream":
        col = np.array(PAPER, np.float32)
    elif kind == "mint":
        col = np.array((70, 165, 138), np.float32)
    else:                                                     # растр: кремовый клочок с чёрными точками
        col = np.array(PAPER, np.float32)
    rgb = np.zeros((S, S, 3), np.float32) + col + r.normal(0, 3, (S, S, 1))
    if kind == "dots":
        yy, xx = np.mgrid[:S, :S]
        p = 9
        u, v = (xx + yy) / math.sqrt(2), (xx - yy) / math.sqrt(2)
        cell = np.hypot((u % p) - p / 2, (v % p) - p / 2)
        dens = .25 + .55 * (xx / S)
        dot = cell < p / 2 * np.sqrt(dens)
        rgb[dot] = (24, 24, 24)
    return Image.fromarray(np.dstack([rgb, m * 255]).clip(0, 255).astype(np.uint8))


def save(im, name):
    im.save(os.path.join(OUT, name))


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = {"themes": {}}
    cuts = cut_sheets()
    for n, im in cuts.items():
        save(im, f"{n}.png")
        meta["themes"][n] = dict(w=im.width, h=im.height)
    # атом
    base, sprites, info = atom_parts(cuts["atom"])
    save(base, "atom_base.png")
    for i, s in enumerate(sprites):
        save(s, f"atom_e{i}.png")
    meta["atom"] = info
    # луна: координаты многоугольников — в кадрировании moon.png (лист 1, x914 y72)
    off = (914 - ORIGIN["moon"][0], 72 - ORIGIN["moon"][1])
    moon, pillow, pivot = moon_parts(cuts["moon"], (-off[0], -off[1]))
    save(moon, "moon_moon.png")
    save(pillow, "moon_pillow.png")
    meta["moon"] = dict(pivot=pivot, w=moon.width, h=moon.height)
    # лампочка
    on, halo, gc = bulb_on(cuts["bulb"])
    save(on, "bulb_on.png")
    save(halo, "bulb_halo.png")
    meta["bulb"] = dict(glass=gc)
    # бегун: опора — бёдра (качание вокруг)
    meta["runner"] = dict(pivot=(.45, .42))
    # тёмная бумага
    L, R = tear_halves()
    save(L, "tear_L.png")
    save(R, "tear_R.png")
    # декорации
    for i in range(6):
        save(flat_tex("wing", TONES[i], 300 + i, (3.2, 3.2), 480), f"wing_{i}.png")
        save(flat_tex("hill", TONES[(i + 2) % 6], 400 + i, (5.0, 1.8), 400), f"hill_{i}.png")
    for i in range(3):
        save(flat_tex("cloud", TONES[(i + 4) % 6], 500 + i, (4.6, 1.8), 400), f"cloud_{i}.png")
    sky_tex().save(os.path.join(OUT, "sky.png"))
    # обрывки
    kinds = ["cream"] * 9 + ["mint"] * 6 + ["dots"] * 5
    for i, k in enumerate(kinds):
        save(scrap(100 + i, k), f"scrap_{i:02d}.png")
    meta["scraps"] = [dict(name=f"scrap_{i:02d}.png", kind=k) for i, k in enumerate(kinds)]
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=float)
    print("tex ok", OUT, "атом: орбит", len(info["orbits"]), "электронов", len(info["electrons"]))
    if "--check" in sys.argv:
        check()


def check():
    names = ["earth", "moon_moon", "moon_pillow", "runner", "finger", "qmark", "chimp", "rosette", "atom", "atom_base", "brain",
             "bulb", "bulb_on", "tear_L", "tear_R", "scrap_00", "scrap_10", "scrap_16", "wing_0", "wing_3", "hill_0", "hill_3",
             "cloud_0", "cloud_1"]
    th = []
    for n in names:
        im = Image.open(os.path.join(OUT, n + ".png"))
        bg = Image.new("RGB", im.size, (60, 160, 140))
        bg.paste(im, (0, 0), im)
        bg.thumbnail((360, 360))
        th.append(bg)
    cols = 6
    sh = Image.new("RGB", (cols * 370, ((len(th) + cols - 1) // cols) * 370), (30, 30, 30))
    for i, im in enumerate(th):
        sh.paste(im, ((i % cols) * 370 + 5, (i // cols) * 370 + 5))
    sh.save(os.path.join(OUT, "_check.jpg"), quality=88)


if __name__ == "__main__":
    main()
