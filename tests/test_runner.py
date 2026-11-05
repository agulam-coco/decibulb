"""Tests for decibulb.runner and decibulb.devices.registry."""

import asyncio
import threading
from unittest import mock

import mido
import pytest

from decibulb import runner
from decibulb.boards.mackie import MackieBoard
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

    def __init__(self, events):
        self.events = events

    async def listen(self):
        for event in self.events:
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

    assert built["desk"].calls == [("brightness", 0.62)]
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
    assert built["corner"].calls == [("brightness", 0.3)]


def test_board_listen_receives_messages_from_another_thread(monkeypatch):
    captured = {}

    class FakePort:
        def __init__(self, name, callback):
            captured["callback"] = callback

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            captured["closed"] = True

    monkeypatch.setattr(mido, "open_input", FakePort)

    async def main():
        listener = MackieBoard(R24, port_name="R24").listen()
        first = asyncio.ensure_future(anext(listener))
        await asyncio.sleep(0)
        message = mido.Message("pitchwheel", channel=0, pitch=8191)
        threading.Thread(target=captured["callback"], args=(message,)).start()
        msg, event = await asyncio.wait_for(first, 1)
        await listener.aclose()
        return event

    event = asyncio.run(main())
    assert (event.control, event.value) == ("fader.1", 1.0)
    assert captured["closed"]