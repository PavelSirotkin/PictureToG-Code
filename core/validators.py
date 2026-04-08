"""Модуль валидации пользовательского ввода."""

import re


class InputValidator:
    """Утилиты для валидации пользовательского ввода."""

    @staticmethod
    def validate_float(value, name="Значение", allow_negative=False, allow_zero=True,
                       min_val=None, max_val=None):
        value = value.strip()
        if not value:
            return False, 0.0, f"{name}: пустое значение"
        if not re.match(r'^-?\d*\.?\d*$', value):
            return False, 0.0, f"{name}: недопустимые символы (допускаются только цифры)"
        try:
            val = float(value)
        except ValueError:
            return False, 0.0, f"{name}: некорректное число"
        if not allow_negative and val < 0:
            return False, 0.0, f"{name}: отрицательное значение недопустимо"
        if not allow_zero and val == 0:
            return False, 0.0, f"{name}: нулевое значение недопустимо"
        if min_val is not None and val < min_val:
            return False, 0.0, f"{name}: значение меньше минимума ({min_val})"
        if max_val is not None and val > max_val:
            return False, 0.0, f"{name}: значение больше максимума ({max_val})"
        return True, val, ""

    @staticmethod
    def validate_int(value, name="Значение", allow_negative=False, allow_zero=True,
                     min_val=None, max_val=None):
        value = value.strip()
        if not value:
            return False, 0, f"{name}: пустое значение"
        if not re.match(r'^-?\d+$', value):
            return False, 0, f"{name}: допускаются только целые числа"
        try:
            val = int(value)
        except ValueError:
            return False, 0, f"{name}: некорректное целое число"
        if not allow_negative and val < 0:
            return False, 0, f"{name}: отрицательное значение недопустимо"
        if not allow_zero and val == 0:
            return False, 0, f"{name}: нулевое значение недопустимо"
        if min_val is not None and val < min_val:
            return False, 0, f"{name}: значение меньше минимума ({min_val})"
        if max_val is not None and val > max_val:
            return False, 0, f"{name}: значение больше максимума ({max_val})"
        return True, val, ""
