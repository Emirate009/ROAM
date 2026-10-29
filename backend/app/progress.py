"""Terminal progress bar for scenario runs.

Bellhop gives no progress of its own, so the bar advances by stage
(bathymetry, environment, Bellhop, ...) and shows the elapsed time, which
keeps ticking while Bellhop runs.
"""

import sys
import time

BAR_WIDTH = 30


class RunProgress:
    """Usage:

        with RunProgress("Standard run", total_steps=5) as progress:
            progress.step("Bathymetry")   # starts a step, completing the previous one
            ...
            progress.refresh()            # redraw the elapsed time mid-step
    """

    def __init__(self, title, total_steps, stream=None):
        self.title = title
        self.total_steps = total_steps
        self.stream = stream or sys.stderr
        # Redraw in place on a terminal; plain one-line-per-step output otherwise
        # (e.g. when the log is piped to a file).
        self.interactive = self.stream.isatty()
        self._completed = 0
        self._status = "Starting"
        self._start = time.monotonic()

    def __enter__(self):
        self.stream.write(f"{self.title}\n")
        self._draw()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._completed = self.total_steps
            self._status = "Done"
        else:
            self._status = f"Failed ({exc_type.__name__})"
        self._draw(final=True)
        return False

    def step(self, status):
        """Start a new step, marking the current one complete."""
        if self._status != "Starting":
            self._completed = min(self._completed + 1, self.total_steps)
        self._status = status
        self._draw()

    def refresh(self):
        """Redraw the bar so the elapsed time keeps moving during a long step."""
        if self.interactive:
            self._draw()

    def _draw(self, final=False):
        fraction = self._completed / self.total_steps if self.total_steps else 1.0
        filled = int(round(BAR_WIDTH * fraction))
        bar = "#" * filled + "-" * (BAR_WIDTH - filled)
        elapsed = int(time.monotonic() - self._start)
        line = (
            f"  [{bar}] {fraction:4.0%}  {self._status}  "
            f"({elapsed // 60:02d}:{elapsed % 60:02d})"
        )
        if self.interactive:
            # \033[K clears leftovers from a longer previous status.
            self.stream.write(f"\r{line}\033[K" + ("\n" if final else ""))
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
