"""Tests for decibulb.cli."""

from unittest import mock

import pytest

from decibulb import __version__, cli
from decibulb.cli import format_event, main
from decibulb.events import ControlEvent, ControlKind


def fake_light(name, address, rssi):
    light = mock.Mock(sku="H6008", address=address, rssi=rssi)
    light.name = name  # Mock(name=...) is reserved, so set it afterward.
    return light


LIGHTS = [
    fake_light("ihoment_H6008_0002", "AA:BB:CC:00:00:02", -52),
    fake_light("ihoment_H6008_0001", "AA:BB:CC:00:00:01", -40),
    fake_light("ihoment_H6008_0003", "AA:BB:CC:00:00:03", None),
]


class FakeBulb:
    """Stands in for GoveeBleBulb and records which lights were blinked."""

    blinked: list[str] = []

    def __init__(self, name, address):
        self.name = name

    async def __aenter__(self):
        FakeBulb.blinked.append(self.name)
        return self

    async def __aexit__(self, *exc_info):
        pass

    async def set_power(self, on):
        pass

    async def set_brightness(self, level):
        pass


@pytest.fixture
def lights(monkeypatch):
    """Make discover_bulbs() return LIGHTS without scanning."""
    monkeypatch.setattr(cli, "discover_bulbs", mock.AsyncMock(return_value=LIGHTS))


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
    out = capsys.readouterr().out
    assert "monitor" in out
    assert "discover" in out
    assert "run" in out


def test_bad_profile_exits_cleanly(capsys):
    assert main(["monitor", "--profile", "does-not-exist"]) == 1
    assert capsys.readouterr().err.startswith("decibulb: No board profile named")


def test_discover_prints_sorted_table(lights, capsys):
    assert main(["discover", "--timeout", "3"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Scanning for Govee lights for 3 seconds..."
    table = [line for line in lines if line.startswith("H6008")]
    assert [line.split()[2] for line in table] == [
        "ihoment_H6008_0001",
        "ihoment_H6008_0002",
        "ihoment_H6008_0003",
    ]
    assert table[0].endswith("-40 dBm")
    assert table[2].endswith("?")
    assert lines[-1] == "Found 3 lights."


def test_discover_with_no_lights(monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover_bulbs", mock.AsyncMock(return_value=[]))
    assert main(["discover"]) == 0
    assert "No lights found" in capsys.readouterr().out


def test_discover_blink_prompts_between_lights_only(lights, monkeypatch):
    FakeBulb.blinked = []
    monkeypatch.setattr(cli, "GoveeBleBulb", FakeBulb)
    monkeypatch.setattr(cli, "BLINK_STEP_SECONDS", 0)
    fake_input = mock.Mock(return_value="")
    monkeypatch.setattr("builtins.input", fake_input)

    assert main(["discover", "--blink"]) == 0
    assert FakeBulb.blinked == ["ihoment_H6008_0001", "ihoment_H6008_0002", "ihoment_H6008_0003"]
    assert fake_input.call_count == len(LIGHTS) - 1


def test_discover_bluetooth_off_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "discover_bulbs", mock.AsyncMock(side_effect=OSError("Bluetooth is unavailable: off"))
    )
    assert main(["discover"]) == 1
    assert capsys.readouterr().err == "decibulb: Bluetooth is unavailable: off\n"
    

def test_run_without_config_exits_cleanly(tmp_path, capsys):
    assert main(["run", "--config", str(tmp_path / "config.yaml")]) == 1
    assert "Copy config.example.yaml" in capsys.readouterr().err