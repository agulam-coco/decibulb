"""Base class for device plugins.

A device is anything decibulb controls, like a light bulb or a speaker.
Each plugin subclasses Device and implements the actions its hardware
supports.

Classes:
    Capability: An action a device can perform.
    UnsupportedActionError: Raised when a device can't perform an action.
    Device: Base class every device plugin implements.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Self


class Capability(Enum):
    """An action a device can perform."""

    POWER = "power"
    BRIGHTNESS = "brightness"
    COLOR = "color"
    COLOR_TEMP = "color_temp"


class UnsupportedActionError(Exception):
    """Raised when a device is asked to do something it can't."""


class Device(ABC):
    """Base class every device plugin implements.

    Subclasses set `capabilities` and override the matching set_* methods.
    Calling a set_* method the device doesn't override raises
    UnsupportedActionError.

    Attributes:
        name: Name from the user's config, e.g. "desk_lamp".
        capabilities: Actions this device supports.
    """

    capabilities: frozenset[Capability] = frozenset()

    def __init__(self, name: str) -> None:
        """Initialize the device.

        Args:
            name: Name from the user's config.
        """
        self.name = name

    def supports(self, capability: Capability) -> bool:
        """Return True if the device supports `capability`."""
        return capability in self.capabilities

    @abstractmethod
    async def connect(self) -> None:
        """Open a connection to the device.

        Raises:
            ConnectionError: If the device can't be reached.
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the connection. Safe to call more than once."""

    async def set_power(self, on: bool) -> None:
        """Turn the device on or off.

        Args:
            on: True to turn on, False to turn off.

        Raises:
            UnsupportedActionError: If the device lacks Capability.POWER.
        """
        raise self._unsupported(Capability.POWER)

    async def set_brightness(self, level: float) -> None:
        """Set the brightness.

        Args:
            level: Brightness from 0.0 (dimmest) to 1.0 (brightest).

        Raises:
            UnsupportedActionError: If the device lacks Capability.BRIGHTNESS.
        """
        raise self._unsupported(Capability.BRIGHTNESS)

    async def set_color(self, rgb: tuple[int, int, int]) -> None:
        """Set an RGB color.

        Args:
            rgb: Red, green, and blue, each from 0 to 255.

        Raises:
            UnsupportedActionError: If the device lacks Capability.COLOR.
        """
        raise self._unsupported(Capability.COLOR)

    async def set_color_temp(self, kelvin: int) -> None:
        """Set a white color temperature.

        Args:
            kelvin: Color temperature, e.g. 2700 (warm) to 6500 (cool).

        Raises:
            UnsupportedActionError: If the device lacks Capability.COLOR_TEMP.
        """
        raise self._unsupported(Capability.COLOR_TEMP)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    def _unsupported(self, capability: Capability) -> UnsupportedActionError:
        return UnsupportedActionError(f"{self.name} does not support {capability.value}")