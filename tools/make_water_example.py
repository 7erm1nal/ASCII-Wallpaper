#!/usr/bin/env python3
"""
make_water_example.py — пример слоя `water.flow`.

    python3 make_water_example.py reference.jpg out_dir/

Пишет:
  water.flow.png                      — слой ЦЕЛИКОМ как он должен лежать в PSD (1280x720, прозрачный фон);
                                        это же и черновик: перетащите его в PSD слоем с именем "water.flow"
  water.flow_example_annotated.png    — то же поверх затемнённого референса со стрелками и подписями (только для понимания)
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_draft_psd import build_draft, W, H, SX, SY

ref_path, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
geo = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "geometry.json")))
M, ref = build_draft(Image.open(ref_path), geo)
flow = M["water.flow"]

# 1) чистый слой
rgba = np.zeros((H, W, 4), np.uint8)
rgba[..., :3] = (0, 170, 255)
rgba[..., 3] = (np.clip(flow, 0, 1) * 255).astype(np.uint8)
Image.fromarray(rgba, "RGBA").save(os.path.join(out, "water.flow.png"))

# 2) аннотированная версия
dim = (np.asarray(ref).astype(np.float32) * 0.45).astype(np.uint8)
base = Image.fromarray(dim).convert("RGBA")
base.alpha_composite(Image.fromarray(rgba, "RGBA"))
d = ImageDraw.Draw(base)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 19)

def arrow(p, q, color=(255, 255, 255, 255)):
    ang = np.arctan2(q[1] - p[1], q[0] - p[0])
    tip = np.array(q, float)
    L, Wd = 22, 11
    a = tip - L * np.array([np.cos(ang), np.sin(ang)]) + Wd * np.array([-np.sin(ang), np.cos(ang)])
    b = tip - L * np.array([np.cos(ang), np.sin(ang)]) - Wd * np.array([-np.sin(ang), np.cos(ang)])
    d.line([tuple(p), tuple(tip)], fill=color, width=3)
    d.polygon([tuple(tip), tuple(a), tuple(b)], fill=color)

for pts in geo["gutters"]:
    P = [(x * SX, y * SY + 12) for x, y in pts]
    seg = []
    for (x0, y0), (x1, y1) in zip(P, P[1:]):
        n = max(int(max(abs(x1 - x0), abs(y1 - y0))), 1)
        seg += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    seg.append(P[-1])
    for f in (0.18, 0.5, 0.82):
        i = int(f * (len(seg) - 1)); j = min(i + 28, len(seg) - 1)
        off = (0, -22)                                   # стрелки чуть выше линии, чтобы не закрывать её
        arrow((seg[i][0] + off[0], seg[i][1] + off[1]), (seg[j][0] + off[0], seg[j][1] + off[1]))
    s, e = seg[0], seg[-1]
    d.ellipse([s[0] - 7, s[1] - 7, s[0] + 7, s[1] + 7], outline=(255, 255, 255, 255), width=3)
    t1, t2 = "НАЧАЛО: бледный (альфа ≈ 35%)", "КОНЕЦ: насыщенный (альфа 100%)"
    left_side = s[0] < W / 2
    x1 = s[0] - d.textlength(t1, font=font) - 14 if left_side else s[0] + 14      # подписи начала — в разные стороны
    d.text((x1, s[1] - 30), t1, font=font, fill=(255, 255, 255, 255))
    x2 = max(12, min(e[0] - 6, W - d.textlength(t2, font=font) - 12))
    d.text((x2, e[1] - 78 if left_side else e[1] - 52), t2, font=font, fill=(255, 255, 255, 255))
d.rectangle([0, 0, W, 64], fill=(0, 0, 0, 190))
d.text((14, 8), "water.flow — направление течения = градиент альфы: от бледного (начало) к насыщенному (конец)", font=big, fill=(255, 255, 255, 255))
d.text((14, 36), "Ширина линии ≥ 1 ячейки (8–10 px). Без градиента (ровная альфа) течение пойдёт к зрителю, т.е. вниз по экрану.", font=font, fill=(200, 220, 255, 255))
base.convert("RGB").save(os.path.join(out, "water.flow_example_annotated.png"))
print("готово:", out)
