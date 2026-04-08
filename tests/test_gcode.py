"""Unit-тесты для core.gcode."""

import pytest
import math
from core.gcode import chains_to_gcode, heightmap_to_gcode, format_time_estimate, RAPID_RATE


class TestFormatTimeEstimate:
    """Тесты форматирования оценки времени."""

    def test_seconds_only(self):
        """Менее 60 секунд."""
        dist = {"rapid_dist": 100, "feed_dist": 100}
        result = format_time_estimate(dist, feedrate=200, rapid_rate=1000)
        assert "сек" in result

    def test_minutes_and_seconds(self):
        """Минуты и секунды."""
        dist = {"rapid_dist": 1000, "feed_dist": 1000}
        result = format_time_estimate(dist, feedrate=100, rapid_rate=1000)
        assert "мин" in result

    def test_hours(self):
        """Часы."""
        dist = {"rapid_dist": 100000, "feed_dist": 100000}
        result = format_time_estimate(dist, feedrate=100, rapid_rate=1000)
        assert "ч" in result

    def test_zero_feedrate(self):
        """Нулевая подача."""
        dist = {"rapid_dist": 100, "feed_dist": 100}
        result = format_time_estimate(dist, feedrate=0)
        assert "сек" in result

    def test_zero_rapid_rate(self):
        """Нулевая скорость холостого хода."""
        dist = {"rapid_dist": 100, "feed_dist": 100}
        result = format_time_estimate(dist, feedrate=100, rapid_rate=0)
        assert "мин" in result or "сек" in result


class TestChainsToGcode:
    """Тесты генерации G-кода из контуров."""

    def _make_simple_chain(self):
        """Простой квадратный контур."""
        return [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]

    def test_empty_chains_raises(self):
        """Пустой список контуров вызывает ошибку."""
        with pytest.raises(ValueError, match="Список контуров пуст"):
            chains_to_gcode([], tool_dia=3.175, feedrate=800,
                          final_depth=2.0, num_passes=1,
                          bridge_mode=False, bridge_size=3.0,
                          simplify_eps=0, safe_z=5.0)

    def test_negative_tool_dia_raises(self):
        """Отрицательный диаметр фрезы вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            chains_to_gcode(self._make_simple_chain(), tool_dia=-1,
                          feedrate=800, final_depth=2.0, num_passes=1,
                          bridge_mode=False, bridge_size=3.0, simplify_eps=0)

    def test_zero_feedrate_raises(self):
        """Нулевая подача вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            chains_to_gcode(self._make_simple_chain(), tool_dia=3.175,
                          feedrate=0, final_depth=2.0, num_passes=1,
                          bridge_mode=False, bridge_size=3.0, simplify_eps=0)

    def test_negative_depth_raises(self):
        """Отрицательная глубина вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            chains_to_gcode(self._make_simple_chain(), tool_dia=3.175,
                          feedrate=800, final_depth=-2.0, num_passes=1,
                          bridge_mode=False, bridge_size=3.0, simplify_eps=0)

    def test_zero_passes_raises(self):
        """Нулевое число проходов вызывает ошибку."""
        with pytest.raises(ValueError, match=">= 1"):
            chains_to_gcode(self._make_simple_chain(), tool_dia=3.175,
                          feedrate=800, final_depth=2.0, num_passes=0,
                          bridge_mode=False, bridge_size=3.0, simplify_eps=0)

    def test_negative_safe_z_raises(self):
        """Отрицательный Safe Z вызывает ошибку."""
        with pytest.raises(ValueError, match="> 0"):
            chains_to_gcode(self._make_simple_chain(), tool_dia=3.175,
                          feedrate=800, final_depth=2.0, num_passes=1,
                          bridge_mode=False, bridge_size=3.0, simplify_eps=0,
                          safe_z=-5.0)

    def test_negative_simplify_eps_raises(self):
        """Отрицательное упрощение вызывает ошибку."""
        with pytest.raises(ValueError, match=">= 0"):
            chains_to_gcode(self._make_simple_chain(), tool_dia=3.175,
                          feedrate=800, final_depth=2.0, num_passes=1,
                          bridge_mode=False, bridge_size=3.0, simplify_eps=-0.1)

    def test_valid_gcode_has_header(self):
        """Валидный G-код имеет заголовок."""
        gcode, _ = chains_to_gcode(
            self._make_simple_chain(), tool_dia=3.175, feedrate=800,
            final_depth=2.0, num_passes=1, bridge_mode=False,
            bridge_size=3.0, simplify_eps=0, safe_z=5.0
        )
        assert "G21" in gcode  # mm
        assert "G90" in gcode  # absolute
        assert "M03" in gcode  # spindle on
        assert "M30" in gcode  # end

    def test_valid_gcode_has_commands(self):
        """Валидный G-код имеет команды перемещения."""
        gcode, _ = chains_to_gcode(
            self._make_simple_chain(), tool_dia=3.175, feedrate=800,
            final_depth=2.0, num_passes=1, bridge_mode=False,
            bridge_size=3.0, simplify_eps=0, safe_z=5.0
        )
        assert "G0" in gcode  # rapid
        assert "G1" in gcode  # feed

    def test_returns_distance_dict(self):
        """Возвращает словарь с расстояниями."""
        _, dist = chains_to_gcode(
            self._make_simple_chain(), tool_dia=3.175, feedrate=800,
            final_depth=2.0, num_passes=1, bridge_mode=False,
            bridge_size=3.0, simplify_eps=0
        )
        assert "rapid_dist" in dist
        assert "feed_dist" in dist
        assert dist["rapid_dist"] >= 0
        assert dist["feed_dist"] >= 0

    def test_multiple_passes(self):
        """Множество проходов генерируют больше команд."""
        chain = self._make_simple_chain()
        gcode_1pass, _ = chains_to_gcode(
            chain, tool_dia=3.175, feedrate=800, final_depth=2.0,
            num_passes=1, bridge_mode=False, bridge_size=3.0, simplify_eps=0
        )
        gcode_2pass, _ = chains_to_gcode(
            chain, tool_dia=3.175, feedrate=800, final_depth=2.0,
            num_passes=2, bridge_mode=False, bridge_size=3.0, simplify_eps=0
        )
        # 2 прохода должны содержать больше строк
        assert len(gcode_2pass) > len(gcode_1pass)


class TestHeightmapToGcode:
    """Тесты генерации G-кода из карты высот."""

    def _make_heightmap(self, w=10, h=10):
        """Простая карта высот (numpy array)."""
        import numpy as np
        return np.full((h, w), 128, dtype=np.uint8)

    def test_none_heightmap_raises(self):
        """None карта высот вызывает ошибку."""
        with pytest.raises(ValueError, match="не предоставлена"):
            heightmap_to_gcode(None, tool_dia=3.175, stepover_pct=40,
                             max_depth=2.0, feedrate=800, plunge_feed=300,
                             safe_z=5.0, output_w=50, output_h=50)

    def test_negative_tool_dia_raises(self):
        """Отрицательный диаметр фрезы вызывает ошибку."""
        hm = self._make_heightmap()
        with pytest.raises(ValueError, match="> 0"):
            heightmap_to_gcode(hm, tool_dia=-1, stepover_pct=40,
                             max_depth=2.0, feedrate=800, plunge_feed=300,
                             safe_z=5.0, output_w=50, output_h=50)

    def test_invalid_stepover_raises(self):
        """Недопустимое перекрытие вызывает ошибку."""
        hm = self._make_heightmap()
        with pytest.raises(ValueError, match=r"\(0, 100\]"):
            heightmap_to_gcode(hm, tool_dia=3.175, stepover_pct=0,
                             max_depth=2.0, feedrate=800, plunge_feed=300,
                             safe_z=5.0, output_w=50, output_h=50)

        with pytest.raises(ValueError, match=r"\(0, 100\]"):
            heightmap_to_gcode(hm, tool_dia=3.175, stepover_pct=150,
                             max_depth=2.0, feedrate=800, plunge_feed=300,
                             safe_z=5.0, output_w=50, output_h=50)

    def test_negative_depth_raises(self):
        """Отрицательная глубина вызывает ошибку."""
        hm = self._make_heightmap()
        with pytest.raises(ValueError, match="> 0"):
            heightmap_to_gcode(hm, tool_dia=3.175, stepover_pct=40,
                             max_depth=-2.0, feedrate=800, plunge_feed=300,
                             safe_z=5.0, output_w=50, output_h=50)

    def test_invalid_strategy_raises(self):
        """Неизвестная стратегия вызывает ошибку."""
        hm = self._make_heightmap()
        with pytest.raises(ValueError, match="Неизвестная стратегия"):
            heightmap_to_gcode(hm, tool_dia=3.175, stepover_pct=40,
                             max_depth=2.0, feedrate=800, plunge_feed=300,
                             safe_z=5.0, output_w=50, output_h=50,
                             strategy="Неизвестная")

    def test_valid_gcode_has_header(self):
        """Валидный G-код имеет заголовок."""
        hm = self._make_heightmap()
        gcode, _ = heightmap_to_gcode(
            hm, tool_dia=3.175, stepover_pct=40, max_depth=2.0,
            feedrate=800, plunge_feed=300, safe_z=5.0,
            output_w=50, output_h=50
        )
        assert "G21" in gcode
        assert "G90" in gcode
        assert "Relief mode" in gcode

    def test_zigzag_strategy_comment(self):
        """Комментарий стратегии Зигзаг."""
        hm = self._make_heightmap()
        gcode, _ = heightmap_to_gcode(
            hm, tool_dia=3.175, stepover_pct=40, max_depth=2.0,
            feedrate=800, plunge_feed=300, safe_z=5.0,
            output_w=50, output_h=50, strategy="Зигзаг"
        )
        assert "zigzag" in gcode

    def test_unidirectional_strategy_comment(self):
        """Комментарий однонаправленной стратегии."""
        hm = self._make_heightmap()
        gcode, _ = heightmap_to_gcode(
            hm, tool_dia=3.175, stepover_pct=40, max_depth=2.0,
            feedrate=800, plunge_feed=300, safe_z=5.0,
            output_w=50, output_h=50, strategy="Однонаправленный"
        )
        assert "без зигзага" in gcode

    def test_returns_distance_dict(self):
        """Возвращает словарь с расстояниями."""
        hm = self._make_heightmap()
        _, dist = heightmap_to_gcode(
            hm, tool_dia=3.175, stepover_pct=40, max_depth=2.0,
            feedrate=800, plunge_feed=300, safe_z=5.0,
            output_w=50, output_h=50
        )
        assert "rapid_dist" in dist
        assert "feed_dist" in dist
