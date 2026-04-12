"""Главное окно приложения PictureToG-Code."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinter.ttk import Progressbar
import math
import os
import re
import sys
import logging

from core.version import __version__, VERSION_DISPLAY

from core.image import extract_contours, load_heightmap
from core.geometry import (
    simplify_chain, offset_chain, sort_chains_nearest,
    get_bounds, scale_chains,
)
from core.gcode import chains_to_gcode, heightmap_to_gcode, format_time_estimate, RAPID_RATE
from core.templates import TEMPLATES, generate_template
from core.validators import InputValidator

from ui.preview import draw_preview, draw_heightmap_preview, draw_binarization_preview

# Настройки
import json

# Логирование
logger = logging.getLogger(__name__)


SETTINGS_FILE = "settings.json"


class SettingsManager:
    """Автосохранение и загрузка настроек приложения."""

    DEFAULT_SETTINGS = {
        "tool_diameter": "3.175", "feedrate": "800", "depth": "2.0",
        "num_passes": "1", "safe_z": "5.0", "spindle_speed": "15000",
        "simplify_eps": "0", "threshold": "128", "blur_size": "3",
        "min_area": "10", "approx_factor": "0.001",
        "smooth_passes": "3", "resample_step": "0",
        "invert": True, "bridge_mode": False, "bridge_size": "3.0", "bridge_count": "2",
        "stepover_pct": "40", "plunge_feed": "300", "blur_relief": "5",
        "strategy": "Зигзаг",
        "mode": "Контур", "template": "(нет)",
        "output_width": "", "output_height": "", "lock_aspect": True,
    }

    def __init__(self, settings_file=None):
        if settings_file:
            self.settings_file = settings_file
        else:
            # Для PyInstaller: путь рядом с .exe файлом
            # Для обычного запуска: путь рядом с корневым файлом скрипта
            if getattr(sys, 'frozen', False):
                # Запущено из PyInstaller .exe
                base_dir = os.path.dirname(sys.executable)
            else:
                # Запущено из исходного кода
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.settings_file = os.path.join(base_dir, SETTINGS_FILE)
        self.settings = dict(self.DEFAULT_SETTINGS)

    def load(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.settings.update(loaded)
                return True
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"Не удалось загрузить настройки: {e}")
        return False

    def save(self):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            logger.warning(f"Не удалось сохранить настройки: {e}")
            return False

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value


class CamApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Picture CAM — G-Code Generator {VERSION_DISPLAY}")
        self.resizable(True, True)
        self.chains = []
        self.img_path = None
        self.img_w = 0
        self.img_h = 0
        self.heightmap = None
        self.gcode = ""
        self._template_active = False
        self._updating_size = False
        self._size_debounce_id = None
        self._thresh_debounce_id = None
        self._auto_save_id = None

        # Инициализация менеджера настроек
        self.settings_mgr = SettingsManager()
        self.settings_mgr.load()

        self._build_ui()
        self._load_settings_to_ui()
        self._setup_auto_save()

    # ─── Построение UI ─────────────────────────────────────────────────

    def _build_ui(self):
        self._combo_boxes = []
        self.configure(bg="#1e1e2e")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame",       background="#1e1e2e")
        style.configure("TLabel",       background="#1e1e2e", foreground="#cdd6f4",
                        font=("Segoe UI", 10))
        style.configure("TButton",      font=("Segoe UI", 10, "bold"),
                        background="#89b4fa", foreground="#1e1e2e")
        style.map("TButton",            background=[("active", "#74c7ec")])
        style.configure("Accent.TButton", background="#a6e3a1", foreground="#1e1e2e",
                        font=("Segoe UI", 11, "bold"))
        style.configure("TCheckbutton", background="#1e1e2e", foreground="#cdd6f4",
                        font=("Segoe UI", 10))
        style.configure("TEntry",       fieldbackground="#313244", foreground="#cdd6f4",
                        insertcolor="#cdd6f4")
        style.configure("TLabelframe",  background="#1e1e2e", foreground="#89b4fa")
        style.configure("TLabelframe.Label", background="#1e1e2e", foreground="#89b4fa",
                        font=("Segoe UI", 10, "bold"))
        style.configure("TCombobox", fieldbackground="#313244", foreground="#cdd6f4")

        # ── верхняя строка ──
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=(10, 0))

        self.lbl_file = ttk.Label(top, text="Файл не выбран", width=45, anchor="w")
        self.lbl_file.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(top, text="Открыть изображение...", command=self._open_image).pack(side=tk.LEFT)

        # ── основная рабочая область ──
        mid = ttk.Frame(self)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # левая панель параметров
        left = ttk.LabelFrame(mid, text="Параметры", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y)

        def row(parent, label, default, row_num, hint="", validator=None):
            ttk.Label(parent, text=label).grid(row=row_num, column=0,
                                                sticky="w", pady=3)
            var = tk.StringVar(value=default)
            e = ttk.Entry(parent, textvariable=var, width=10)
            e.grid(row=row_num, column=1, padx=(8, 0), pady=3)
            if hint:
                ttk.Label(parent, text=hint, foreground="#6c7086",
                          font=("Segoe UI", 8)).grid(row=row_num, column=2,
                                                      padx=(4, 0))
            if validator:
                e.bind("<FocusOut>", lambda event: self._validate_field(var, validator))
                e.bind("<KeyRelease>", lambda event: self._clear_field_error(var))
            return var

        # ── Секция: Режим ──
        frm_mode = ttk.Frame(left)
        frm_mode.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(frm_mode, text="Режим:").pack(side=tk.LEFT)
        self.v_mode = tk.StringVar(value="Контур")
        self.cmb_mode = tk.OptionMenu(frm_mode, self.v_mode, "Контур", "Рельеф")
        self.cmb_mode.config(width=14)
        self.cmb_mode.pack(side=tk.LEFT, padx=(8, 0))
        self.v_mode.trace_add("write", self._on_mode_changed_trace)

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, pady=6)

        # ── Секция: Общие параметры ──
        self.frm_common = ttk.Frame(left)
        self.frm_common.pack(fill=tk.X)

        self.v_tool   = row(self.frm_common, "Диаметр фрезы (мм):", "3.175", 0, "d",
                           {"type": "float", "name": "Диаметр фрезы", "min_val": 0.1, "max_val": 50.0})
        self.v_feed   = row(self.frm_common, "Подача (мм/мин):", "800", 1, "F",
                           {"type": "int", "name": "Подача", "min_val": 10, "max_val": 10000})
        self.v_depth  = row(self.frm_common, "Глубина (мм):", "2.0", 2, "Z",
                           {"type": "float", "name": "Глубина", "min_val": 0.01, "max_val": 100.0})
        self.v_passes = row(self.frm_common, "Число проходов:", "1", 3, "n",
                           {"type": "int", "name": "Число проходов", "min_val": 1, "max_val": 50})
        self.v_safe   = row(self.frm_common, "Safe Z (мм):", "5.0", 4, "",
                           {"type": "float", "name": "Safe Z", "min_val": 0.5, "max_val": 50.0})
        self.v_spindle = row(self.frm_common, "Скорость шпинделя (об/мин):", "15000", 5, "S",
                            {"type": "int", "name": "Скорость шпинделя", "min_val": 100, "max_val": 60000})

        # ── Секция: Контурные параметры ──
        self.frm_contour = ttk.Frame(left)
        self.frm_contour.pack(fill=tk.X)

        ttk.Separator(self.frm_contour, orient="horizontal").grid(
            row=0, columnspan=3, sticky="ew", pady=6)

        self.v_simp = row(self.frm_contour, "Упрощение (мм, 0=нет):", "0", 1, "e",
                         {"type": "float", "name": "Упрощение", "min_val": 0, "max_val": 1.0})

        ttk.Separator(self.frm_contour, orient="horizontal").grid(
            row=2, columnspan=3, sticky="ew", pady=6)
        ttk.Label(self.frm_contour, text="Шаблон:").grid(row=3, column=0, sticky="w", pady=3)
        self.v_template = tk.StringVar(value="(нет)")
        self.cmb_template = ttk.Combobox(self.frm_contour, textvariable=self.v_template,
                                          values=TEMPLATES, state="readonly", width=20)
        self.cmb_template.grid(row=3, column=1, columnspan=2, padx=(8, 0), pady=3, sticky="w")
        self.cmb_template.bind("<<ComboboxSelected>>", self._on_template_selected)
        self._combo_boxes.append(self.cmb_template)

        # Обработка изображения
        ttk.Separator(self.frm_contour, orient="horizontal").grid(
            row=4, columnspan=3, sticky="ew", pady=6)
        ttk.Label(self.frm_contour, text="Обработка изображения",
                  foreground="#89b4fa", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 4))

        self.v_thresh = row(self.frm_contour, "Порог бинаризации:", "128", 6, "0-255",
                            {"type": "int", "name": "Порог", "min_val": 0, "max_val": 255})

        self._thresh_debounce_id = None
        self.scl_thresh = tk.Scale(
            self.frm_contour, from_=0, to=255, orient="horizontal",
            bg="#1e1e2e", fg="#89b4fa", troughcolor="#313244",
            activebackground="#89b4fa", highlightthickness=0,
            length=200, showvalue=False, command=self._on_thresh_slider)
        self.scl_thresh.set(128)
        self.scl_thresh.grid(row=7, column=0, columnspan=3, sticky="ew", padx=4)
        self.v_thresh.trace_add("write", self._sync_thresh_slider)

        self.v_blur     = row(self.frm_contour, "Размытие (px):", "3", 8, "нечёт.",
                             {"type": "int", "name": "Размытие", "min_val": 0, "max_val": 21})
        self.v_min_area = row(self.frm_contour, "Мин. площадь (px2):", "10", 9, "фильтр",
                             {"type": "int", "name": "Мин. площадь", "min_val": 0, "max_val": 10000})
        self.v_approx   = row(self.frm_contour, "Аппроксимация:", "0.001", 10, "0-0.05",
                             {"type": "float", "name": "Аппроксимация", "min_val": 0, "max_val": 0.1})

        self.v_smooth_passes = row(
            self.frm_contour, "Проходов Chaikin (0–8):", "3", 11, "0=выкл.",
            {"type": "int", "name": "Проходов Chaikin", "min_val": 0, "max_val": 8})
        self.v_resample_step = row(
            self.frm_contour, "Шаг ре-сэмплинга (px, 0=нет):", "0", 12, "px",
            {"type": "float", "name": "Шаг ре-сэмплинга", "min_val": 0, "max_val": 100.0})

        self.v_invert = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.frm_contour, text="Инвертировать (тёмное = контур)",
                        variable=self.v_invert).grid(
            row=13, column=0, columnspan=3, sticky="w", pady=3)

        # Мостики
        ttk.Separator(self.frm_contour, orient="horizontal").grid(
            row=14, columnspan=3, sticky="ew", pady=6)
        self.v_bridge = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.frm_contour, text="Мостики (bridges)",
                        variable=self.v_bridge).grid(
            row=15, column=0, columnspan=3, sticky="w")
        self.v_bsize = row(self.frm_contour, "Размер мостика (мм):", "3.0", 16, "",
                          {"type": "float", "name": "Размер мостика", "min_val": 0.1, "max_val": 20.0})
        self.v_bnum  = row(self.frm_contour, "Кол-во мостиков:", "2", 17, "",
                          {"type": "int", "name": "Кол-во мостиков", "min_val": 1, "max_val": 20})

        # ── Секция: Рельефные параметры ──
        self.frm_relief = ttk.Frame(left)

        ttk.Separator(self.frm_relief, orient="horizontal").grid(
            row=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(self.frm_relief, text="⬆ 2.5D Фрезеровка (Рельеф)",
                  foreground="#a6e3a1", font=("Segoe UI", 11, "bold")).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(self.frm_relief,
                  text="Создаёт 3D рельеф по яркости изображения.\nТёмные участки = глубже, светлые = выше.",
                  foreground="#6c7086", font=("Segoe UI", 8), justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(0, 6))

        ttk.Separator(self.frm_relief, orient="horizontal").grid(
            row=3, columnspan=3, sticky="ew", pady=6)
        ttk.Label(self.frm_relief, text="Параметры обработки",
                  foreground="#89b4fa", font=("Segoe UI", 10, "bold")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(self.frm_relief, text="Стратегия:").grid(row=5, column=0, sticky="w", pady=3)
        self.v_strategy = tk.StringVar(value="Зигзаг")
        self.cmb_strategy = tk.OptionMenu(self.frm_relief, self.v_strategy,
                                           "Зигзаг", "Однонаправленный")
        self.cmb_strategy.config(width=16)
        self.cmb_strategy.grid(row=5, column=1, columnspan=2, padx=(8, 0), pady=3, sticky="w")

        self.v_stepover    = row(self.frm_relief, "Перекрытие (% диам.):", "40", 6, "%",
                                {"type": "int", "name": "Перекрытие", "min_val": 5, "max_val": 90})
        self.v_plunge_feed = row(self.frm_relief, "Подача врезания:", "300", 7, "мм/мин",
                                {"type": "int", "name": "Подача врезания", "min_val": 10, "max_val": 5000})
        self.v_blur_relief = row(self.frm_relief, "Размытие (px):", "5", 8, "нечёт.",
                                {"type": "int", "name": "Размытие рельефа", "min_val": 0, "max_val": 21})

        # ── Секция: Размер вывода ──
        self.frm_size = ttk.Frame(left)
        self.frm_size.pack(fill=tk.X)

        ttk.Separator(self.frm_size, orient="horizontal").grid(
            row=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(self.frm_size, text="Размер вывода",
                  foreground="#89b4fa", font=("Segoe UI", 10, "bold")).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))

        self.lbl_img_size = ttk.Label(self.frm_size, text="Изображение: ---",
                                       foreground="#6c7086", font=("Segoe UI", 8))
        self.lbl_img_size.grid(row=2, column=0, columnspan=3, sticky="w")

        size_row = ttk.Frame(self.frm_size, style="TFrame")
        size_row.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)

        ttk.Label(size_row, text="W:").pack(side=tk.LEFT)
        self.v_out_w = tk.StringVar(value="")
        self.e_out_w = ttk.Entry(size_row, textvariable=self.v_out_w, width=8)
        self.e_out_w.pack(side=tk.LEFT, padx=(3, 2))
        self.e_out_w.bind("<FocusOut>", self._on_size_focus_out)
        self.e_out_w.bind("<Return>", self._on_size_enter)

        self.v_lock = tk.BooleanVar(value=True)
        self.btn_lock = tk.Button(
            size_row, text="\U0001F512", relief="flat", bd=0,
            bg="#313244", fg="#cdd6f4", activebackground="#45475a",
            font=("Segoe UI", 11), cursor="hand2", command=self._toggle_lock)
        self.btn_lock.pack(side=tk.LEFT, padx=2)

        ttk.Label(size_row, text="H:").pack(side=tk.LEFT, padx=(2, 0))
        self.v_out_h = tk.StringVar(value="")
        self.e_out_h = ttk.Entry(size_row, textvariable=self.v_out_h, width=8)
        self.e_out_h.pack(side=tk.LEFT, padx=(3, 0))
        self.e_out_h.bind("<FocusOut>", self._on_size_focus_out)
        self.e_out_h.bind("<Return>", self._on_size_enter)

        ttk.Label(self.frm_size, text="мм  (пусто = 1 px = 1 мм)",
                  foreground="#6c7086", font=("Segoe UI", 8)).grid(
            row=4, column=0, columnspan=3, sticky="w")

        self.v_out_w.trace_add("write", lambda *_: self._on_size_trace("w"))
        self.v_out_h.trace_add("write", lambda *_: self._on_size_trace("h"))

        # ── Секция: Кнопки ──
        self.frm_buttons = ttk.Frame(left)
        self.frm_buttons.pack(fill=tk.X)

        ttk.Separator(self.frm_buttons, orient="horizontal").pack(fill=tk.X, pady=6)

        self.btn_reload = ttk.Button(self.frm_buttons, text="Обновить контуры",
                                      command=self._reload_contours)
        self.btn_reload.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(self.frm_buttons, text="Сгенерировать G-Code",
                   style="Accent.TButton", command=self._generate).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(self.frm_buttons, text="Сохранить .nc...",
                   command=self._save).pack(fill=tk.X)

        # Индикатор прогресса
        self.progress = Progressbar(self.frm_buttons, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(6, 0))
        self.progress['value'] = 0

        # Стиль прогресс-бара — светло-зелёный
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor="#313244",    # тёмный фон
                        background="#a6e3a1",     # светло-зелёный
                        lightbackground="#a6e3a1",
                        bordercolor="#313244",
                        thickness=10)
        self.progress.configure(style="green.Horizontal.TProgressbar")

        # ── Превью (центр) ──
        self.center_frame = ttk.LabelFrame(mid, text="Превью", padding=4)
        self.center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)

        self.canvas = tk.Canvas(self.center_frame, bg="#181825", width=420, height=420,
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ── Правая панель — G-Code ──
        right = ttk.LabelFrame(mid, text="G-Code", padding=4)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.txt_gcode = scrolledtext.ScrolledText(
            right, width=42, bg="#181825", fg="#cdd6f4",
            insertbackground="#cdd6f4", font=("Consolas", 9), relief="flat")
        self.txt_gcode.pack(fill=tk.BOTH, expand=True)

        self.txt_gcode.tag_configure("g0",      foreground="#f38ba8")
        self.txt_gcode.tag_configure("g1",      foreground="#a6e3a1")
        self.txt_gcode.tag_configure("coord",   foreground="#89b4fa")
        self.txt_gcode.tag_configure("feed",    foreground="#f9e2af")
        self.txt_gcode.tag_configure("mcode",   foreground="#cba6f7")
        self.txt_gcode.tag_configure("comment", foreground="#6c7086")
        self.txt_gcode.tag_configure("gother",  foreground="#fab387")

        # ── Статистика ──
        self.stats_frame = ttk.Frame(right, style="TFrame")
        self.stats_frame.pack(fill=tk.X, pady=(4, 0))

        row1 = ttk.Frame(self.stats_frame, style="TFrame")
        row1.pack(fill=tk.X)
        self.lbl_stat_lines = ttk.Label(row1, text="", anchor="w",
                                         foreground="#a6e3a1", font=("Consolas", 9, "bold"))
        self.lbl_stat_lines.pack(side=tk.LEFT, padx=4, pady=1)
        self.lbl_stat_time = ttk.Label(row1, text="", anchor="w",
                                        foreground="#89b4fa", font=("Consolas", 9))
        self.lbl_stat_time.pack(side=tk.LEFT, padx=(8, 4), pady=1)

        row2 = ttk.Frame(self.stats_frame, style="TFrame")
        row2.pack(fill=tk.X)
        self.lbl_stat_cut = ttk.Label(row2, text="", anchor="w",
                                       foreground="#f9e2af", font=("Consolas", 8))
        self.lbl_stat_cut.pack(side=tk.LEFT, padx=4, pady=1)
        self.lbl_stat_rapid = ttk.Label(row2, text="", anchor="w",
                                         foreground="#6c7086", font=("Consolas", 8))
        self.lbl_stat_rapid.pack(side=tk.LEFT, padx=(8, 4), pady=1)

        # ── Статус бар ──
        self.lbl_status = ttk.Label(self, text="Готов.", anchor="w", foreground="#6c7086")
        self.lbl_status.pack(fill=tk.X, padx=10, pady=(0, 6))

    # ─── Валидация ─────────────────────────────────────────────────────

    def _validate_field(self, var, validator_config):
        value = var.get()
        vtype = validator_config.get("type", "float")
        name = validator_config.get("name", "Поле")
        min_val = validator_config.get("min_val", None)
        max_val = validator_config.get("max_val", None)

        if vtype == "int":
            ok, parsed, error = InputValidator.validate_int(
                value, name=name, min_val=min_val, max_val=max_val)
        else:
            ok, parsed, error = InputValidator.validate_float(
                value, name=name, min_val=min_val, max_val=max_val)

        if not ok:
            self._status(error, "#f38ba8")

    def _clear_field_error(self, var):
        self._status("Готов.", "#6c7086")

    # ─── Загрузка и сохранение настроек ────────────────────────────────

    def _load_settings_to_ui(self):
        s = self.settings_mgr
        self.v_tool.set(s.get("tool_diameter", "3.175"))
        self.v_feed.set(s.get("feedrate", "800"))
        self.v_depth.set(s.get("depth", "2.0"))
        self.v_passes.set(s.get("num_passes", "1"))
        self.v_safe.set(s.get("safe_z", "5.0"))
        self.v_spindle.set(s.get("spindle_speed", "15000"))
        self.v_simp.set(s.get("simplify_eps", "0"))
        self.v_thresh.set(s.get("threshold", "128"))
        self.v_blur.set(s.get("blur_size", "3"))
        self.v_min_area.set(s.get("min_area", "10"))
        self.v_approx.set(s.get("approx_factor", "0.001"))
        self.v_smooth_passes.set(s.get("smooth_passes", "3"))
        self.v_resample_step.set(s.get("resample_step", "0"))
        self.v_invert.set(s.get("invert", True))
        self.v_bridge.set(s.get("bridge_mode", False))
        self.v_bsize.set(s.get("bridge_size", "3.0"))
        self.v_bnum.set(s.get("bridge_count", "2"))
        self.v_stepover.set(s.get("stepover_pct", "40"))
        self.v_plunge_feed.set(s.get("plunge_feed", "300"))
        self.v_blur_relief.set(s.get("blur_relief", "5"))
        self.v_strategy.set(s.get("strategy", "Зигзаг"))
        self.v_mode.set(s.get("mode", "Контур"))
        self.v_template.set(s.get("template", "(нет)"))
        self.v_out_w.set(s.get("output_width", ""))
        self.v_out_h.set(s.get("output_height", ""))
        self.v_lock.set(s.get("lock_aspect", True))
        self.btn_lock.config(text="\U0001F512" if self.v_lock.get() else "\U0001F513")
        try:
            self.scl_thresh.set(int(self.v_thresh.get()))
        except (ValueError, AttributeError):
            pass

    def _setup_auto_save(self):
        vars_to_save = [
            self.v_tool, self.v_feed, self.v_depth, self.v_passes, self.v_safe,
            self.v_spindle, self.v_simp, self.v_thresh, self.v_blur, self.v_min_area, self.v_approx,
            self.v_smooth_passes, self.v_resample_step,
            self.v_bsize, self.v_bnum, self.v_stepover, self.v_plunge_feed,
            self.v_blur_relief, self.v_out_w, self.v_out_h,
        ]
        for var in vars_to_save:
            var.trace_add("write", lambda *_: self._schedule_auto_save())
        self.v_invert.trace_add("write", lambda *_: self._schedule_auto_save())
        self.v_bridge.trace_add("write", lambda *_: self._schedule_auto_save())
        self.v_lock.trace_add("write", lambda *_: self._schedule_auto_save())
        self.v_mode.trace_add("write", lambda *_: self._schedule_auto_save())
        self.v_template.trace_add("write", lambda *_: self._schedule_auto_save())
        self.v_strategy.trace_add("write", lambda *_: self._schedule_auto_save())

    def _schedule_auto_save(self):
        if self._auto_save_id:
            self.after_cancel(self._auto_save_id)
        self._auto_save_id = self.after(500, self._do_auto_save)

    def _do_auto_save(self):
        self._auto_save_id = None
        s = self.settings_mgr
        s.set("tool_diameter", self.v_tool.get())
        s.set("feedrate", self.v_feed.get())
        s.set("depth", self.v_depth.get())
        s.set("num_passes", self.v_passes.get())
        s.set("safe_z", self.v_safe.get())
        s.set("spindle_speed", self.v_spindle.get())
        s.set("simplify_eps", self.v_simp.get())
        s.set("threshold", self.v_thresh.get())
        s.set("blur_size", self.v_blur.get())
        s.set("min_area", self.v_min_area.get())
        s.set("approx_factor", self.v_approx.get())
        s.set("smooth_passes", self.v_smooth_passes.get())
        s.set("resample_step", self.v_resample_step.get())
        s.set("invert", self.v_invert.get())
        s.set("bridge_mode", self.v_bridge.get())
        s.set("bridge_size", self.v_bsize.get())
        s.set("bridge_count", self.v_bnum.get())
        s.set("stepover_pct", self.v_stepover.get())
        s.set("plunge_feed", self.v_plunge_feed.get())
        s.set("blur_relief", self.v_blur_relief.get())
        s.set("strategy", self.v_strategy.get())
        s.set("mode", self.v_mode.get())
        s.set("template", self.v_template.get())
        s.set("output_width", self.v_out_w.get())
        s.set("output_height", self.v_out_h.get())
        s.set("lock_aspect", self.v_lock.get())
        s.save()

    # ─── Переключение режимов ────────────────────────────────────────────

    def _on_mode_changed_trace(self, *_):
        self._on_mode_changed_impl(self.v_mode.get())

    def _on_mode_changed_impl(self, mode):
        if mode == "Контур":
            self.frm_relief.pack_forget()
            self.frm_contour.pack(fill=tk.X, after=self.frm_common)
            self.btn_reload.config(text="Обновить контуры")
        else:
            self.frm_contour.pack_forget()
            self.frm_relief.pack(fill=tk.X, after=self.frm_common)
            self.btn_reload.config(text="Обновить карту высот")

        if self.img_path:
            self._load_contours()
        else:
            if mode == "Рельеф":
                self._status("Режим 2.5D (Рельеф): откройте изображение для создания карты высот", "#89b4fa")
            else:
                self._status("Готов.", "#6c7086")

    # ─── Шаблоны ─────────────────────────────────────────────────────────

    def _on_template_selected(self, *_):
        name = self.v_template.get()
        if name == "(нет)":
            self._template_active = False
            return

        try:
            w = float(self.v_out_w.get()) if self.v_out_w.get().strip() else None
        except ValueError:
            w = None
        try:
            h = float(self.v_out_h.get()) if self.v_out_h.get().strip() else None
        except ValueError:
            h = None

        if name in ("Брелок круглый", "Звезда", "Сердце"):
            w = w or 40.0
            h = h or 40.0
        else:
            w = w or 50.0
            h = h or 30.0

        self._template_active = True
        self.img_path = None
        self.heightmap = None
        chains, iw, ih = generate_template(name, w, h)
        self.chains = chains
        self.img_w, self.img_h = int(iw), int(ih)

        self.lbl_file.config(text=f"Шаблон: {name}")
        self._update_size_label()

        self._updating_size = True
        self.v_out_w.set(f"{w:.1f}")
        self.v_out_h.set(f"{h:.1f}")
        self._updating_size = False

        cw = self.canvas.winfo_width() or 420
        ch = self.canvas.winfo_height() or 420
        draw_preview(self.canvas, self.chains, cw, ch)
        self._status(f"Шаблон «{name}» загружен, контуров: {len(chains)}", "#a6e3a1")

    # ─── Живое превью бинаризации ───────────────────────────────────────

    def _sync_thresh_slider(self, *_):
        try:
            v = int(self.v_thresh.get())
            if 0 <= v <= 255 and self.scl_thresh.get() != v:
                self.scl_thresh.set(v)
        except (ValueError, AttributeError):
            pass

    def _on_thresh_slider(self, val):
        val = int(float(val))
        self.v_thresh.set(str(val))
        if self._thresh_debounce_id:
            self.after_cancel(self._thresh_debounce_id)
        self._thresh_debounce_id = self.after(150, self._update_binarization_preview)

    def _update_binarization_preview(self):
        self._thresh_debounce_id = None
        if not self.img_path or self.v_mode.get() != "Контур":
            return
        cw = self.canvas.winfo_width() or 420
        ch = self.canvas.winfo_height() or 420
        draw_binarization_preview(
            self.canvas, self.img_path,
            threshold=self._int(self.v_thresh, 128),
            invert=self.v_invert.get(),
            blur_size=self._int(self.v_blur, 3),
            width=cw, height=ch)

    # ─── UI helpers ──────────────────────────────────────────────────────

    def _toggle_lock(self):
        self.v_lock.set(not self.v_lock.get())
        self.btn_lock.config(text="\U0001F512" if self.v_lock.get() else "\U0001F513")

    def _on_size_focus_out(self, event):
        self._update_other_field(event.widget)

    def _on_size_enter(self, event):
        self._update_other_field(event.widget)

    def _update_other_field(self, widget):
        if not self.v_lock.get():
            return
        ar = self._aspect_ratio()
        if ar is None:
            return
        try:
            w = float(self.v_out_w.get())
            h = float(self.v_out_h.get())
            if widget == self.e_out_w:
                new_h = f"{w / ar:.3f}"
                self.e_out_h.delete(0, tk.END)
                self.e_out_h.insert(0, new_h)
            elif widget == self.e_out_h:
                new_w = f"{h * ar:.3f}"
                self.e_out_w.delete(0, tk.END)
                self.e_out_w.insert(0, new_w)
        except ValueError:
            pass

    def _aspect_ratio(self):
        if self.v_mode.get() == "Рельеф" and self.heightmap is not None:
            h, w = self.heightmap.shape[:2]
            return w / h if h else None
        if not self.chains:
            return None
        mn_x, mn_y, mx_x, mx_y = get_bounds(self.chains)
        w, h = mx_x - mn_x, mx_y - mn_y
        if h == 0:
            return None
        return w / h

    def _on_size_trace(self, which):
        if self._updating_size:
            return
        if self._size_debounce_id:
            self.after_cancel(self._size_debounce_id)
        self._size_debounce_id = self.after(300, lambda: self._apply_size_sync(which))

    def _apply_size_sync(self, which):
        self._size_debounce_id = None
        if not self.v_lock.get():
            return
        ar = self._aspect_ratio()
        if ar is None:
            return
        self._updating_size = True
        try:
            if which == "w":
                w = float(self.v_out_w.get())
                self.v_out_h.set(f"{w / ar:.3f}")
            else:
                h = float(self.v_out_h.get())
                self.v_out_w.set(f"{h * ar:.3f}")
        except ValueError:
            pass
        finally:
            self._updating_size = False

    def _update_size_label(self):
        if self.v_mode.get() == "Рельеф" and self.heightmap is not None:
            self.lbl_img_size.config(text=f"Изображение: {self.img_w} x {self.img_h} px")
            return
        if not self.chains:
            self.lbl_img_size.config(text="Изображение: ---")
            return
        self.lbl_img_size.config(
            text=f"Изображение: {self.img_w} x {self.img_h} px, "
                 f"контуров: {len(self.chains)}")

    def _status(self, msg, color="#6c7086"):
        self.lbl_status.config(text=msg, foreground=color)
        self.update_idletasks()

    def _set_progress(self, value):
        """Плавно обновляет прогресс-бар."""
        self.progress['value'] = value
        self.update_idletasks()

    def _update_gen_info(self, lines_count, time_str, feedrate, dist_dict=None):
        contour_info = ""
        mode = self.v_mode.get()
        if mode == "Контур" and self.chains:
            contour_info = f"  Контуров: {len(self.chains)}"
        self.lbl_stat_lines.config(text=f"Строк: {lines_count}{contour_info}")
        self.lbl_stat_time.config(text=f"Время: {time_str}")

        if dist_dict:
            cut_m = dist_dict["feed_dist"] / 1000
            rapid_m = dist_dict["rapid_dist"] / 1000
            self.lbl_stat_cut.config(text=f"Рез: {dist_dict['feed_dist']:.0f} мм ({cut_m:.2f} м)")
            self.lbl_stat_rapid.config(text=f"Холостые: {dist_dict['rapid_dist']:.0f} мм ({rapid_m:.2f} м)")
        else:
            self.lbl_stat_cut.config(text="")
            self.lbl_stat_rapid.config(text="")

    def _clear_gen_info(self):
        self.lbl_stat_lines.config(text="")
        self.lbl_stat_time.config(text="")
        self.lbl_stat_cut.config(text="")
        self.lbl_stat_rapid.config(text="")

    def _highlight_gcode(self):
        txt = self.txt_gcode
        for tag in ("g0", "g1", "coord", "feed", "mcode", "comment", "gother"):
            txt.tag_remove(tag, "1.0", tk.END)

        content = txt.get("1.0", tk.END)
        for i, line in enumerate(content.split("\n"), 1):
            sc = line.find(";")
            if sc != -1:
                txt.tag_add("comment", f"{i}.{sc}", f"{i}.end")
                line_code = line[:sc]
            else:
                line_code = line

            for m in re.finditer(r'\bG0\b', line_code):
                txt.tag_add("g0", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r'\bG1\b', line_code):
                txt.tag_add("g1", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r'\bG(?!0\b|1\b)\d+', line_code):
                txt.tag_add("gother", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r'\bM\d+', line_code):
                txt.tag_add("mcode", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r'[XYZ]-?\d+\.?\d*', line_code):
                txt.tag_add("coord", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r'F\d+\.?\d*', line_code):
                txt.tag_add("feed", f"{i}.{m.start()}", f"{i}.{m.end()}")

    def _float(self, var, default):
        try:
            return float(var.get())
        except ValueError:
            return default

    def _int(self, var, default):
        try:
            return int(var.get())
        except ValueError:
            return default

    # ─── Загрузка данных ─────────────────────────────────────────────────

    def _load_contours(self):
        if not self.img_path:
            return

        mode = self.v_mode.get()

        if mode == "Рельеф":
            self._status("Загрузка карты высот...", "#f9e2af")
            try:
                blur = self._int(self.v_blur_relief, 5)
                self.heightmap, self.img_w, self.img_h = load_heightmap(
                    self.img_path, blur_size=blur)
                self.chains = []
                self._status(f"Карта высот: {self.img_w}x{self.img_h} px", "#a6e3a1")
            except Exception as e:
                self._status(f"Ошибка: {e}", "#f38ba8")
                messagebox.showerror("Ошибка", str(e))
                return

            self._update_size_label()
            self._updating_size = True
            self.v_out_w.set(f"{self.img_w:.1f}")
            self.v_out_h.set(f"{self.img_h:.1f}")
            self._updating_size = False

            w = self.canvas.winfo_width() or 420
            h = self.canvas.winfo_height() or 420
            draw_heightmap_preview(self.canvas, self.heightmap, w, h)
        else:
            self._status("Извлечение контуров...", "#f9e2af")
            try:
                self.chains, self.img_w, self.img_h = extract_contours(
                    self.img_path,
                    threshold=self._int(self.v_thresh, 128),
                    invert=self.v_invert.get(),
                    blur_size=self._int(self.v_blur, 3),
                    min_area=self._float(self.v_min_area, 10),
                    epsilon_factor=self._float(self.v_approx, 0.001),
                    smooth_passes=self._int(self.v_smooth_passes, 3),
                    resample_step=self._float(self.v_resample_step, 0.0),
                )
                self.heightmap = None
                self._status(f"Найдено контуров: {len(self.chains)}", "#a6e3a1")
            except Exception as e:
                self._status(f"Ошибка: {e}", "#f38ba8")
                messagebox.showerror("Ошибка", str(e))
                return

            self._update_size_label()
            mn_x, mn_y, mx_x, mx_y = get_bounds(self.chains)
            self._updating_size = True
            self.v_out_w.set(f"{mx_x - mn_x:.1f}")
            self.v_out_h.set(f"{mx_y - mn_y:.1f}")
            self._updating_size = False

            w = self.canvas.winfo_width() or 420
            h = self.canvas.winfo_height() or 420
            draw_preview(self.canvas, self.chains, w, h)

    def _open_image(self):
        path = filedialog.askopenfilename(
            title="Открыть изображение",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.tiff *.tif"),
                       ("Все файлы", "*.*")])
        if not path:
            return
        # Проверка существования файла
        if not os.path.exists(path):
            messagebox.showerror("Ошибка", f"Файл не найден:\n{path}")
            self._status("Ошибка: файл не найден", "#f38ba8")
            return
        self.img_path = path
        self._template_active = False
        self.v_template.set("(нет)")
        try:
            self.lbl_file.config(text=os.path.basename(path))
        except Exception:
            pass
        self._load_contours()

    def _reload_contours(self):
        if self._template_active:
            self._on_template_selected()
            return
        if not self.img_path:
            messagebox.showwarning("Нет файла", "Сначала откройте изображение.")
            return
        self._load_contours()

    # ─── Генерация G-Code ────────────────────────────────────────────────

    def _generate(self):
        mode = self.v_mode.get()
        if mode == "Рельеф":
            self._generate_relief()
        else:
            self._generate_contour()

    def _generate_contour(self):
        if not self.chains:
            messagebox.showwarning("Нет данных",
                                   "Сначала откройте изображение или выберите шаблон.")
            return
        self._status("Генерация G-Code...", "#f9e2af")
        self._set_progress(5)
        try:
            tw = th = None
            try:
                tw = float(self.v_out_w.get()) if self.v_out_w.get().strip() else None
            except ValueError:
                pass
            try:
                th = float(self.v_out_h.get()) if self.v_out_h.get().strip() else None
            except ValueError:
                pass
            
            self._set_progress(10)
            chains = scale_chains(self.chains, tw, th, keep_aspect=self.v_lock.get())

            tool_dia     = self._float(self.v_tool, 3.175)
            simplify_eps = self._float(self.v_simp, 0.0)
            feedrate     = self._float(self.v_feed, 800.0)
            spindle_speed = self._int(self.v_spindle, 15000)

            self._set_progress(25)
            gcode, dist_dict = chains_to_gcode(
                chains=chains, tool_dia=tool_dia, feedrate=feedrate,
                final_depth=self._float(self.v_depth, 2.0),
                num_passes=self._int(self.v_passes, 1),
                bridge_mode=self.v_bridge.get(),
                bridge_size=self._float(self.v_bsize, 3.0),
                simplify_eps=simplify_eps,
                safe_z=self._float(self.v_safe, 5.0),
                spindle_speed=spindle_speed,
            )
            
            self._set_progress(70)
            if tw or th:
                mn_x, mn_y, mx_x, mx_y = get_bounds(chains)
                ow, oh = mx_x - mn_x, mx_y - mn_y
                gcode = f"; Output size: {ow:.2f} x {oh:.2f} mm\n" + gcode

            offset = tool_dia / 2.0
            preview_chains = []
            for c in sort_chains_nearest(chains):
                c = simplify_chain(c, simplify_eps)
                if len(c) < 2:
                    continue
                ocs = offset_chain(c, -offset)
                for oc in ocs:
                    if len(oc) >= 2:
                        preview_chains.append(oc)

            self._set_progress(95)

        except Exception as e:
            self._set_progress(0)
            self._status(f"Ошибка генерации: {e}", "#f38ba8")
            messagebox.showerror("Ошибка", str(e))
            return

        self.gcode = gcode
        self.txt_gcode.delete("1.0", tk.END)
        self.txt_gcode.insert(tk.END, gcode)
        self._highlight_gcode()
        lines_count = gcode.count("\n") + 1
        time_str = format_time_estimate(dist_dict, feedrate)
        self._update_gen_info(lines_count, time_str, feedrate, dist_dict)
        self._status(f"Готово! {lines_count} строк | {time_str}", "#a6e3a1")
        
        self._set_progress(100)
        self.after(800, lambda: self._set_progress(0))

        w = self.canvas.winfo_width() or 420
        h = self.canvas.winfo_height() or 420
        draw_preview(self.canvas, preview_chains, w, h)

    def _generate_relief(self):
        if self.heightmap is None:
            messagebox.showwarning("Нет данных", "Сначала откройте изображение.")
            return
        self._status("Генерация G-Code (рельеф)...", "#f9e2af")
        self._set_progress(5)
        try:
            tw = th = None
            try:
                tw = float(self.v_out_w.get()) if self.v_out_w.get().strip() else None
            except ValueError:
                pass
            try:
                th = float(self.v_out_h.get()) if self.v_out_h.get().strip() else None
            except ValueError:
                pass

            self._set_progress(15)
            output_w = tw or float(self.img_w)
            output_h = th or float(self.img_h)
            tool_dia = self._float(self.v_tool, 3.175)
            feedrate = self._float(self.v_feed, 800.0)
            spindle_speed = self._int(self.v_spindle, 15000)

            self._set_progress(30)
            gcode, dist_dict = heightmap_to_gcode(
                heightmap=self.heightmap, tool_dia=tool_dia,
                stepover_pct=self._float(self.v_stepover, 40.0),
                max_depth=self._float(self.v_depth, 2.0),
                feedrate=feedrate,
                plunge_feed=self._float(self.v_plunge_feed, 300.0),
                safe_z=self._float(self.v_safe, 5.0),
                output_w=output_w, output_h=output_h,
                strategy=self.v_strategy.get(),
                spindle_speed=spindle_speed,
            )
            self._set_progress(95)
        except Exception as e:
            self._set_progress(0)
            self._status(f"Ошибка генерации: {e}", "#f38ba8")
            messagebox.showerror("Ошибка", str(e))
            return

        self.gcode = gcode
        self.txt_gcode.delete("1.0", tk.END)
        self.txt_gcode.insert(tk.END, gcode)
        self._highlight_gcode()
        lines_count = gcode.count("\n") + 1
        time_str = format_time_estimate(dist_dict, feedrate)
        self._update_gen_info(lines_count, time_str, feedrate, dist_dict)
        self._status(f"Готово! {lines_count} строк | {time_str}", "#a6e3a1")
        
        self._set_progress(100)
        self.after(800, lambda: self._set_progress(0))

        w = self.canvas.winfo_width() or 420
        h = self.canvas.winfo_height() or 420
        draw_heightmap_preview(self.canvas, self.heightmap, w, h)

    # ─── Сохранение ──────────────────────────────────────────────────────

    def _save(self):
        if not self.gcode:
            messagebox.showwarning("Нет G-Code", "Сначала сгенерируйте G-Code.")
            return
        if self._template_active:
            default = self.v_template.get().replace(" ", "_") + ".nc"
        elif self.img_path:
            default = os.path.splitext(os.path.basename(self.img_path))[0] + ".nc"
        else:
            default = "output.nc"
        path = filedialog.asksaveasfilename(
            title="Сохранить G-Code",
            defaultextension=".nc",
            initialfile=default,
            filetypes=[("G-Code / NC", "*.nc *.gcode *.tap"),
                       ("Все файлы", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.gcode)
            self._status(f"Сохранено: {os.path.basename(path)}", "#a6e3a1")
        except PermissionError:
            messagebox.showerror("Ошибка", f"Нет прав для записи в файл:\n{path}")
            self._status("Ошибка сохранения: нет прав доступа", "#f38ba8")
        except OSError as e:
            messagebox.showerror("Ошибка", f"Ошибка записи файла:\n{e}")
            self._status(f"Ошибка сохранения: {e}", "#f38ba8")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Неожиданная ошибка:\n{e}")
            self._status(f"Ошибка сохранения: {e}", "#f38ba8")
