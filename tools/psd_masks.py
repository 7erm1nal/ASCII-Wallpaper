"""
psd_masks.py — загрузка масок из PSD (или из папки PNG) для gen_scene.py.

Протокол имён слоёв (плоские имена через точку; вложенные группы Photoshop склеиваются через ".",
поэтому группа "lamp" со слоем "core" == слой "lamp.core"):

Значение маски в точке:
  * слой с прозрачностью  -> значение = alpha (рисуйте любым цветом на прозрачном слое);
  * полностью непрозрачный слой -> значение = яркость (так удобно рисовать "depth" серым).
Видимость слоя (глазик) НЕ учитывается — скрывайте слои сколько угодно.
Слои вне списка (например "reference") игнорируются.
"""
import os
import numpy as np
from PIL import Image

# имя -> (тип, описание). Тип: bin — класс (порог 0.5), soft — интенсивность 0..1
SPEC = {
    "depth":            ("soft", "глубина: белое = близко, чёрное = далеко (серый, непрозрачный слой)"),
    "sky":              ("bin",  "открытое небо (без контуров-шума, дымка)"),
    "fog":              ("soft", "туман/дымка: интенсивность = альфа; дрейфует слоем"),
    "hill.mass":        ("bin",  "масса горы (без храма)"),
    "hill.church":      ("bin",  "храм (заливка блоками ░▒▓)"),
    "hill.church_edge": ("bin",  "линии-контуры храма: купол, крест, башня (рисовать толщиной >= 1 ячейка)"),
    "lamp.core":        ("bin",  "ядра света: маленькие яркие точки ламп (мерцают)"),
    "lamp.body":        ("bin",  "корпус/плафон фонаря"),
    "lamp.pole":        ("bin",  "столб и кронштейн (толстые линии)"),
    "lamp.glow":        ("soft", "ореол света: интенсивность = альфа"),
    "rain.edges":       ("bin",  "линии, где капли бьются: края крыш, карнизы, перила, подоконники, лавка"),
    "rain.drips":       ("bin",  "точки, откуда начинают капать капли (концы карнизов, трубы)"),
    "rain.sheltered":   ("bin",  "зона под крышей — дождя нет (остановка и т.п.)"),
    "ground.road":      ("bin",  "проезжая часть (брусчатка с перспективой)"),
    "ground.sidewalk":  ("bin",  "тротуары"),
    "ground.curb":      ("bin",  "бордюр: верхняя грань/линия (толщиной >= 1 ячейка)"),
    "ground.puddles":   ("bin",  "лужи: сюда чаще падают капли (круги на воде)"),
    "ground.reflect":   ("soft", "блики фонарей на мокрой дороге: интенсивность = альфа"),
    "water.flow":       ("soft", "ручьи: линия вдоль бордюра; НАПРАВЛЕНИЕ = градиент альфы, от бледного (начало) к насыщенному (конец течения)"),
    "veg.cypress":      ("bin",  "кипарисы"),
    "veg.foliage":      ("bin",  "густая листва, кусты, кроны"),
    "veg.ivy":          ("bin",  "плющ на стенах"),
    "arch.windows":     ("bin",  "окна: контуры, светящиеся — тёплой заливкой"),
    "arch.wires":       ("bin",  "провода (рисовать толстыми линиями)"),
    "busstop.board":    ("bin",  "табло остановки (прямоугольник)"),
    "ctrl.edge_keep":   ("bin",  "принудительно сделать линиями (контуры, которые обязаны остаться)"),
    "ctrl.edge_suppress": ("bin", "подавить контурный шум: здесь только тоновая заливка"),
}


def _walk(layers, prefix=""):
    for l in layers:
        name = (prefix + "." + l.name) if prefix else l.name
        if l.is_group():
            yield from _walk(l, name)
        else:
            yield name, l


def _layer_value(layer, canvas_wh):
    """Слой -> float32 (H, W) на холсте PSD."""
    W, H = canvas_wh
    out = np.zeros((H, W), np.float32)
    if not layer.has_pixels():
        return out
    im = layer.topil()
    if im is None:
        return out
    im = im.convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255
    alpha, lum = a[..., 3], a[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    val = lum if (alpha.min() > 0.999) else alpha          # непрозрачный слой -> яркость
    x0, y0 = layer.left, layer.top
    h, w = val.shape
    xs, ys = max(0, x0), max(0, y0)
    xe, ye = min(W, x0 + w), min(H, y0 + h)
    if xe > xs and ye > ys:
        out[ys:ye, xs:xe] = val[ys - y0:ye - y0, xs - x0:xe - x0]
    return out


def load_masks(path, target_wh=None):
    """
    Возвращает (masks, canvas_wh). masks: {имя: float32 (H, W) 0..1}; target_wh — привести к размеру (W, H).
    Если слой встречается несколько раз под одним именем — берётся максимум (объединение).
    """
    raw = {}
    if os.path.isdir(path):
        canvas = None
        for name in SPEC:
            f = os.path.join(path, name + ".png")
            if os.path.exists(f):
                im = Image.open(f).convert("RGBA")
                canvas = canvas or im.size
                a = np.asarray(im).astype(np.float32) / 255
                lum = a[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
                raw[name] = lum if a[..., 3].min() > 0.999 else a[..., 3]
        canvas = canvas or (1280, 720)
    else:
        from psd_tools import PSDImage
        psd = PSDImage.open(path)
        canvas = psd.size
        for name, layer in _walk(psd):
            if name in SPEC:
                v = _layer_value(layer, canvas)
                raw[name] = np.maximum(raw[name], v) if name in raw else v
    if target_wh and tuple(target_wh) != tuple(canvas):
        tw, th = target_wh
        for k, v in raw.items():
            raw[k] = np.asarray(Image.fromarray(v).resize((tw, th), Image.BILINEAR))
    return raw, canvas
