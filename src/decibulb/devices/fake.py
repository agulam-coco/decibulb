"""In-memory device for tests and demo mode.

Classes:
    FakeDevice: A device that records actions instead of performing them.
"""

from decibulb.devices.base import Capability, Device


class FakeDevice(Device):
    """A device that records actions instead of performing them.

    Supports every capability.

    Attributes:
        connected: True between connect() and close().
        calls: Every action performed, in order, e.g. ("brightness", 0.5).
    """

    capabilities = frozenset(Capability)

    def __init__(self, name: str) -> None:
        """Initialize the device.

        Args:
            name: Name from the user's config.
        """
        super().__init__(name)
        self.connected = False
        self.calls: list[tuple[str, object]] = []

    async def connect(self) -> None:
        """Mark the device as connected."""
        self.connected = True

    async def close(self) -> None:
        """Mark the device as disconnected."""
        self.connected = False

    async def set_power(self, on: bool) -> None:
        """Record a power change."""
        self.calls.append(("power", on))

    async def set_brightness(self, level: float) -> None:
        """Record a brightness change."""
        self.calls.append(("brightness", level))

    async def set_color(self, rgb: tuple[int, int, int]) -> None:
        """Record a color change."""
        self.calls.append(("color", rgb))

    async def set_color_temp(self, kelvin: int) -> None:
        """Record a color temperature change."""
        self.calls.append(("color_temp", kelvin))