#!/usr/bin/env python3
"""
make_draft_psd.py — собирает ЧЕРНОВОЙ PSD с именованными слоями-масками для gen_scene.py.

    python3 make_draft_psd.py reference.jpg -o masks_draft.psd [--geometry geometry.json]

Что получается: холст 1280x720 (ровно 4x8 px на ячейку сетки 320x90), внизу слой "reference",
выше — слои из psd_masks.SPEC. Часть слоёв заполнена автодетектом (фонари, кромки для дождя, блики),
часть — грубыми полигонами "на глаз" под текущий референс (гора, храм, небо, дорога, растительность),
остальные пустые. Всё это черновик: правьте кистью/ластиком прямо на слоях.
Цвета слоёв — только для удобства в Photoshop, конвертер читает АЛЬФУ (или яркость у непрозрачных слоёв).
"""
import argparse, json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from psd_masks import SPEC

W, H = 1280, 720
RW, RH = 1366, 768                      # размер текущего референса, в котором заданы полигоны ниже
SX, SY = W / RW, H / RH

# --- грубые полигоны "на глаз" (пиксели референса 1366x768) ---
POLY = {
    "hill.mass": [(457, 318), (500, 305), (550, 285), (600, 262), (640, 236), (665, 212), (682, 196), (708, 190),
                  (722, 178), (745, 175), (766, 182), (850, 176), (872, 168), (892, 170), (910, 195), (945, 210),
                  (952, 245), (950, 300), (940, 350), (700, 355), (520, 345), (470, 335)],
    "hill.church": [(806, 92), (808, 100), (820, 114), (823, 125), (830, 130), (836, 132), (845, 140), (846, 152),
                    (850, 160), (850, 188), (845, 190), (765, 190), (766, 150), (768, 140), (776, 134), (782, 132),
                    (790, 128), (793, 122), (795, 112), (805, 100)],
    "sky": [(350, 0), (1050, 0), (1050, 100), (962, 106), (952, 205), (910, 192), (892, 166), (872, 166), (850, 172),
            (766, 180), (745, 173), (722, 177), (708, 188), (682, 194), (665, 210), (640, 234), (600, 260), (550, 283),
            (500, 303), (457, 316), (420, 325), (350, 330)],
    "ground.road": [(600, 646), (775, 647), (900, 665), (1040, 702), (1180, 768), (0, 768), (0, 745), (220, 698), (420, 664)],
    "rain.sheltered": [(1010, 330), (1366, 300), (1366, 700), (1010, 700)],
    "veg.cypress": [(958, 470), (962, 300), (968, 170), (975, 115), (985, 115), (992, 170), (1000, 300), (1004, 470)],
    "veg.foliage": [(1050, 0), (1366, 0), (1366, 150), (1250, 120), (1150, 125), (1060, 110)],
    "veg.ivy": [(0, 215), (140, 230), (185, 300), (105, 335), (0, 345)],
}
FOLIAGE2 = [(268, 480), (330, 450), (410, 470), (415, 540), (300, 560), (268, 540)]     # кусты у левого фонаря

COLORS = {"depth": (128, 128, 128), "sky": (80, 140, 255), "fog": (200, 200, 220), "hill": (150, 90, 200),
          "lamp": (255, 200, 0), "rain": (0, 200, 255), "ground": (255, 90, 90), "veg": (60, 200, 90), "water": (0, 170, 255),
          "arch": (255, 140, 0), "busstop": (255, 255, 0), "ctrl": (255, 0, 255)}


def poly_mask(pts):
    im = Image.new("L", (W, H), 0)
    ImageDraw.Draw(im).polygon([(x * SX, y * SY) for x, y in pts], fill=255)
    return np.asarray(im) > 0


def thick_polyline(lines, width):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for pts in lines:
        d.line([(x * SX, y * SY) for x, y in pts], fill=255, width=width)
    return np.asarray(im) > 0


def build_draft(ref_img, geo):
    """Черновые маски {имя: float32 (H, W)} по картинке + geometry.json. Возвращает (M, ref 1280x720)."""
    ref = ref_img.convert("RGB").resize((W, H), Image.LANCZOS)
    arr = np.asarray(ref).astype(np.float32) / 255
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    lum = arr @ np.array([0.2126, 0.7152, 0.0722], np.float32)

    M = {}
    ground = poly_mask(geo["ground"]) if False else None
    gpoly = [(x * SX / SX, y) for x, y in geo["ground"]]
    ground = poly_mask(gpoly)
    for k, pts in POLY.items():
        M[k] = poly_mask(pts).astype(np.float32)
    M["veg.foliage"] = np.maximum(M["veg.foliage"], poly_mask(FOLIAGE2).astype(np.float32))
    road = M["ground.road"] > 0.5
    M["ground.sidewalk"] = (ground & ~road).astype(np.float32)

    bx0, by0, bx1, by1 = geo["board"]
    board = poly_mask([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)])
    M["busstop.board"] = board.astype(np.float32)

    # --- церковный контур: граница маски храма, утолщённая ---
    ch = M["hill.church"] > 0.5
    M["hill.church_edge"] = (ndi.binary_dilation(ch, iterations=3) & ~ndi.binary_erosion(ch, iterations=1)).astype(np.float32)

    # --- бордюр: водостоки из geometry.json ---
    M["ground.curb"] = thick_polyline(geo["gutters"], 7).astype(np.float32)

    # --- ручьи: линии водостоков чуть ниже бордюра (в сторону дороги); альфа растёт по течению 0.35 -> 1.0 ---
    flow = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(flow)
    for pts in geo["gutters"]:
        P = [(x * SX, y * SY + 12) for x, y in pts]
        seg = []
        for (x0, y0), (x1, y1) in zip(P, P[1:]):
            n = max(int(max(abs(x1 - x0), abs(y1 - y0))), 1)
            seg += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
        seg.append(P[-1])
        for k in range(len(seg) - 1):
            al = 0.35 + 0.65 * k / max(len(seg) - 2, 1)
            fd.line([seg[k], seg[k + 1]], fill=int(255 * al), width=9)
    M["water.flow"] = np.asarray(flow).astype(np.float32) / 255

    # --- фонари: ядра (очень яркое тёплое), ореол (мягко), корпус (кольцо), столб (вертикаль вниз до земли) ---
    warm = (r > 1.2 * b) & (r >= 0.8 * g)
    # ядро: колба почти белая-жёлтая (синий канал >= ~0.3 от красного), а отсвет на стене насыщенно оранжевый
    core = warm & (lum > 0.45) & (b > 0.28 * r) & ~ground & ~board
    core = ndi.binary_opening(core, iterations=1)
    labc, nc = ndi.label(core)
    szc = ndi.sum(core, labc, range(1, nc + 1))
    core = np.isin(labc, [i + 1 for i, v in enumerate(szc) if v >= 3])
    M["lamp.core"] = core.astype(np.float32)
    glow = ndi.gaussian_filter((warm & (lum > 0.28) & ~ground & ~board).astype(np.float32), 9)
    M["lamp.glow"] = np.clip(glow / (glow.max() + 1e-6) * 1.4, 0, 1) * (~ndi.binary_dilation(core, iterations=3))
    M["lamp.body"] = (ndi.binary_dilation(core, iterations=6) & ~ndi.binary_dilation(core, iterations=2)).astype(np.float32)
    lab, n = ndi.label(ndi.binary_dilation(core, iterations=6))
    pole = Image.new("L", (W, H), 0)
    pd = ImageDraw.Draw(pole)
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(xs) < 40:
            continue
        cx, cy = int(xs.mean()), int(ys.max())
        # земля под фонарём: первая строка полигона земли в этом столбце
        col = np.nonzero(ground[:, cx])[0]
        gy = int(col.min()) if len(col) else H - 1
        pd.line([(cx, cy), (cx, min(gy, cy + 260))], fill=255, width=6)
    M["lamp.pole"] = (np.asarray(pole) > 0).astype(np.float32)

    # --- блики на дороге ---
    refl = ndi.gaussian_filter((warm & (lum > 0.18) & ground & ~board).astype(np.float32), 4)
    M["ground.reflect"] = np.clip(refl / (refl.max() + 1e-6) * 1.6, 0, 1)
    M["ground.puddles"] = (ndi.binary_dilation(refl > 0.25, iterations=10) & road).astype(np.float32)

    # --- кромки для дождя: сильные горизонтальные края ---
    sm = ndi.gaussian_filter(lum, 1.0)
    gy_, gx_ = np.gradient(sm)
    gm = np.abs(gy_)
    strong = (gm > np.percentile(gm, 94)) & (gm > 2.2 * np.abs(gx_))
    strong &= ~ground & ~board & ~(M["sky"] > 0.5)
    strong[: int(H * 0.12)] = False
    lab, n = ndi.label(ndi.binary_dilation(strong, structure=np.ones((1, 5))))
    sizes = ndi.sum(strong, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 10])
    edges = ndi.binary_dilation(strong & keep, iterations=1)
    M["rain.edges"] = edges.astype(np.float32)
    ys, xs = np.nonzero(strong & keep)
    rng = np.random.default_rng(5)
    drips = Image.new("L", (W, H), 0)
    dd = ImageDraw.Draw(drips)
    for i in rng.choice(len(xs), size=min(160, len(xs)), replace=False):
        dd.ellipse([xs[i] - 3, ys[i] - 3, xs[i] + 3, ys[i] + 3], fill=255)
    M["rain.drips"] = (np.asarray(drips) > 0).astype(np.float32)

    # --- глубина: радиально от точки схода; небо и гора — далеко ---
    vp = (712 * SX, 632 * SY)
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.hypot((xx - vp[0]) / W, (yy - vp[1]) / H * 1.2)
    depth = np.clip(dist / 0.62, 0, 1) ** 0.75
    depth = np.where(M["sky"] > 0.5, 0.05, depth)
    depth = np.where(M["hill.mass"] > 0.5, np.minimum(depth, 0.15), depth)
    depth = np.where(M["hill.church"] > 0.5, 0.15, depth)
    M["depth"] = ndi.gaussian_filter(depth.astype(np.float32), 6)

    # --- туман: мягкие пояса вокруг подножия горы ---
    fog = np.exp(-(((xx - 700 * SX) / (380 * SX)) ** 2 + ((yy - 395 * SY) / (70 * SY)) ** 2))
    fog += 0.6 * np.exp(-(((xx - 790 * SX) / (260 * SX)) ** 2 + ((yy - 300 * SY) / (55 * SY)) ** 2))
    M["fog"] = np.clip(fog, 0, 1).astype(np.float32) * 0.8

    # --- управление контурами: на проезжей части шум брусчатки не нужен ---
    M["ctrl.edge_suppress"] = road.astype(np.float32)

    return M, ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default="masks_draft.psd")
    ap.add_argument("--geometry", default="geometry.json")
    a = ap.parse_args()
    geo = json.load(open(a.geometry))
    M, ref = build_draft(Image.open(a.image), geo)

    # --- сборка PSD ---
    psd = PSDImage.new("RGBA", (W, H))
    PixelLayer.frompil(ref.convert("RGBA"), psd, "reference", top=0, left=0)
    for name in SPEC:
        v = M.get(name)
        group = name.split(".")[0]
        if name == "depth":
            g8 = (np.clip(v if v is not None else 0, 0, 1) * 255).astype(np.uint8)
            img = Image.fromarray(g8).convert("RGBA")                       # непрозрачный серый слой
        else:
            col = COLORS.get(group, (255, 255, 255))
            al = (np.clip(v if v is not None else np.zeros((H, W)), 0, 1) * 255).astype(np.uint8)
            rgba = np.zeros((H, W, 4), np.uint8)
            rgba[..., :3] = col
            rgba[..., 3] = al
            img = Image.fromarray(rgba, "RGBA")
        PixelLayer.frompil(img, psd, name, top=0, left=0)
    psd.save(a.out)
    filled = [k for k in SPEC if M.get(k) is not None and (M[k] > 0.5).sum() > 0]
    print(f"{a.out}: {len(SPEC)} слоёв масок, заполнено черновиком: {len(filled)}")
    print("пустые (рисовать вручную):", [k for k in SPEC if k not in filled])


if __name__ == "__main__":
    main()
