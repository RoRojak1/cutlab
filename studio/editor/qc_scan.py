#!/usr/bin/env python3
"""Автопроверка монтажа Cutlab перед показом (механические пункты quality-gate).

    python3 studio/editor/qc_scan.py --project ep03 [--max-run 2] [--max-still 8]

Ищет:
  1. серии AI-картинок подряд (> --max-run штук или > --max-still секунд) — главная претензия к ep03;
  2. один и тот же исходник в двух местах (картинка дважды или пересекающиеся отрезки видео);
  3. картинки без наезда/панорамы (motion = static);
  4. плотность надписей (дорожка text): больше ~1 в минуту — пользователь удаляет;
  5. «поп» надписи (sfx-tx-*) без самой надписи рядом;
  6. сцены Ника с губами — список с in/speed: каждую мерить studio/lipsync (сдвиг И растяжение);
  7. галочки в выделениях стопок фото (export/<проект>/build/highlights/*.json, items с kind "check"; ep05+):
     пользователь запретил галочки в ролике (09.10) — заменить на пометку по смыслу (removed/audit_removed — история, не считаем).
Только читает project.json и разметку выделений, ничего не меняет.
"""
import argparse, json, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMG = re.compile(r"\.(png|jpe?g|webp)$", re.I)
NICK = re.compile(r"/scenes/video/|/nick/video/|/H\d+[a-z]?/h\d", re.I)
# с ep05 сборщик пишет в клип поле mat (что за материал): рамки 4A — это видео, но внутри фото/архив/AI
MAT = {"nick": "Ник", "ai": "AI-картинки", "real": "реальное видео", "archive": "реальное видео", "photo": "архивные фото",
       "3d": "3D и карточки", "step": "3D и карточки", "gfx": "свои GFX", "intro": "прочее"}


def tc(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--max-run", type=int, default=2, help="допустимо AI-картинок подряд")
    ap.add_argument("--max-still", type=float, default=8.0, help="допустимо секунд картинок подряд")
    a = ap.parse_args()
    p = json.load(open(ROOT / "projects" / a.project / "project.json"))
    clips = p["clips"]
    v1 = sorted([c for c in clips if c["track"] == "v1"], key=lambda c: c["start"])
    is_img = lambda c: (c["mat"] == "ai") if c.get("mat") else (c.get("kind") == "image" or bool(IMG.search(c.get("src") or "")))
    problems = 0

    # 0. доли по типам (экранное время)
    def kind_of(c):
        if c.get("kind") == "card": return "заглушки"
        if c.get("mat"): return MAT.get(c["mat"], "прочее")
        src = c.get("src") or ""
        if NICK.search(src): return "Ник"
        if "/memes/" in src: return "мемы"
        if is_img(c): return "AI-картинки"
        if "/stock/" in src or "nasa" in src.lower(): return "реальное видео"
        if "/3d/" in src or "/cards/" in src or "3d_tower" in src: return "3D и карточки"
        if "/gfx/" in src or "/H3a/" in src: return "свои GFX"
        return "прочее"
    tot = sum(c["dur"] for c in v1) or 1
    # куски одной сцены с разной скоростью (поле piece, ep05: 3D по меткам синхрона) — одна склейка
    cuts = sum(1 for i, c in enumerate(v1) if i == 0 or not (c.get("piece") and c.get("piece") == v1[i - 1].get("piece")))
    share = defaultdict(float)
    for c in v1:
        share[kind_of(c)] += c["dur"]
    print("0. Доли экранного времени: " + ", ".join(f"{k} {v / tot * 100:.0f} %" for k, v in sorted(share.items(), key=lambda kv: -kv[1]))
          + f"  (цель: реальное ≥ 30 %, AI ≤ 10–15 %, Ник 8–10 %); {cuts} кусков, {cuts / (tot / 60):.1f} склеек/мин")

    # 1. серии картинок
    runs, cur = [], []
    for c in v1:
        if is_img(c) and "/memes/" not in (c.get("src") or ""):
            cur.append(c)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    bad = [r for r in runs if len(r) > a.max_run or sum(c["dur"] for c in r) > a.max_still]
    print(f"1. Серии AI-картинок (> {a.max_run} подряд или > {a.max_still:g} с): {len(bad)}")
    for r in bad:
        print(f"   {tc(r[0]['start'])}–{tc(r[-1]['start'] + r[-1]['dur'])}  {len(r)} шт, {sum(c['dur'] for c in r):.1f} с: "
              + ", ".join(c["id"] for c in r))
    problems += len(bad)

    # 2. повторы исходников
    uses = defaultdict(list)
    for c in v1:
        if c.get("src"):
            uses[c["src"]].append(c)
    dups = []
    for src, cs in uses.items():
        if len(cs) < 2:
            continue
        if is_img(cs[0]):
            dups.append((src, cs))
            continue
        spans = [(c.get("in") or 0, (c.get("in") or 0) + c["dur"] * (c.get("speed") or 1), c) for c in cs]
        hit = [(x, y) for i, x in enumerate(spans) for y in spans[i + 1:] if min(x[1], y[1]) - max(x[0], y[0]) > 0.5]
        if hit:
            dups.append((src, sorted({id(z[2]): z[2] for pair in hit for z in pair}.values(), key=lambda c: c["start"])))
    # соседние куски одного клипа (разрез) — не повтор; тизер и финальная нарезка повторяют кадры выпуска намеренно
    adjacent = lambda x, y: abs(x["start"] + x["dur"] - y["start"]) < 0.05 or abs(y["start"] + y["dur"] - x["start"]) < 0.05
    recap = lambda c: bool(re.search(r"ТИЗЕР|ФИНАЛ|TEASER|FINAL", c.get("chapter") or "", re.I))
    real, planned = [], []
    for src, cs in dups:
        cs = [c for c in cs if not all(adjacent(c, o) for o in cs if o is not c)]
        if len(cs) < 2:
            continue
        (planned if any(recap(c) for c in cs) else real).append((src, cs))
    print(f"2. Один исходник в двух местах: {len(real)} (+ {len(planned)} намеренно в тизере/финале)")
    for src, cs in real:
        print(f"   {Path(src).name}: " + ", ".join(f"{c['id']} @ {tc(c['start'])}" for c in cs))
    for src, cs in planned:
        print(f"   [тизер/финал] {Path(src).name}: " + ", ".join(f"{c['id']} @ {tc(c['start'])}" for c in cs))
    problems += len(real)

    # 3. статичные картинки
    static = [c for c in v1 if is_img(c) and c.get("kind") != "video" and (c.get("motion") or "static") == "static"]
    print(f"3. Картинки без наезда/панорамы: {len(static)}"
          + ("" if not static else "  (" + ", ".join(f"{c['id']} @ {tc(c['start'])}" for c in static[:12]) + (" …" if len(static) > 12 else "") + ")"))

    # 4. плотность надписей
    texts = sorted([c for c in clips if c["track"] == "text"], key=lambda c: c["start"])
    total = (v1[-1]["start"] + v1[-1]["dur"]) / 60 if v1 else 1
    per_min = defaultdict(int)
    for c in texts:
        per_min[int(c["start"] // 60)] += 1
    busy = {m: n for m, n in per_min.items() if n > 2}
    print(f"4. Надписей: {len(texts)} ({len(texts) / total:.1f}/мин; цель ≤ ~1/мин)"
          + ("" if not busy else "; густо на минутах " + ", ".join(f"{m}:xx ({n})" for m, n in sorted(busy.items()))))

    # 5. «поп» без надписи
    orphans = []
    for c in clips:
        if c["track"].startswith("sfx") and c["id"].startswith("sfx-tx"):
            if not any(abs(t["start"] - c["start"]) < 0.6 for t in texts):
                orphans.append(c)
    print(f"5. «Поп» надписи без надписи: {len(orphans)}" + ("" if not orphans else "  (" + ", ".join(c["id"] for c in orphans[:10]) + ")"))
    problems += len(orphans)

    # 6. сцены Ника
    nick = [c for c in v1 if ((c.get("mat") == "nick") if c.get("mat") else NICK.search(c.get("src") or ""))]
    print(f"6. Сцены Ника с губами — мерить каждую (studio/lipsync: stretch.py → tstrip.py): {len(nick)}")
    for c in nick:
        print(f"   {c['id']:10} {tc(c['start'])}  in={c.get('in')}  speed={c.get('speed', 1)}  {Path(c['src']).name}")

    # 7. галочки в выделениях (разметка стопок фото frame_grid_stack: highlights/<кусок>.json, подпапки-копии не смотрим)
    hl_dir = ROOT / "export" / a.project / "build" / "highlights"
    at_piece = {}
    for c in v1:
        if c.get("piece"):
            at_piece.setdefault(c["piece"], c)
    checks, broken = [], []
    for f in (sorted(hl_dir.glob("*.json")) if hl_dir.is_dir() else []):
        try:
            d = json.load(open(f))
        except (OSError, ValueError) as e:
            broken.append((f, e))
            continue
        items = (d.get("items") if isinstance(d, dict) else d) or []
        piece = (d.get("piece") if isinstance(d, dict) else None) or f.stem
        for i, it in enumerate(items):
            if isinstance(it, dict) and it.get("kind") == "check":
                checks.append((f, piece, i, it))
    if hl_dir.is_dir():
        print(f"7. Галочки в выделениях (build/highlights/*.json, kind \"check\" в items): {len(checks)}"
              + (f"; не читается: {len(broken)}" if broken else ""))
        for f, piece, i, it in checks:
            c = at_piece.get(piece)
            where = f"{piece} @ {tc(c['start'])}" if c else f"{piece} (в монтаже нет)"
            print(f"   {where}  {f.name} items[{i}] «{it.get('word') or ''}»: галочка в выделении: пользователь запретил (09.10)"
                  " — заменить на пометку по смыслу")
        for f, e in broken:
            print(f"   {f.name}: не читается ({e})")
        problems += len(checks) + len(broken)
    print(f"\nИтого замечаний (1, 2, 5, 7): {problems}")


if __name__ == "__main__":
    main()
