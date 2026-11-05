"""Tests for decibulb.config."""

from pathlib import Path

import pytest

from decibulb.config import Action, ConfigError, Curve, load_config

EXAMPLE_CONFIG = Path(__file__).parents[1] / "config.example.yaml"

MINIMAL = """
board:
  profile: zoom-r24
devices:
  desk_lamp:
    type: govee_ble
    address: "AA:BB:CC:00:00:01"
controls:
  fader.1:
    action: brightness
    device: desk_lamp
"""


@pytest.fixture
def write_config(tmp_path):
    """Write YAML text to a temporary config.yaml and return its path."""

    def write(text: str) -> Path:
        path = tmp_path / "config.yaml"
        path.write_text(text)
        return path

    return write


def test_example_config_is_valid():
    config = load_config(EXAMPLE_CONFIG)
    assert config.profile == "zoom-r24"
    assert config.controls["master"].action is Action.MASTER_BRIGHTNESS
    assert len(config.controls["fader.5"].devices) == 3


def test_minimal_config(write_config):
    config = load_config(write_config(MINIMAL))
    assert config.port is None
    assert config.devices["desk_lamp"].type == "govee_ble"
    assert config.devices["desk_lamp"].options == {"address": "AA:BB:CC:00:00:01"}
    mapping = config.controls["fader.1"]
    assert (mapping.action, mapping.devices) == (Action.BRIGHTNESS, ("desk_lamp",))
    assert config.brightness_curve is Curve.PERCEPTUAL


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="Copy config.example.yaml"):
        load_config(tmp_path / "config.yaml")


def test_invalid_yaml(write_config):
    with pytest.raises(ConfigError, match="isn't valid YAML"):
        load_config(write_config("board: [unclosed"))


def test_empty_file(write_config):
    with pytest.raises(ConfigError, match="is empty"):
        load_config(write_config(""))


def test_profile_is_required(write_config):
    with pytest.raises(ConfigError, match="board.profile is required"):
        load_config(write_config(MINIMAL.replace("profile: zoom-r24", "port: x")))


def test_device_needs_type(write_config):
    with pytest.raises(ConfigError, match="devices.desk_lamp needs a type"):
        load_config(write_config(MINIMAL.replace("type: govee_ble", "")))


def test_unquoted_numeric_address_is_caught(write_config):
    text = MINIMAL.replace('"AA:BB:CC:00:00:01"', "12:34:56:12:34:56")
    with pytest.raises(ConfigError, match="must be in quotes"):
        load_config(write_config(text))


def test_unknown_action(write_config):
    with pytest.raises(ConfigError, match="Choose from: brightness"):
        load_config(write_config(MINIMAL.replace("action: brightness", "action: dim")))


def test_unknown_device(write_config):
    text = MINIMAL.replace("device: desk_lamp", "device: dsk_lamp")
    with pytest.raises(ConfigError, match="unknown device 'dsk_lamp'. Devices: desk_lamp"):
        load_config(write_config(text))


def test_action_needs_a_device(write_config):
    with pytest.raises(ConfigError, match="brightness needs a device"):
        load_config(write_config(MINIMAL.replace("    device: desk_lamp\n", "")))


def test_master_brightness_takes_no_device(write_config):
    text = MINIMAL.replace("action: brightness", "action: master_brightness")
    with pytest.raises(ConfigError, match="applies to every device"):
        load_config(write_config(text))


def test_linear_brightness_curve(write_config):
    config = load_config(write_config("brightness_curve: linear\n" + MINIMAL))
    assert config.brightness_curve is Curve.LINEAR


def test_unknown_brightness_curve(write_config):
    with pytest.raises(ConfigError, match="brightness_curve must be perceptual or linear"):
        load_config(write_config("brightness_curve: log\n" + MINIMAL))