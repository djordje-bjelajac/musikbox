from dataclasses import dataclass

from rich.console import Console


@dataclass(frozen=True)
class Viewport:
    """Terminal geometry resolved once per frame.

    The single source of geometric truth for the player panel. Every derived
    dimension carries a floor so string multiplication can never receive a
    negative count, however narrow the terminal gets.
    """

    columns: int
    lines: int

    @staticmethod
    def from_console(console: Console) -> "Viewport":
        """Resolve the viewport from a single ``console.size`` read."""
        size = console.size
        return Viewport(columns=max(1, size.width), lines=max(1, size.height))

    def panel_inner_width(self) -> int:
        """Width available inside the panel borders, which consume 4 cells."""
        return max(1, self.columns - 4)

    def progress_bar_width(self) -> int:
        """Width of the progress bar.

        Budget: panel borders (4), icon and spaces (4), two timestamps (12),
        separating spaces (3).
        """
        return max(10, self.columns - 23)

    def max_queue_rows(self) -> int:
        """Number of queue rows that fit below the panel chrome."""
        return max(3, self.lines - 14)
