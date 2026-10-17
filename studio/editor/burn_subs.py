"""Вшить русские субтитры для просмотра в копию ролика (ffmpeg здесь без libass и drawtext → плашки рисует PIL).
Субтитры — assets/subs/<pid>_ru.json (studio/editor/subs_ru.py). В итоговый ролик не идут: только копия для просмотра.

  python3 studio/editor/burn_subs.py --project ep04 --in export/ep04/ep04_pilot_v2_720p.mp4 --out export/ep04/ep04_pilot_v2_720p_ru.mp4
"""
import argparse, json, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]


def font(size):
    for f in FONTS:
        if os.path.exists(f): return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def wrap(d, text, fnt, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    if len(lines) == 2 and d.textlength(lines[0], font=fnt) > 1.6 * d.textlength(lines[1], font=fnt):   # ровнее по строкам
        ws = text.split(); best = None
        for k in range(1, len(ws)):
            a, b = " ".join(ws[:k]), " ".join(ws[k:])
            la, lb = d.textlength(a, font=fnt), d.textlength(b, font=fnt)
            if la <= maxw and lb <= maxw and (best is None or abs(la - lb) < best[0]): best = (abs(la - lb), [a, b])
        if best: lines = best[1]
    return lines


def plate(text, W, SH, fs):
    im = Image.new("RGBA", (W, SH), (0, 0, 0, 0)); d = ImageDraw.Draw(im); fnt = font(fs)
    lines = wrap(d, text, fnt, W * 0.84); lh = int(fs * 1.28)
    tw = max(d.textlength(l, font=fnt) for l in lines); th = lh * len(lines)
    px, py = int(fs * 0.55), int(fs * 0.25)
    x0, y1 = (W - tw) / 2 - px, SH - int(SH * 0.10); y0 = y1 - th - 2 * py
    d.rounded_rectangle((x0, y0, x0 + tw + 2 * px, y1), radius=int(fs * 0.3), fill=(12, 12, 14, 192))
    for i, l in enumerate(lines):
        lw = d.textlength(l, font=fnt); x, y = (W - lw) / 2, y0 + py + i * lh
        d.text((x + 1, y + 2), l, font=fnt, fill=(0, 0, 0, 160)); d.text((x, y), l, font=fnt, fill=(255, 255, 255, 255))
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True); ap.add_argument("--in", dest="src", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cues = [c for c in json.load(open(f"{ROOT}/assets/subs/{a.project}_ru.json")) if c.get("ru")]
    W, H = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                    "-of", "csv=p=0", a.src], capture_output=True, text=True).stdout.strip().split(","))
    SH = int(H * 0.30); fs = max(16, int(H * 0.040))
    tmp = tempfile.mkdtemp(prefix="subs_")
    Image.new("RGBA", (W, SH), (0, 0, 0, 0)).save(f"{tmp}/blank.png")
    lst, t = [], 0.0
    for i, c in enumerate(cues):
        if c["t0"] > t + 1e-3: lst += [f"file '{tmp}/blank.png'", f"duration {c['t0'] - t:.3f}"]
        plate(c["ru"], W, SH, fs).save(f"{tmp}/s{i:03d}.png")
        lst += [f"file '{tmp}/s{i:03d}.png'", f"duration {c['t1'] - c['t0']:.3f}"]; t = c["t1"]
    lst += [f"file '{tmp}/blank.png'", "duration 1.0", f"file '{tmp}/blank.png'"]
    open(f"{tmp}/list.txt", "w").write("\n".join(lst) + "\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-f", "concat", "-safe", "0", "-i", f"{tmp}/list.txt",
                    "-filter_complex", "[1:v]format=rgba[s];[0:v][s]overlay=0:H-h:eof_action=pass:format=auto[v]",
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "21", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", a.out], check=True)
    print(f"готово: {a.out} · фраз {len(cues)}")


if __name__ == "__main__":
    main()
