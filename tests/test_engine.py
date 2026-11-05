"""Tests for decibulb.engine."""

import pytest

from decibulb.config import Action, ControlMapping
from decibulb.devices.base import Capability
from decibulb.devices.fake import FakeDevice
from decibulb.engine import Engine, hue_to_rgb, level_to_kelvin
from decibulb.events import ControlEvent, ControlKind


class RecordingQueue:
    """Stands in for DeviceQueue and records every submitted command."""

    def __init__(self, device):
        self.device = device
        self.sent = []

    def submit(self, capability, value):
        self.sent.append((capability, value))


class PowerOnlyDevice(FakeDevice):
    capabilities = frozenset({Capability.POWER})


CONTROLS = {
    "fader.1": ControlMapping("fader.1", Action.BRIGHTNESS, ("desk",)),
    "fader.2": ControlMapping("fader.2", Action.BRIGHTNESS, ("corner",)),
    "fader.5": ControlMapping("fader.5", Action.COLOR, ("desk", "corner")),
    "fader.6": ControlMapping("fader.6", Action.COLOR_TEMP, ("desk",)),
    "master": ControlMapping("master", Action.MASTER_BRIGHTNESS),
    "solo.1": ControlMapping("solo.1", Action.TOGGLE_POWER, ("desk",)),
    "solo.8": ControlMapping("solo.8", Action.TOGGLE_POWER, ("desk", "corner")),
    "f1": ControlMapping("f1", Action.BRIGHTNESS, ("desk",)),
    "fader.8": ControlMapping("fader.8", Action.TOGGLE_POWER, ("plug",)),
}


@pytest.fixture
def setup():
    queues = {
        "desk": RecordingQueue(FakeDevice("desk")),
        "corner": RecordingQueue(FakeDevice("corner")),
        "plug": RecordingQueue(PowerOnlyDevice("plug")),
    }
    return Engine(CONTROLS, queues), queues


def fader(name, value):
    return ControlEvent(name, ControlKind.FADER, value)


def press(name):
    return ControlEvent(name, ControlKind.BUTTON, 1.0)


def release(name):
    return ControlEvent(name, ControlKind.BUTTON, 0.0)


B, P = Capability.BRIGHTNESS, Capability.POWER


@pytest.mark.parametrize(
    ("hue", "rgb"),
    [(0.0, (255, 0, 0)), (1 / 3, (0, 255, 0)), (2 / 3, (0, 0, 255)), (1.0, (255, 0, 0))],
)
def test_hue_to_rgb(hue, rgb):
    assert hue_to_rgb(hue) == rgb


@pytest.mark.parametrize(("level", "kelvin"), [(0.0, 2700), (0.5, 4600), (1.0, 6500)])
def test_level_to_kelvin(level, kelvin):
    assert level_to_kelvin(level) == kelvin


def test_fader_sets_brightness(setup):
    engine, queues = setup
    engine.handle(fader("fader.1", 0.62))
    assert queues["desk"].sent == [(B, 0.62)]
    assert queues["corner"].sent == []


def test_master_scales_faders(setup):
    engine, queues = setup
    engine.handle(fader("master", 0.5))
    engine.handle(fader("fader.1", 0.8))
    assert queues["desk"].sent[-1] == (B, pytest.approx(0.4))


def test_master_updates_every_light_that_is_on(setup):
    engine, queues = setup
    engine.handle(fader("fader.1", 0.8))
    engine.handle(fader("fader.2", 0.6))
    engine.handle(press("solo.1"))
    for queue in queues.values():
        queue.sent.clear()

    engine.handle(fader("master", 0.5))
    assert queues["desk"].sent == []
    assert queues["corner"].sent == [(B, pytest.approx(0.3))]


def test_button_toggles_on_press_only(setup):
    engine, queues = setup
    engine.handle(press("solo.1"))
    engine.handle(release("solo.1"))
    engine.handle(press("solo.1"))
    assert queues["desk"].sent == [(P, False), (P, True)]


def test_group_toggle_turns_all_off_if_any_are_on(setup):
    engine, queues = setup
    engine.handle(press("solo.1"))
    engine.handle(press("solo.8"))
    assert queues["desk"].sent[-1] == (P, False)
    assert queues["corner"].sent == [(P, False)]
    engine.handle(press("solo.8"))
    assert queues["desk"].sent[-1] == (P, True)
    assert queues["corner"].sent[-1] == (P, True)


def test_moving_a_fader_turns_its_light_back_on(setup):
    engine, queues = setup
    engine.handle(press("solo.1"))
    engine.handle(fader("fader.1", 0.5))
    assert queues["desk"].sent == [(P, False), (P, True), (B, 0.5)]


def test_color_fader(setup):
    engine, queues = setup
    engine.handle(fader("fader.5", 0.0))
    assert queues["desk"].sent == [(Capability.COLOR, (255, 0, 0))]
    assert queues["corner"].sent == [(Capability.COLOR, (255, 0, 0))]


def test_color_temp_fader(setup):
    engine, queues = setup
    engine.handle(fader("fader.6", 1.0))
    assert queues["desk"].sent == [(Capability.COLOR_TEMP, 6500)]


def test_unmapped_controls_are_ignored(setup):
    engine, queues = setup
    engine.handle(fader("fader.7", 0.5))
    assert all(queue.sent == [] for queue in queues.values())


def test_wrong_kind_of_control_is_ignored(setup):
    engine, queues = setup
    engine.handle(press("f1"))
    engine.handle(fader("fader.8", 1.0))
    assert all(queue.sent == [] for queue in queues.values())


def test_unsupported_commands_are_skipped(setup):
    engine, queues = setup
    engine.handle(fader("master", 0.5))
    assert queues["plug"].sent == []