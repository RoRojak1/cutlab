"""Заставка D «Пролёт сквозь коллаж» — план: тайминг по сетке музыки, путь камеры, раскладка и движение всех плоскостей.
Чистый Python + numpy: импортируют и Blender (intro_D_scene.py), и сборщик (intro_D.py) — одна правда на двоих.

Мир: камера смотрит вдоль +Y, вверх — +Z. Плоскости-вырезки стоят в плоскости XZ лицом к камере (нормаль −Y),
единица ≈ метр (диорама: тема ≈ 0,5 высотой, пролёт в 0,1 от камеры). Сетка — восьмые доли: t(k) = PH + k·E8.
"""
import math
import random

import numpy as np

FPS = 30
LENS, SENSOR = 28.0, 36.0
TANH = SENSOR / 2 / LENS                  # tg половины угла по горизонтали
TANV = TANH * 9 / 16

# пролёты тем: восьмая доля сетки, тема, направление на экране (°, 0 — вправо, 90 — вверх), зазор до пути камеры,
# дистанция на долю, высота на экране на долю (доля кадра), наклон «к центру», поворот в плоскости
PASSES = [
    (2, "moon", 172, .10, 1.00, .70, 10, -6),
    (4, "runner", 8, .10, 1.00, .86, -12, 4),
    (7, "earth", 160, .05, .82, .98, 14, -8),        # после брейка — самый близкий
    (9, "atom", 35, .10, 1.00, .74, -10, 8),
    (10, "finger", 215, .10, 1.00, .74, 12, -10),
    (12, "chimp", -12, .10, 1.00, .82, -12, 3),
    (14, "rosette", 165, .09, .95, .84, 12, 0),
    (16, "brain", 30, .10, 1.00, .70, -10, -6),
    (17, "bulb", 205, .10, 1.00, .80, 10, 8),
    (18, "qmark", -25, .10, 1.00, .70, -12, -10),
]
RING = ["earth", "moon", "runner", "finger", "chimp", "rosette", "atom", "brain", "bulb"]


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ss(a, b, x):
    if b == a:
        return float(x >= a)
    t = clamp((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def ease_in(t, p=2.0):
    return clamp(t) ** p


def ease_out(t, p=3.0):
    return 1 - (1 - clamp(t)) ** p


def bump(a, b, x):
    """0→1→0 на [a, b] (синус)"""
    if x <= a or x >= b:
        return 0.0
    return math.sin(math.pi * (x - a) / (b - a))


class Plan:
    def __init__(self, grid, meta, seed=7):
        self.grid = grid
        self.meta = meta
        E8, PH = grid["E8"], grid["PH"]
        self.tk = lambda k: PH + k * E8
        tk = self.tk
        self.T = T = dict(
            STAB=0.0, PICK=tk(0), DROP=tk(1),
            BOOM=tk(20), COL0=tk(18.6), QMOVE=tk(21),
            STAMP1=tk(22), STAMP2=tk(22.5), STAMP3=tk(23),
            STRIP=tk(24), ASTRO=tk(25), HOP=tk(26),
            BLACK=grid["t_last"], END=grid["dur"])
        T["STOP"] = T["BOOM"] - .05                       # камера встала
        self.passes = [dict(k=p[0], t=tk(p[0]), name=p[1], dir=p[2], clear=p[3], d=p[4], f=p[5], tilt=p[6], roll=p[7])
                       for p in PASSES]
        self.nf_render = int(math.ceil(T["BLACK"] * FPS)) + 1     # Blender рисует до щелчка в чёрное
        self.rng = random.Random(seed)
        self._camera()
        self._objects()

    # ───────── камера ─────────
    def _speed(self, t):
        T = self.T
        if t < T["DROP"]:
            return .05
        V0 = 4.6
        v = V0 * ease_out((t - T["DROP"]) / .16, 2)
        for p in self.passes:
            a = .55 if p["name"] == "earth" else .32
            v += V0 * a * math.exp(-((t - (p["t"] - .09)) / .10) ** 2)
        v *= 1 - .45 * bump(T["DROP"] + .95, self.tk(6.6), t)      # брейк: притормозить перед большим ударом
        v *= 1 - ss(T["BOOM"] - .62, T["STOP"], t)               # выход к центру, остановка
        return max(v, 0.0)

    def _lat(self, t):
        T = self.T
        u = t - T["DROP"]
        env = ss(T["DROP"], T["DROP"] + .5, t) * (1 - ss(T["BOOM"] - .95, T["STOP"], t))
        x = (.30 * math.sin(2 * math.pi * u / 2.9) + .09 * math.sin(2 * math.pi * u / 1.45 + 1.1)) * env
        z = (.11 * math.sin(2 * math.pi * u / 2.2 + .4)) * env
        return x, z

    def _camera(self):
        dt = 1 / 1200
        n = int((self.T["END"] + .5) / dt) + 2
        ts = np.arange(n) * dt
        v = np.array([self._speed(t) for t in ts])
        y = np.concatenate([[0], np.cumsum((v[1:] + v[:-1]) / 2 * dt)])
        xz = np.array([self._lat(t) for t in ts])
        self._ts, self._y, self._v = ts, y, v
        self._x, self._z = xz[:, 0], xz[:, 1]
        dx = np.gradient(self._x, dt)
        dz = np.gradient(self._z, dt)
        ddx = np.gradient(dx, dt)
        from_k = np.convolve(ddx, np.ones(120) / 120, "same")     # сгладить (0,1 с)
        self._roll = np.clip(-.020 * from_k, -.12, .12)
        self._yaw = -.55 * np.arctan2(dx, v + .6)
        self._pitch = .55 * np.arctan2(dz, v + .6)
        self.y_end = float(y[int(self.T["STOP"] / dt)])
        self.x_end, self.z_end = 0.0, 0.0
        self.ring_c = (0.0, self.y_end + 2.3, 0.0)

    def _ci(self, t):
        return int(clamp(t / (self._ts[1] - self._ts[0]), 0, len(self._ts) - 1))

    def cam_pos(self, t):
        i = self._ci(t)
        return float(self._x[i]), float(self._y[i]), float(self._z[i])

    def cam(self, t):
        """→ dict(loc, rot (эйлер XYZ Blender), focus, fstop)"""
        i = self._ci(t)
        x, y, z = float(self._x[i]), float(self._y[i]), float(self._z[i])
        T = self.T
        roll = float(self._roll[i]) + .10 * bump(T["DROP"] + .9, self.tk(7), t) * math.sin(2 * math.pi * (t - T["DROP"] - .9) / 1.4)
        # щелчки камеры на событиях разрыва
        sh = 0.0
        for te, a in ((T["STAB"], .006), (T["PICK"], .004), (T["DROP"], .010)):
            u = t - te
            if 0 <= u < .3:
                sh += a * math.exp(-u * 14) * math.sin(u * 90)
        rot = (math.pi / 2 + float(self._pitch[i]) + sh, roll, float(self._yaw[i]))
        return dict(loc=(x, y, z), rot=rot, focus=self.focus(t), fstop=4.0)

    def focus(self, t):
        T = self.T
        if t < T["DROP"] + .02:
            return .30                                           # тёмная бумага у камеры
        y = self.cam_pos(t)[1]
        tgt = None
        for th in self.themes:
            dd = th["loc"][1] - y
            if dd > .55:
                tgt = dd
                break
        ring_d = self.ring_c[1] - y
        if tgt is None or t > T["BOOM"] - .5:
            tgt = ring_d
        if t > T["BOOM"]:
            tgt = lerp(ring_d, 30.0, ss(T["BOOM"], T["BOOM"] + .3, t))
        rack = ss(T["DROP"] + .02, T["DROP"] + .22, t)
        return lerp(.30, tgt, rack)

    # ───────── объекты ─────────
    def _size(self, name, h):
        m = self.meta["themes"][name]
        return h * m["w"] / m["h"], h

    def _objects(self):
        R = self.rng
        T = self.T
        self.objs = []
        self.themes = []
        tones = [(124, 222, 193), (108, 208, 178), (130, 227, 199), (114, 213, 183), (102, 202, 172), (126, 224, 195)]
        wing_i = hill_i = 0
        for i, p in enumerate(self.passes):
            d, th = p["d"], math.radians(p["dir"])
            h = p["f"] * 2 * d * TANV
            w, h = self._size(p["name"], h)
            cx0, cy0, cz0 = self.cam_pos(p["t"])
            y = cy0 + d
            # время, когда камера проходит плоскость темы
            j = int(np.searchsorted(self._y, y))
            tc = float(self._ts[min(j, len(self._ts) - 1)])
            px, _, pz = self.cam_pos(tc)
            ext = abs(math.cos(th)) * w / 2 + abs(math.sin(th)) * h / 2
            r = p["clear"] + ext
            x, z = px + r * math.cos(th), pz + r * math.sin(th)
            o = dict(name=f"T{i}_{p['name']}", tex=p["name"], w=w, h=h, loc=(x, y, z),
                     rot=(math.radians(p["tilt"] * .3 * math.sin(th)), math.radians(p["roll"]), math.radians(p["tilt"] * math.cos(th))),
                     mat="paper", shadow=True, anim=p["name"], t_pass=p["t"], tc=tc)
            self.objs.append(o)
            self.themes.append(o)
            self._theme_children(o)
            # подложка: крыло/холм/облако позади темы — на него падает тень
            yb = y + .22
            if abs(math.cos(th)) >= .62:
                side = 1 if math.cos(th) > 0 else -1
                self.objs.append(dict(name=f"W{i}", tex=f"wing_{(1, 3, 4)[wing_i % 3]}", w=3.2, h=3.2, kind="wing", side=side,
                                      edge=x - side * w * .05, loc=None, y=yb, zc=pz, mat="paper", shadow=True,
                                      tone=tones[wing_i % 6]))
                wing_i += 1
            elif math.sin(th) < 0:
                self.objs.append(dict(name=f"H{i}", tex=f"hill_{hill_i % 6}", w=4.6, h=1.8, kind="hill", edge=z + h * .05,
                                      loc=None, y=yb, xc=px, mat="paper", shadow=True, tone=tones[(hill_i + 2) % 6]))
                hill_i += 1
            else:
                self.objs.append(dict(name=f"C{i}", tex=f"cloud_{i % 3}", w=4.6, h=1.8, kind="cloud", edge=z - h * .05,
                                      loc=None, y=yb, xc=px, mat="paper", shadow=True, tone=tones[(i + 4) % 6]))
            # крыло на противоположной стороне, глубже (параллакс)
            if i % 2 == 0:
                side = -1 if math.cos(th) > 0 else 1
                self.objs.append(dict(name=f"WO{i}", tex=f"wing_{(0, 2, 5)[wing_i % 3]}", w=3.2, h=3.2, kind="wing", side=side,
                                      edge=px + side * R.uniform(.62, .85), loc=None, y=y + R.uniform(.7, 1.1), zc=pz,
                                      mat="paper", shadow=True, tone=tones[(wing_i + 3) % 6]))
                wing_i += 1
        # пол из холмов вдоль пути
        yy = 1.6
        k = 0
        while yy < self.y_end - .9:
            j = int(np.searchsorted(self._y, yy))
            px, _, pz = self.cam_pos(float(self._ts[min(j, len(self._ts) - 1)]))
            self.objs.append(dict(name=f"F{k}", tex=f"hill_{(2, 0, 5, 3, 1, 4)[k % 6]}", w=5.0, h=1.8, kind="hill",
                                  edge=pz - .40 - .12 * R.random(), loc=None, y=yy, xc=px + R.uniform(-.6, .6),
                                  mat="paper", shadow=True, tone=tones[k % 6]))
            yy += R.uniform(1.1, 1.6)
            k += 1
        # полоса облаков сверху (как холмы снизу): туннель из рваной бумаги
        yy = 3.2
        k = 0
        while yy < self.y_end - 1.6:
            j = int(np.searchsorted(self._y, yy))
            px, _, pz = self.cam_pos(float(self._ts[min(j, len(self._ts) - 1)]))
            self.objs.append(dict(name=f"K{k}", tex=f"cloud_{k % 3}", w=4.6, h=1.8, kind="cloud",
                                  edge=pz + .50 + .14 * R.random(), loc=None, y=yy, xc=px + R.uniform(-1.4, 1.4),
                                  mat="paper", shadow=False))
            yy += R.uniform(2.6, 3.8)
            k += 1
        for o in self.objs:
            if o.get("kind") == "wing":
                o["loc"] = (o["edge"] + o["side"] * o["w"] / 2, o["y"], o["zc"])
                o["rot"] = (0.0, 0.0, 0.0)
                o["uvflip"] = o["side"] < 0
            elif o.get("kind") == "hill":
                o["loc"] = (o["xc"], o["y"], o["edge"] - o["h"] / 2)
                o["rot"] = (0.0, 0.0, 0.0)
                o["uvflip"] = bool(int(o["name"][1:] if o["name"][1:].isdigit() else 0) % 2)
            elif o.get("kind") == "cloud":
                o["loc"] = (o["xc"], o["y"], o["edge"] + o["h"] / 2)
                o["rot"] = (0.0, 0.0, 0.0)
                o["uvflip"] = False
        # кольцо тем в конце (схлопывается в «?»)
        n = len(RING)
        for i, nm in enumerate(RING):
            w, h = self._size(nm, .30 if nm not in ("runner", "chimp") else .32)
            self.objs.append(dict(name=f"R{i}_{nm}", tex=nm, w=w, h=h, loc=self.ring_c, rot=(0, 0, 0), mat="paper", shadow=True,
                                  anim="ring", ring_i=i, ring_a=2 * math.pi * i / n + .35))
        # обрывки и конфетти в объёме полёта
        scr = self.meta["scraps"]
        for i in range(260):
            y = R.uniform(.9, self.y_end - .6)
            j = int(np.searchsorted(self._y, y))
            px, _, pz = self.cam_pos(float(self._ts[min(j, len(self._ts) - 1)]))
            while True:
                dx, dz = R.uniform(-2.2, 2.2), R.uniform(-.9, 1.3)
                if math.hypot(dx, dz * 1.3) > .28:
                    break
            s = R.uniform(.028, .085)
            sc = scr[i % len(scr)]
            self.objs.append(dict(name=f"S{i}", tex=sc["name"][:-4], w=s, h=s, loc=(px + dx, y, pz + dz), mat="paper",
                                  shadow=True, anim="scrap", spin=(R.uniform(-4, 4), R.uniform(-6, 6), R.uniform(-4, 4)),
                                  ph=(R.uniform(0, 6.3), R.uniform(0, 6.3), R.uniform(0, 6.3)),
                                  drift=(R.uniform(-.05, .05), R.uniform(-.05, .05), R.uniform(-.06, .02))))
        for i in range(4):                                       # маленькие «?»
            y = R.uniform(2.0, self.y_end - 2.0)
            j = int(np.searchsorted(self._y, y))
            px, _, pz = self.cam_pos(float(self._ts[min(j, len(self._ts) - 1)]))
            side = 1 if i % 2 else -1
            s = R.uniform(.10, .15)
            w, h = self._size("qmark", s)
            self.objs.append(dict(name=f"Q{i}", tex="qmark", w=w, h=h, loc=(px + side * R.uniform(.6, 1.2), y, pz + R.uniform(-.2, .6)),
                                  mat="paper", shadow=True, anim="scrap", spin=(R.uniform(-1, 1), R.uniform(-2.5, 2.5), R.uniform(-1, 1)),
                                  ph=(0, R.uniform(0, 6.3), 0), drift=(0, 0, 0)))
        # взрыв конфетти на ударе (из центра кольца к камере)
        for i in range(80):
            a = R.uniform(0, 2 * math.pi)
            sp = R.uniform(.6, 1.0)
            vel = (math.cos(a) * sp * R.uniform(1.2, 3.2), -R.uniform(1.4, 4.2), math.sin(a) * sp * R.uniform(.9, 2.4))
            s = R.uniform(.035, .095)
            sc = scr[(i * 7) % len(scr)]
            self.objs.append(dict(name=f"B{i}", tex=sc["name"][:-4], w=s, h=s, loc=self.ring_c, mat="paper", shadow=False,
                                  anim="burst", vel=vel, spin=(R.uniform(-9, 9), R.uniform(-12, 12), R.uniform(-9, 9))))
        # тёмная бумага (половинки у камеры)
        for side in ("L", "R"):
            self.objs.append(dict(name=f"tear_{side}", tex=f"tear_{side}", w=.44, h=.44 * 1400 / 2400, loc=(0, .30, 0), rot=(0, 0, 0),
                                  mat="paper", shadow=False, parent="camera", anim="tear", side=-1 if side == "L" else 1))

    def _theme_children(self, o):
        m = self.meta
        nm = o["tex"]
        W_, H_ = o["w"], o["h"]
        if nm == "atom":
            o["tex"] = "atom_base"
            iw, ih = m["themes"]["atom"]["w"], m["themes"]["atom"]["h"]
            for k, e in enumerate(m["atom"]["electrons"]):
                s = 2 * (e["r"] + 4) / ih * H_
                self.objs.append(dict(name=f"{o['name']}_e{k}", tex=f"atom_e{k}", w=s, h=s, parent=o["name"], mat="paper",
                                      shadow=False, anim="electron", el=e, iw=iw, ih=ih, pw=W_, ph_=H_, loc=(0, 0, 0), rot=(0, 0, 0)))
        elif nm == "moon":
            o["tex"] = "moon_pillow"
            self.objs.append(dict(name=f"{o['name']}_m", tex="moon_moon", w=W_, h=H_, parent=o["name"], mat="paper", shadow=True,
                                  anim="moon", loc=(0, 0, 0), rot=(0, 0, 0)))
        elif nm == "bulb":
            self.objs.append(dict(name=f"{o['name']}_on", tex="bulb_on", w=W_, h=H_, parent=o["name"], mat="paper", shadow=False,
                                  anim="bulb_on", loc=(0, -.001, 0), rot=(0, 0, 0)))
            gx, gy = m["bulb"]["glass"]
            self.objs.append(dict(name=f"{o['name']}_halo", tex="bulb_halo", w=W_ * 1.9, h=W_ * 1.9, parent=o["name"], mat="glow",
                                  shadow=False, anim="bulb_on", loc=((gx - .5) * W_, .004, (.5 - gy) * H_), rot=(0, 0, 0)))

    # ───────── состояние на момент t ─────────
    def state(self, o, t):
        """→ (loc, rot, scale, видим ли)"""
        T = self.T
        a = o.get("anim")
        loc, rot, sc, vis = o["loc"], o.get("rot", (0, 0, 0)), (1, 1, 1), True
        if a in ("moon", "runner", "earth", "atom", "finger", "chimp", "rosette", "brain", "bulb", "qmark") and o.get("t_pass") is not None:
            x, y, z = loc
            rx, ry, rz = rot
            ph = o["t_pass"]
            # лёгкое «дыхание» бумаги
            ry += .03 * math.sin(2 * math.pi * .7 * t + ph)
            z += .008 * math.sin(2 * math.pi * .9 * t + ph * 2)
            if a == "earth":
                ry += .55 * (t - ph)                            # Земля поворачивается
            elif a == "rosette":
                ry += .9 * (t - ph)                             # витраж-калейдоскоп
            elif a == "runner":
                piv = self.meta["runner"]["pivot"]
                ang = .07 * math.sin(2 * math.pi * 2.2 * t)
                px_, pz_ = (piv[0] - .5) * o["w"], (.5 - piv[1]) * o["h"]
                ca, sa = math.cos(ang), math.sin(ang)
                x += px_ - (px_ * ca + pz_ * sa)                 # поворот вокруг бёдер
                z += pz_ - (-px_ * sa + pz_ * ca)
                ry += ang
                z += .012 * abs(math.sin(2 * math.pi * 2.2 * t))
            elif a == "brain":
                s_ = 1 + .05 * max(0.0, math.cos(2 * math.pi * (t - ph) / (2 * self.grid["E8"]))) ** 8
                sc = (s_, 1, s_)
            elif a == "qmark":
                ry += .25 * math.sin(2 * math.pi * 1.1 * t)
            loc, rot = (x, y, z), (rx, ry, rz)
        elif a == "moon":
            piv = self.meta["moon"]["pivot"]
            mw, mh = self.meta["moon"]["w"], self.meta["moon"]["h"]
            px_, pz_ = (piv[0] / mw - .5) * o["w"], (.5 - piv[1] / mh) * o["h"]
            ang = .065 * math.sin(2 * math.pi * 1.25 * t)
            ca, sa = math.cos(ang), math.sin(ang)
            # поворот вокруг оси Y на ang: (x, z) → (x cos + z sin, −x sin + z cos)
            loc = (px_ - (px_ * ca + pz_ * sa), -.002, pz_ - (-px_ * sa + pz_ * ca))
            rot = (0, ang, 0)
        elif a == "electron":
            e = o["el"]
            ob = self.meta["atom"]["orbits"][e["orbit"]]
            th = e["theta"] + 2 * math.pi * 1.1 * t * (1 if e["orbit"] != 1 else -1)
            u, v = ob["a"] * math.cos(th), ob["b"] * math.sin(th)
            X = ob["cx"] + u * math.cos(ob["phi"]) - v * math.sin(ob["phi"])
            Y = ob["cy"] + u * math.sin(ob["phi"]) + v * math.cos(ob["phi"])
            loc = ((X / o["iw"] - .5) * o["pw"], -.0025, (.5 - Y / o["ih"]) * o["ph_"])
        elif a == "bulb_on":
            parent = next(p for p in self.themes if p["name"] == o["parent"])
            tp = parent["t_pass"]
            E8 = self.grid["E8"]
            # мигает: выкл — вкл (на долю раньше) — выкл — ВКЛ на пролёте
            u = t - tp
            on = (-3.0 * E8 <= u < -2.4 * E8) or (-1.6 * E8 <= u < -1.25 * E8) or (u >= -.55 * E8)
            vis = on
        elif a == "ring":
            i = o["ring_i"]
            n = len(RING)
            ang = o["ring_a"] + .35 * t
            Rr = 1.0
            s_ = 1.0
            spin = .15 * math.sin(2 * math.pi * .8 * t + i)
            u0 = (t - T["COL0"])
            if u0 > 0:
                wind = bump(0, .12, u0)
                Rr *= 1 + .10 * wind
                s_ *= 1 + .08 * wind
                v = clamp((t - T["COL0"] - .08 - (n - 1 - i) * .010) / (T["BOOM"] - .02 - T["COL0"] - .08))
                e = ease_in(v, 2.4)
                Rr *= 1 - e
                s_ *= 1 - .9 * ease_in(v, 1.6)
                ang += 2.8 * ease_in(v, 2)
                spin += 5.0 * e * (1 if i % 2 else -1)
            cx, cy, cz = self.ring_c
            loc = (cx + .62 * Rr * math.cos(ang), cy, cz + .40 * Rr * math.sin(ang))
            rot = (0, spin, 0)
            sc = (max(s_, .001),) * 3
            vis = t < T["BOOM"] + .5 / FPS
        elif a == "scrap":
            x, y, z = loc
            sp, ph, dr = o["spin"], o["ph"], o["drift"]
            loc = (x + dr[0] * t + .03 * math.sin(1.3 * t + ph[0]), y + dr[1] * t, z + dr[2] * t + .03 * math.sin(1.1 * t + ph[1]))
            rot = (ph[0] + sp[0] * t, ph[1] + sp[1] * t, ph[2] + sp[2] * t)
        elif a == "burst":
            u = t - T["BOOM"]
            if u < 0:
                return loc, (0, 0, 0), (.001, .001, .001), False
            vx, vy, vz = o["vel"]
            k = (1 - math.exp(-u * 1.6)) / 1.6
            loc = (loc[0] + vx * k, loc[1] + vy * k, loc[2] + vz * k - .5 * u * u)
            rot = tuple(s * u for s in o["spin"])
            sc = (min(1.0, u * 12),) * 3
            vis = u < 1.2
        elif a == "tear":
            side = o["side"]
            # щель: на STAB — узкая, на PICK — шире, на DROP — половинки улетают (поворот на внешнем крае к камере)
            g = 0.0
            g += .0010 * ss(T["STAB"], T["STAB"] + .06, t) + .0006 * ss(T["STAB"], T["PICK"], t)
            g += .0030 * ss(T["PICK"], T["PICK"] + .07, t)
            u = clamp((t - T["DROP"]) / .30)
            e = ease_in(u, 1.7)
            hinge = side * o["w"] / 2                            # внешний край половинки
            ang = side * math.radians(78) * e
            x0 = side * g + side * .55 * e
            # поворот вокруг вертикали на внешнем крае: центр половинки уходит к камере
            ca, sa = math.cos(ang), math.sin(ang)
            cxl = hinge + (-hinge) * ca
            cyl = -hinge * sa
            wedge = side * .012 * ss(T["STAB"], T["PICK"] + .1, t) * (1 - e)    # клин: вверху щель шире
            loc = (x0 + cxl, .30 + .004 * (side > 0) + cyl - .05 * e, -.004 * side * e)
            rot = (0, wedge, ang)
            vis = t < T["DROP"] + .34
        return loc, rot, sc, vis


def lerp(a, b, t):
    return a + (b - a) * t


def grid_from_music(path, bpm_hint=None):
    """сетка восьмых по огибающей трека: период и фаза (макс. сумма атак на сетке) + последний сильный удар"""
    import subprocess
    from scipy import ndimage, signal
    sr = 48000
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    dur = len(x) / sr
    hop = 240
    n = len(x) // hop
    fr = x[:n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(1))
    b, a = signal.butter(4, 150 / (sr / 2), "low")
    lo = signal.filtfilt(b, a, x)
    lr = np.sqrt((lo[:n * hop].reshape(n, hop) ** 2).mean(1))

    def onset(e):
        lg = np.log(e + 1e-5)
        d = np.diff(lg, prepend=lg[0])
        d[d < 0] = 0
        return ndimage.gaussian_filter1d(d, 1.0)
    on = onset(rms) + onset(lr)
    hz = sr / hop
    loud = 20 * np.log10(rms + 1e-7)
    end_i = np.where(loud > loud.max() - 25)[0].max()
    t_end = end_i / hz
    if bpm_hint:
        lo_p, hi_p = 30 / bpm_hint * .97, 30 / bpm_hint * 1.03
    else:
        lo_p, hi_p = .25, .40
    best = None
    for p in np.arange(lo_p, hi_p, .0005):
        for ph in np.arange(0, 2 * p, .0025):
            g = np.arange(ph, t_end, p)
            sc = on[(g * hz).astype(int)].mean()
            if best is None or sc > best[0]:
                best = (sc, p, ph)
    _, E8, PH = best
    # якорь: k = 1 — первый громкий удар баса (дроп) после 0,3 с; k = 0 — затакт перед ним
    t_drop = float(np.where((lr > .5 * lr.max()) & (np.arange(n) > .3 * hz))[0][0] / hz)
    k = round((t_drop - PH) / E8)
    PH = PH + (k - 1) * E8
    # последний удар: самый громкий пик (огибающая по 1 мс) в последние 0,4 с звучания, момент атаки (−6 дБ от пика)
    a0, a1 = int((t_end - .4) * sr), int(t_end * sr)
    env = ndimage.maximum_filter1d(np.abs(x[a0:a1]), 48)
    im = int(env.argmax())
    ia = im
    while ia > 0 and env[ia] > env[im] * .5:
        ia -= 1
    t_last = (a0 + ia) / sr
    return dict(E8=float(E8), PH=float(PH), bpm=float(30 / E8), t_last=t_last, t_end=float(t_end), dur=float(dur), t_drop=t_drop)
