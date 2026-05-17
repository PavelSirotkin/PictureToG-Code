"""Обработка изображений: извлечение контуров и загрузка карты высот."""

import cv2
import numpy as np
import os
import math

from core.geometry import (
    chaikin_smooth, resample_by_length, simplify_chain, _chain_length,
)

# 8-связные смещения соседей (для операций над скелетом)
_NBR_OFFSETS = [
    (-1, -1), (0, -1), (1, -1),
    (-1,  0),          (1,  0),
    (-1,  1), (0,  1), (1,  1),
]


def extract_contours(image_path, threshold=128, invert=True,
                     blur_size=3, min_area=10, epsilon_factor=0.001,
                     smooth_passes=0, resample_step=0.0):
    """
    Загружает растровое изображение и возвращает список полилиний
    [(x,y), ...] в пиксельных координатах (Y — вверх).

    Конвейер обработки контура:
      1. Gaussian blur + бинаризация
      2. cv2.findContours
      3. Фильтрация по площади
      4a. Если smooth_passes > 0 или resample_step > 0:
            – Chaikin-сглаживание (smooth_passes проходов)
            – Равномерный ре-сэмплинг (если resample_step > 0)
              ИЛИ RDP-прореживание (если epsilon_factor > 0)
      4b. Иначе: cv2.approxPolyDP (исходное поведение)

    Args:
        image_path: Путь к изображению
        threshold: Порог бинаризации (0-255)
        invert: Инвертировать ли изображение
        blur_size: Размер ядра размытия
        min_area: Минимальная площадь контура
        epsilon_factor: Коэффициент упрощения контура (RDP)
        smooth_passes: Число проходов Chaikin (0 = выкл., рек. 3-4)
        resample_step: Шаг ре-сэмплинга в пикс. (0 = выкл.; если > 0 — заменяет RDP)

    Returns:
        tuple: (chains, width, height)

    Raises:
        FileNotFoundError: Если файл не найден
        RuntimeError: Если не удалось загрузить изображение
        ValueError: При некорректных параметрах
    """
    # Проверка существования файла
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл не найден: {image_path}")
    
    # Валидация параметров
    if not (0 <= threshold <= 255):
        raise ValueError(f"Порог должен быть в диапазоне [0, 255], получено: {threshold}")
    if blur_size < 0:
        raise ValueError(f"Размер размытия должен быть >= 0, получено: {blur_size}")
    if min_area < 0:
        raise ValueError(f"Минимальная площадь должна быть >= 0, получено: {min_area}")
    if epsilon_factor < 0:
        raise ValueError(f"Коэффициент упрощения должен быть >= 0, получено: {epsilon_factor}")
    if not isinstance(smooth_passes, int) or smooth_passes < 0:
        raise ValueError(f"Число проходов Chaikin должно быть целым >= 0, получено: {smooth_passes}")
    if resample_step < 0:
        raise ValueError(f"Шаг ре-сэмплинга должен быть >= 0, получено: {resample_step}")
    
    # Используем np.fromfile + cv2.imdecode для поддержки кириллицы в пути
    img_data = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Не удалось загрузить изображение: {image_path}")

    h, w = img.shape[:2]
    if h == 0 or w == 0:
        raise RuntimeError(f"Изображение имеет нулевые размеры: {w}x{h}")

    if blur_size > 0:
        k = blur_size if blur_size % 2 == 1 else blur_size + 1
        img = cv2.GaussianBlur(img, (k, k), 0)

    if invert:
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
    else:
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    chains = []
    use_smoothing = smooth_passes > 0 or resample_step > 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        if use_smoothing:
            # Работаем с плотным пиксельным контуром — сглаживаем фактическую форму,
            # а не уже упрощённую. Порядок: Chaikin → ре-сэмплинг/RDP.
            pts = [(float(p[0][0]), float(h - p[0][1])) for p in cnt]
            if len(pts) < 3:
                continue
            pts.append(pts[0])  # замкнуть

            if smooth_passes > 0:
                pts = chaikin_smooth(pts, smooth_passes, closed=True)

            if resample_step > 0:
                pts = resample_by_length(pts, resample_step, closed=True)
            elif epsilon_factor > 0:
                peri = sum(
                    math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                    for i in range(len(pts) - 1)
                )
                pts = simplify_chain(pts, epsilon_factor * peri)
        else:
            # Исходный путь: cv2.approxPolyDP
            peri = cv2.arcLength(cnt, True)
            eps = epsilon_factor * peri
            approx = cv2.approxPolyDP(cnt, eps, True)
            pts = []
            for p in approx:
                pts.append((float(p[0][0]), float(h - p[0][1])))
            if len(pts) >= 3:
                pts.append(pts[0])

        if len(pts) >= 2:
            chains.append(pts)

    return chains, w, h


def load_heightmap(image_path, blur_size=3):
    """Загружает изображение как карту высот (grayscale).
    
    Args:
        image_path: Путь к изображению
        blur_size: Размер ядра размытия
    
    Returns:
        tuple: (heightmap, width, height)
    
    Raises:
        FileNotFoundError: Если файл не найден
        RuntimeError: Если не удалось загрузить изображение
        ValueError: При некорректных параметрах
    """
    # Проверка существования файла
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл не найден: {image_path}")
    
    # Валидация параметров
    if blur_size < 0:
        raise ValueError(f"Размер размытия должен быть >= 0, получено: {blur_size}")
    
    # Используем np.fromfile + cv2.imdecode для поддержки кириллицы в пути
    img_data = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Не удалось загрузить изображение: {image_path}")
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        raise RuntimeError(f"Изображение имеет нулевые размеры: {w}x{h}")
    if blur_size > 0:
        k = blur_size if blur_size % 2 == 1 else blur_size + 1
        img = cv2.GaussianBlur(img, (k, k), 0)
    return img, w, h


# ─────────────────────────── Средняя линия (скелет) ─────────────────────────

def _zhang_suen_thinning(binary):
    """Утончение бинарного изображения алгоритмом Чжана-Суэня.

    Итеративно «обгрызает» границу фигуры, пока не останется скелет
    толщиной в 1 пиксель, сохраняя связность.

    Args:
        binary: 2D numpy array (фигура — значения > 127).

    Returns:
        2D numpy array uint8: 1 = пиксель скелета, 0 = фон.
    """
    img = (binary > 127).astype(np.uint8)
    h, w = img.shape
    if h < 3 or w < 3:
        return img

    def _sub_iteration(im, pass_no):
        p = np.zeros((h + 2, w + 2), dtype=np.uint8)
        p[1:-1, 1:-1] = im
        p2 = p[0:-2, 1:-1]
        p3 = p[0:-2, 2:]
        p4 = p[1:-1, 2:]
        p5 = p[2:, 2:]
        p6 = p[2:, 1:-1]
        p7 = p[2:, 0:-2]
        p8 = p[1:-1, 0:-2]
        p9 = p[0:-2, 0:-2]
        b = (p2.astype(np.int32) + p3 + p4 + p5 + p6 + p7 + p8 + p9)
        seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
        a = np.zeros((h, w), dtype=np.int32)
        for k in range(8):
            a += ((seq[k] == 0) & (seq[k + 1] == 1)).astype(np.int32)
        cond = (im == 1) & (b >= 2) & (b <= 6) & (a == 1)
        if pass_no == 0:
            cond &= (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
        else:
            cond &= (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
        # Границы изображения не трогаем (как в эталонной реализации)
        cond[0, :] = False
        cond[-1, :] = False
        cond[:, 0] = False
        cond[:, -1] = False
        return cond

    for _ in range(500):
        changed = False
        m0 = _sub_iteration(img, 0)
        if m0.any():
            img[m0] = 0
            changed = True
        m1 = _sub_iteration(img, 1)
        if m1.any():
            img[m1] = 0
            changed = True
        if not changed:
            break
    return img


def _skel_fg_neighbors(skel, x, y, w, h):
    """Список 8-связных соседей-пикселей скелета вокруг (x, y)."""
    r = []
    for dx, dy in _NBR_OFFSETS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and skel[ny, nx]:
            r.append((nx, ny))
    return r


def _clean_skeleton(skel):
    """Схлопывает диагональные «лесенки» шириной 2 px до ширины 1 px.

    Пиксель удаляется, если есть сосед N, к которому примыкают все
    остальные соседи пикселя — тогда N берёт на себя связность.
    Концевые пиксели (1 сосед) не трогаются. Скелет мутируется на месте.
    """
    h, w = skel.shape

    def adjacent(a, b):
        return (a != b) and abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1

    changed = True
    guard = 0
    while changed and guard < 60:
        guard += 1
        changed = False
        ys, xs = np.nonzero(skel)
        for y, x in zip(ys.tolist(), xs.tolist()):
            if not skel[y, x]:
                continue
            nb = _skel_fg_neighbors(skel, x, y, w, h)
            if len(nb) < 2:
                continue
            for n in nb:
                dominated = True
                for m in nb:
                    if m == n:
                        continue
                    if not adjacent(m, n):
                        dominated = False
                        break
                if dominated:
                    skel[y, x] = 0
                    changed = True
                    break


def _trace_skeleton(skel):
    """Трассировка скелета в набор полилиний (пиксельные координаты).

    Идёт от узлов (концы — степень 1, развилки — степень >=3) вдоль
    цепочек пикселей степени 2; оставшиеся замкнутые петли — отдельно.
    """
    h, w = skel.shape
    pix = []
    degree = {}
    ys, xs = np.nonzero(skel)
    for y, x in zip(ys.tolist(), xs.tolist()):
        degree[(x, y)] = len(_skel_fg_neighbors(skel, x, y, w, h))
        pix.append((x, y))

    used_edge = set()

    def ekey(a, b):
        ka = a[1] * w + a[0]
        kb = b[1] * w + b[0]
        return (ka, kb) if ka < kb else (kb, ka)

    def walk(a, b):
        path = [a, b]
        used_edge.add(ekey(a, b))
        prev, cur = a, b
        while degree.get(cur, 0) == 2:
            nxt = None
            for n in _skel_fg_neighbors(skel, cur[0], cur[1], w, h):
                if n == prev:
                    continue
                nxt = n
            if nxt is None:
                break
            k = ekey(cur, nxt)
            if k in used_edge:
                break
            used_edge.add(k)
            path.append(nxt)
            prev, cur = cur, nxt
        return path

    chains = []
    # 1. Ветви, начинающиеся в узлах (концы и развилки)
    for (x, y) in pix:
        if degree[(x, y)] == 2:
            continue
        for n in _skel_fg_neighbors(skel, x, y, w, h):
            if ekey((x, y), n) in used_edge:
                continue
            chains.append(walk((x, y), n))
    # 2. Оставшиеся замкнутые петли (все пиксели степени 2)
    for (x, y) in pix:
        for n in _skel_fg_neighbors(skel, x, y, w, h):
            if ekey((x, y), n) in used_edge:
                continue
            path = walk((x, y), n)
            if len(path) > 2:
                path.append((x, y))
            chains.append(path)
    return chains


def _prune_skeleton_spurs(skel, max_spur_len=14):
    """Удаляет короткие «заусенцы» — тупиковые веточки на развилках.

    Заусенец = сегмент с одним концом-тупиком (степень 1) и одним
    концом-развилкой (степень >=3), короче max_spur_len. Скелет мутируется.
    """
    h, w = skel.shape
    for _ in range(30):
        deg_map = {}
        ys, xs = np.nonzero(skel)
        for y, x in zip(ys.tolist(), xs.tolist()):
            deg_map[(x, y)] = len(_skel_fg_neighbors(skel, x, y, w, h))

        chains = _trace_skeleton(skel)
        to_remove = []
        for ch in chains:
            if len(ch) < 2:
                continue
            a, b = ch[0], ch[-1]
            da = deg_map.get(a, 0)
            db = deg_map.get(b, 0)
            is_spur = (da == 1 and db >= 3) or (db == 1 and da >= 3)
            if not is_spur:
                continue
            if _chain_length(ch) >= max_spur_len:
                continue
            for p in ch:
                if deg_map.get(p, 0) >= 3:
                    continue
                to_remove.append(p)

        if not to_remove:
            break
        for (x, y) in to_remove:
            skel[y, x] = 0


def _stitch_chains(chains):
    """Сшивает сегменты скелета в длинные непрерывные линии.

    В каждом узле сегменты попарно соединяются по принципу «наиболее
    прямого продолжения» (сегменты, идущие почти навстречу).
    """
    n = len(chains)
    if n < 2:
        return chains

    def key(p):
        return (round(p[0]), round(p[1]))

    def sid(ci, end):
        return ci * 2 + end

    def dir_away(chain, end):
        m = len(chain)
        span = min(m - 1, 5)
        a = chain[0] if end == 0 else chain[m - 1]
        b = chain[span] if end == 0 else chain[m - 1 - span]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        return (dx / length, dy / length)

    nodes = {}
    for ci in range(n):
        ch = chains[ci]
        if len(ch) < 2:
            continue
        for end in (0, 1):
            p = ch[0] if end == 0 else ch[-1]
            nodes.setdefault(key(p), []).append((ci, end))

    partner = [-1] * (n * 2)
    for stubs in nodes.values():
        if len(stubs) < 2:
            continue
        dirs = [dir_away(chains[ci], end) for (ci, end) in stubs]
        pairs = []
        for i in range(len(stubs)):
            for j in range(i + 1, len(stubs)):
                if stubs[i][0] == stubs[j][0]:
                    continue
                dot = dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1]
                pairs.append((dot, i, j))
        # dot ~ -1 → сегменты идут навстречу (прямое продолжение)
        pairs.sort(key=lambda t: t[0])
        taken = set()
        for (dot, i, j) in pairs:
            if i in taken or j in taken:
                continue
            if dot > 0.5:  # слишком резкий загиб — не сшивать
                continue
            si, sj = stubs[i], stubs[j]
            if partner[sid(*si)] != -1 or partner[sid(*sj)] != -1:
                continue
            partner[sid(*si)] = sid(*sj)
            partner[sid(*sj)] = sid(*si)
            taken.add(i)
            taken.add(j)

    visited = [False] * n
    result = []

    def build_from(ci, entry_end):
        poly = []
        first = True
        while not visited[ci]:
            visited[ci] = True
            ch = chains[ci]
            ordered = ch if entry_end == 0 else list(reversed(ch))
            if first:
                poly.extend(ordered)
                first = False
            else:
                poly.extend(ordered[1:])
            exit_end = 1 - entry_end
            np_ = partner[sid(ci, exit_end)]
            if np_ == -1:
                break
            ci = np_ >> 1
            entry_end = np_ & 1
        return poly

    # 1. Начинаем со «свободных» концов (без партнёра)
    for ci in range(n):
        if visited[ci] or len(chains[ci]) < 2:
            continue
        for end in (0, 1):
            if partner[sid(ci, end)] == -1:
                result.append(build_from(ci, end))
                break
    # 2. Оставшиеся — замкнутые петли
    for ci in range(n):
        if visited[ci] or len(chains[ci]) < 2:
            continue
        result.append(build_from(ci, 0))
    return result


def extract_centerlines(image_path, threshold=128, invert=True, blur_size=3,
                        smooth_passes=3, resample_step=0.0, min_branch_len=8):
    """Извлекает «среднюю линию» фигур — скелет бинарного изображения.

    В отличие от extract_contours (обводка фигуры снаружи), здесь
    генерируется одиночная линия по центру штриха. Подходит для
    гравировки рукописного текста, где толстый штрих нужно пройти
    фрезой один раз посередине.

    Конвейер:
      1. Gaussian blur + бинаризация
      2. Утончение Чжана-Суэня → скелет толщиной 1 px
      3. Чистка скелета (схлопывание диагональных лесенок)
      4. Отсев коротких заусенцев
      5. Трассировка скелета в сегменты + сшивка в длинные линии
      6. Chaikin-сглаживание + равномерный ре-сэмплинг (открытые линии)

    Args:
        image_path: Путь к изображению
        threshold: Порог бинаризации (0-255)
        invert: Инвертировать ли изображение
        blur_size: Размер ядра размытия
        smooth_passes: Число проходов Chaikin (0 = выкл.)
        resample_step: Шаг ре-сэмплинга в пикс. (0 = выкл.)
        min_branch_len: Мин. длина линии в пикс. (отсев отростков)

    Returns:
        tuple: (chains, width, height) — chains это открытые полилинии,
               Y уже перевёрнут (вверх).

    Raises:
        FileNotFoundError: Если файл не найден
        RuntimeError: Если не удалось загрузить изображение
        ValueError: При некорректных параметрах
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл не найден: {image_path}")
    if not (0 <= threshold <= 255):
        raise ValueError(f"Порог должен быть в диапазоне [0, 255], получено: {threshold}")
    if blur_size < 0:
        raise ValueError(f"Размер размытия должен быть >= 0, получено: {blur_size}")
    if not isinstance(smooth_passes, int) or smooth_passes < 0:
        raise ValueError(f"Число проходов Chaikin должно быть целым >= 0, получено: {smooth_passes}")
    if resample_step < 0:
        raise ValueError(f"Шаг ре-сэмплинга должен быть >= 0, получено: {resample_step}")

    img_data = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Не удалось загрузить изображение: {image_path}")

    h, w = img.shape[:2]
    if h == 0 or w == 0:
        raise RuntimeError(f"Изображение имеет нулевые размеры: {w}x{h}")

    if blur_size > 0:
        k = blur_size if blur_size % 2 == 1 else blur_size + 1
        img = cv2.GaussianBlur(img, (k, k), 0)

    if invert:
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
    else:
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

    skel = _zhang_suen_thinning(binary)
    _clean_skeleton(skel)
    _prune_skeleton_spurs(skel, 14)
    chains = _trace_skeleton(skel)
    chains = _stitch_chains(chains)

    result = []
    for chain in chains:
        if len(chain) < 2:
            continue
        pts = [(float(px), float(py)) for px, py in chain]
        if _chain_length(pts) < min_branch_len:
            continue
        if smooth_passes > 0:
            pts = chaikin_smooth(pts, smooth_passes, closed=False)
        if resample_step > 0:
            pts = resample_by_length(pts, resample_step, closed=False)
        if len(pts) < 2:
            continue
        result.append([(px, float(h - py)) for px, py in pts])

    return result, w, h
