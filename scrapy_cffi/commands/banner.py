"""Render the dependency-free scrapy-cffi terminal banner."""

import os
import sys
from typing import Mapping, Optional, TextIO, Tuple

from .._version import __version__


_GLYPHS = {
    "S": (" ####", "#    ", " ### ", "    #", "#### "),
    "C": (" ####", "#    ", "#    ", "#    ", " ####"),
    "R": ("#### ", "#   #", "#### ", "#  # ", "#   #"),
    "A": (" ### ", "#   #", "#####", "#   #", "#   #"),
    "P": ("#### ", "#   #", "#### ", "#    ", "#    "),
    "Y": ("#   #", " # # ", "  #  ", "  #  ", "  #  "),
    "F": ("#####", "#    ", "#### ", "#    ", "#    "),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "#####"),
    "-": ("     ", "     ", "#####", "     ", "     "),
}
_WORDMARK = "SCRAPY-CFFI"
_PALETTE = (45, 39, 63, 99, 135)
_RESET = "\033[0m"


def _wordmark_lines() -> Tuple[str, ...]:
    """Build the five-row ASCII wordmark from fixed-width glyphs."""
    return tuple(
        "  " + " ".join(_GLYPHS[character][row] for character in _WORDMARK)
        for row in range(5)
    )


def render_banner(use_color: bool = True, version: str = __version__) -> str:
    """Return the banner with optional ANSI 256-color row gradients."""
    rows = _wordmark_lines()
    if use_color:
        rows = tuple(
            "\033[1;38;5;%dm%s%s" % (color, row, _RESET)
            for color, row in zip(_PALETTE, rows)
        )
        accent = "\033[38;5;45m"
        muted = "\033[38;5;244m"
        detail = "%s[ async worker kernel ]%s  %sv%s%s" % (
            accent,
            _RESET,
            muted,
            version,
            _RESET,
        )
    else:
        detail = "[ async worker kernel ]  v%s" % version
    return "\n".join(rows + ("", "  " + detail))


def _color_enabled(stream: TextIO, environ: Mapping[str, str]) -> bool:
    """Return whether ANSI color is appropriate for the current terminal."""
    return bool(
        stream.isatty()
        and "NO_COLOR" not in environ
        and environ.get("CLICOLOR") != "0"
        and environ.get("TERM", "").lower() != "dumb"
    )


def print_banner(
    stream: Optional[TextIO] = None,
    environ: Optional[Mapping[str, str]] = None,
    force: bool = False,
    use_color: Optional[bool] = None,
) -> bool:
    """Print the banner when interactive or explicitly forced.

    Returns ``True`` when output was written. Non-forced calls stay quiet for
    redirected output and honor ``SCRAPY_CFFI_NO_BANNER``; exact root ``-h``
    and the explicit ``banner`` command pass ``force=True``.
    """
    output = sys.stdout if stream is None else stream
    environment = os.environ if environ is None else environ
    disabled = environment.get("SCRAPY_CFFI_NO_BANNER", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not force and (disabled or not output.isatty()):
        return False
    color = (
        _color_enabled(output, environment)
        if use_color is None
        else use_color
    )
    output.write(render_banner(use_color=color))
    output.write("\n\n")
    return True


__all__ = ["print_banner", "render_banner"]
