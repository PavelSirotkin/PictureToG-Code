"""Unit-тесты для core.templates."""

import pytest
import math
from core.templates import (
    generate_template, TEMPLATES,
    _circle_pts, _rounded_rect_pts,
    KEYCHAIN_RECT_CORNER_RATIO, KEYCHAIN_RECT_HOLE_RATIO,
    KEYCHAIN_CIRCLE_HOLE_RATIO, FRAME_INSET_RATIO,
    STAR_INNER_RADIUS_RATIO, HEART_POINTS, CIRCLE_SEGMENTS, ARC_SEGMENTS,
)


class TestConstants:
    """Тесты констант шаблонов."""

    def test_keychain_rect_corner_ratio(self):
        assert KEYCHAIN_RECT_CORNER_RATIO == pytest.approx(0.12)

    def test_keychain_rect_hole_ratio(self):
        assert KEYCHAIN_RECT_HOLE_RATIO == pytest.approx(0.08)

    def test_keychain_circle_hole_ratio(self):
        assert KEYCHAIN_CIRCLE_HOLE_RATIO == pytest.approx(0.15)

    def test_frame_inset_ratio(self):
        assert FRAME_INSET_RATIO == pytest.approx(0.12)

    def test_star_inner_radius_ratio(self):
        assert STAR_INNER_RADIUS_RATIO == pytest.approx(0.38)

    def test_heart_points(self):
        assert HEART_POINTS == 100

    def test_circle_segments(self):
        assert CIRCLE_SEGMENTS == 64

    def test_arc_segments(self):
        assert ARC_SEGMENTS == 8


class TestCirclePts:
    """Тесты генерации точек окружности."""

    def test_circle_point_count(self):
        """Количество точек = n + 1."""
        pts = _circle_pts(0, 0, 10, n=32)
        assert len(pts) == 33

    def test_circle_default_segments(self):
        """По умолчанию используется CIRCLE_SEGMENTS."""
        pts = _circle_pts(0, 0, 10)
        assert len(pts) == CIRCLE_SEGMENTS + 1

    def test_circle_center(self):
        """Точки окружности вокруг центра."""
        cx, cy, r = 50, 50, 10
        pts = _circle_pts(cx, cy, r, n=64)
        for x, y in pts:
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            assert abs(dist - r) < 0.01

    def test_circle_closed(self):
        """Окружность замкнута (первая == последняя)."""
        pts = _circle_pts(0, 0, 10, n=32)
        assert pts[0] == pytest.approx(pts[-1])


class TestRoundedRectPts:
    """Тесты генерации точек скругленного прямоугольника."""

    def test_rect_point_count(self):
        """Количество точек = 4 * (n_arc + 1) + 1."""
        pts = _rounded_rect_pts(100, 50, 10, n_arc=8)
        expected = 4 * (ARC_SEGMENTS + 1) + 1
        assert len(pts) == expected

    def test_rect_closed(self):
        """Прямоугольник замкнут."""
        pts = _rounded_rect_pts(100, 50, 10)
        assert pts[0] == pytest.approx(pts[-1])

    def test_rect_radius_clamped(self):
        """Радиус не превышает половину размера."""
        # Радиус больше половины ширины
        pts = _rounded_rect_pts(50, 100, 100)
        # Должен работать без ошибок
        assert len(pts) > 0


class TestGenerateTemplate:
    """Тесты генерации шаблонов."""

    def test_templates_list_not_empty(self):
        assert len(TEMPLATES) > 1

    def test_no_template_selected(self):
        """'(нет)' возвращает пустой список."""
        chains, w, h = generate_template("(нет)", 50, 30)
        assert chains == []
        assert w == 0
        assert h == 0

    def test_unknown_template(self):
        """Неизвестный шаблон возвращает пустой список."""
        chains, w, h = generate_template("Неизвестный", 50, 30)
        assert chains == []
        assert w == 0
        assert h == 0

    def test_negative_width_raises(self):
        """Отрицательная ширина вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            generate_template("Звезда", -10, 30)

    def test_negative_height_raises(self):
        """Отрицательная высота вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            generate_template("Звезда", 50, -10)

    def test_zero_width_raises(self):
        """Нулевая ширина вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            generate_template("Звезда", 0, 30)


class TestSpecificTemplates:
    """Тесты конкретных шаблонов."""

    def test_rect_keychain_has_outer_and_hole(self):
        """Прямоугольный брелок имеет внешний контур и отверстие."""
        chains, w, h = generate_template("Брелок прямоугольный", 50, 30)
        assert len(chains) == 2  # внешний + отверстие
        assert len(chains[0]) > 4  # внешний контур
        assert len(chains[1]) > 4  # отверстие

    def test_circle_keychain_has_outer_and_hole(self):
        """Круглый брелок имеет внешний контур и отверстие."""
        chains, w, h = generate_template("Брелок круглый", 40, 40)
        assert len(chains) == 2

    def test_frame_has_outer_and_inner(self):
        """Табличка имеет внешнюю и внутреннюю рамки."""
        chains, w, h = generate_template("Табличка с рамкой", 60, 40)
        assert len(chains) == 2

    def test_star_is_closed(self):
        """Звезда замкнута."""
        chains, w, h = generate_template("Звезда", 50, 50)
        assert len(chains) == 1
        star = chains[0]
        assert star[0] == pytest.approx(star[-1])

    def test_heart_is_closed(self):
        """Сердце замкнуто."""
        chains, w, h = generate_template("Сердце", 50, 50)
        assert len(chains) == 1
        heart = chains[0]
        assert heart[0] == pytest.approx(heart[-1])

    def test_templates_fit_within_bounds(self):
        """Все шаблоны помещаются в заданные размеры."""
        test_cases = [
            ("Брелок прямоугольный", 50, 30),
            ("Брелок круглый", 40, 40),
            ("Табличка с рамкой", 60, 40),
            ("Звезда", 50, 50),
            ("Сердце", 50, 50),
        ]
        for name, w, h in test_cases:
            chains, _, _ = generate_template(name, w, h)
            for chain in chains:
                for x, y in chain:
                    assert 0 <= x <= w + 1, f"{name}: x={x} вне [0, {w}]"
                    assert 0 <= y <= h + 1, f"{name}: y={y} вне [0, {h}]"
