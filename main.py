#!/usr/bin/env python3
"""PictureToG-Code — Точка входа."""

import sys
import os
import logging
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Глобальный обработчик необработанных исключений."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Не перехватываем KeyboardInterrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.error(
        "Необработанное исключение:",
        exc_info=(exc_type, exc_value, exc_traceback)
    )
    
    # Записываем traceback в файл для отладки
    try:
        error_log_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "error.log"
        )
        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write("\n=== НЕОБРАБОТАННОЕ ИСКЛЮЧЕНИЕ ===\n")
            f.write(f"Тип: {exc_type.__name__}\n")
            f.write(f"Сообщение: {exc_value}\n")
            f.write("Traceback:\n")
            f.write(''.join(traceback.format_tb(exc_traceback)))
            f.write("=" * 40 + "\n")
    except Exception:
        pass


# Устанавливаем глобальный обработчик
sys.excepthook = global_exception_handler


def main():
    """Точка входа в приложение."""
    try:
        from ui.app import CamApp
    except ImportError as e:
        logger.error(f"Ошибка импорта модулей: {e}")
        print(f"\nОшибка: Не удалось загрузить необходимые модули.", file=sys.stderr)
        print(f"Причина: {e}", file=sys.stderr)
        print("\nПопробуйте установить зависимости:", file=sys.stderr)
        print("  pip install -r requirements.txt", file=sys.stderr)
        input("\nНажмите Enter для выхода...")
        return 1
    
    try:
        app = CamApp()

        def on_resize(event):
            try:
                w = app.canvas.winfo_width()
                h = app.canvas.winfo_height()
                if app.v_mode.get() == "Рельеф" and app.heightmap is not None:
                    from ui.preview import draw_heightmap_preview
                    draw_heightmap_preview(app.canvas, app.heightmap, w, h)
                elif app.chains:
                    from ui.preview import draw_preview
                    draw_preview(app.canvas, app.chains, w, h)
            except Exception as e:
                logger.error(f"Ошибка при отрисовке превью: {e}")
        
        app.canvas.bind("<Configure>", on_resize)
        app.mainloop()
        return 0
        
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}")
        print(f"\nОшибка при запуске приложения: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
