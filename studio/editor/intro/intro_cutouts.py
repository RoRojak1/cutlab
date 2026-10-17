"""Вырезки для заставок канала (ep06+): астронавт R1 и 8 тем из эскиза C0_lineup.
Астронавт — функция hero() из шапки v4 (альфа по насыщенности: фон бирюзовый, вырезка почти серая).
Темы слиплись в две группы — делим по «ядрам» (грубые многоугольники внутри каждого предмета): каждый пиксель
маски отходит ближайшему ядру; там, где разрез прошёл не по кайме, а по рисунку, рисуем рваный кремовый край.
Запуск: python3 studio/editor/intro/intro_cutouts.py → assets/shots/ep06/intro/cutouts/*.png + _check_*.png"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART = os.path.join(ROOT, "export/publish/channel_art")
OUT = os.path.join(ROOT, "assets/shots/ep06/intro/cutouts")
sys.path.insert(0, os.path.join(ART, "v4_concepts"))
sys.path.insert(0, os.path.join(ART, "v3_hands"))
import make_banner_v4 as b  # noqa: E402

PAPER = (238, 232, 218)

# ядра предметов в координатах эскиза 1344×576 (z — порядок наложения: больше = выше)
CORES = {
    "earth":   (0, [(20, 230), (60, 185), (125, 180), (170, 215), (172, 270), (150, 300), (125, 330), (75, 350), (30, 320), (15, 275)]),
    "moon":    (1, [(235, 205), (250, 200), (225, 245), (235, 285), (280, 300), (295, 320), (295, 345), (225, 370), (185, 375), (150, 320), (190, 295), (195, 240)]),
    "runner":  (2, [(380, 170), (410, 195), (415, 235), (390, 250), (360, 285), (340, 340), (320, 390), (310, 375), (320, 305), (305, 265), (295, 240), (320, 225), (350, 195)]),
    "finger":  (3, ("ellipse", 467, 285, 62, 88)),
    "rosette": (0, ("ellipse", 992, 262, 52, 82)),
    "chimp":   (1, [(775, 215), (825, 195), (865, 210), (885, 250), (910, 300), (940, 355), (935, 380), (850, 385), (750, 375), (745, 305), (760, 255)]),
    "atom":    (2, [(1056, 238), (1080, 232), (1115, 200), (1150, 220), (1175, 240), (1165, 290), (1175, 330), (1135, 365), (1110, 350), (1082, 340), (1064, 322), (1070, 290), (1062, 258)]),
    "brain":   (3, [(1190, 240), (1250, 220), (1315, 230), (1330, 280), (1315, 320), (1285, 360), (1250, 340), (1200, 315), (1180, 275)]),
}


def alpha_from_chroma(a):
    chroma = a.max(-1) - a.min(-1)
    return np.clip((95 - chroma) / 45, 0, 1)


def clean_edge(rgb, alpha, shrink=5):
    """как в hero(): альфа ужимается, полупрозрачная кромка — цвет бумаги (без бирюзовой каймы)"""
    al = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(shrink))
    al = np.array(al.point(lambda v: 0 if v < 60 else min(255, int((v - 60) * 1.4))), np.float32) / 255
    rgb = rgb.copy()
    edge = (al > 0) & (al < .98)
    rgb[edge] = PAPER
    return rgb, al


def rim_clean(rgb, al, width):
    """тёмные пиксели в наружной полосе (там должна быть кремовая кайма) → бумага"""
    m = al > .5
    band = m & ~ndi.binary_erosion(m, iterations=width)
    rgb = rgb.copy()
    rgb[band & (rgb.mean(-1) < 170)] = PAPER
    return rgb


def lineup():
    src = Image.open(os.path.join(ART, "v4_concepts/src/C0_lineup_ccf5c1b4.png")).convert("RGB")
    S = 2                                                       # работаем в 2× — края мягче, чем у ресайза готовой вырезки
    src = src.resize((src.width * S, src.height * S), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 60, 2))
    a = np.array(src, np.float32)
    alpha = alpha_from_chroma(a)
    fg = alpha > .5
    h, w = fg.shape
    markers = np.zeros((h, w), np.int32)
    names = list(CORES)
    for i, n in enumerate(names):
        z, shp = CORES[n]
        m = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(m)
        if isinstance(shp, tuple):
            _, cx, cy, rx, ry = shp
            d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
        else:
            d.polygon([(x * S, y * S) for x, y in shp], fill=255)
        markers[(np.array(m) > 0) & fg] = i + 1
    # каждый пиксель переднего плана — ближайшему ядру
    _, (iy, ix) = ndi.distance_transform_edt(markers == 0, return_indices=True)
    lab = markers[iy, ix]
    lab[~(alpha > .02)] = 0
    ink = a.mean(-1) < 150                                      # рисунок (тёмное), кайма — светлая
    check = np.zeros((h, w, 3), np.uint8)
    rng = np.random.default_rng(11)
    pal = rng.integers(60, 255, (len(names) + 1, 3)); pal[0] = 0
    check[:] = pal[lab]
    Image.fromarray((check * .55 + a * .45).astype(np.uint8)).save(os.path.join(OUT, "_check_lineup.png"))
    info = {}
    bgm = alpha < .3

    def poly(pts):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).polygon([(x * S, y * S) for x, y in pts], fill=255)
        return np.array(m) > 0

    def circle_fit(m):
        """окружность по краю предмета, граничащему с фоном (МНК)"""
        edge = m & ndi.binary_dilation(bgm, iterations=2)
        ys, xs = np.where(edge)
        A = np.c_[2 * xs, 2 * ys, np.ones(len(xs))]
        cx, cy, c = np.linalg.lstsq(A, xs ** 2 + ys ** 2, rcond=None)[0]
        return cx, cy, np.sqrt(c + cx ** 2 + cy ** 2)

    def disk(cx, cy, r):
        yy, xx = np.mgrid[:h, :w]
        return (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r

    def sym_fill(vis, full, cx, cy, angles):
        """недостающее (под соседом) — из повёрнутой копии видимой части (предмет симметричен)"""
        rgba = Image.fromarray(np.dstack([a, vis * alpha * 255]).clip(0, 255).astype(np.uint8))
        out = np.dstack([a, vis * alpha * 255]).astype(np.float32)
        for ang in angles:
            r = np.array(rgba.rotate(ang, Image.BICUBIC, center=(cx, cy)), np.float32)
            need = full & (out[..., 3] < 128) & (r[..., 3] > 128)
            out[need] = r[need]
        return out[..., :3], out[..., 3] / 255 * full

    chimp_m = fg & poly([(700, 150), (780, 165), (850, 172), (866, 196), (880, 220), (890, 240), (902, 256), (912, 270),
                         (926, 292), (936, 310), (944, 326), (948, 340), (954, 360), (959, 380), (957, 394), (940, 410), (700, 410)])
    brain_m = fg & poly([(1240, 204), (1250, 195), (1310, 200), (1344, 235), (1344, 330), (1300, 395), (1250, 390), (1217, 340),
                         (1199, 324), (1183, 306), (1174, 280), (1172, 262), (1178, 245), (1195, 232), (1215, 218)])
    atom_poly = poly([(1047, 228), (1056, 216), (1075, 214), (1100, 196), (1111, 176), (1135, 172), (1153, 188), (1161, 208),
                      (1182, 208), (1206, 212), (1224, 228), (1224, 332), (1192, 346), (1170, 350), (1170, 366), (1148, 387),
                      (1119, 390), (1103, 364), (1096, 350), (1070, 354), (1060, 347), (1055, 330), (1054, 310), (1057, 280), (1051, 255)])
    atom_vis = fg & atom_poly & ~brain_m
    shapes = {}
    for i, n in enumerate(names):
        m = lab == i + 1
        m = ndi.binary_opening(m, iterations=2)
        lbl, k = ndi.label(m)
        if k > 1:                                               # только самый большой кусок
            sizes = ndi.sum(m, lbl, range(1, k + 1)); m = lbl == (np.argmax(sizes) + 1)
        shapes[n] = m
    for i, n in enumerate(names):
        m = shapes[n]
        rgb, al = a.copy(), None
        if n == "chimp":
            al = alpha * chimp_m
        elif n == "brain":
            al = alpha * brain_m
        elif n == "atom":
            cx, cy = 1133.75 * S, 281 * S                       # ядро атома — центр симметрии орбит
            full = atom_vis | np.array(Image.fromarray((atom_vis * 255).astype(np.uint8)).rotate(180, center=(cx, cy))) > 0
            rgb, al = sym_fill(atom_vis, full, cx, cy, [180])
            rgb = rim_clean(rgb, al, 18)
        elif n == "finger":                                     # овал: слева его кайму закрыл бегун → кайма заново
            ys, xs = np.where(m & ndi.binary_dilation(bgm, iterations=2) & (np.mgrid[:h, :w][1] > 430 * S))
            A = np.c_[xs ** 2, ys ** 2, xs, ys].astype(np.float64)
            k1, k2, k3, k4 = np.linalg.lstsq(A, np.ones(len(xs)), rcond=None)[0]
            cx, cy = -k3 / (2 * k1), -k4 / (2 * k2)
            g = 1 + k3 ** 2 / (4 * k1) + k4 ** 2 / (4 * k2)
            rx, ry = np.sqrt(g / k1), np.sqrt(g / k2)
            yy, xx = np.mgrid[:h, :w]
            ang = np.arctan2(yy - cy, xx - cx)
            jag = np.interp(ang, np.linspace(-np.pi, np.pi, 181), rng.normal(0, 1, 181)) * .006
            el = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1 + jag
            rgb[el & (alpha < .5)] = PAPER
            al = el.astype(np.float32)
            rgb = rim_clean(rgb, al, 10)
            print(n, "овал", round(cx / S), round(cy / S), round(rx / S), round(ry / S))
        elif n in ("rosette", "earth"):
            cx, cy, r = circle_fit(m)
            full = disk(cx, cy, r + 2 * S)
            vis = m & disk(cx, cy, r + 2 * S)
            if n == "rosette":
                vis &= ~chimp_m & ~atom_poly
            vis = ndi.binary_erosion(vis, iterations=3) & ~ndi.binary_dilation(fg & ~vis & ~bgm, iterations=4)
            rgb, al = sym_fill(vis, full, cx, cy, [180, 90, 270, 45, 135, 225, 315])
            print(n, "круг", round(cx / S), round(cy / S), round(r / S))
        else:
            other = (lab > 0) & (lab != i + 1)
            cut = m & ndi.binary_dilation(other, iterations=3)          # разрез по рисунку → рваный кремовый край
            band = ndi.binary_dilation(cut, iterations=4) & m
            noise = ndi.gaussian_filter(rng.normal(0, 1, (h, w)), 2) > -.25
            rgb[band & noise & ndi.binary_dilation(ink, iterations=2)] = PAPER
            al = alpha * m
        rgb, al = clean_edge(rgb, al, 3)
        ys, xs = np.where(al > .5)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        im = Image.fromarray(np.dstack([rgb, al * 255]).clip(0, 255).astype(np.uint8)).crop((x0, y0, x1, y1))
        im.save(os.path.join(OUT, f"theme_{n}.png"))
        info[n] = (int(x0), int(y0), CORES[n][0])               # место в эскизе (2×) — для сборки «как в шапке»
        print(n, im.size, (x0, y0))
    # группы целиком (как на шапке C0) — для финального кадра C
    for gname, (gx0, gx1) in {"left": (0, 600 * S), "right": (700 * S, w)}.items():
        al = alpha.copy(); al[:, :gx0] = 0; al[:, gx1:] = 0
        rgb, al = clean_edge(a, al, 3)
        ys, xs = np.where(al > .5)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        Image.fromarray(np.dstack([rgb, al * 255]).clip(0, 255).astype(np.uint8)).crop((x0, y0, x1, y1)).save(
            os.path.join(OUT, f"group_{gname}.png"))
        info["group_" + gname] = (int(x0), int(y0), 0)
    with open(os.path.join(OUT, "layout.txt"), "w") as f:
        for k, v in info.items():
            f.write(f"{k} {v[0]} {v[1]} {v[2]}\n")


def astronaut():
    im = b.hero(Image.open(os.path.join(ART, "v5_astronaut/src/R1_rock_one_68509028.png")))
    a = np.array(im, np.float32)
    solid = a[..., 3] > 127
    holes = ndi.binary_fill_holes(ndi.binary_closing(solid, iterations=2)) & ~solid    # мятные «дырки» в кайме
    holes = ndi.binary_dilation(holes, iterations=1) & (ndi.binary_fill_holes(solid) | holes)
    a[holes, :3] = PAPER
    a[holes, 3] = 255
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    im.save(os.path.join(OUT, "astronaut.png"))
    print("astronaut", im.size)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    astronaut()
    lineup()
