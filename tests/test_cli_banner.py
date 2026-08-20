"""Verify terminal banner rendering and CLI-safe output behavior."""

import io
import sys

import pytest

from scrapy_cffi.commands import banner, startproject
from scrapy_cffi.commands.main import main


class _TerminalBuffer(io.StringIO):
    """Provide a deterministic TTY flag for banner tests."""

    def __init__(self, is_terminal: bool) -> None:
        """Initialize the buffer with its simulated terminal capability."""
        super().__init__()
        self._is_terminal = is_terminal

    def isatty(self) -> bool:
        """Return the configured terminal state."""
        return self._is_terminal


def test_render_banner_plain_has_fixed_ascii_wordmark() -> None:
    """Plain output should remain portable and identify the framework."""
    output = banner.render_banner(use_color=False, version="1.2.3")

    assert "\033[" not in output
    assert "async crawler framework" in output
    assert "v1.2.3" in output
    assert len(output.splitlines()) == 7


def test_render_banner_color_uses_reset_sequences() -> None:
    """Colored rows must reset their ANSI state before following output."""
    output = banner.render_banner(use_color=True)

    assert "\033[1;38;5;45m" in output
    assert output.count("\033[0m") >= 7


def test_print_banner_is_quiet_for_redirected_output() -> None:
    """Normal CLI pipelines should not receive decorative output."""
    stream = _TerminalBuffer(is_terminal=False)

    written = banner.print_banner(stream=stream, environ={})

    assert written is False
    assert stream.getvalue() == ""


def test_print_banner_respects_disable_environment() -> None:
    """Interactive users can disable automatic banner rendering."""
    stream = _TerminalBuffer(is_terminal=True)

    written = banner.print_banner(
        stream=stream,
        environ={"SCRAPY_CFFI_NO_BANNER": "1"},
    )

    assert written is False
    assert stream.getvalue() == ""


def test_banner_command_forces_plain_preview(monkeypatch, capsys) -> None:
    """The explicit command should work when stdout is captured or piped."""
    monkeypatch.setattr(sys, "argv", ["scrapy-cffi", "banner", "--no-color"])

    result = main()
    output = capsys.readouterr().out

    assert result == 0
    assert "\033[" not in output
    assert "async crawler framework" in output


def test_short_root_help_starts_with_plain_banner(monkeypatch, capsys) -> None:
    """The concise root-help command should include a portable banner."""
    monkeypatch.setattr(sys, "argv", ["scrapy-cffi", "-h"])

    with pytest.raises(SystemExit) as raised:
        main()
    output = capsys.readouterr().out

    assert raised.value.code == 0
    assert "\033[" not in output
    assert "async crawler framework" in output
    assert "usage: scrapy-cffi" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["-help"],
        ["startproject", "-h"],
        ["demo", "--help"],
        ["test", "-help"],
    ],
)
def test_subcommand_help_does_not_render_banner(
    monkeypatch,
    capsys,
    arguments,
) -> None:
    """Subcommand help should stay compact after users enter a workflow."""
    monkeypatch.setattr(sys, "argv", ["scrapy-cffi", *arguments])

    with pytest.raises(SystemExit) as raised:
        main()
    output = capsys.readouterr().out

    assert raised.value.code == 0
    assert "async crawler framework" not in output
    assert "usage: scrapy-cffi" in output


def test_normal_command_does_not_render_banner(monkeypatch) -> None:
    """Decorative output should stay limited to help and banner commands."""
    banner_calls = []
    monkeypatch.setattr(sys, "argv", ["scrapy-cffi", "startproject", "demo"])
    monkeypatch.setattr(
        banner,
        "print_banner",
        lambda **kwargs: banner_calls.append(kwargs),
    )
    monkeypatch.setattr(startproject, "run", lambda name: None)

    result = main()

    assert result is None
    assert banner_calls == []
