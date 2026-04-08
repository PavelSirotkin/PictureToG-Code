"""Unit-тесты для core.validators."""

import pytest
from core.validators import InputValidator


class TestValidateFloat:
    """Тесты валидации float значений."""

    def test_valid_positive_float(self):
        ok, val, err = InputValidator.validate_float("3.14", name="Тест")
        assert ok is True
        assert val == pytest.approx(3.14)
        assert err == ""

    def test_valid_negative_float(self):
        ok, val, err = InputValidator.validate_float("-2.5", name="Тест", allow_negative=True)
        assert ok is True
        assert val == pytest.approx(-2.5)

    def test_valid_integer_as_float(self):
        ok, val, err = InputValidator.validate_float("5", name="Тест")
        assert ok is True
        assert val == pytest.approx(5.0)

    def test_empty_string(self):
        ok, val, err = InputValidator.validate_float("", name="Тест")
        assert ok is False
        assert val == 0.0
        assert "пустое" in err

    def test_invalid_characters(self):
        ok, val, err = InputValidator.validate_float("abc", name="Тест")
        assert ok is False
        assert "недопустимые символы" in err

    def test_negative_not_allowed(self):
        ok, val, err = InputValidator.validate_float("-1.5", name="Тест")
        assert ok is False
        assert "отрицательное" in err

    def test_zero_not_allowed(self):
        ok, val, err = InputValidator.validate_float("0", name="Тест", allow_zero=False)
        assert ok is False
        assert "нулевое" in err

    def test_below_minimum(self):
        ok, val, err = InputValidator.validate_float("0.5", name="Тест", min_val=1.0)
        assert ok is False
        assert "меньше минимума" in err

    def test_above_maximum(self):
        ok, val, err = InputValidator.validate_float("10.5", name="Тест", max_val=10.0)
        assert ok is False
        assert "больше максимума" in err

    def test_valid_with_bounds(self):
        ok, val, err = InputValidator.validate_float("5.0", name="Тест", min_val=1.0, max_val=10.0)
        assert ok is True
        assert val == pytest.approx(5.0)

    def test_whitespace_stripping(self):
        ok, val, err = InputValidator.validate_float("  3.14  ", name="Тест")
        assert ok is True
        assert val == pytest.approx(3.14)


class TestValidateInt:
    """Тесты валидации int значений."""

    def test_valid_positive_int(self):
        ok, val, err = InputValidator.validate_int("42", name="Тест")
        assert ok is True
        assert val == 42

    def test_valid_negative_int(self):
        ok, val, err = InputValidator.validate_int("-5", name="Тест", allow_negative=True)
        assert ok is True
        assert val == -5

    def test_empty_string(self):
        ok, val, err = InputValidator.validate_int("", name="Тест")
        assert ok is False
        assert val == 0
        assert "пустое" in err

    def test_float_not_allowed(self):
        ok, val, err = InputValidator.validate_int("3.14", name="Тест")
        assert ok is False
        assert "целые числа" in err

    def test_invalid_characters(self):
        ok, val, err = InputValidator.validate_int("abc", name="Тест")
        assert ok is False
        assert "целые числа" in err

    def test_negative_not_allowed(self):
        ok, val, err = InputValidator.validate_int("-10", name="Тест")
        assert ok is False
        assert "отрицательное" in err

    def test_zero_not_allowed(self):
        ok, val, err = InputValidator.validate_int("0", name="Тест", allow_zero=False)
        assert ok is False
        assert "нулевое" in err

    def test_below_minimum(self):
        ok, val, err = InputValidator.validate_int("0", name="Тест", min_val=1)
        assert ok is False
        assert "меньше минимума" in err

    def test_above_maximum(self):
        ok, val, err = InputValidator.validate_int("100", name="Тест", max_val=50)
        assert ok is False
        assert "больше максимума" in err

    def test_valid_with_bounds(self):
        ok, val, err = InputValidator.validate_int("25", name="Тест", min_val=10, max_val=50)
        assert ok is True
        assert val == 25

    def test_whitespace_stripping(self):
        ok, val, err = InputValidator.validate_int("  42  ", name="Тест")
        assert ok is True
        assert val == 42
