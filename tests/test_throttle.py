"""Tests for decibulb.throttle."""

import asyncio
import logging
import time

from decibulb import throttle
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


class TimedDevice(FakeDevice):
    """A FakeDevice that records when each command starts."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.starts: list[float] = []

    async def set_brightness(self, level: float) -> None:
        self.starts.append(time.monotonic())
        await super().set_brightness(level)

    async def set_color(self, rgb: tuple[int, int, int]) -> None:
        self.starts.append(time.monotonic())
        await super().set_color(rgb)


def run_queue(device, scenario, min_interval=0.0):
    """Run `scenario(queue)` with a DeviceQueue running in the background."""

    async def main():
        queue = DeviceQueue(device, min_interval)
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


def test_send_timing_is_logged_at_debug_level(caplog):
    lamp = SlowDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.BRIGHTNESS, 0.5)

    with caplog.at_level(logging.DEBUG, logger="decibulb.throttle"):
        run_queue(lamp, scenario)
    assert "lamp brightness 0.50: sent in 10" in caplog.text
    assert "ms after the control moved" in caplog.text


def test_slow_commands_are_warned_about(caplog, monkeypatch):
    monkeypatch.setattr(throttle, "SLOW_COMMAND_SECONDS", 0.05)
    lamp = SlowDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.BRIGHTNESS, 0.5)

    with caplog.at_level(logging.WARNING):
        run_queue(lamp, scenario)
    assert "lamp brightness took 0.1 s to send" in caplog.text


def test_fast_device_is_paced_to_the_newest_value():
    lamp = FakeDevice("lamp")

    async def scenario(queue):
        # A fader sweep: 100 values over about half a second.
        for step in range(101):
            queue.submit(Capability.BRIGHTNESS, step / 100)
            await asyncio.sleep(0.005)

    run_queue(lamp, scenario, min_interval=0.1)
    sent = [value for kind, value in lamp.calls if kind == "brightness"]
    assert len(sent) <= 8
    assert sent[-1] == 1.0


def test_commands_in_one_batch_are_paced_too():
    lamp = TimedDevice("lamp")

    async def scenario(queue):
        queue.submit(Capability.BRIGHTNESS, 0.5)
        queue.submit(Capability.COLOR, (255, 0, 0))

    run_queue(lamp, scenario, min_interval=0.1)
    assert sorted(lamp.calls) == [("brightness", 0.5), ("color", (255, 0, 0))]
    assert lamp.starts[1] - lamp.starts[0] >= 0.09