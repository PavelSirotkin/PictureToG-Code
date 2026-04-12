"""Обработка изображений: извлечение контуров и загрузка карты высот."""

import cv2
import numpy as np
import os
import math

from core.geometry import chaikin_smooth, resample_by_length, simplify_chain


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
