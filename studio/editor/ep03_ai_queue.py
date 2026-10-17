#!/usr/bin/env python3
"""Очередь AI-картинок ep03 (GPT Image 2.5 medium 1k) → assets/shots/ep03/ai/queue.json + QUEUE.md.

Каждая строка таблицы: (клип-заглушка в Cutlab, тип, сцена). Тип: N — Ник (элемент + референсы Ника, фон — ангар),
P — люди в стиле Ника (PRE_PEOPLE), O — без людей (стиль фонов). Сцена — ровно про свою фразу.
  python3 studio/editor/ep03_ai_queue.py
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio"))
from fix_people_style import PRE_PEOPLE  # noqa: E402

NICK_EL = "<<<8e0fe404-422b-4b73-9677-3bde163c9b36>>>"
CARD, FULL, BG, HANGAR = ("946adfb6-4c83-4346-a441-f3c5a813a0f9", "091fc760-89cf-473a-b7c4-a9ed9f403e9c",
                          "33da1683-753a-40a9-8b0a-a55c99fe1dd4", "fc5a1b2d-410e-4ca5-943b-5104a5294c60")
STYLE = ("Flat 2D adult cartoon, thin uniform black outlines, flat cel colors, minimal shading, clean and readable, "
         "exactly the art style of the references. ")
TAIL = " Every eye has exactly one small solid black dot pupil. No logos, no watermark, no extra text. 16:9 cinematic composition."
NICK = (f"The character is {NICK_EL} (Nick), drawn exactly like the Nick model sheet and full-body reference: messy short black hair, "
        "tired eyes with dark circles, light stubble, ironic half-smirk, dark charcoal suit jacket worn open, black turtleneck. ")
HANG = " Background: the same night testing hangar as the last reference image (dark navy, red beacons, cyan screens)."

Q = [
    ("0.2", "P", "A prehistoric herder family in a harsh snowy famine winter at a stone-age village; one young herder happily drinks milk from a clay bowl beside a cow while the others look thin and hungry; dusk light."),
    ("0.2", "O", "A stylized world map on parchment with five glowing spots — Europe, East Africa, the Middle East, South Asia — where milk tolerance evolved independently, a small clay milk bowl on each spot."),
    ("0.2", "P", "A busy modern city crosswalk seen from above; every third adult holds a glass of milk and glows softly, the others hold coffee cups."),
    ("0.3", "N", "Nick sits on a crate holding a dripping ice-cream cone with a betrayed, queasy face, comic rumble lines around his stomach."),
    ("0.3", "N", "Nick gestures with a smirk at a huge toy-style box labelled 'HUMAN — FACTORY SETTINGS' with a plain human figure inside."),
    ("1.1", "P", "A totally crushed old sedan on a Midwestern roadside in 1994; a stocky middle-aged man climbs out and dusts off his jacket, completely unhurt, paramedics staring in disbelief; evening light."),
    ("1.1", "P", "A 1990s hospital X-ray room: a puzzled doctor holds a spine X-ray film up to a glowing lightbox."),
    ("1.1", "O", "Close-up of an X-ray film where the spine and pelvis glow pure bright white like polished marble against dark tissue, a pen pointing at them."),
    ("1.4", "P", "The same stocky man in a swimming pool sinking straight down like a stone despite flailing arms, bubbles rising, a lifeguard shrugging."),
    ("1.4", "P", "Heroic poster-style portrait of the same stocky man with a comically wide square action-hero jaw, dramatic backlight."),
    ("1.4", "N", "Nick holds a balance scale: a small anchor on one pan, a sparkling unbreakable bone on the other; the bone side wins and Nick nods approvingly."),
    ("1.5", "O", "A dark dossier folder 'SUPERHUMAN #1' on a desk under a lamp, a big green rubber stamp 'REAL ✓' slamming onto it."),
    ("1.6", "O", "A rainy Scottish hospital: old stone building, wet street, green hills behind, warm windows."),
    ("1.6", "P", "A cheerful elderly woman with short white curly hair and round glasses in a hospital bed, bandaged hand resting, serenely smiling as she pushes away a tray of painkiller pills with one finger."),
    ("1.6", "P", "Three panels of the same woman through life — child, young woman, middle age — always calmly smiling while small everyday mishaps happen around her (no blood)."),
    ("1.8", "O", "A dark dossier folder 'SUPERHUMAN #2' with a big green stamp 'REAL ✓'."),
    ("1.8", "P", "The same elderly woman mid-sentence with an empty speech bubble holding only a question mark, smiling calmly."),
    ("1.8", "P", "The same elderly woman searching her cosy living room for keys that hang right behind her on a hook, totally relaxed, cup of tea in hand."),
    ("1.9", "N", "Nick leans toward the camera wagging his index finger with a sly grin; behind him, slightly blurred, a dossier 'SUPERHUMAN #3' with a red 'FAKE?' stamp."),
    ("1.10", "P", "A busy street in Lahore, Pakistan: colorful rickshaws and market stalls, a researcher with a notebook talking to a family."),
    ("1.10", "O", "A DNA double helix on a dark background with two matching links glowing red and visibly snapped, label 'SCN9A'."),
    ("1.10", "P", "A teenage street performer seen from behind juggling flaming torches before a wincing crowd; nobody is hurt."),
    ("1.10", "O", "A ceiling fire alarm with its wire cut, hanging silent while faint smoke drifts nearby; muted moody light."),
    ("1.11", "N", "Nick points like a teacher at a giant red fire-alarm bell mounted on the hangar wall."),
    ("1.11", "O", "A small suburban house at night with orange glow and smoke in the windows on a completely quiet street, a cat on the fence; no people."),
    ("1.12_3", "O", "A glowing lab screen listing blood group systems; a new entry '48' highlighted and blinking."),
    ("1.12_3", "P", "A woman from Guadeloupe sits in a hospital chair looking at a single blood bag tagged 'FOR: HERSELF'."),
    ("1.13", "N", "Nick sits alone at a tiny folding table under a 'BLOOD DRIVE' banner in an empty school gym: one chair, one cookie, bored face."),
    ("1.14", "O", "A river of DNA strips flowing from huge server racks into a giant funnel labelled '589,306 GENOMES'."),
    ("1.14", "O", "A corkboard 'WANTED: GENETIC SUPERHEROES' with 13 anonymous silhouettes pinned and red string connecting them."),
    ("1.14", "P", "A scientist at her desk holding a phone, hesitating, a towering stack of consent forms in front of her."),
    ("1.14", "O", "A consent form close-up with a big red stamp 'ACCESS DENIED' slamming onto it."),
    ("1.14", "N", "Nick facepalms in front of the corkboard with 13 silhouettes stamped 'ACCESS DENIED'."),
    ("2.3", "N", "Nick holds a phone to his ear with a deadpan face next to a heart monitor showing an almost flat line '11 BPM'."),
    ("2.3", "N", "Nick points sternly at the viewer holding a hand-drawn sign 'DON'T TRY THIS'."),
    ("2.6", "P", "A packed operating room: many doctors and nurses around a heart-lung machine, tubes glowing warm red, a wall clock showing hours passing."),
    ("2.6", "P", "A sunny hospital office: the recovered young woman doctor in a white coat smiling at the window, back at work."),
    ("2.7", "P", "A man in dark glasses walking down a sidewalk clicking his tongue, sound ripples spreading from his mouth."),
    ("2.7", "O", "First-person street view drawn as glowing outlines appearing where sound echoes hit: a wall, a parked car, a tree — like a sonar image on black."),
    ("2.7", "O", "Side view of a human brain: sound waves enter through the ear and light up the visual cortex at the back."),
    ("2.7", "P", "The man in dark glasses confidently steps around a lamppost and a tree, sound ripples outlining them."),
    ("2.12", "P", "A mother straining heroically to lift the corner of a car, a big question mark above the scene (myth framing)."),
    ("2.12", "P", "A 1960s laboratory: a man in a short-sleeve shirt pulls a lever dynamometer while a scientist behind him secretly holds a starter pistol."),
    ("2.12", "P", "The starter pistol goes 'BANG' pointed at the ceiling behind the startled subject, the dynamometer needle jumping."),
    ("2.12", "O", "A vintage 1960s lab chart on graph paper: strength bar rises only modestly, a small arrow."),
    ("2.14", "N", "Nick strains to push a heavy couch across the hangar, a comic speech bubble full of grawlix symbols '#@$%!'."),
    ("2.14", "N", "Nick dusts off his hands next to the moved couch, raising a finger like a professor, a tiny framed 'SCIENCE' diploma on the wall."),
    ("3.1", "O", "A glowing brain connected to the world by one thin frayed wire, with a new bright cable bypassing the bottleneck."),
    ("3.3", "P", "A man thinking with closed eyes, faint words floating from his head captured by a small implant device behind his ear."),
    ("3.3", "O", "A screen 'ENTER THOUGHT PASSWORD' with a blinking cursor and a padlock icon over a stylized brain."),
    ("3.3", "P", "The man imagines a silly code word, a padlock on his head clicking open."),
    ("3.4", "N", "Nick scratches his head, confused, in front of a big padlock-shaped head icon reading 'WRONG PASSWORD'."),
    ("3.7", "N", "Nick holds a coffee cup, a phone and a donut at once using a robotic third thumb strapped beside his pinky, a small sensor under his toe; he looks smug."),
    ("3.7", "P", "A science fair crowd of all ages — kids and grandparents — trying robotic third thumbs and laughing."),
    ("3.8", "O", "A cartoon brain wearing tiny glasses looks at a hand with six fingers and says 'oh, handy' in a speech bubble."),
    ("3.8", "N", "Nick happily wiggles a hand with a robotic sixth finger."),
    ("3.10", "P", "A generic long jumper with a carbon running-blade prosthetic soaring over a sand pit under stadium lights (not a real person)."),
    ("3.11", "P", "A woman wearing glasses with a tiny camera on the frame; her view of the street shown as a grid of glowing dots."),
    ("3.11", "O", "An office door with a sign 'CLOSED — NO SUPPORT', boxes of devices and dust."),
    ("3.11", "P", "The same woman standing in a subway car as her dot-grid view fades to black, other passengers oblivious."),
    ("3.12", "N", "Nick holds an old cracked smartphone showing 'NO UPDATES AVAILABLE' up to his eye like a monocle, deadpan."),
    ("4.4", "N", "Nick admires a giant coiled spring strapped to his forearm; a red 'DENIED' stamp in the corner."),
    ("4.7", "N", "Nick at a sushi bar holding a blob of wasabi with chopsticks, teary eyes, while a rattlesnake wearing tiny thermal goggles sits on the counter next to him."),
    ("4.8", "O", "A tiny cannon on a lab bench aimed at a sand tray, a microscopic tardigrade peeking out of the barrel wearing a tiny helmet."),
    ("4.9", "O", "A tardigrade standing proudly on a grain of sand wearing a gold medal."),
    ("4.9", "N", "Nick standing on a chair, frightened of a tiny spider on the floor."),
    ("5.3", "N", "Nick holds a car overhead while his body comically bends like a folding chair (cartoony, no injury)."),
    ("5.3", "O", "A folding chair collapsing flat with motion lines — simple diagram style."),
    ("5.4", "N", "Nick lifts a city bus overhead with a confident smirk on a city street."),
    ("5.4", "O", "Diagram: a stiletto heel and a sneaker pressing into soft asphalt, pressure arrows, same pressure marks."),
    ("5.4", "N", "Nick holding the bus overhead while sinking knee-deep into cracking asphalt."),
    ("5.4", "N", "Nick waist-deep in asphalt still holding the bus, annoyed."),
    ("5.4", "O", "A city street with a human-shaped hole in the asphalt and a bus resting on top, cracks radiating."),
    ("5.6", "N", "Nick presents a pair of futuristic glowing super sneakers like a product reveal."),
    ("6.1", "P", "A generic sprinter crossing the finish line at night in a packed stadium, motion lines (not a real person)."),
    ("6.1", "O", "A big stadium speed display reading '44.7 KM/H · 27.8 MPH'."),
    ("6.1", "P", "Sprinters exploding out of the starting blocks at the gun; one runner noticeably late."),
    ("6.7", "N", "Nick blurs past a crowd at supersonic speed, the letters of his yell 'LOOK OUT!' trailing far behind him."),
    ("6.7", "P", "A crowd turning their heads long after a blur has passed, the letters 'LOOK OUT!' only now arriving."),
    ("6.9", "P", "A long line of customers at a burger counter."),
    ("6.9", "N", "Nick at a burger counter with a mountain of burgers, cheeks stuffed, chewing frantically while a conveyor belt brings more."),
    ("7.1", "N", "Nick running inside a glowing orange fire cocoon like a meteor through the sky, sparks streaming behind."),
    ("7.3", "N", "Nick stands in a smoking, burnt hoodie full of holes, holding a tiny charred scrap of fabric, deadpan."),
    ("9.7", "N", "Nick in a running pose glances at his wristwatch while a huge bright fireball expands behind him (abstract, no damage)."),
    ("10.3", "N", "Nick holds a party popper bursting with confetti while behind him the starry sky cracks like glass."),
    ("10.3", "O", "A cracked clock face spinning backwards over a starfield."),
    ("10.5", "N", "Nick crouches behind a huge physics detector holding a loose fiber-optic cable plug, smug."),
    ("10.7", "N", "Nick gives a thumbs up from a tiny spaceship inside a shimmering warp bubble."),
    ("10.7", "O", "A clipboard shopping list: '1. WARP DRIVE  2. THE WHOLE UNIVERSE (×−1)'."),
]


def main():
    proj = json.loads((ROOT / "projects/ep03/project.json").read_text())
    dur = {c["id"]: c["dur"] for c in proj["clips"] if c.get("kind") == "card"}
    count = {}
    for clip, _, _ in Q:
        count[clip] = count.get(clip, 0) + 1
    out, k = [], {}
    for clip, typ, scene in Q:
        k[clip] = k.get(clip, 0) + 1
        if typ == "N":
            prompt, refs = STYLE + NICK + scene + HANG + TAIL, [CARD, FULL, HANGAR]
        elif typ == "P":
            prompt, refs = PRE_PEOPLE + scene + TAIL, [CARD, BG]
        else:
            prompt, refs = STYLE + scene + TAIL, [BG]
        out.append({"id": f"{clip}_{k[clip]}", "clip": clip, "k": k[clip], "type": typ,
                    "dur": round(dur.get(clip, 4.0) / count[clip], 3), "scene": scene, "prompt": prompt, "refs": refs})
    d = ROOT / "assets/shots/ep03/ai"
    d.mkdir(parents=True, exist_ok=True)
    (d / "queue.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    md = ["# AI-картинки ep03 — очередь", "", "| Клип | № | Тип | Сцена |", "|---|---|---|---|"]
    md += [f"| {x['clip']} | {x['k']} | {x['type']} | {x['scene']} |" for x in out]
    md += ["", f"Итого: {len(out)} картинок × 0,5 кр (GPT Image 2.5 medium 1k) = {len(out) * 0.5:g} кр."]
    (d / "QUEUE.md").write_text("\n".join(md))
    print(f"{len(out)} картинок → {d / 'queue.json'}; заглушек без очереди: {sorted(set(count) - set(dur))}")


if __name__ == "__main__":
    main()
