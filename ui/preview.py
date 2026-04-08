"""Превью на Canvas: контуры, бинаризация, карта высот."""

import tkinter as tk

import cv2
import numpy as np


def draw_preview(canvas, chains, width=400, height=400):
    canvas.delete("all")
    if not chains:
        canvas.create_text(width // 2, height // 2, text="Нет контуров",
                           fill="#888", font=("Arial", 12))
        return
    all_pts = [pt for c in chains for pt in c]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    margin = 20
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)

    def to_canvas(x, y):
        cx = margin + (x - min_x) * scale
        cy = height - margin - (y - min_y) * scale
        return cx, cy

    colors = ["#00aaff", "#ff6600", "#00cc66", "#ff00aa", "#ffcc00"]
    for i, chain in enumerate(chains):
        col = colors[i % len(colors)]
        pts = [to_canvas(x, y) for x, y in chain]
        flat = [v for p in pts for v in p]
        if len(flat) >= 4:
            canvas.create_line(flat, fill=col, width=1.5, smooth=False)

    ox, oy = to_canvas(min_x, min_y)
    canvas.create_text(ox, oy + 10, text=f"({min_x:.1f},{min_y:.1f})",
                       fill="#666", font=("Arial", 7))


def draw_binarization_preview(canvas, image_path, threshold, invert, blur_size,
                              width=400, height=400):
    """Показывает превью бинаризации на canvas (чёрно-белое изображение)."""
    canvas.delete("all")
    try:
        # Используем np.fromfile + cv2.imdecode для поддержки кириллицы в пути
        img_data = np.fromfile(image_path, dtype=np.uint8)
        img = cv2.imdecode(img_data, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return
        ih, iw = img.shape[:2]
        if blur_size > 0:
            k = blur_size if blur_size % 2 == 1 else blur_size + 1
            img = cv2.GaussianBlur(img, (k, k), 0)
        if invert:
            _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
        else:
            _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

        # Ресайз под canvas
        margin = 10
        avail_w = width - 2 * margin
        avail_h = height - 2 * margin
        scale = min(avail_w / iw, avail_h / ih)
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resized = cv2.resize(binary, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Grayscale → RGB для PPM
        rgb = cv2.cvtColor(resized, cv2.COLOR_GRAY2RGB)
        ppm_header = f"P6\n{new_w} {new_h}\n255\n".encode("ascii")
        ppm_data = ppm_header + rgb.tobytes()
        photo = tk.PhotoImage(data=ppm_data)

        canvas._photo = photo
        x_off = margin + (avail_w - new_w) // 2
        y_off = margin + (avail_h - new_h) // 2
        canvas.create_image(x_off, y_off, anchor="nw", image=photo)

        # Подпись
        canvas.create_text(width // 2, height - 4,
                           text=f"Превью бинаризации (порог: {threshold})",
                           fill="#89b4fa", font=("Arial", 8))
    except (cv2.error, tk.TclError, OverflowError, ValueError):
        # cv2.error - ошибка обработки изображения
        # tk.TclError - ошибка создания PhotoImage
        # OverflowError/ValueError - ошибки конвертации данных
        pass


def draw_heightmap_preview(canvas, heightmap, width=400, height=400):
    """Отрисовывает карту высот как цветное изображение на canvas."""
    canvas.delete("all")
    if heightmap is None:
        canvas.create_text(width // 2, height // 2, text="Нет данных",
                           fill="#888", font=("Arial", 12))
        return

    try:
        # Применяем colormap
        colored = cv2.applyColorMap(heightmap, cv2.COLORMAP_INFERNO)
        colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)

        # Ресайз под canvas с сохранением пропорций
        ih, iw = colored.shape[:2]
        margin = 10
        avail_w = width - 2 * margin
        avail_h = height - 2 * margin
        scale = min(avail_w / iw, avail_h / ih)
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        resized = cv2.resize(colored, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Конвертируем в PPM → tk.PhotoImage (без PIL)
        ppm_header = f"P6\n{new_w} {new_h}\n255\n".encode("ascii")
        ppm_data = ppm_header + resized.tobytes()
        photo = tk.PhotoImage(data=ppm_data)

        # Сохраняем ссылку и рисуем
        canvas._photo = photo
        x_off = margin + (avail_w - new_w) // 2
        y_off = margin + (avail_h - new_h) // 2
        canvas.create_image(x_off, y_off, anchor="nw", image=photo)

        # Подпись
        canvas.create_text(width // 2, height - 4,
                           text="Тёмное = глубоко, светлое = поверхность",
                           fill="#666", font=("Arial", 7))
    except (cv2.error, tk.TclError, OverflowError, ValueError):
        # cv2.error - ошибка обработки изображения
        # tk.TclError - ошибка создания PhotoImage
        # OverflowError/ValueError - ошибки конвертации данных
        pass
