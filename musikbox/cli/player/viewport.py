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

    def queue_rows(self, chrome_lines: int) -> int:
        """Number of queue rows left once the panel chrome is paid for.

        ``chrome_lines`` counts every row the panel spends on something other
        than the queue, borders included. Counting the chrome beats guessing
        at it: the header grows and shrinks with the track, and any row the
        budget forgets is a row that pushes the bottom border off screen.

        Floors at zero, not one. On a terminal too short for both, the
        controls footer is worth more than a single stray queue entry, and
        forcing that entry in would only crop the footer off the bottom.
        """
        return max(0, self.lines - chrome_lines)
