"""Turn control events into device commands.

Classes:
    Engine: Applies the user's config to each ControlEvent.

Functions:
    hue_to_rgb: Convert a 0.0 to 1.0 hue to a fully saturated RGB color.
    level_to_kelvin: Convert a 0.0 to 1.0 level to a color temperature.
"""

import colorsys
import logging

from decibulb.config import Action, ControlMapping
from decibulb.devices.base import Capability
from decibulb.events import ControlEvent, ControlKind
from decibulb.throttle import DeviceQueue

logger = logging.getLogger(__name__)

WARMEST_KELVIN = 2700
COOLEST_KELVIN = 6500


def hue_to_rgb(hue: float) -> tuple[int, int, int]:
    """Convert a 0.0 to 1.0 hue to a fully saturated RGB color.

    Args:
        hue: Position around the color wheel. 0.0 and 1.0 are both red.

    Returns:
        Red, green, and blue, each from 0 to 255.
    """
    red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return round(red * 255), round(green * 255), round(blue * 255)


def level_to_kelvin(level: float) -> int:
    """Convert a 0.0 to 1.0 level to a color temperature.

    Args:
        level: 0.0 for the warmest white, 1.0 for the coolest.

    Returns:
        Color temperature in kelvin.
    """
    return round(WARMEST_KELVIN + level * (COOLEST_KELVIN - WARMEST_KELVIN))


class Engine:
    """Applies the user's config to each ControlEvent.

    The engine remembers each device's fader level and power state, so the
    master fader can scale every light and buttons can toggle. Lights are
    assumed to be on at startup. Devices without a queue, such as ones that
    failed to connect, are skipped.

    Attributes:
        master: Current master brightness, from 0.0 to 1.0.
    """

    def __init__(self, controls: dict[str, ControlMapping], queues: dict[str, DeviceQueue]) -> None:
        """Create an engine.

        Args:
            controls: Control mappings from the config, by control name.
            queues: A running DeviceQueue for each connected device, by name.
        """
        self._controls = controls
        self._queues = queues
        self.master = 1.0
        self._levels = {name: 1.0 for name in queues}
        self._power = {name: True for name in queues}

    def handle(self, event: ControlEvent) -> None:
        """Apply one event.

        Events for unmapped controls, and events from the wrong kind of
        control (such as a button mapped to brightness), are ignored.

        Args:
            event: The event from the board.
        """
        mapping = self._controls.get(event.control)
        if mapping is None:
            return

        names = [name for name in mapping.devices if name in self._queues]

        if mapping.action is Action.TOGGLE_POWER:
            if event.kind is ControlKind.BUTTON and event.pressed and names:
                self._toggle(names)
            return

        if event.kind is not ControlKind.FADER:
            logger.debug("%s: %s needs a fader", event.control, mapping.action.value)
            return

        match mapping.action:
            case Action.MASTER_BRIGHTNESS:
                self._set_master(event.value)
            case Action.BRIGHTNESS:
                for name in names:
                    self._set_level(name, event.value)
            case Action.COLOR:
                for name in names:
                    self._submit(name, Capability.COLOR, hue_to_rgb(event.value))
            case Action.COLOR_TEMP:
                for name in names:
                    self._submit(name, Capability.COLOR_TEMP, level_to_kelvin(event.value))

    def _set_level(self, name: str, level: float) -> None:
        """Set one device's fader level, turning it on if it was off."""
        self._levels[name] = level
        if not self._power[name]:
            self._power[name] = True
            self._submit(name, Capability.POWER, True)
        self._submit(name, Capability.BRIGHTNESS, level * self.master)

    def _set_master(self, master: float) -> None:
        """Rescale every light that's on."""
        self.master = master
        for name, level in self._levels.items():
            if self._power[name]:
                self._submit(name, Capability.BRIGHTNESS, level * master)

    def _toggle(self, names: list[str]) -> None:
        """Turn the devices off if any are on, otherwise turn them all on."""
        turn_on = not any(self._power[name] for name in names)
        for name in names:
            self._power[name] = turn_on
            self._submit(name, Capability.POWER, turn_on)

    def _submit(self, name: str, capability: Capability, value: object) -> None:
        """Queue a command if the device supports it."""
        queue = self._queues[name]
        if queue.device.supports(capability):
            queue.submit(capability, value)