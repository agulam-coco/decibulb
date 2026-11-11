"""Send only the newest command to each device.

A fader sends hundreds of values a second, but a Govee bulb can only show
about 3 changes a second. Instead of queueing every value, each device
keeps only the newest pending value per kind of command and sends it when
the device is ready: once its previous command finished and at least
min_interval has passed since that command started. Values in between
are skipped, and so is any command that wouldn't change what the device
is showing.

Classes:
    DeviceQueue: Command queue for one device that drops outdated values.
"""

import asyncio
import logging
import time
from typing import Any

from decibulb.devices.base import Capability, Device, UnsupportedActionError

logger = logging.getLogger(__name__)

# Govee bulbs ack in ~50 ms but fade into each change; sending faster than
# they can show builds a backlog inside the bulb. 0.3 s found by testing.
MIN_SEND_INTERVAL = 0.3
SLOW_COMMAND_SECONDS = 1.0  # a healthy Bluetooth command takes about 0.1 s

_Pending = tuple[Any, float]  # (value, time.monotonic() when submitted)

_SETTERS = {
    Capability.POWER: "set_power",
    Capability.BRIGHTNESS: "set_brightness",
    Capability.COLOR: "set_color",
    Capability.COLOR_TEMP: "set_color_temp",
}


class DeviceQueue:
    """Command queue for one device that drops outdated values.

    Call submit() as often as you like; it never blocks. A background task
    started with run() sends the newest value of each kind of command
    whenever the device is ready for another one.

    Attributes:
        device: The device commands are sent to.
        min_interval: Fewest seconds between the starts of two commands.
    """

    def __init__(self, device: Device, min_interval: float = MIN_SEND_INTERVAL) -> None:
        """Create an empty queue for `device`.

        Args:
            device: The device commands are sent to. Must already be connected
                before run() sends anything.
            min_interval: Fewest seconds between the starts of two commands.
                0 sends as fast as the device acknowledges.
        """
        self.device = device
        self.min_interval = min_interval
        self._last_send = float("-inf")
        self._applied: dict[Capability, Any] = {}
        self._pending: dict[Capability, _Pending] = {}
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()

    def submit(self, capability: Capability, value: Any) -> None:
        """Queue a command, replacing any pending command of the same kind.

        Args:
            capability: Kind of command, e.g. Capability.BRIGHTNESS.
            value: Argument for the matching Device.set_* method.
        """
        self._pending[capability] = (value, time.monotonic())
        self._idle.clear()
        self._wake.set()

    async def wait_idle(self) -> None:
        """Wait until every submitted command has been sent."""
        await self._idle.wait()

    async def run(self) -> None:
        """Send queued commands until cancelled.

        Errors from the device are logged and don't stop the queue.
        """
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self._drop_unchanged():
                # Wait before taking the batch so the newest values are sent.
                await self._wait_turn()
                batch, self._pending = self._pending, {}
                for capability, (value, submitted) in _in_send_order(batch):
                    effective = self.device.effective_value(capability, value)
                    if self._applied.get(capability) == effective:
                        continue
                    await self._wait_turn()
                    if await self._send(capability, value, submitted):
                        self._applied[capability] = effective
            self._idle.set()

    def _drop_unchanged(self) -> bool:
        """Drop pending commands that wouldn't change anything. Return True if any remain."""
        for capability, (value, _submitted) in list(self._pending.items()):
            if self._applied.get(capability) == self.device.effective_value(capability, value):
                del self._pending[capability]
        return bool(self._pending)

    async def _wait_turn(self) -> None:
        """Sleep until min_interval has passed since the last command started."""
        delay = self._last_send + self.min_interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    async def _send(self, capability: Capability, value: Any, submitted: float) -> bool:
        """Send one command. Return False if it failed, logging why."""
        started = self._last_send = time.monotonic()
        try:
            await getattr(self.device, _SETTERS[capability])(value)
        except (ConnectionError, UnsupportedActionError) as err:
            logger.warning("%s: %s", self.device.name, err)
            return False
        finished = time.monotonic()
        shown = f"{value:.2f}" if isinstance(value, float) else value
        took = finished - started
        logger.debug(
            "%s %s %s: sent in %.0f ms, %.0f ms after the control moved",
            self.device.name,
            capability.value,
            shown,
            took * 1000,
            (finished - submitted) * 1000,
        )
        if took > SLOW_COMMAND_SECONDS:
            logger.warning(
                "%s %s took %.1f s to send (usually about 0.1 s)",
                self.device.name,
                capability.value,
                took,
            )
        return True


def _in_send_order(batch: dict[Capability, _Pending]) -> list[tuple[Capability, _Pending]]:
    """Order a batch so power-on goes first and power-off goes last.

    Otherwise a brightness change sent after power-off could turn the light
    back on, and one sent before power-on would be lost.
    """
    power = batch.pop(Capability.POWER, None)
    commands = list(batch.items())
    if power is not None and power[0]:
        commands.insert(0, (Capability.POWER, power))
    elif power is not None:
        commands.append((Capability.POWER, power))
    return commands