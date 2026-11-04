"""Tests for decibulb.cli."""

import pytest

from decibulb import __version__
from decibulb.cli import format_event, main
from decibulb.events import ControlEvent, ControlKind


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (ControlEvent("fader.1", ControlKind.FADER, 0.0), "fader.1    ░░░░░░░░░░░░░░░░░░░░ 0.00"),
        (ControlEvent("master", ControlKind.FADER, 1.0), "master     ████████████████████ 1.00"),
        (ControlEvent("play", ControlKind.BUTTON, 1.0), "play       pressed"),
        (ControlEvent("play", ControlKind.BUTTON, 0.0), "play       released"),
        (ControlEvent("jog", ControlKind.ENCODER, 1.0), "jog        → +1"),
        (ControlEvent("jog", ControlKind.ENCODER, -2.0), "jog        ← -2"),
    ],
)
def test_format_event(event, expected):
    assert format_event(event) == expected


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"decibulb {__version__}"


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "monitor" in capsys.readouterr().out


def test_bad_profile_exits_cleanly(capsys):
    assert main(["monitor", "--profile", "does-not-exist"]) == 1
    assert capsys.readouterr().err.startswith("decibulb: No board profile named")