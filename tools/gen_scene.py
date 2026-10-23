#!/usr/bin/env python3
"""
gen_scene.py v2 — конвертер "картинка + маски -> сцена ASCII" для QML-плагина.

    python3 gen_scene.py reference.jpg --masks masks.psd -o ../plugin/.../scene.js --preview prev.png
    python3 gen_scene.py reference.jpg                      # без --masks: черновые маски строятся автоматически

Идея: маски говорят, ЧТО и ГДЕ (фонарь, бордюр, храм, кипарис, кромка для дождя), а конвертер решает, КАК
рисовать каждый класс: свои наборы символов, плотность, цвет и анимационные хуки. Остальное (всё, что не
размечено) рисуется как раньше: рампа яркости + направленные контуры + серые полутона.

Приоритет клеток (кто занял клетку — тот и рисует; выше — важнее):
  ядра ламп > табло > корпус фонаря > столб > бордюр > контур храма > растительность > окна > провода >
  ореол ламп > заливка храма > ободок горы > заливка горы > брусчатка > остальной фон > серые полутона
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from psd_masks import load_masks

RAMP = " .:-=+*#%@"
SS_X, SS_Y = 4, 8                      # субпикселей на ячейку (при cols=320 это ровно холст 1280x720)
L = np.array([0.2126, 0.7152, 0.0722], np.float32)


def kmeans(x, k, iters=14, seed=7):
    rng = np.random.default_rng(seed)
    c = [x[rng.integers(len(x))]]
    for _ in range(k - 1):
        d = np.min([((x - ci) ** 2).sum(1) for ci in c], axis=0)
        c.append(x[rng.choice(len(x), p=d / d.sum())])
    c = np.array(c)
    for _ in range(iters):
        lab = np.argmin(((x[:, None] - c[None]) ** 2).sum(2), axis=1)
        for i in range(k):
            m = lab == i
            if m.any():
                c[i] = x[m].mean(0)
    return c


def line_cells(pts):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(int(abs(x1 - x0)), int(abs(y1 - y0)), 1)
        for i in range(n):
            c = (round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n))
            if not out or out[-1] != c:
                out.append(c)
    return out


def hexcolor(rgb):
    return "#%02x%02x%02x" % tuple(int(255 * v) for v in np.clip(rgb, 0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--masks", action="append", default=None,
                    help="PSD с именованными слоями-масками или папка PNG; можно несколько (поздние переопределяют ранние)")
    ap.add_argument("-o", "--out", default="scene.js")
    ap.add_argument("--geometry", default="geometry.json")
    ap.add_argument("--cols", type=int, default=320)
    ap.add_argument("--aspect", type=float, default=2.0)
    ap.add_argument("--colors", type=int, default=12)
    ap.add_argument("--gamma", type=float, default=0.62)
    ap.add_argument("--edge", type=float, default=0.6)
    ap.add_argument("--surfaces", type=int, default=900, help="максимум точек-кромок для дождя")
    ap.add_argument("--halftone", type=float, default=1.0)
    ap.add_argument("--board-min-h", type=int, default=8)
    ap.add_argument("--glow-tint", type=float, default=0.7, help="сила подкраски ореола ламп (0 — выкл.)")
    ap.add_argument("--spill", type=float, default=0.16, help="макс. непрозрачность тёплой подложки-отсвета (0 — выкл.)")
    ap.add_argument("--church-density", type=float, default=0.45, help="доля клеток заливки храма (0..1)")
    ap.add_argument("--church-gain", type=float, default=0.8, help="яркость заливки храма (1 — как раньше)")
    ap.add_argument("--overlay", default="overlay", help="папка текстовой накладки (overlay.txt, overlay.base.txt, overlay_color.png)")
    ap.add_argument("--export-overlay", action="store_true", help="выгрузить текущий ASCII-фон в overlay.txt для ручной правки")
    ap.add_argument("--no-overlay", action="store_true", help="не применять накладку")
    ap.add_argument("--force", action="store_true", help="разрешить перезапись overlay.txt при выгрузке")
    ap.add_argument("--preview", default=None)
    a = ap.parse_args()

    geo = json.load(open(a.geometry))
    im = Image.open(a.image).convert("RGB")
    W, H = im.size
    cols = a.cols
    rows = round(cols * (H / W) / a.aspect)
    HW, HH = cols * SS_X, rows * SS_Y
    rng = np.random.default_rng(42)

    # ---------------- маски ----------------
    if a.masks:
        masks, srcs = {}, []
        for mp in a.masks:
            mm, canvas = load_masks(mp, (HW, HH))
            masks.update(mm)
            srcs.append(f"{mp} ({len(mm)} сл.)")
        src = " + ".join(srcs)
    else:
        from make_draft_psd import build_draft
        draft, _ = build_draft(im, geo)
        masks = {k: np.asarray(Image.fromarray(v.astype(np.float32)).resize((HW, HH), Image.BILINEAR)) for k, v in draft.items()}
        src = "черновые маски (автодетект)"

    def cm(v):
        return v.reshape(rows, SS_Y, cols, SS_X).mean((1, 3))

    def mcell(name):
        v = masks.get(name)
        return None if v is None else cm(v)

    def mbin(name, thr=0.5):
        c = mcell(name)
        return np.zeros((rows, cols), bool) if c is None else c > thr

    def erode(m, n=1):
        return ndi.binary_erosion(m, iterations=n, border_value=0)

    def boundary(m):
        return m & ~erode(m)

    # ---------------- изображение: тон, контуры ----------------
    hi = np.asarray(im.resize((HW, HH), Image.LANCZOS)).astype(np.float32) / 255
    cell = hi.reshape(rows, SS_Y, cols, SS_X, 3).mean((1, 3))
    lum_hi = hi @ L
    lum = cell @ L

    depth = mcell("depth")
    if depth is not None:                                    # дымка на дальних планах
        haze = np.clip(1 - depth, 0, 1)[..., None]
        cell = cell * (1 - 0.35 * haze) + np.array([0.16, 0.22, 0.34], np.float32) * 0.18 * haze
        lum = cell @ L

    lo, hi_p = np.percentile(lum, 4), np.percentile(lum, 99.6)
    t = np.clip((lum - lo) / (hi_p - lo + 1e-6), 0, 1) ** a.gamma

    # --- ореол ламп = подкраска, а не символы: цвет существующих глифов смешивается с оранжевым ---
    ORANGE = np.array([1.0, 0.56, 0.20], np.float32)
    glow_c = mcell("lamp.glow")
    glow_s = np.clip(glow_c * 1.25, 0, 1) if glow_c is not None else np.zeros((rows, cols), np.float32)
    if a.glow_tint > 0 and glow_s.max() > 0:
        m_ = (a.glow_tint * glow_s)[..., None]
        warm = ORANGE * np.clip(cell.max(axis=-1, keepdims=True) * 1.8, 0.30, 1.0)
        cell = cell * (1 - m_) + warm * m_                       # дальше k-means сам даст "тёплые" кластеры
        glow_level = np.where(glow_s < 0.15, 0, np.where(glow_s < 0.5, 1, 2))
    else:
        glow_level = np.zeros((rows, cols), int)

    def tensor(vhi, sigma):
        sm = ndi.gaussian_filter(vhi.astype(np.float32), sigma)
        gy, gx = np.gradient(sm)
        return cm(gx * gx), cm(gy * gy), cm(gx * gy)

    def dir_chars(Jxx, Jyy, Jxy, valid=None):
        theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)
        phi = np.degrees(np.arctan2(-np.cos(theta), -np.sin(theta))) % 180
        ch = np.full((rows, cols), "-", dtype="<U1")
        ch[(phi >= 25) & (phi < 70)] = "/"
        ch[(phi >= 70) & (phi < 110)] = "|"
        ch[(phi >= 110) & (phi < 155)] = "\\"
        if valid is not None and (~valid).any() and valid.any():
            idx = ndi.distance_transform_edt(~valid, return_distances=False, return_indices=True)
            ch = ch[idx[0], idx[1]]
        return ch

    Jxx, Jyy, Jxy = tensor(lum_hi, 0.8)
    E = np.sqrt(Jxx + Jyy)
    E = np.clip(E / (np.percentile(E, 97) + 1e-6), 0, 1)
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-9)
    edge_ch = dir_chars(Jxx, Jyy, Jxy)
    is_edge = (E > a.edge) & (coh > 0.55)

    def mask_dirs(name):
        mh = masks.get(name)
        if mh is None:
            return np.full((rows, cols), "|", dtype="<U1")
        jxx, jyy, jxy = tensor(mh, 2.0)
        return dir_chars(jxx, jyy, jxy, valid=(jxx + jyy) > 1e-5)

    sky, sup = mbin("sky"), mbin("ctrl.edge_suppress")
    keep = mbin("ctrl.edge_keep", 0.12)
    is_edge &= ~(sky | sup)
    E = np.where(sky | sup, 0, E)
    if keep.any():
        kd = mask_dirs("ctrl.edge_keep")
        edge_ch = np.where(keep, kd, edge_ch)
        is_edge |= keep

    Eadj = np.clip((E - 0.22) / 0.78, 0, 1) ** 1.3
    score = np.clip(0.10 * t + Eadj, 0, 1)
    if depth is not None:
        score *= 0.55 + 0.45 * depth
    idx = np.rint(score * (len(RAMP) - 1)).astype(int)
    ch = np.array([[RAMP[i] for i in r] for r in idx], dtype="<U1")
    ch[is_edge] = edge_ch[is_edge]
    ch[(score < 0.10) & ~is_edge] = " "

    # ---------------- табло ----------------
    sx, sy = cols / geo["ref_size"][0], rows / geo["ref_size"][1]
    bm = mbin("busstop.board", 0.3)
    if bm.any():
        ys, xs = np.nonzero(bm)
        B = dict(x=int(xs.min()), y=int(ys.min()), w=int(xs.max() - xs.min() + 1), h=int(ys.max() - ys.min() + 1))
    else:
        bx0, by0, bx1, by1 = geo["board"]
        B = dict(x=int(bx0 * sx + .5), y=int(by0 * sy + .5))
        B["w"] = int(bx1 * sx + .5) - B["x"]
        B["h"] = int(by1 * sy + .5) - B["y"]
    B["w"] = max(B["w"], 12)
    B["h"] = max(B["h"], a.board_min_h)
    board = np.zeros((rows, cols), bool)
    board[B["y"]:B["y"] + B["h"], B["x"]:B["x"] + B["w"]] = True
    frame = np.full((rows, cols), " ", dtype="<U1")
    x0, y0, w, h = B["x"], B["y"], B["w"], B["h"]
    frame[y0, x0:x0 + w] = "-"
    frame[y0 + h - 1, x0:x0 + w] = "-"
    frame[y0:y0 + h, x0] = "|"
    frame[y0:y0 + h, x0 + w - 1] = "|"
    for yy, xx in ((y0, x0), (y0, x0 + w - 1), (y0 + h - 1, x0), (y0 + h - 1, x0 + w - 1)):
        frame[yy, xx] = "+"

    # ---------------- реестр классов ----------------
    claims = []                 # (layer, cells, chars, reserve)   — порядок = приоритет
    meta = {}                   # layer -> dict(color, opacity, motion?)

    def claim(layer, cells, chars, color, opacity=1.0, reserve=False, motion=None):
        if isinstance(chars, str):
            chars = np.full((rows, cols), chars, dtype="<U1")
        claims.append((layer, cells, chars, reserve))
        if layer not in meta:
            meta[layer] = dict(color=color, opacity=opacity)
            if motion:
                meta[layer]["motion"] = motion

    # --- ручная накладка: tools/overlay/overlay.txt (+ overlay.base.txt, overlay_color.png) ---
    ov_dir = a.overlay if os.path.isabs(a.overlay) else os.path.join(os.path.dirname(os.path.abspath(__file__)), a.overlay)
    ov_txt, ov_base, ov_png = (os.path.join(ov_dir, n) for n in ("overlay.txt", "overlay.base.txt", "overlay_color.png"))

    def read_grid(path):
        raw = open(path, encoding="utf-8").read()
        if "\t" in raw:
            sys.exit(f"{path}: найдены табуляции — используйте пробелы")
        lines = raw.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        if len(lines) != rows:
            sys.exit(f"{path}: {len(lines)} строк, ожидается {rows} (строки добавлять/удалять нельзя)")
        grid = np.full((rows, cols), " ", dtype="<U1")
        for y, line in enumerate(lines):
            line = line.rstrip("\r")
            if len(line) > cols:
                sys.exit(f"{path}: строка {y + 1} длиннее {cols} символов ({len(line)})")
            for x, c in enumerate(line):
                grid[y, x] = c
        return grid

    n_manual = 0
    if not (a.no_overlay or a.export_overlay) and os.path.exists(ov_txt) and os.path.exists(ov_base):
        g1, g0 = read_grid(ov_txt), read_grid(ov_base)
        force_blank = g1 == "¤"                               # маркер "принудительно пусто" (в т.ч. отключает туман)
        g1 = np.where(force_blank, " ", g1)
        ov_cells = (g1 != g0) | force_blank                   # правка = клетка, отличающаяся от снимка при выгрузке
        has_col = np.zeros((rows, cols), bool)
        rgba = None
        if os.path.exists(ov_png):
            png = Image.open(ov_png).convert("RGBA")
            if png.size != (cols, rows):
                sys.exit(f"{ov_png}: размер {png.size}, ожидается {(cols, rows)}")
            rgba = np.asarray(png).astype(np.float32) / 255
            has_col = rgba[..., 3] > 0.05
            ov_cells |= has_col & (g1 != " ")                 # правка только цвета: глиф остаётся
        v_ = np.maximum(cell.max(-1, keepdims=True), 1e-3)
        auto = np.clip(cell * (np.minimum(1.0, 0.30 + 0.85 * v_ ** 0.65) / v_), 0, 1)
        sel = ov_cells & (g1 != " ")
        k_layer = 0
        explicit = sel & has_col                              # цвет задан в overlay_color.png — точные оттенки
        if explicit.any():
            q = np.round(rgba[..., :3][explicit] * 255).astype(int)
            uniq, inv = np.unique(q, axis=0, return_inverse=True)
            inv = inv.reshape(-1)
            if len(uniq) > 16:
                pe = rgba[..., :3][explicit]
                cen_ = kmeans(pe.astype(np.float32), 16)
                inv = np.argmin(((pe[:, None] - cen_[None]) ** 2).sum(2), axis=1)
                ucols = cen_
            else:
                ucols = uniq / 255.0
            for j_ in range(len(ucols)):
                mk = np.zeros((rows, cols), bool)
                mk[explicit] = inv == j_
                claim(f"manual_{k_layer}", mk, g1, hexcolor(ucols[j_]))
                k_layer += 1
        autosel = sel & ~has_col                              # цвет не задан — берём цвет картинки в клетке, 4 группы
        if autosel.any():
            pa = auto[autosel]
            kk = min(4, len(pa))
            cen_ = kmeans(pa.astype(np.float32), kk) if kk > 1 else pa[:1]
            inv = np.argmin(((pa[:, None] - cen_[None]) ** 2).sum(2), axis=1)
            for j_ in range(len(cen_)):
                mk = np.zeros((rows, cols), bool)
                mk[autosel] = inv == j_
                claim(f"manual_{k_layer}", mk, g1, hexcolor(cen_[j_]))
                k_layer += 1
        blank = ov_cells & (g1 == " ")
        claim("manual_blank", blank, " ", "#000000", reserve=True)
        n_manual = int(ov_cells.sum())

    # --- фонари ---
    lc = mcell("lamp.core")
    core = (lc > 0.18) if lc is not None else np.zeros((rows, cols), bool)
    if core.any():
        lamp_ch = np.where(lc > 0.55, "@", np.where(lc > 0.32, "O", "o"))
        claim("lamps", core, lamp_ch, "#ffb454")
    claim("board", board & (frame != " "), frame, "#8a5a1c", reserve=False)
    claim("board_fill", board, " ", "#000000", reserve=True)            # внутренность табло не трогаем
    body = mbin("lamp.body", 0.25)
    claim("lamp_body", body, "#", "#a8854f")
    pole = mbin("lamp.pole", 0.12)
    claim("lamp_pole", pole, mask_dirs("lamp.pole"), "#6a7585")
    curb = mbin("ground.curb", 0.12)
    claim("curb", curb, mask_dirs("ground.curb"), "#a2b2cb")

    church = mbin("hill.church", 0.5)
    cedge = mbin("hill.church_edge", 0.12)
    if not cedge.any() and church.any():
        cedge = boundary(church)
        cedge_dirs = mask_dirs("hill.church")
    else:
        cedge_dirs = mask_dirs("hill.church_edge")
    claim("church_edge", cedge, cedge_dirs, "#aebfe2")

    # --- растительность: случайные глифы, прореживание по краю, 2 тона по яркости ---
    veg_sets = {
        "veg.cypress": ("cypress", "|||!I1l:", ("#274540", "#36625b")),
        "veg.foliage": ("foliage", "%&8#@o*{(", ("#2f4f45", "#42695a")),
        "veg.ivy": ("ivy", "{}[]|;:!", ("#35564a", "#4a7060")),
    }
    for name, (key, glyphs, colors) in veg_sets.items():
        m = mbin(name, 0.5)
        if not m.any():
            continue
        edge_zone = boundary(m)
        drop = np.where(edge_zone, 0.40, 0.05)
        ok = m & (rng.random((rows, cols)) > drop)
        g = np.array(list(glyphs))
        chars = g[rng.integers(0, len(g), (rows, cols))]
        med = np.median(t[m])
        claim(f"veg_{key}_a", ok & (t <= med), chars, colors[0])
        claim(f"veg_{key}_b", ok & (t > med), chars, colors[1])

    # --- окна: контур + тёплая заливка у светящихся ---
    win = mbin("arch.windows", 0.5)
    if win.any():
        lit = win & (cell[..., 0] > 1.15 * cell[..., 2]) & (lum > 0.12)
        claim("windows_lit", lit, ":", "#c98a3d")
        claim("windows", boundary(win), mask_dirs("arch.windows"), "#7788a3")
    claim("wires", mbin("arch.wires", 0.12), mask_dirs("arch.wires"), "#5b6881")

    # (ореол ламп больше не занимает клетки — см. подкраску выше и spill.png)

    # --- храм: заливка блоками по тону, прорежена и приглушена, чтобы не перетягивать глаз ---
    def scale_hex(hexc, g):
        c = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
        return hexcolor(c * g)

    if church.any():
        qc = np.percentile(t[church], 60)
        keep_c = rng.random((rows, cols)) < a.church_density
        for nm, sym, col, cond in (("church_a", "░", "#4a5d7e", t <= qc), ("church_b", "▒", "#5f7499", t > qc)):
            claim(nm, church & cond & keep_c & (ch == " "), sym, scale_hex(col, a.church_gain))

    # --- гора: ободок + заливка ---
    hill = mbin("hill.mass", 0.5) & ~church
    if hill.any():
        claim("hill_rim", boundary(hill) & (rng.random((rows, cols)) > 0.08), mask_dirs("hill.mass"), "#566b91")
        free_h = hill & (ch == " ")
        rr = rng.random((rows, cols))
        th = np.percentile(t[hill], 55)
        claim("hill_a", free_h & (rr < 0.45) & (t <= th), "░", "#2a3850")
        claim("hill_b", free_h & (rr < 0.45) & (t > th), "▒", "#364872")
        trees = np.array(list("^^AiYl|"))[rng.integers(0, 7, (rows, cols))]       # намёк на лес по склону
        claim("hill_trees", free_h & (rr >= 0.45) & (rr < 0.62), trees, "#2f4062")

    # --- дорога: брусчатка с перспективой ---
    road = mbin("ground.road", 0.5)
    if road.any():
        ys = np.nonzero(road.any(1))[0]
        y_h = int(ys.min())
        pat = np.full((rows, cols), " ", dtype="<U1")
        K = 7
        course = {int(round(y_h + (rows - 1 - y_h) * (k / K) ** 1.6)) for k in range(1, K + 1)}
        for y in range(y_h, rows):
            s = (y - y_h + 1) / max(rows - y_h, 1)
            spacing = max(3, int(round(3 + 13 * s)))
            off = (y * 7) % spacing
            for x in range(cols):
                if not road[y, x]:
                    continue
                if y in course:
                    pat[y, x] = "-" if rng.random() < 0.80 else " "
                elif (x + off) % spacing == 0:
                    pat[y, x] = ":" if s > 0.5 else "."
                elif rng.random() < 0.06:
                    pat[y, x] = "."
        claim("road", road, pat, "#2c3649", reserve=True)

    # ---------------- назначение клеток ----------------
    taken = np.zeros((rows, cols), bool)
    owned = {}
    taken_high = None
    for layer, cells, chars, reserve in claims:
        m = cells & ~taken & (chars != " ")
        if layer in owned:
            owned[layer] = (owned[layer][0] | m, np.where(m, chars, owned[layer][1]))
        else:
            owned[layer] = (m, chars)
        taken |= (cells & ~taken) if reserve else m
        if layer == "wires":
            taken_high = taken.copy()
    if taken_high is None:
        taken_high = taken.copy()

    # ---------------- остальной фон: цветовые слои k-means ----------------
    base_layers = []
    use = ~taken & (ch != " ")
    if use.any():
        pts = cell[use]
        pts = np.vstack([pts, pts[lum[use] > np.percentile(lum[use], 85)]])
        cen = kmeans(pts, a.colors)
        lab_all = np.argmin(((cell[:, :, None] - cen[None, None]) ** 2).sum(3), axis=2)
        for k in np.argsort(cen @ L):
            m = use & (lab_all == k)
            if not m.any():
                continue
            c = cen[k]
            v = max(float(c.max()), 1e-3)
            c = c * (min(1.0, 0.30 + 0.85 * v ** 0.65) / v)
            base_layers.append((f"base{len(base_layers)}", m, ch, hexcolor(c), 1.0))
        taken |= use

    # ---------------- серые полутона на свободных клетках ----------------
    ht_layers = []
    if a.halftone > 0:
        free = ~taken
        thr = np.random.default_rng(11).random((rows, cols))
        dens = np.clip(0.30 + 0.70 * t ** 1.1, 0, 1) * a.halftone
        put_ht = free & (thr < dens)
        ht_ch = np.where(dens < 0.52, ".", np.where(dens < 0.78, ":", ";"))
        tint = cell.reshape(-1, 3).mean(0)
        tint = 0.55 * tint / max(tint.max(), 1e-3) + 0.45
        for sym, lvl in ((".", 0.17), (":", 0.23), (";", 0.30)):
            m = put_ht & (ht_ch == sym)
            if m.any():
                ht_layers.append((f"ht{len(ht_layers)}", m, ht_ch, hexcolor(tint * lvl), 1.0))

    if a.export_overlay:
        if os.path.exists(ov_txt) and not a.force:
            sys.exit(f"{ov_txt} уже существует — ваши правки будут потеряны. Добавьте --force, если это нужно.")
        final = np.full((rows, cols), " ", dtype="<U1")
        for _nm, (m_, chars_) in owned.items():
            final = np.where(m_, chars_, final)
        for _nm, m_, chars_, _c, _o in base_layers + ht_layers:
            final = np.where(m_, chars_, final)
        os.makedirs(ov_dir, exist_ok=True)
        text_ = "\n".join("".join(r) for r in final) + "\n"
        for p_ in (ov_txt, ov_base):
            open(p_, "w", encoding="utf-8").write(text_)
        Image.new("RGBA", (cols, rows), (0, 0, 0, 0)).save(ov_png)
        print(f"накладка выгружена в {ov_dir}: overlay.txt ({cols}x{rows}), overlay.base.txt (снимок), overlay_color.png (пустой)")

    # ---------------- туман (дрейфует) ----------------
    fog_layer = []
    fc = mcell("fog")
    if fc is not None and (fc > 0.05).any():
        fm = (rng.random((rows, cols)) < np.clip(fc * 1.1, 0, 1)) & ~taken_high
        fch = np.where(fc > 0.6, "~", np.where(fc > 0.3, "-", "."))
        fog_layer.append(("fog", fm, fch, "#5f7694", 0.55, dict(dx=3, period=70000)))

    # ---------------- сборка слоёв в порядке отрисовки ----------------
    def text_of(m, chars):
        return "\n".join("".join(chars[y, x] if m[y, x] else " " for x in range(cols)) for y in range(rows))

    out_layers = []

    def mix_hex(hexc, m):
        c = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
        warm = ORANGE * float(np.clip(c.max() * 1.8, 0.30, 1.0))
        return hexcolor(c * (1 - m) + warm * m)

    TINT_EXEMPT = {"lamps", "lamp_body", "board", "fog", "manual_blank"}

    def emit(nm, m, chars, color, op, motion=None, tint=True):
        extra = dict(opacity=op)
        if motion:
            extra["motion"] = motion
        if tint and a.glow_tint > 0 and glow_level.max() > 0 and nm not in TINT_EXEMPT and not nm.startswith("manual"):
            k = a.glow_tint / 0.7
            for lvl, mixv in ((0, 0.0), (1, 0.35 * k), (2, 0.70 * k)):
                mm = m & (glow_level == lvl)
                if mm.any():
                    out_layers.append(dict(name=nm if lvl == 0 else f"{nm}_w{lvl}",
                                           color=color if lvl == 0 else mix_hex(color, min(mixv, 0.95)),
                                           text=text_of(mm, chars), **extra))
        else:
            out_layers.append(dict(name=nm, color=color, text=text_of(m, chars), **extra))

    for nm, m, chars, color, op in base_layers:
        emit(nm, m, chars, color, op, tint=False)               # цвета уже подкрашены до кластеризации
    for nm, m, chars, color, op in ht_layers:
        emit(nm, m, chars, color, op)
    z_order = ["hill_a", "hill_b", "hill_trees", "hill_rim", "church_a", "church_b", "road",
               "veg_cypress_a", "veg_cypress_b", "veg_foliage_a", "veg_foliage_b", "veg_ivy_a", "veg_ivy_b",
               "windows", "windows_lit", "wires", "curb", "church_edge"]
    for nm in z_order:
        if nm in owned and owned[nm][0].any():
            emit(nm, owned[nm][0], owned[nm][1], meta[nm]["color"], meta[nm]["opacity"])
    for nm, m, chars, color, op, motion in fog_layer:
        emit(nm, m, chars, color, op, motion=motion)
    for nm in sorted(k for k in owned if k.startswith("manual_") and k != "manual_blank"):
        if owned[nm][0].any():
            emit(nm, owned[nm][0], owned[nm][1], meta[nm]["color"], meta[nm]["opacity"])
    for nm in ["lamp_pole", "lamp_body", "lamps", "board"]:
        if nm in owned and owned[nm][0].any():
            emit(nm, owned[nm][0], owned[nm][1], meta[nm]["color"], meta[nm]["opacity"])

    # ---------------- данные для дождя ----------------
    def cells_of(m):
        ys, xs = np.nonzero(m)
        return [int(v) for p in zip(xs, ys) for v in p]

    edges = mbin("rain.edges", 0.15) & ~board
    ey, ex = np.nonzero(edges)
    if len(ex) > a.surfaces:
        pick = np.sort(rng.choice(len(ex), size=a.surfaces, replace=False))
        ex, ey = ex[pick], ey[pick]
    surfaces = [int(v) for p in zip(ex, ey) for v in p]
    drips = cells_of(mbin("rain.drips", 0.2))
    sheltered = cells_of(mbin("rain.sheltered", 0.3))
    ground_m = mbin("ground.road", 0.5) | mbin("ground.sidewalk", 0.5)
    puddles = cells_of(mbin("ground.puddles", 0.3))
    rc = mcell("ground.reflect")
    reflect = cells_of(rc > 0.12) if rc is not None else []

    # ---------------- ручьи: маска water.flow (направление = градиент альфы) ----------------
    road_rows = np.nonzero(mbin("ground.road", 0.5).any(1))[0]
    y_h = int(road_rows.min()) if len(road_rows) else int(rows * 0.8)

    def pf(y):                                     # перспективный масштаб: вдали ручей "короче" и медленнее
        return 0.35 + 1.15 * float(np.clip((y - y_h) / max(rows - 1 - y_h, 1), 0, 1))

    def corr_sign(sig, other):
        if sig.std() < 1e-9 or np.std(other) < 1e-9:
            return 1.0
        return 1.0 if np.corrcoef(sig, other)[0, 1] >= 0 else -1.0

    def make_stream(xs, ys, v):
        """Клетки ручья -> плоский список [x, y, s*10, ...]; s растёт по течению, с перспективной поправкой."""
        if len(xs) < 3:
            return None
        P = np.stack([xs.astype(float), 2.0 * ys], 1)            # ячейка 1:2 -> физические единицы
        Pc = P - P.mean(0)
        w, V = np.linalg.eigh(np.cov(Pc.T) + 1e-9 * np.eye(2))
        sigma = Pc @ V[:, np.argmax(w)]
        has_grad = v is not None and (np.percentile(v, 90) - np.percentile(v, 10)) > 0.12
        sigma = sigma * corr_sign(sigma, v if has_grad else ys.astype(float))   # иначе: "к зрителю" (вниз)
        sigma -= sigma.min()
        b = np.floor(sigma).astype(int)
        nb = int(b.max()) + 1
        ysum, cnt = np.zeros(nb), np.zeros(nb)
        np.add.at(ysum, b, ys)
        np.add.at(cnt, b, 1)
        ybin = np.where(cnt > 0, ysum / np.maximum(cnt, 1), np.nan)
        for i_ in range(nb):                                      # пустые корзины — значение соседа
            if np.isnan(ybin[i_]):
                ybin[i_] = ybin[i_ - 1] if i_ > 0 else np.nanmin(ybin)
        steps = np.array([pf(y_) for y_ in ybin])
        cum = np.concatenate([[0.0], np.cumsum(steps)[:-1]])
        sp = cum[b] + (sigma - b) * steps[b]
        order = np.argsort(sp)
        return [int(q) for i_ in order for q in (xs[i_], ys[i_], round(sp[i_] * 10))]

    streams = []
    flc = mcell("water.flow")
    if flc is not None and (flc > 0.12).any():
        labf, nf = ndi.label(flc > 0.12, structure=np.ones((3, 3)))
        for i_ in range(1, nf + 1):
            yy_, xx_ = np.nonzero(labf == i_)
            st_ = make_stream(xx_, yy_, flc[yy_, xx_])
            if st_:
                streams.append(st_)
    else:                                                          # запасной вариант: ломаные из geometry.json
        for g_ in geo["gutters"]:
            cl = line_cells([(x * sx, y * sy) for x, y in g_])
            st_ = make_stream(np.array([c[0] for c in cl]), np.array([c[1] for c in cl]), None)
            if st_:
                streams.append(st_)

    scene = dict(
        cols=cols, rows=rows, board=B, layers=out_layers,
        surfaces=surfaces, drips=drips, sheltered=sheltered, puddles=puddles,
        ground=cells_of(ground_m),
        gutters=streams,
        reflect=reflect,
    )
    with open(a.out, "w") as f:
        f.write("// GENERATED by tools/gen_scene.py — не править руками\n.pragma library\n")
        for k, v in scene.items():
            f.write(f"var {k} = {json.dumps(v, separators=(',', ':'), ensure_ascii=False)};\n")
    # подложка-отсвет: тёплое мягкое пятно под текстом (мерцает в QML)
    spill = ndi.gaussian_filter(glow_s.astype(np.float32), 2.0)
    spill_rgba = np.zeros((rows, cols, 4), np.uint8)
    spill_rgba[..., 0], spill_rgba[..., 1], spill_rgba[..., 2] = 255, 138, 58
    spill_rgba[..., 3] = (np.clip(spill * a.spill, 0, a.spill) * 255).astype(np.uint8)
    Image.fromarray(spill_rgba, "RGBA").resize((cols * 2, rows * 2), Image.BILINEAR).save(
        os.path.join(os.path.dirname(os.path.abspath(a.out)), "spill.png"))
    print(f"маски: {src}")
    print(f"сетка {cols}x{rows}, слоёв {len(out_layers)}, кромок {len(surfaces) // 2}, капельных точек {len(drips) // 2}, "
          f"укрытие {len(sheltered) // 2}, земля {len(scene['ground']) // 2}, лужи {len(puddles) // 2}, блики {len(reflect) // 2}, "
          f"табло {B}, ручьёв {len(streams)}, правок накладки {n_manual}")

    if a.preview:
        render_preview(scene, a.preview, W, H)


def render_preview(scene, path, W, H):
    cols, rows = scene["cols"], scene["rows"]
    S = 2
    cw, chh = W * S / cols, H * S / rows
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", int(chh * 0.78))
    img = Image.new("RGB", (W * S, H * S), (10, 13, 20))
    d = ImageDraw.Draw(img)
    for lay in scene["layers"]:
        c = tuple(int(lay["color"][i:i + 2], 16) for i in (1, 3, 5))
        c = tuple(int(v * lay["opacity"] * 0.9) for v in c)
        for y, line in enumerate(lay["text"].split("\n")):
            for x, chr_ in enumerate(line):
                if chr_ != " ":
                    d.text((x * cw, y * chh), chr_, font=font, fill=c)
    img.save(path)


if __name__ == "__main__":
    main()
