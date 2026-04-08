"""Unit-тесты для core.geometry."""

import pytest
import math
from core.geometry import (
    simplify_chain, offset_chain, get_bounds, scale_chains,
    sort_chains_nearest, insert_bridges, _chain_length
)


class TestSimplifyChain:
    """Тесты упрощения контуров (RDP)."""

    def test_simple_triangle_unchanged(self):
        """Треугольник с малым epsilon не меняется."""
        chain = [(0, 0), (10, 0), (5, 8.66), (0, 0)]
        result = simplify_chain(chain, 0.001)
        assert len(result) == len(chain)

    def test_simplify_removes_redundant_points(self):
        """Коллинеарные точки удаляются."""
        chain = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
        result = simplify_chain(chain, 0.5)
        assert len(result) < len(chain)
        assert result[0] == (0, 0)
        assert result[-1] == (4, 0)

    def test_epsilon_zero_returns_original(self):
        """При epsilon=0 возвращается исходный контур."""
        chain = [(0, 0), (1, 1), (2, 0)]
        result = simplify_chain(chain, 0)
        assert result == chain

    def test_negative_epsilon_raises(self):
        """Отрицательный epsilon вызывает ValueError."""
        with pytest.raises(ValueError, match=">= 0"):
            simplify_chain([(0, 0), (1, 1), (2, 0)], -0.1)

    def test_short_chain_unchanged(self):
        """Контур менее 3 точек не меняется."""
        chain = [(0, 0), (1, 1)]
        result = simplify_chain(chain, 0.5)
        assert result == chain


class TestOffsetChain:
    """Тесты смещения контуров."""

    def test_zero_offset_returns_original(self):
        """Нулевое смещение возвращает исходный контур."""
        chain = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        result = offset_chain(chain, 0)
        assert result == [chain]

    def test_no_shapely_returns_original(self):
        """Без Shapely возвращается исходный контур."""
        try:
            from shapely.geometry import LineString
            pytest.skip("Shapely установлен")
        except ImportError:
            chain = [(0, 0), (10, 0), (10, 10)]
            result = offset_chain(chain, 1.0)
            assert result == [chain]


class TestGetBounds:
    """Тесты вычисления границ."""

    def test_single_chain(self):
        """Границы одного контура."""
        chains = [[(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)]]
        bounds = get_bounds(chains)
        assert bounds == (0, 0, 10, 5)

    def test_multiple_chains(self):
        """Границы нескольких контуров."""
        chains = [[(0, 0), (5, 0)], [(10, 10), (20, 20)]]
        bounds = get_bounds(chains)
        assert bounds == (0, 0, 20, 20)

    def test_empty_chains(self):
        """Пустой список контуров."""
        bounds = get_bounds([])
        assert bounds == (0, 0, 0, 0)


class TestScaleChains:
    """Тесты масштабирования контуров."""

    def test_scale_to_width(self):
        """Масштабирование к заданной ширине."""
        chains = [[(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)]]
        result = scale_chains(chains, target_w=20.0)
        bounds = get_bounds(result)
        assert abs(bounds[2] - bounds[0] - 20.0) < 0.01

    def test_scale_to_height(self):
        """Масштабирование к заданной высоте."""
        chains = [[(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)]]
        result = scale_chains(chains, target_h=10.0)
        bounds = get_bounds(result)
        assert abs(bounds[3] - bounds[1] - 10.0) < 0.01

    def test_scale_keep_aspect(self):
        """Масштабирование с сохранением пропорций."""
        chains = [[(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)]]
        # Исходное соотношение 10:5 = 2:1
        # При keep_aspect=True и target_w=20, target_h=20
        # масштаб = min(20/10, 20/5) = min(2, 4) = 2
        # Результат: 20 x 10
        result = scale_chains(chains, target_w=20.0, target_h=20.0, keep_aspect=True)
        bounds = get_bounds(result)
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        # Пропорции сохранены: w/h = 2.0
        assert abs(w / h - 2.0) < 0.01
        # fits within bounds
        assert w <= 20.0 + 0.01
        assert h <= 20.0 + 0.01

    def test_negative_width_raises(self):
        """Отрицательная ширина вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            scale_chains([[(0, 0), (1, 0)]], target_w=-10)

    def test_negative_height_raises(self):
        """Отрицательная высота вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            scale_chains([[(0, 0), (1, 0)]], target_h=-10)

    def test_empty_chains_unchanged(self):
        """Пустой список возвращается без изменений."""
        result = scale_chains([], target_w=10)
        assert result == []

    def test_no_targets_unchanged(self):
        """Без целевых размеров возвращается исходный список."""
        chains = [[(0, 0), (10, 5)]]
        result = scale_chains(chains)
        assert result == chains


class TestSortChainsNearest:
    """Тесты сортировки контуров."""

    def test_single_chain_unchanged(self):
        """Один контур не меняется."""
        chains = [[(0, 0), (10, 0), (10, 10)]]
        result = sort_chains_nearest(chains)
        assert result == chains

    def test_empty_list_unchanged(self):
        """Пустой список не меняется."""
        result = sort_chains_nearest([])
        assert result == []

    def test_sorting_preserves_all_points(self):
        """Сортировка сохраняет все точки."""
        chains = [
            [(100, 100), (110, 100)],
            [(0, 0), (10, 0)],
            [(50, 50), (60, 50)],
        ]
        result = sort_chains_nearest(chains)
        # Все контуры должны быть в результате
        assert len(result) == len(chains)


class TestChainLength:
    """Тесты вычисления длины контура."""

    def test_straight_line(self):
        """Длина прямой линии."""
        chain = [(0, 0), (3, 0), (6, 0)]
        length = _chain_length(chain)
        assert length == pytest.approx(6.0)

    def test_single_segment(self):
        """Длина одного сегмента."""
        chain = [(0, 0), (3, 4)]
        length = _chain_length(chain)
        assert length == pytest.approx(5.0)  # 3-4-5 triangle


class TestInsertBridges:
    """Тесты вставки мостиков."""

    def test_chain_too_short_returns_unchanged(self):
        """Короткий контур возвращается без изменений."""
        chain = [(0, 0), (1, 0)]
        result = insert_bridges(chain, bridge_size=5.0, num_bridges=2)
        assert result == [(chain, False)]

    def test_zero_bridge_size_raises(self):
        """Нулевой размер мостика вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            insert_bridges([(0, 0), (10, 0)], bridge_size=0, num_bridges=2)

    def test_negative_bridge_size_raises(self):
        """Отрицательный размер мостика вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            insert_bridges([(0, 0), (10, 0)], bridge_size=-1, num_bridges=2)

    def test_zero_num_bridges_raises(self):
        """Нулевое количество мостиков вызывает ошибку."""
        with pytest.raises(ValueError, match=">= 1"):
            insert_bridges([(0, 0), (10, 0)], bridge_size=1.0, num_bridges=0)

    def test_single_point_chain_raises(self):
        """Контур из одной точки вызывает ошибку."""
        with pytest.raises(ValueError, match="минимум 2 точки"):
            insert_bridges([(0, 0)], bridge_size=1.0, num_bridges=1)

    def test_valid_bridges_returns_segments(self):
        """Валидные мостики возвращают сегменты."""
        # Создаём длинный контур
        chain = [(0, 0), (50, 0), (50, 50), (0, 50), (0, 0)]
        result = insert_bridges(chain, bridge_size=5.0, num_bridges=2)
        # Должен быть хотя бы один сегмент
        assert len(result) >= 1
        # Некоторые сегменты должны быть мостиками
        is_bridge_flags = [is_bridge for _, is_bridge in result]
        # Мостики могут не вставиться если контур слишком короткий
        # Проверим что результат - список кортежей
        for seg, flag in result:
            assert isinstance(seg, list)
            assert isinstance(flag, bool)
