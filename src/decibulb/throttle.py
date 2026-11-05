"""Send only the newest command to each device.

A fader sends hundreds of values a second, but a Bluetooth bulb handles
about 10. Instead of queueing every value, each device keeps only the
newest pending value per kind of command and sends it when the device is
free. Fast devices get every value; slow ones skip straight to the latest.

Classes:
    DeviceQueue: Command queue for one device that drops outdated values.
"""

import asyncio
import logging
from typing import Any

from decibulb.devices.base import Capability, Device, UnsupportedActionError

logger = logging.getLogger(__name__)

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
    whenever the device finishes its previous command.

    Attributes:
        device: The device commands are sent to.
    """

    def __init__(self, device: Device) -> None:
        """Create an empty queue for `device`.

        Args:
            device: The device commands are sent to. Must already be connected
                before run() sends anything.
        """
        self.device = device
        self._pending: dict[Capability, Any] = {}
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()

    def submit(self, capability: Capability, value: Any) -> None:
        """Queue a command, replacing any pending command of the same kind.

        Args:
            capability: Kind of command, e.g. Capability.BRIGHTNESS.
            value: Argument for the matching Device.set_* method.
        """
        self._pending[capability] = value
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
            while self._pending:
                batch, self._pending = self._pending, {}
                for capability, value in _in_send_order(batch):
                    await self._send(capability, value)
            self._idle.set()

    async def _send(self, capability: Capability, value: Any) -> None:
        """Send one command, logging failures instead of raising them."""
        try:
            await getattr(self.device, _SETTERS[capability])(value)
        except (ConnectionError, UnsupportedActionError) as err:
            logger.warning("%s: %s", self.device.name, err)


def _in_send_order(batch: dict[Capability, Any]) -> list[tuple[Capability, Any]]:
    """Order a batch so power-on goes first and power-off goes last.

    Otherwise a brightness change sent after power-off could turn the light
    back on, and one sent before power-on would be lost.
    """
    power = batch.pop(Capability.POWER, None)
    commands = list(batch.items())
    if power is True:
        commands.insert(0, (Capability.POWER, True))
    elif power is False:
        commands.append((Capability.POWER, False))
    return commands