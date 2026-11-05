"""Connect the board and devices, then route every event to the engine.

Functions:
    check_controls: Find config mistakes that need the board profile.
    run: Connect everything and handle events until cancelled.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from decibulb.config import Action, Config
from decibulb.devices.base import Capability, Device
from decibulb.devices.registry import create_device
from decibulb.engine import Engine
from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import BoardProfile
from decibulb.throttle import DeviceQueue

logger = logging.getLogger(__name__)

SHUTDOWN_TIMEOUT = 2.0  # seconds to finish sending final values on exit

_REQUIRED_CAPABILITY = {
    Action.BRIGHTNESS: Capability.BRIGHTNESS,
    Action.COLOR: Capability.COLOR,
    Action.COLOR_TEMP: Capability.COLOR_TEMP,
    Action.TOGGLE_POWER: Capability.POWER,
}


class Board(Protocol):
    """Anything that yields (message, event) pairs, like MackieBoard."""

    def listen(self) -> AsyncIterator[tuple[Any, ControlEvent | None]]: ...


def check_controls(config: Config, profile: BoardProfile, devices: dict[str, Device]) -> list[str]:
    """Find control mappings the board or devices can't carry out.

    Args:
        config: The loaded config.
        profile: The board's profile.
        devices: Devices built from the config, by name.

    Returns:
        One readable warning per problem. Empty if everything checks out.
    """
    kinds = {name: ControlKind.FADER for name in profile.faders.values()}
    kinds |= {name: ControlKind.BUTTON for name in profile.buttons.values()}
    kinds |= {name: ControlKind.ENCODER for name in profile.encoders.values()}

    warnings = []
    for control, mapping in config.controls.items():
        kind = kinds.get(control)
        if kind is None:
            warnings.append(f"controls.{control}: {profile.name} has no control named {control!r}")
            continue

        wanted = ControlKind.BUTTON if mapping.action is Action.TOGGLE_POWER else ControlKind.FADER
        if kind is not wanted:
            warnings.append(
                f"controls.{control}: {mapping.action.value} needs a {wanted.value}, "
                f"but {control} is a {kind.value}"
            )

        capability = _REQUIRED_CAPABILITY.get(mapping.action)
        for name in mapping.devices:
            if capability and not devices[name].supports(capability):
                warnings.append(f"controls.{control}: {name} doesn't support {capability.value}")
    return warnings


async def run(config: Config, profile: BoardProfile, board: Board) -> None:
    """Connect everything and handle events until the board stops or the task is cancelled.

    Devices that fail to connect are skipped with a warning. On exit, the
    last values are sent before devices disconnect.

    Args:
        config: The loaded config.
        profile: The board's profile.
        board: An opened board to read events from.

    Raises:
        ConfigError: If a device entry has an unknown type or wrong settings.
    """
    devices = {name: create_device(entry) for name, entry in config.devices.items()}
    for warning in check_controls(config, profile, devices):
        logger.warning(warning)

    connected = await _connect_all(devices)
    queues = {name: DeviceQueue(device) for name, device in connected.items()}
    workers = [asyncio.create_task(queue.run()) for queue in queues.values()]
    engine = Engine(config.controls, queues)

    print(f"Ready: {len(connected)} of {len(devices)} devices connected. Press Ctrl+C to stop.")
    try:
        async for _msg, event in board.listen():
            if event is not None:
                engine.handle(event)
    finally:
        await _shut_down(queues, workers)


async def _connect_all(devices: dict[str, Device]) -> dict[str, Device]:
    """Connect each device in turn and return the ones that connected."""
    # One at a time: overlapping Bluetooth scans can fail on Linux.
    connected = {}
    for name, device in devices.items():
        print(f"Connecting {name}...")
        try:
            await device.connect()
        except ConnectionError as err:
            logger.warning("%s", err)
        else:
            connected[name] = device
    return connected


async def _shut_down(queues: dict[str, DeviceQueue], workers: list[asyncio.Task]) -> None:
    """Send any final values, stop the queues, and disconnect every device."""
    try:
        idle = [queue.wait_idle() for queue in queues.values()]
        await asyncio.wait_for(asyncio.gather(*idle), SHUTDOWN_TIMEOUT)
    except TimeoutError:
        logger.warning("Gave up sending final values after %g seconds", SHUTDOWN_TIMEOUT)
    for worker in workers:
        worker.cancel()
    for queue in queues.values():
        await queue.device.close()