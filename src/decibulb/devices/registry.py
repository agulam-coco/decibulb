"""Build devices from config entries.

To add a device plugin, add its class to DEVICE_TYPES.

Functions:
    create_device: Build a Device from a config entry.
"""

from decibulb.config import ConfigError, DeviceConfig
from decibulb.devices.base import Device
from decibulb.devices.fake import FakeDevice
from decibulb.devices.govee_ble import GoveeBleBulb

DEVICE_TYPES: dict[str, type[Device]] = {
    "fake": FakeDevice,
    "govee_ble": GoveeBleBulb,
}


def create_device(entry: DeviceConfig) -> Device:
    """Build a Device from a config entry. Nothing is connected yet.

    Args:
        entry: One entry from the config's `devices:` section.

    Returns:
        A device of the entry's type, named after the entry.

    Raises:
        ConfigError: If the type is unknown or its options are wrong.
    """
    device_class = DEVICE_TYPES.get(entry.type)
    if device_class is None:
        known = ", ".join(DEVICE_TYPES)
        raise ConfigError(f"devices.{entry.name}: unknown type {entry.type!r}. Types: {known}")
    try:
        return device_class(entry.name, **entry.options)
    except TypeError as err:
        raise ConfigError(f"devices.{entry.name}: wrong settings for {entry.type} ({err})") from err