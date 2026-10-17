#!/usr/bin/env python3
"""Пилот ep03 в Cutlab: 0:00 → конец заставки (холодный старт H1–H5, тизер T1–T11, заставка).

Холодный старт — по мастер-голосу assets/voice/ep03/coldopen_take1_master.wav (начала фраз сверены по паузам
в самом файле, привязка клипов Ника — корреляцией их звука с мастером). Губы клипов ep03 совпадают со звуком с первого
кадра (проверено покадрово по рту: H2, S09, S99, SF3 — сдвиг 0; в ep02 было 13 кадров, у ep03 промпт «from the very
first frame»). Поэтому склейки стоят на границах звука самих клипов: H2 до 7.27, H3 с 7.27 и с 17.58, H4 с 22.24.
H1 кончается кадром, совпадающим с первым кадром H2 (кадр 98 из h1_v4_endframe.mp4) — склейка невидима.
Тизер — из assets/shots/ep03/T/teaser_edl.json: каждый кусок берётся готовым сегментом studio/gfx/ep03_teaser_cut.py
(уже с ×speed, наездом и кропом), поэтому в Cutlab он стоит без сдвигов: in 0, static.

  python3 studio/editor/build_ep03_pilot.py           # план
  python3 studio/editor/build_ep03_pilot.py --apply   # создать (или перезаписать) проект ep03 через сервер Cutlab
"""
import json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "gfx"))
URL = "http://127.0.0.1:8777/api"
TITLE = "How Superhuman Can a Human Get?"
FPS = 30
LAG = 0.0                            # отставание губ: у клипов ep03 нет (замер 01.10)
SH = "assets/shots/ep03"
VO = "assets/voice/ep03"
SFX = "assets/sfx/epidemic/ep03"
MUS = "assets/music/epidemic/ep03"

H1_END = 122 / FPS                   # 4.067 с: кадр 98 исходника (24 fps) = первый кадр H2
V0 = H1_END + LAG                    # где на таймлайне 0.0 мастер-голоса холодного старта
# начала фраз в мастере (паузы файла): «Warm-up» 7.11, «A man» 9.33, «One of them» 17.42, «So how» 22.11, «…and find» 29.60
# клипы Ника озвучены кусками мастера: H2 0–7.27, H3 7.27–9.29 + 17.58–22.24, H4 22.24–29.70 → режем на этих границах
# удар по кнопке в H4 — 7.25–7.5 с клипа (мастер 29.49–29.74): наезд в циферблат с 29.62, башня с 30.12 (in 0.42)
CUT_H3A, CARDS_AT, CUT_H3B, CUT_H4, ZOOM_AT, TOWER_AT = 7.27, 9.29, 17.58, 22.24, 29.62, 30.12
TOWER_REF = 29.70                    # мастер, которому соответствует 0.0 ролика башни (метки уровней)
CO_VOICE_DUR = 53.13
TOWER_DUR = 23.8
TEASER_MUSIC_SRC = "assets/music/epidemic/ep03/N3_dancing_darklight_teaser.wav"   # выбор пользователя 01.10: N3 Daniel Fridell — Dancing in the Darklight
TEASER_MUSIC_DB = -13              # музыка тизера; на словах приглушается: под голосом ~19 дБ тише голоса, в паузах ~13 дБ
# привязка звука клипов к мастеру (корреляция): H3.mp3 — первая часть с 7.27, вторая (с 2.37 в клипе) ↔ 15.21 + τ; H4.mp3 с 22.24
H3A_REF, H3B_REF, H4_REF = 7.27, 15.21, 22.24


DUCK_DIR = "assets/music/epidemic/ep03/_ducked"


def ducked(src, m_in, dur, key_src, key_off, name, key_ss=0.0):
    """Музыка под голос: кусок трека [m_in, m_in+dur], вырез частот голоса (1.2 и 2.6 кГц) и приглушение на словах
    (sidechain по голосу, сдвинутому на key_off). Возвращает путь к готовому WAV (кэш по имени)."""
    import subprocess
    out = ROOT / DUCK_DIR / f"{name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    ms = int(round(key_off * 1000))
    fc = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},apad,atrim=0:{dur:.3f}[key];"
          f"[0:a]aresample=48000,aformat=channel_layouts=stereo,equalizer=f=1200:t=q:w=1.0:g=-2.5,"
          f"equalizer=f=2600:t=q:w=1.1:g=-5[m];"
          f"[m][key]sidechaincompress=threshold=0.04:ratio=2.5:attack=20:release=180:knee=4:makeup=1[o]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m_in:.3f}", "-t", f"{dur:.3f}", "-i", str(ROOT / src), "-ss", f"{key_ss:.3f}", "-i", str(ROOT / key_src),
                    "-filter_complex", fc, "-map", "[o]", "-c:a", "pcm_s16le", str(out)], check=True)
    return str(out.relative_to(ROOT))


def fr(t):
    return round(t * FPS) / FPS


def T(m):
    """время мастера холодного старта → таймлайн"""
    return fr(V0 + m)


def vclip(cid, start, end, src, inp, chapter, text, say="", say_en=""):
    return {"id": cid, "track": "v1", "shot": cid, "chapter": chapter, "start": fr(start), "dur": round(fr(end) - fr(start), 6),
            "motion": "static", "transition": "cut", "fit": "fill", "kind": "video", "src": src, "in": round(inp, 4),
            "mute": True, "text": text, "say": say, "say_en": say_en}


def aclip(cid, track, src, start, dur, inp=0.0, db=0.0, fi=0.0, fo=0.0, tag=None):
    c = {"id": cid, "track": track, "src": src, "start": fr(start), "dur": round(dur, 4), "in": round(inp, 4),
         "volume_db": db, "loop": False}
    if fi:
        c["fade_in"] = fi
    if fo:
        c["fade_out"] = fo
    if tag:
        c["tag"] = tag
    return c


def cold_open():
    ch = "0. ХОЛОДНЫЙ СТАРТ — полигон суперлюдей"
    v = [
        vclip("H1", 0, H1_END, f"{SH}/H1/h1_v4_endframe.mp4", 0.0, ch, "H1 [NICK] спуск к Нику, без слов"),
        vclip("H2", H1_END, T(CUT_H3A), f"{SH}/H2/h2_seedance20.mp4", 0.0, ch, "H2 [NICK] Oh. A volunteer…",
              "О. Доброволец. Отлично. Не бойся — тут почти ничего не взрывалось. Со вчерашнего дня.",
              "Oh. A volunteer. Perfect. Relax — almost nothing's exploded in here. Since yesterday."),
        vclip("H3a", T(CUT_H3A), T(CARDS_AT), f"{SH}/H3/h3_seedance20.mp4", CUT_H3A - H3A_REF + LAG, ch,
              "H3 [NICK] Warm-up. Three superhumans.", "Разминка. Три суперчеловека.", "Warm-up. Three superhumans."),
        vclip("H3cards", T(CARDS_AT), T(CUT_H3B), f"{SH}/H3a/cards_H3a.mp4", 0.0, ch, "H3a [GFX] три досье + штамп FAKE?",
              "Мужчина, чьи кости не ломаются. Женщина, которая не чувствует боли — и не знает, что такое тревога. "
              "И женщина, которая видит сто миллионов цветов.",
              "A man whose bones don't break. A woman who can't feel pain — and doesn't know what anxiety is. "
              "And a woman who sees a hundred million colors."),
        vclip("H3b", T(CUT_H3B), T(CUT_H4), f"{SH}/H3/h3_seedance20.mp4", CUT_H3B - H3B_REF + LAG, ch,
              "H3 [NICK] One of them is fake…", "Один из них — выдумка. Кто? Ответ будет. И не вздумай перематывать.",
              "One of them is fake. Which one? Answer's coming. And don't you dare skip."),
        vclip("H4", T(CUT_H4), T(ZOOM_AT), f"{SH}/H4/h4_seedance20.mp4", CUT_H4 - H4_REF + LAG, ch,
              "H4 [NICK] кнопка START", "Так насколько сверхчеловеком может стать человек? Сегодня мы пройдём все уровни — "
              "от тебя, прямо сейчас… до миллиона километров в секунду.",
              "So how superhuman can a human get? Today we climb every level — from you, right now… "
              "to a million kilometers per second."),
        vclip("H4z", T(ZOOM_AT), T(TOWER_AT), f"{SH}/H4/h4_tail_zoom.mp4", 0.0, ch, "H4 наезд в центр циферблата ⟶ башня"),
        vclip("H5", T(TOWER_AT), T(TOWER_REF) + TOWER_DUR, f"{SH}/H5/3d_tower.mp4", TOWER_AT - TOWER_REF, ch, "H5 [3D] Башня уровней",
              "…и найдём точный уровень, на котором ты ломаешь Вселенную. Уровень ноль — ты. … А десятый… "
              "…до десятого сначала надо дожить.",
              "…and find the exact level where you break the universe. Level zero: you. … And ten… "
              "…you'll have to survive to ten first."),
    ]
    end = v[-1]["start"] + v[-1]["dur"]
    meta = {"crack": 625}                  # кадр трещины 10-го этажа в 3d_tower.mp4 (tower_meta.json рендера)
    crack = T(TOWER_REF) + (meta.get("crack", 640) / FPS)
    a = [
        aclip("vo-co", "voice", f"{VO}/coldopen_take1_master.wav", V0, CO_VOICE_DUR),
        aclip("m-co", "music", ducked(f"{MUS}/01_slipping_coldopen.wav", 64.0 - T(TOWER_REF), end, f"{VO}/coldopen_take1_master.wav", V0, "coldopen_slipping"),
              0, end, db=-15, fi=1.0, fo=0.6),
        aclip("sfx-amb", "sfx2", f"{SFX}/ambience_machine_room.wav", 0, T(TOWER_AT), inp=5.0, db=-26, fi=0.4, fo=0.8, tag="ambience"),
        aclip("sfx-card1", "sfx1", f"{SFX}/whoosh_air_short.wav", T(CARDS_AT), 0.55, db=-12, tag="whoosh"),
        aclip("sfx-card1h", "sfx2", f"{SFX}/stamp_rubber.wav", T(9.457), 0.25, db=-10, tag="hit"),
        aclip("sfx-card2", "sfx1", f"{SFX}/whoosh_air_short.wav", T(11.03), 0.55, db=-12, tag="whoosh"),
        aclip("sfx-card2h", "sfx2", f"{SFX}/stamp_rubber.wav", T(11.19), 0.25, db=-10, tag="hit"),
        aclip("sfx-card3", "sfx1", f"{SFX}/whoosh_air_short.wav", T(14.63), 0.55, db=-12, tag="whoosh"),
        aclip("sfx-card3h", "sfx2", f"{SFX}/stamp_rubber.wav", T(14.79), 0.25, db=-10, tag="hit"),
        aclip("sfx-fake", "sfx1", f"{SFX}/stamp_rubber.wav", T(17.223), 0.25, db=-3, tag="stamp"),
        aclip("sfx-button", "sfx1", f"{SFX}/button_click.wav", T(29.52), 0.3, db=-8, tag="click"),
        aclip("sfx-slam", "sfx2", f"{SFX}/impact_dark_low.wav", T(29.56), 2.6, db=-7, fo=0.8, tag="hit"),
        aclip("sfx-zoom", "sfx1", f"{SFX}/whoosh_mids_1.wav", T(29.60), 0.8, db=-9, tag="whoosh"),
        aclip("sfx-glitch", "sfx1", f"{SFX}/glitch_stutter.wav", crack, 1.6, db=-10, fo=0.3, tag="glitch"),
        aclip("sfx-riser", "sfx2", f"{SFX}/riser_fast_suspense.wav", end - 2.4, 2.4, inp=1.9, db=-11, tag="riser"),
    ]
    return v, a, end


def teaser(t0):
    import ep03_teaser_cut as TC
    e = json.loads((ROOT / f"{SH}/T/teaser_edl.json").read_text())
    ch = "1. ТИЗЕР — «Сегодня вы узнаете»"
    v = []
    for c in e["clips"]:
        seg = Path(TC.render_segment(c)).resolve().relative_to(ROOT)
        f0, n = TC._clip_frames(c)
        v.append({"id": c["id"], "track": "v1", "shot": c["id"], "chapter": ch, "start": fr(t0 + f0 / FPS), "dur": n / FPS,
                  "motion": "static", "transition": "cut", "fit": "fill", "kind": "video", "src": str(seg), "in": 0.0,
                  "mute": True, "text": f"{c['id']} [{c.get('kind', '').upper()}] {c.get('phrase', '')}",
                  "say_en": c.get("phrase", ""), "orig_src": c["src"], "orig_in": c["in"], "orig_speed": c.get("speed", 1)})
    vo, mu = e["voice"], e["music"]
    if TEASER_MUSIC_SRC:
        mu = {"src": TEASER_MUSIC_SRC, "in": 0.0, "start": 0.0, "dur": mu["dur"]}
    a = [aclip("vo-teaser", "voice", vo["src"], t0 + vo.get("start", 0), vo["dur"], db=vo.get("volume_db", 0)),
         aclip("m-teaser", "music", ducked(mu["src"], mu.get("in", 0), mu["dur"], vo["src"], vo.get("start", 0) - mu.get("start", 0),
                                           "teaser_" + Path(mu["src"]).stem), t0 + mu.get("start", 0), mu["dur"], db=TEASER_MUSIC_DB, fo=0.05)]
    for k, s in enumerate(e["sfx"]):
        a.append(aclip(f"sfx-t{k:02d}", "sfx1", s["src"], t0 + s["start"], 0.8 if "whoosh" in s["src"] else 0.5,
                       db=s.get("volume_db", -10), tag=s.get("note")))
    end = v[-1]["start"] + v[-1]["dur"]
    return v, a, end


def intro(t0):
    v = [{"id": "INTRO", "track": "v1", "shot": "INTRO", "chapter": "1. ТИЗЕР — «Сегодня вы узнаете»", "start": fr(t0),
          "dur": 7.6, "motion": "static", "transition": "cut", "fit": "fill", "kind": "video", "src": "assets/intro/intro_v3.mp4",
          "in": 0.0, "mute": True, "text": "INTRO заставка канала"}]
    a = [aclip("m-intro", "music", "assets/intro/intro_music.wav", t0, 7.6, db=0)]
    return v, a


def api(path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=60))


def main():
    v1, a1, t1 = cold_open()
    v2, a2, t2 = teaser(t1)
    v3, a3 = intro(t2)
    clips = v1 + v2 + v3 + a1 + a2 + a3
    total = v3[-1]["start"] + v3[-1]["dur"]
    print(f"холодный старт до {t1:.2f} с, тизер до {t2:.2f} с, заставка до {total:.2f} с; клипов {len(clips)}")
    for c in v1:
        print(f"  {c['start']:7.3f} +{c['dur']:6.3f}  in {c.get('in', 0):6.3f}  {c['id']}")
    if "--apply" not in sys.argv:
        return
    ids = {p["id"] for p in api("/projects")["projects"]}
    pid = next((p["id"] for p in api("/projects")["projects"] if p["title"] == TITLE), None)
    if not pid:
        pid = api("/projects", {"title": TITLE})["id"]
        print("создан проект", pid)
    proj = api(f"/projects/{pid}")
    ops = [{"op": "remove", "id": c["id"], "fill": False} for c in proj["clips"]]
    ops += [{"op": "add", "clip": c, "restore": True} for c in clips]
    r = api(f"/projects/{pid}/ops", {"ops": ops, "client": "claude", "base_revision": proj.get("revision")})
    print(f"проект {pid}: ревизия {r['revision']}, клипов {len(r['project']['clips'])}")


if __name__ == "__main__":
    main()
