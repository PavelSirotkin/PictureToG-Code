"""3D-просмотр траектории G-кода на tkinter Canvas.

Программный 3D-рендер (без OpenGL): парсит G-код, строит траекторию
инструмента и рисует её на обычном Canvas с орбитальной камерой.

Аналог js/viewer3d.js (там используется Three.js / WebGL).

Управление:
  • перетаскивание ЛКМ — поворот камеры
  • колесо мыши       — зум
"""

import math
import tkinter as tk

BG_COLOR = "#1a1a2e"
RAPID_COLOR = "#4a9eff"      # холостой ход (G0)
FEED_COLOR = "#555555"       # рабочий ход, не выполнено (G1)
DONE_COLOR = "#00ff88"       # рабочий ход, выполнено
GRID_COLOR = "#33334d"
START_COLOR = "#00ff00"
END_COLOR = "#ff0000"
AXIS_COLORS = ("#ff5555", "#55ff55", "#5599ff")  # X, Y, Z


class GCodeViewer3D:
    """Рендер траектории G-кода в 3D на переданном tk.Canvas."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.segments = []        # [{from,to,type,line_no}]
        self.gcode_lines = []
        self.animation_progress = 0.0
        self.on_line_change = None

        # Орбитальная камера: сферические координаты вокруг target
        self.azimuth = math.radians(-45)
        self.elevation = math.radians(30)
        self.distance = 300.0
        self.target = [0.0, 0.0, 0.0]
        self.fov = math.radians(45)

        self._bbox = None
        self._drag = None
        self._disposed = False

        self._bind()
        self._draw_message("Загрузите G-код для 3D-просмотра")

    # ─── События мыши ────────────────────────────────────────────────────

    def _bind(self):
        c = self.canvas
        c.bind("<ButtonPress-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<MouseWheel>", self._on_wheel)     # Windows / macOS
        c.bind("<Button-4>", self._on_wheel)       # Linux scroll up
        c.bind("<Button-5>", self._on_wheel)       # Linux scroll down

    def _unbind(self):
        c = self.canvas
        for seq in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>",
                    "<MouseWheel>", "<Button-4>", "<Button-5>"):
            c.unbind(seq)

    def _on_press(self, event):
        self._drag = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag is None:
            return
        dx = event.x - self._drag[0]
        dy = event.y - self._drag[1]
        self._drag = (event.x, event.y)
        self.azimuth -= dx * 0.01
        self.elevation += dy * 0.01
        lim = math.radians(89)
        self.elevation = max(-lim, min(lim, self.elevation))
        self.render()

    def _on_release(self, event):
        self._drag = None

    def _on_wheel(self, event):
        up = getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4
        self.distance *= 0.88 if up else 1.13
        self.distance = max(5.0, min(8000.0, self.distance))
        self.render()

    # ─── Парсинг G-кода ──────────────────────────────────────────────────

    def load_gcode(self, gcode):
        """Парсит G-код и строит траекторию, подгоняя камеру под неё."""
        self.gcode_lines = gcode.split("\n")
        self.segments = []
        self.animation_progress = 0.0

        cx, cy, cz = 0.0, 0.0, 5.0
        for i, raw in enumerate(self.gcode_lines):
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            code = line.split(";")[0].strip()
            if not code:
                continue
            cmd = self._parse_line(code)
            if cmd is None:
                continue
            t = cmd["type"]
            if t in ("G0", "G00", "G1", "G01"):
                nx = cmd.get("x", cx)
                ny = cmd.get("y", cy)
                nz = cmd.get("z", cz)
                norm = "G0" if t in ("G0", "G00") else "G1"
                self.segments.append({
                    "from": (cx, cy, cz),
                    "to": (nx, ny, nz),
                    "type": norm,
                    "line_no": i + 1,   # 1-based номер строки в тексте
                })
                cx, cy, cz = nx, ny, nz

        self._compute_bbox()
        self._fit_camera()
        self.render()

    @staticmethod
    def _parse_line(line):
        cmd = {"type": None}
        for tok in line.split():
            if not tok:
                continue
            letter = tok[0].upper()
            rest = tok[1:]
            if letter in ("G", "M"):
                cmd["type"] = letter + rest
                continue
            try:
                val = float(rest)
            except ValueError:
                continue
            if letter == "X":
                cmd["x"] = val
            elif letter == "Y":
                cmd["y"] = val
            elif letter == "Z":
                cmd["z"] = val
        return cmd if cmd["type"] else None

    # ─── Камера ──────────────────────────────────────────────────────────

    def _compute_bbox(self):
        if not self.segments:
            self._bbox = None
            return
        xs, ys, zs = [], [], []
        for s in self.segments:
            for p in (s["from"], s["to"]):
                xs.append(p[0])
                ys.append(p[1])
                zs.append(p[2])
        self._bbox = (min(xs), min(ys), min(zs),
                      max(xs), max(ys), max(zs))

    def _fit_camera(self):
        if not self._bbox:
            return
        mnx, mny, mnz, mxx, mxy, mxz = self._bbox
        self.target = [(mnx + mxx) / 2, (mny + mxy) / 2, (mnz + mxz) / 2]
        size = max(mxx - mnx, mxy - mny, mxz - mnz, 1.0)
        self.distance = size * 2.0

    def set_view(self, view):
        """Устанавливает преднастроенный ракурс камеры."""
        presets = {
            "top":   (math.radians(-90), math.radians(89)),
            "front": (math.radians(-90), math.radians(0)),
            "side":  (math.radians(0),   math.radians(0)),
            "iso":   (math.radians(-45), math.radians(30)),
        }
        if view in presets:
            self.azimuth, self.elevation = presets[view]
            self.render()

    def _camera_basis(self):
        """Возвращает (cam_pos, right, up, forward) для текущей камеры."""
        el, az = self.elevation, self.azimuth
        ce = math.cos(el)
        offset = (self.distance * ce * math.cos(az),
                  self.distance * ce * math.sin(az),
                  self.distance * math.sin(el))
        cam = (self.target[0] + offset[0],
               self.target[1] + offset[1],
               self.target[2] + offset[2])

        fwd = (self.target[0] - cam[0],
               self.target[1] - cam[1],
               self.target[2] - cam[2])
        fwd = _normalize(fwd)
        world_up = (0.0, 0.0, 1.0)
        right = _normalize(_cross(fwd, world_up))
        up = _cross(right, fwd)
        return cam, right, up, fwd

    # ─── Проекция и рендер ───────────────────────────────────────────────

    def render(self):
        if self._disposed:
            return
        canvas = self.canvas
        canvas.delete("all")
        w = canvas.winfo_width() or 420
        h = canvas.winfo_height() or 420
        canvas.configure(bg=BG_COLOR)

        if not self.segments:
            self._draw_message("Нет траектории")
            return

        cam, right, up, fwd = self._camera_basis()
        focal = (h / 2) / math.tan(self.fov / 2)
        cx, cy = w / 2, h / 2

        def project(pt):
            rx = pt[0] - cam[0]
            ry = pt[1] - cam[1]
            rz = pt[2] - cam[2]
            depth = rx * fwd[0] + ry * fwd[1] + rz * fwd[2]
            if depth <= 0.5:
                return None
            sx = rx * right[0] + ry * right[1] + rz * right[2]
            sy = rx * up[0] + ry * up[1] + rz * up[2]
            return (cx + focal * sx / depth, cy - focal * sy / depth)

        self._draw_grid(project)
        self._draw_axes(project)
        self._draw_toolpath(project)
        self._draw_hud(w, h)

    def _draw_toolpath(self, project):
        feed_total = sum(1 for s in self.segments if s["type"] == "G1")
        completed = int((self.animation_progress / 100.0) * feed_total)

        # Группируем подряд идущие сегменты одного цвета в полилинии
        runs = []          # [(color, [pt, pt, ...])]
        cur_color = None
        cur_pts = []
        feed_idx = 0
        last_completed_line = None

        for seg in self.segments:
            if seg["type"] == "G0":
                color = RAPID_COLOR
            else:
                if feed_idx < completed:
                    color = DONE_COLOR
                    last_completed_line = seg["line_no"]
                else:
                    color = FEED_COLOR
                feed_idx += 1

            a = project(seg["from"])
            b = project(seg["to"])
            if a is None or b is None:
                if cur_pts:
                    runs.append((cur_color, cur_pts))
                cur_color, cur_pts = None, []
                continue

            if color != cur_color or not cur_pts:
                if cur_pts:
                    runs.append((cur_color, cur_pts))
                cur_color = color
                cur_pts = [a, b]
            else:
                cur_pts.append(b)
        if cur_pts:
            runs.append((cur_color, cur_pts))

        # Сначала холостой ход (тонкий), затем рабочий — поверх
        for color, pts in runs:
            if color != RAPID_COLOR:
                continue
            self._draw_polyline(pts, color, 1)
        for color, pts in runs:
            if color == RAPID_COLOR:
                continue
            self._draw_polyline(pts, color, 2)

        # Маркеры начала и конца
        start = project(self.segments[0]["from"])
        end = project(self.segments[-1]["to"])
        if start:
            self._draw_marker(start, START_COLOR)
        if end:
            self._draw_marker(end, END_COLOR)

        if self.on_line_change:
            self.on_line_change(last_completed_line)

    def _draw_polyline(self, pts, color, width):
        if len(pts) < 2:
            return
        flat = [v for p in pts for v in p]
        self.canvas.create_line(*flat, fill=color, width=width)

    def _draw_marker(self, pt, color):
        x, y = pt
        r = 4
        self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                fill=color, outline="")

    def _draw_grid(self, project):
        if not self._bbox:
            return
        mnx, mny, _, mxx, mxy, _ = self._bbox
        lo_x = min(0.0, mnx)
        hi_x = max(0.0, mxx)
        lo_y = min(0.0, mny)
        hi_y = max(0.0, mxy)
        span = max(hi_x - lo_x, hi_y - lo_y, 1.0)
        step = _nice_step(span / 8.0)

        gx0 = math.floor(lo_x / step) * step
        gx1 = math.ceil(hi_x / step) * step
        gy0 = math.floor(lo_y / step) * step
        gy1 = math.ceil(hi_y / step) * step

        x = gx0
        while x <= gx1 + 1e-6:
            a = project((x, gy0, 0.0))
            b = project((x, gy1, 0.0))
            if a and b:
                self.canvas.create_line(a[0], a[1], b[0], b[1],
                                        fill=GRID_COLOR)
            x += step
        y = gy0
        while y <= gy1 + 1e-6:
            a = project((gx0, y, 0.0))
            b = project((gx1, y, 0.0))
            if a and b:
                self.canvas.create_line(a[0], a[1], b[0], b[1],
                                        fill=GRID_COLOR)
            y += step

    def _draw_axes(self, project):
        if not self._bbox:
            return
        mnx, mny, mnz, mxx, mxy, mxz = self._bbox
        length = max(mxx - mnx, mxy - mny, mxz - mnz, 10.0) * 0.25
        origin = project((0.0, 0.0, 0.0))
        if not origin:
            return
        ends = [(length, 0, 0), (0, length, 0), (0, 0, length)]
        labels = ("X", "Y", "Z")
        for axis, color, label in zip(ends, AXIS_COLORS, labels):
            tip = project(axis)
            if not tip:
                continue
            self.canvas.create_line(origin[0], origin[1], tip[0], tip[1],
                                    fill=color, width=2)
            self.canvas.create_text(tip[0], tip[1], text=label,
                                    fill=color, font=("Segoe UI", 9, "bold"))

    def _draw_hud(self, w, h):
        self.canvas.create_text(
            10, h - 10, anchor="sw",
            text="ЛКМ — поворот • колесо — зум",
            fill="#6c7086", font=("Segoe UI", 8))

    def _draw_message(self, text):
        canvas = self.canvas
        canvas.delete("all")
        canvas.configure(bg=BG_COLOR)
        w = canvas.winfo_width() or 420
        h = canvas.winfo_height() or 420
        canvas.create_text(w // 2, h // 2, text=text,
                           fill="#888", font=("Segoe UI", 11))

    # ─── Анимация ────────────────────────────────────────────────────────

    def set_animation_progress(self, progress):
        """Прогресс анимации 0-100 (доля выполненного рабочего хода)."""
        self.animation_progress = max(0.0, min(100.0, float(progress)))
        self.render()

    # ─── Очистка ─────────────────────────────────────────────────────────

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self._unbind()
        self.segments = []
        try:
            self.canvas.delete("all")
        except tk.TclError:
            pass


# ─── Векторные утилиты ───────────────────────────────────────────────────

def _normalize(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _nice_step(raw):
    """Округляет шаг сетки до «красивого» значения (1, 2, 5 × 10^n)."""
    if raw <= 0:
        return 1.0
    exp = math.floor(math.log10(raw))
    base = 10 ** exp
    for mult in (1, 2, 5, 10):
        if raw <= mult * base:
            return mult * base
    return 10 * base
