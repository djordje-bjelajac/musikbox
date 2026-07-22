from typing import cast

from rich.console import Console, ConsoleDimensions

from musikbox.cli.player.viewport import Viewport


class _CountingConsole:
    """Console double that records how many times `size` is read."""

    def __init__(self, width: int, height: int) -> None:
        self._width = width
        self._height = height
        self.size_reads = 0

    @property
    def size(self) -> ConsoleDimensions:
        self.size_reads += 1
        return ConsoleDimensions(self._width, self._height)


def test_from_console_reads_size_exactly_once() -> None:
    console = _CountingConsole(100, 30)

    viewport = Viewport.from_console(cast(Console, console))

    assert console.size_reads == 1
    assert viewport.columns == 100
    assert viewport.lines == 30


def test_from_console_with_zero_size_clamps_to_one() -> None:
    console = _CountingConsole(0, 0)

    viewport = Viewport.from_console(cast(Console, console))

    assert viewport.columns == 1
    assert viewport.lines == 1


def test_from_console_with_negative_size_clamps_to_one() -> None:
    console = _CountingConsole(-5, -20)

    viewport = Viewport.from_console(cast(Console, console))

    assert viewport.columns == 1
    assert viewport.lines == 1


def test_derived_widths_never_negative_at_one_column() -> None:
    viewport = Viewport(columns=1, lines=1)

    assert viewport.panel_inner_width() >= 1
    assert viewport.progress_bar_width() >= 1
    assert viewport.queue_rows(14) >= 0


def test_progress_bar_width_floors_at_ten() -> None:
    assert Viewport(columns=20, lines=40).progress_bar_width() == 10


def test_queue_rows_subtracts_chrome_from_terminal_height() -> None:
    assert Viewport(columns=80, lines=40).queue_rows(14) == 26
    assert Viewport(columns=80, lines=40).queue_rows(0) == 40


def test_queue_rows_floors_at_zero_when_chrome_exceeds_height() -> None:
    assert Viewport(columns=80, lines=5).queue_rows(14) == 0
    assert Viewport(columns=80, lines=14).queue_rows(14) == 0
    assert Viewport(columns=80, lines=1).queue_rows(999) == 0


def test_panel_inner_width_floors_at_one() -> None:
    assert Viewport(columns=2, lines=40).panel_inner_width() == 1


def test_derived_values_match_previous_formulas_at_typical_size() -> None:
    viewport = Viewport(columns=120, lines=40)

    assert viewport.panel_inner_width() == 116
    assert viewport.progress_bar_width() == 97
    assert viewport.queue_rows(14) == 26


def test_viewport_is_frozen_and_hashable() -> None:
    assert Viewport(columns=80, lines=24) == Viewport(columns=80, lines=24)
    assert hash(Viewport(columns=80, lines=24)) == hash(Viewport(columns=80, lines=24))
