#!/usr/bin/env python3
"""
compare_styles.py — один и тот же фрагмент референса в четырёх стилях символов, в РЕАЛЬНОМ масштабе
экрана 1920x1080 (ячейка 6x12 px). Нужен, чтобы выбрать стиль глазами.

    python3 compare_styles.py reference.jpg --crop 640 70 960 330 --out /tmp/cmp

Стили:  ascii   — рампа + направленные края (как сейчас)
        blocks  — квадранты ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█ (2x2 пикселя на ячейку, ошибка диффундирует)
        braille — U+2800.. (2x4 точки на ячейку), шрифт FreeMono
        hybrid  — ASCII-символы на сильных краях, Брайль в тональных массах
"""
import argparse, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BRAILLE_FONT = "/usr/share/fonts/truetype/freefont/FreeMono.ttf"
CELL_W, CELL_H, FONT_PX = 6, 12, 10
BG_TOP, BG_BOT = (13, 17, 25), (7, 9, 14)
RAMP = " .:-=+*#%@"
QUAD = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"
L = np.array([0.2126, 0.7152, 0.0722], np.float32)


def fs_dither(v):
    """Floyd–Steinberg до 1 бита. v в 0..1."""
    v = v.copy()
    h, w = v.shape
    out = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            old = v[y, x]
            new = 1.0 if old >= 0.5 else 0.0
            out[y, x] = new > 0
            e = old - new
            if x + 1 < w: v[y, x + 1] += e * 7 / 16
            if y + 1 < h:
                if x > 0: v[y + 1, x - 1] += e * 3 / 16
                v[y + 1, x] += e * 5 / 16
                if x + 1 < w: v[y + 1, x + 1] += e * 1 / 16
    return out


def lift(c, gain=1.0):
    """Приподнять яркость цвета для читаемости на тёмном фоне; gain — авто-экспозиция."""
    v = max(float(c.max()), 1e-3)
    k = min(1.0, 0.32 + 0.90 * v ** 0.62) / v * gain
    return tuple(int(255 * min(1, x * k)) for x in c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--crop", type=int, nargs=4, default=[640, 70, 960, 330], help="x0 y0 x1 y1 в пикселях референса")
    ap.add_argument("--out", default="/tmp/cmp")
    ap.add_argument("--edge", type=float, default=0.55)
    ap.add_argument("--gamma", type=float, default=0.6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    im = Image.open(a.image).convert("RGB")
    W, H = im.size
    s = 1920 / W                                   # масштаб референса -> экран
    x0, y0, x1, y1 = a.crop
    crop = im.crop((x0, y0, x1, y1))
    cols = round((x1 - x0) * s / CELL_W)
    rows = round((y1 - y0) * s / CELL_H)
    pw, ph = cols * CELL_W, rows * CELL_H

    def sample(nx, ny):
        return np.asarray(crop.resize((nx, ny), Image.LANCZOS)).astype(np.float32) / 255

    def tone(arr):
        lum = arr @ L
        lo, hi = np.percentile(lum, 3), np.percentile(lum, 99.7)
        return np.clip((lum - lo) / (hi - lo + 1e-6), 0, 1) ** a.gamma

    # ---- общие величины на уровне ячейки ----
    hi8 = sample(cols * 4, rows * 8)
    cell = hi8.reshape(rows, 8, cols, 4, 3).mean((1, 3))
    lum_hi = hi8 @ L
    sm = np.asarray(Image.fromarray((lum_hi * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32) / 255
    gy, gx = np.gradient(sm)
    cm = lambda v: v.reshape(rows, 8, cols, 4).mean((1, 3))
    Jxx, Jyy, Jxy = cm(gx * gx), cm(gy * gy), cm(gx * gy)
    E = np.sqrt(Jxx + Jyy)
    E = np.clip(E / (np.percentile(E, 97) + 1e-6), 0, 1)
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-9)
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)
    phi = np.degrees(np.arctan2(-np.cos(theta), -np.sin(theta))) % 180
    edge_ch = np.full((rows, cols), "-", dtype="<U1")
    edge_ch[(phi >= 25) & (phi < 70)] = "/"
    edge_ch[(phi >= 70) & (phi < 110)] = "|"
    edge_ch[(phi >= 110) & (phi < 155)] = "\\"
    is_edge = (E > a.edge) & (coh > 0.55)
    t = tone(cell)

    # ---- стиль 1: ASCII ----
    Eadj = np.clip((E - 0.22) / 0.78, 0, 1) ** 1.3
    score = np.clip(0.10 * t + Eadj, 0, 1)
    idx = np.rint(score * (len(RAMP) - 1)).astype(int)
    ascii_g = np.array([[RAMP[i] for i in r] for r in idx], dtype="<U1")
    ascii_g[is_edge] = edge_ch[is_edge]
    ascii_g[(score < 0.10) & ~is_edge] = " "

    # ---- тон на субпикселях (с резкостью), общий для дизеринга ----
    def dither_bits(nx, ny):
        arr = sample(nx, ny)
        img = Image.fromarray((arr * 255).astype(np.uint8)).filter(ImageFilter.UnsharpMask(radius=1.6, percent=160, threshold=2))
        arr = np.asarray(img).astype(np.float32) / 255
        return fs_dither(tone(arr))

    # ---- стиль 2: квадранты ----
    qb = dither_bits(cols * 2, rows * 2).reshape(rows, 2, cols, 2)
    q_idx = qb[:, 0, :, 0] * 1 + qb[:, 0, :, 1] * 2 + qb[:, 1, :, 0] * 4 + qb[:, 1, :, 1] * 8
    quad_g = np.array([[QUAD[i] for i in r] for r in q_idx], dtype="<U1")

    # ---- стиль 3: Брайль ----
    bb = dither_bits(cols * 2, rows * 4).reshape(rows, 4, cols, 2)
    weights = {(0, 0): 1, (1, 0): 2, (2, 0): 4, (0, 1): 8, (1, 1): 16, (2, 1): 32, (3, 0): 64, (3, 1): 128}
    bits = np.zeros((rows, cols), int)
    for (dy, dx), w_ in weights.items():
        bits += bb[:, dy, :, dx] * w_
    braille_g = np.array([[chr(0x2800 + b) if b else " " for b in r] for r in bits], dtype="<U1")

    # ---- стиль 4: гибрид ----
    hyb_g = braille_g.copy()
    hyb_g[is_edge] = edge_ch[is_edge]

    # ---- отрисовка ----
    f_mono = ImageFont.truetype(MONO, FONT_PX)
    f_br = ImageFont.truetype(BRAILLE_FONT, FONT_PX)

    def render_once(grid, gain):
        img = Image.new("RGB", (pw, ph))
        d = ImageDraw.Draw(img)
        for y in range(ph):
            k = y / max(ph - 1, 1)
            d.line([(0, y), (pw, y)], fill=tuple(int(BG_TOP[i] * (1 - k) + BG_BOT[i] * k) for i in range(3)))
        for r in range(rows):
            for c in range(cols):
                ch = grid[r, c]
                if ch == " ":
                    continue
                is_br = 0x2800 <= ord(ch) <= 0x28FF
                font = f_br if is_br else f_mono
                d.text((c * CELL_W, r * CELL_H), ch, font=font, fill=lift(cell[r, c], gain))
        return img

    TARGET = 0.095          # средняя яркость кадра (0..1): одинаковая "экспозиция" для честного сравнения

    def mean_lum(img):
        return float((np.asarray(img).astype(np.float32) / 255 @ L).mean())

    def render(grid):
        gain = 1.0
        for _ in range(4):
            img = render_once(grid, gain)
            m = mean_lum(img)
            if abs(m - TARGET) / TARGET < 0.04:
                break
            gain *= (TARGET - 0.045) / max(m - 0.045, 1e-3)     # 0.045 — средняя яркость фона
            gain = float(np.clip(gain, 0.15, 6.0))
        print(f"  gain={gain:.2f} mean={mean_lum(img):.3f}")
        return img

    styles = [("ascii", "ASCII (as now)", ascii_g), ("blocks", "Quadrant blocks", quad_g),
              ("braille", "Braille (FreeMono)", braille_g), ("hybrid", "Hybrid: ASCII edges + Braille", hyb_g)]
    imgs = []
    for key, name, g in styles:
        im_ = render(g)
        imgs.append((name, im_))
        im_.save(os.path.join(a.out, key + ".png"))
        im_.resize((pw * 2, ph * 2), Image.NEAREST).save(os.path.join(a.out, key + "_x2.png"))

    # контактный лист 2x2 в реальном масштабе
    pad, lab = 10, 22
    sheet = Image.new("RGB", (pw * 2 + pad * 3, (ph + lab) * 2 + pad * 3), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    lf = ImageFont.truetype(MONO, 13)
    for i, (name, im_) in enumerate(imgs):
        cx, cy = pad + (i % 2) * (pw + pad), pad + (i // 2) * (ph + lab + pad)
        d.text((cx, cy), name, font=lf, fill=(220, 220, 220))
        sheet.paste(im_, (cx, cy + lab))
    sheet.save(os.path.join(a.out, "sheet.png"))

    # исходник для сравнения
    crop.resize((pw, ph), Image.LANCZOS).save(os.path.join(a.out, "reference_crop.png"))
    print(f"fragment {cols}x{rows} cells, {pw}x{ph}px at 1920x1080 scale -> {a.out}")


if __name__ == "__main__":
    main()
