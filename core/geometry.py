"""Геометрические операции: упрощение, офсет, сортировка, масштабирование, мостики."""

import math

try:
    from shapely.geometry import LineString
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


# ─────────────────────────── Упрощение Рамера-Дугласа-Пекера ────────────────

def _rdp(points, epsilon):
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    dist_sq = dx * dx + dy * dy
    max_dist, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if dist_sq == 0:
            d = math.hypot(px - start[0], py - start[1])
        else:
            t = ((px - start[0]) * dx + (py - start[1]) * dy) / dist_sq
            t = max(0.0, min(1.0, t))
            d = math.hypot(px - (start[0] + t * dx), py - (start[1] + t * dy))
        if d > max_dist:
            max_dist, idx = d, i
    if max_dist > epsilon:
        left = _rdp(points[:idx + 1], epsilon)
        right = _rdp(points[idx:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_chain(chain, epsilon):
    """Упрощает контур алгоритмом Рамера-Дугласа-Пекера.
    
    Args:
        chain: Список точек [(x,y), ...]
        epsilon: Допуск упрощения
    
    Returns:
        list: Упрощенный контур
    """
    if epsilon < 0:
        raise ValueError(f"Допуск упрощения должен быть >= 0, получено: {epsilon}")
    if epsilon <= 0 or len(chain) < 3:
        return chain
    return _rdp(chain, epsilon)


# ─────────────────────────── Офсет (tool compensation) ──────────────────────

def offset_chain(chain, offset):
    """Смещает контур на указанное расстояние (компенсация инструмента).
    
    Args:
        chain: Список точек [(x,y), ...]
        offset: Смещение (отрицательное = внутрь, положительное = наружу)
    
    Returns:
        list: Список смещенных контуров
    """
    if not HAS_SHAPELY or offset == 0:
        return [chain]
    try:
        ls = LineString(chain)
        result = ls.offset_curve(offset)
        if result is None or result.is_empty:
            return [chain]
        if result.geom_type == "LineString":
            return [list(result.coords)]
        elif result.geom_type == "MultiLineString":
            return [list(g.coords) for g in result.geoms]
    except Exception:
        pass
    return [chain]


# ─────────────────────────── Масштабирование ────────────────────────────────

def get_bounds(chains):
    all_pts = [pt for c in chains for pt in c]
    if not all_pts:
        return (0, 0, 0, 0)
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    return (min(xs), min(ys), max(xs), max(ys))


def scale_chains(chains, target_w=None, target_h=None, keep_aspect=True):
    """Масштабирует контуры к целевым размерам.
    
    Args:
        chains: Список контуров
        target_w: Целевая ширина (мм)
        target_h: Целевая высота (мм)
        keep_aspect: Сохранять ли пропорции
    
    Returns:
        list: Масштабированные контуры
    """
    if not chains or (target_w is None and target_h is None):
        return chains
    
    # Валидация размеров
    if target_w is not None and target_w <= 0:
        raise ValueError(f"Целевая ширина должна быть > 0, получено: {target_w}")
    if target_h is not None and target_h <= 0:
        raise ValueError(f"Целевая высота должна быть > 0, получено: {target_h}")
    
    min_x, min_y, max_x, max_y = get_bounds(chains)
    src_w = max_x - min_x
    src_h = max_y - min_y
    if src_w == 0 or src_h == 0:
        return chains
    if target_w is not None and target_h is not None:
        sx = target_w / src_w
        sy = target_h / src_h
        if keep_aspect:
            sx = sy = min(sx, sy)
    elif target_w is not None:
        sx = sy = target_w / src_w
    else:
        sx = sy = target_h / src_h
    result = []
    for chain in chains:
        scaled = [((x - min_x) * sx, (y - min_y) * sy) for x, y in chain]
        result.append(scaled)
    return result


# ─────────────────────────── Сортировка контуров (Nearest Neighbor) ─────────

def sort_chains_nearest(chains):
    if len(chains) <= 1:
        return chains
    remaining = list(range(len(chains)))
    ordered = [remaining.pop(0)]
    while remaining:
        last = chains[ordered[-1]][-1]
        best_idx = 0
        best_dist = float("inf")
        for i, ri in enumerate(remaining):
            sx, sy = chains[ri][0]
            d = (sx - last[0]) ** 2 + (sy - last[1]) ** 2
            if d < best_dist:
                best_dist = d
                best_idx = i
        ordered.append(remaining.pop(best_idx))
    return [chains[i] for i in ordered]


# ─────────────────────────── Мостики (tabs) ─────────────────────────────────

def _chain_length(chain):
    return sum(math.hypot(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1])
               for i in range(len(chain) - 1))


def insert_bridges(chain, bridge_size, num_bridges=2):
    """Вставляет мостики (perемычки) в контур.
    
    Args:
        chain: Список точек [(x,y), ...]
        bridge_size: Размер мостика (мм)
        num_bridges: Количество мостиков
    
    Returns:
        list: Список сегментов [(segment, is_bridge), ...]
    
    Raises:
        ValueError: При некорректных параметрах
    """
    if bridge_size <= 0:
        raise ValueError(f"Размер мостика должен быть > 0, получено: {bridge_size}")
    if num_bridges < 1:
        raise ValueError(f"Количество мостиков должно быть >= 1, получено: {num_bridges}")
    if len(chain) < 2:
        raise ValueError("Контур должен иметь минимум 2 точки")
    
    total = _chain_length(chain)
    if total < bridge_size * num_bridges * 2 or bridge_size <= 0:
        return [(chain, False)]

    interval = total / num_bridges
    bridge_starts = [interval * i + interval * 0.5 for i in range(num_bridges)]

    segments = []
    cur_dist = 0.0
    seg_pts = [chain[0]]
    bridge_idx = 0
    in_bridge = False

    for i in range(len(chain) - 1):
        p0, p1 = chain[i], chain[i + 1]
        step = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if step == 0:
            continue

        events = []
        if bridge_idx < len(bridge_starts):
            bs = bridge_starts[bridge_idx]
            be = bs + bridge_size
            for dist_event in [bs, be]:
                d_local = dist_event - cur_dist
                if 0 < d_local < step:
                    t = d_local / step
                    events.append((t, dist_event))

        events.sort()
        for (t, dist_event) in events:
            interp = (p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1]))
            seg_pts.append(interp)
            segments.append((seg_pts, in_bridge))
            seg_pts = [interp]
            in_bridge = not in_bridge
            if not in_bridge:
                bridge_idx += 1

        seg_pts.append(p1)
        cur_dist += step

    if len(seg_pts) >= 2:
        segments.append((seg_pts, in_bridge))

    return segments
