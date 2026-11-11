"""Tests for decibulb.devices.base and decibulb.devices.fake."""

import asyncio

import pytest

from decibulb.devices.base import Capability, Device, UnsupportedActionError
from decibulb.devices.fake import FakeDevice


class PowerOnlyDevice(Device):
    capabilities = frozenset({Capability.POWER})

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def set_power(self, on: bool) -> None:
        pass


def test_device_base_class_cannot_be_used_directly():
    with pytest.raises(TypeError):
        Device("lamp")


def test_supports_reflects_capabilities():
    device = PowerOnlyDevice("plug")
    assert device.supports(Capability.POWER)
    assert not device.supports(Capability.BRIGHTNESS)


def test_unsupported_action_raises():
    device = PowerOnlyDevice("plug")
    with pytest.raises(UnsupportedActionError, match="plug does not support brightness"):
        asyncio.run(device.set_brightness(0.5))


def test_fake_device_records_calls_and_connection():
    lamp = FakeDevice("desk_lamp")

    async def scenario():
        async with lamp:
            assert lamp.connected
            await lamp.set_power(True)
            await lamp.set_brightness(0.62)
            await lamp.set_color((255, 0, 0))
            await lamp.set_color_temp(2700)

    asyncio.run(scenario())
    assert not lamp.connected
    assert lamp.calls == [
        ("power", True),
        ("brightness", 0.62),
        ("color", (255, 0, 0)),
        ("color_temp", 2700),
    ]


def test_read_power_defaults_to_unknown():
    assert asyncio.run(PowerOnlyDevice("plug").read_power()) is None


def test_fake_device_reports_its_power_state():
    lamp = FakeDevice("desk_lamp", on=False)

    async def scenario():
        before = await lamp.read_power()
        await lamp.set_power(True)
        return before, await lamp.read_power()

    assert asyncio.run(scenario()) == (False, True)
    assert lamp.calls == [("power", True)]