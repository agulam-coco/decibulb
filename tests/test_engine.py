"""Tests for decibulb.runner and decibulb.devices.registry."""

import asyncio

import pytest

from decibulb import runner
from decibulb.config import Action, Config, ConfigError, ControlMapping, DeviceConfig
from decibulb.devices.base import Capability
from decibulb.devices.fake import FakeDevice
from decibulb.devices.govee_ble import GoveeBleBulb
from decibulb.devices.registry import create_device
from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import load_profile

R24 = load_profile("zoom-r24")


class FakeBoard:
    """Yields a fixed list of events, then stops."""

    def __init__(self, events, delay=0.0):
        self.events = events
        self.delay = delay

    async def listen(self):
        for event in self.events:
            await asyncio.sleep(self.delay)
            yield None, event


class UnreachableDevice(FakeDevice):
    async def connect(self):
        raise ConnectionError(f"{self.name}: no Govee light found")


class PowerOnlyDevice(FakeDevice):
    capabilities = frozenset({Capability.POWER})


def make_config(controls):
    devices = {"desk": DeviceConfig("desk", "fake"), "corner": DeviceConfig("corner", "fake")}
    return Config("zoom-r24", None, devices, controls)


def test_create_device_builds_the_right_type():
    device = create_device(DeviceConfig("desk", "govee_ble", {"address": "aa:bb:cc:00:00:01"}))
    assert isinstance(device, GoveeBleBulb)
    assert (device.name, device.address) == ("desk", "AA:BB:CC:00:00:01")


def test_create_device_rejects_unknown_type():
    with pytest.raises(ConfigError, match="unknown type 'hue'. Types: fake, govee_ble"):
        create_device(DeviceConfig("desk", "hue"))


def test_create_device_rejects_wrong_settings():
    with pytest.raises(ConfigError, match="devices.desk: wrong settings for govee_ble"):
        create_device(DeviceConfig("desk", "govee_ble", {"adress": "AA:BB:CC:00:00:01"}))


def test_check_controls_accepts_a_good_config():
    controls = {
        "fader.1": ControlMapping("fader.1", Action.BRIGHTNESS, ("desk",)),
        "master": ControlMapping("master", Action.MASTER_BRIGHTNESS),
        "solo.1": ControlMapping("solo.1", Action.TOGGLE_POWER, ("desk",)),
    }
    devices = {"desk": FakeDevice("desk"), "corner": FakeDevice("corner")}
    assert runner.check_controls(make_config(controls), R24, devices) == []


def test_check_controls_finds_problems():
    controls = {
        "fader.9": ControlMapping("fader.9", Action.BRIGHTNESS, ("desk",)),
        "play": ControlMapping("play", Action.BRIGHTNESS, ("desk",)),
        "fader.2": ControlMapping("fader.2", Action.BRIGHTNESS, ("corner",)),
    }
    devices = {"desk": FakeDevice("desk"), "corner": PowerOnlyDevice("corner")}
    assert runner.check_controls(make_config(controls), R24, devices) == [
        "controls.fader.9: Zoom R24 has no control named 'fader.9'",
        "controls.play: brightness needs a fader, but play is a button",
        "controls.fader.2: corner doesn't support brightness",
    ]


def test_run_routes_events_and_cleans_up(monkeypatch):
    built = {}

    def fake_create(entry):
        built[entry.name] = FakeDevice(entry.name)
        return built[entry.name]

    monkeypatch.setattr(runner, "create_device", fake_create)
    controls = {"fader.1": ControlMapping("fader.1", Action.BRIGHTNESS, ("desk",))}
    board = FakeBoard([ControlEvent("fader.1", ControlKind.FADER, 0.62)])

    asyncio.run(runner.run(make_config(controls), R24, board))

    assert built["desk"].calls == [("brightness", pytest.approx(0.62**2))]
    assert not built["desk"].connected
    assert not built["corner"].connected


def test_run_skips_devices_that_fail_to_connect(monkeypatch, caplog):
    built = {"desk": UnreachableDevice("desk"), "corner": FakeDevice("corner")}
    monkeypatch.setattr(runner, "create_device", lambda entry: built[entry.name])
    controls = {
        "fader.1": ControlMapping("fader.1", Action.BRIGHTNESS, ("desk",)),
        "fader.2": ControlMapping("fader.2", Action.BRIGHTNESS, ("corner",)),
    }
    board = FakeBoard([
        ControlEvent("fader.1", ControlKind.FADER, 0.5),
        ControlEvent("fader.2", ControlKind.FADER, 0.3),
    ])

    asyncio.run(runner.run(make_config(controls), R24, board))

    assert "desk: no Govee light found" in caplog.text
    assert built["corner"].calls == [("brightness", pytest.approx(0.3**2))]


class PowerUnreadableDevice(FakeDevice):
    async def read_power(self):
        raise ConnectionError("no reply")


def test_run_starts_from_each_lights_real_power_state(monkeypatch, capsys):
    built = {"desk": FakeDevice("desk", on=False), "corner": FakeDevice("corner", on=None)}
    monkeypatch.setattr(runner, "create_device", lambda entry: built[entry.name])
    controls = {
        "fader.1": ControlMapping("fader.1", Action.BRIGHTNESS, ("desk",)),
        "master": ControlMapping("master", Action.MASTER_BRIGHTNESS),
    }
    board = FakeBoard([
        ControlEvent("master", ControlKind.FADER, 0.5),
        ControlEvent("fader.1", ControlKind.FADER, 1.0),
    ])

    asyncio.run(runner.run(make_config(controls), R24, board))

    assert "desk is off." in capsys.readouterr().out
    # The master skips the desk lamp while it's off; its own fader turns it on.
    assert built["desk"].calls == [("power", True), ("brightness", pytest.approx(0.25))]
    # Unknown power is treated as on.
    assert built["corner"].calls == [("brightness", pytest.approx(0.25))]


def test_run_assumes_on_when_power_cant_be_read(monkeypatch, caplog):
    built = {"desk": PowerUnreadableDevice("desk"), "corner": FakeDevice("corner")}
    monkeypatch.setattr(runner, "create_device", lambda entry: built[entry.name])
    controls = {"master": ControlMapping("master", Action.MASTER_BRIGHTNESS)}
    board = FakeBoard([ControlEvent("master", ControlKind.FADER, 0.5)])

    asyncio.run(runner.run(make_config(controls), R24, board))

    assert "Couldn't read whether desk is on, assuming on: no reply" in caplog.text
    assert built["desk"].calls == [("brightness", pytest.approx(0.25))]


class LateDevice(FakeDevice):
    """A FakeDevice that can't be reached until its second connect attempt."""

    def __init__(self, name, on=True):
        super().__init__(name, on)
        self.attempts = 0

    async def connect(self):
        self.attempts += 1
        if self.attempts == 1:
            raise ConnectionError(f"{self.name}: no Govee light found")
        await super().connect()


def test_devices_that_connect_late_join_in(monkeypatch, capsys):
    monkeypatch.setattr(runner, "RECONNECT_SECONDS", 0.01)
    built = {"desk": LateDevice("desk", on=False), "corner": FakeDevice("corner")}
    monkeypatch.setattr(runner, "create_device", lambda entry: built[entry.name])
    controls = {"fader.1": ControlMapping("fader.1", Action.BRIGHTNESS, ("desk",))}
    # The delay gives the retry time to connect the desk lamp before the event.
    board = FakeBoard([ControlEvent("fader.1", ControlKind.FADER, 1.0)], delay=0.1)

    asyncio.run(runner.run(make_config(controls), R24, board))

    out = capsys.readouterr().out
    assert "Ready: 1 of 2 devices connected" in out
    assert "desk connected." in out
    assert built["desk"].calls == [("power", True), ("brightness", 1.0)]
    assert not built["desk"].connected