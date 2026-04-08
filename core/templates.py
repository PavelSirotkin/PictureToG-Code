"""Параметрические шаблоны: брелоки, таблички, звёзды, сердца."""

import math

# ─── Константы шаблонов ─────────────────────────────────────────────────────

# Брелок прямоугольный
KEYCHAIN_RECT_CORNER_RATIO = 0.12      # Относительный радиус скругления
KEYCHAIN_RECT_HOLE_RATIO = 0.08        # Относительный радиус отверстия
KEYCHAIN_RECT_HOLE_OFFSET = 1.5        # Отступ отверстия от края (мм)

# Брелок круглый
KEYCHAIN_CIRCLE_HOLE_RATIO = 0.15      # Относительный радиус отверстия
KEYCHAIN_CIRCLE_HOLE_OFFSET_RATIO = 0.65  # Смещение отверстия от центра

# Табличка с рамкой
FRAME_INSET_RATIO = 0.12               # Отступ рамки от края

# Звезда
STAR_INNER_RADIUS_RATIO = 0.38         # Отношение внутреннего радиуса к внешнему
STAR_POINTS = 5                        # Количество лучей

# Сердце
HEART_POINTS = 100                     # Количество точек аппроксимации

# Общие
CIRCLE_SEGMENTS = 64                   # Количество сегментов окружения
ARC_SEGMENTS = 8                       # Количество сегментов дуги скругления

TEMPLATES = [
    "(нет)",
    "Брелок прямоугольный",
    "Брелок круглый",
    "Табличка с рамкой",
    "Звезда",
    "Сердце",
]


def _circle_pts(cx, cy, r, n=None):
    if n is None:
        n = CIRCLE_SEGMENTS
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _rounded_rect_pts(w, h, r, n_arc=None):
    if n_arc is None:
        n_arc = ARC_SEGMENTS
    r = min(r, w / 2, h / 2)
    pts = []
    corners = [(w - r, h - r, 0), (r, h - r, math.pi / 2),
               (r, r, math.pi), (w - r, r, 3 * math.pi / 2)]
    for cx, cy, start_a in corners:
        for i in range(n_arc + 1):
            a = start_a + (math.pi / 2) * i / n_arc
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    return pts


def _template_rect_keychain(w, h):
    r = min(w, h) * KEYCHAIN_RECT_CORNER_RATIO
    outer = _rounded_rect_pts(w, h, r)
    hole_r = min(w, h) * KEYCHAIN_RECT_HOLE_RATIO
    hole_cx = w / 2
    hole_cy = h - r - hole_r - KEYCHAIN_RECT_HOLE_OFFSET
    hole = _circle_pts(hole_cx, hole_cy, hole_r)
    return [outer, hole]


def _template_circle_keychain(w, h):
    r = min(w, h) / 2
    cx, cy = w / 2, h / 2
    outer = _circle_pts(cx, cy, r)
    hole_r = r * KEYCHAIN_CIRCLE_HOLE_RATIO
    hole = _circle_pts(cx, cy + r * KEYCHAIN_CIRCLE_HOLE_OFFSET_RATIO, hole_r)
    return [outer, hole]


def _template_frame(w, h):
    inset = min(w, h) * FRAME_INSET_RATIO
    outer = [(0, 0), (w, 0), (w, h), (0, h), (0, 0)]
    inner = [(inset, inset), (w - inset, inset), (w - inset, h - inset),
             (inset, h - inset), (inset, inset)]
    return [outer, inner]


def _template_star(w, h):
    cx, cy = w / 2, h / 2
    R = min(w, h) / 2
    r = R * STAR_INNER_RADIUS_RATIO
    pts = []
    num_points = STAR_POINTS * 2
    for i in range(num_points):
        a = math.pi / 2 + 2 * math.pi * i / num_points
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    pts.append(pts[0])
    return [pts]


def _template_heart(w, h):
    pts = []
    n = HEART_POINTS
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x, y))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    sx = w / (max_x - min_x) if max_x != min_x else 1
    sy = h / (max_y - min_y) if max_y != min_y else 1
    s = min(sx, sy)
    scaled = [((p[0] - min_x) * s, (p[1] - min_y) * s) for p in pts]
    scaled.append(scaled[0])
    return [scaled]


def generate_template(name, width, height):
    """Генерирует контур параметрического шаблона.
    
    Args:
        name: Имя шаблона
        width: Ширина (мм)
        height: Высота (мм)
    
    Returns:
        tuple: (chains, width, height)
    
    Raises:
        ValueError: При некорректных размерах
    """
    # Валидация размеров
    if width <= 0:
        raise ValueError(f"Ширина должна быть > 0, получено: {width}")
    if height <= 0:
        raise ValueError(f"Высота должна быть > 0, получено: {height}")
    
    generators = {
        "Брелок прямоугольный": _template_rect_keychain,
        "Брелок круглый": _template_circle_keychain,
        "Табличка с рамкой": _template_frame,
        "Звезда": _template_star,
        "Сердце": _template_heart,
    }
    gen = generators.get(name)
    if gen is None:
        return [], 0, 0
    chains = gen(width, height)
    return chains, width, height
