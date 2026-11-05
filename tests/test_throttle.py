"""Tests for decibulb.throttle."""

import asyncio
import logging

from decibulb.devices.base import Capability
from decibulb.devices.fake import FakeDevice
from decibulb.throttle import DeviceQueue


class SlowDevice(FakeDevice):
    """A FakeDevice whose brightness changes take as long as a real bulb's."""

    async def set_brightness(self, level: float) -> None:
        await asyncio.sleep(0.1)
        await super().set_brightness(level)


class BrokenDevice(FakeDevice):
    """A FakeDevice whose brightness changes always fail."""

    async def set_brightness(self, level: float) -> None:
        raise ConnectionError("link lost")


def run_queue(device, scenario):
    """Run `scenario(queue)` with a DeviceQueue running in the background."""

    async def main():
        queue = DeviceQueue(device)
        task = asyncio.create_task(queue.run())
        try:
            await scenario(queue)
            await queue.wait_idle()
        finally:
            task.cancel()

    asyncio.run(main())


def test_every_value_reaches_a_fast_device():
    lamp = FakeDevice("lamp")

    async def scenario(queue):
        for level in (0.1, 0.2, 0.3):
            queue.submit(Capability.BRIGHTNESS, level)
            await queue.wait_idle()

    run_queue(lamp, scenario)
    assert lamp.calls == [("brightness", 0.1), ("brightness", 0.2), ("brightness", 0.3)]


def test_slow_device_skips_to_the_newest_value():
    lamp = SlowDevice("lamp")

    async def scenario(queue):
        # A fader sweep: 100 values over about half a second.
        for step in range(101):
            queue.submit(Capability.BRIGHTNESS, step / 100)
            await asyncio.sleep(0.005)

    run_queue(lamp, scenario)
    sent = [value for kind, value in lamp.calls if kind == "brightness"]
    assert len(sent) < 15
    assert sent[-1] == 1.0


def test_different_commands_dont_replace_each_other():
    lamp = FakeDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.BRIGHTNESS, 0.5)
        queue.submit(Capability.COLOR, (255, 0, 0))
        queue.submit(Capability.BRIGHTNESS, 0.8)

    run_queue(lamp, scenario)
    assert sorted(lamp.calls) == [("brightness", 0.8), ("color", (255, 0, 0))]


def test_power_on_is_sent_first():
    lamp = FakeDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.BRIGHTNESS, 0.5)
        queue.submit(Capability.POWER, True)

    run_queue(lamp, scenario)
    assert lamp.calls == [("power", True), ("brightness", 0.5)]


def test_power_off_is_sent_last():
    lamp = FakeDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.POWER, False)
        queue.submit(Capability.BRIGHTNESS, 0.5)

    run_queue(lamp, scenario)
    assert lamp.calls == [("brightness", 0.5), ("power", False)]


def test_errors_are_logged_and_the_queue_keeps_going(caplog):
    lamp = BrokenDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.BRIGHTNESS, 0.5)
        await queue.wait_idle()
        queue.submit(Capability.COLOR, (0, 0, 255))

    with caplog.at_level(logging.WARNING):
        run_queue(lamp, scenario)
    assert "lamp: link lost" in caplog.text
    assert lamp.calls == [("color", (0, 0, 255))]