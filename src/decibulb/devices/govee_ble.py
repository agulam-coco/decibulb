"""Device plugin for Govee lights controlled over Bluetooth.

Uses the unofficial govee-ble-local library. Tested with the Govee H6008
bulb, which has no LAN API.

Classes:
    GoveeBleBulb: A Govee light connected over Bluetooth.

Functions:
    discover_bulbs: Scan for nearby Govee lights.
    brightness_to_percent: Convert a 0.0 to 1.0 level to Govee's 1 to 100.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError
from govee_ble_local import Device as GoveeDevice
from govee_ble_local import DiscoveredDevice, GoveeBleError, create_device, discover, match

from decibulb.devices.base import Capability, Device

DEFAULT_SCAN_TIMEOUT = 10.0
MIN_PERCENT = 1  # Govee rejects 0%; turning a light off is set_power(False).
MAX_PERCENT = 100


async def discover_bulbs(timeout: float = DEFAULT_SCAN_TIMEOUT) -> list[DiscoveredDevice]:
    """Scan for nearby Govee lights this plugin can control.

    Args:
        timeout: Seconds to scan.

    Returns:
        Supported lights found during the scan.

    Raises:
        OSError: If Bluetooth is unavailable.
    """
    try:
        return await discover(timeout=timeout)
    except BleakError as err:
        raise OSError(f"Bluetooth is unavailable: {err}") from err


def brightness_to_percent(level: float) -> int:
    """Convert a 0.0 to 1.0 brightness level to Govee's 1 to 100 percent.

    Args:
        level: Brightness level. Values outside 0.0 to 1.0 are clamped.

    Returns:
        Percent from 1 to 100.
    """
    return max(MIN_PERCENT, min(MAX_PERCENT, round(level * MAX_PERCENT)))


async def _find(address: str, timeout: float) -> DiscoveredDevice | None:
    """Scan until the Govee light at `address` is seen, or time out.

    Raises:
        OSError: If Bluetooth is unavailable.
    """
    found: DiscoveredDevice | None = None

    def is_target(ble_device: BLEDevice, advertisement: AdvertisementData) -> bool:
        nonlocal found
        if ble_device.address.upper() != address:
            return False
        found = match(ble_device, advertisement)
        return found is not None

    try:
        await BleakScanner.find_device_by_filter(is_target, timeout=timeout)
    except BleakError as err:
        raise OSError(f"Bluetooth is unavailable: {err}") from err
    return found


class GoveeBleBulb(Device):
    """A Govee light connected over Bluetooth.

    The connection stays open until close(), so commands go out without a
    reconnect delay.

    Attributes:
        name: Name from the user's config.
        address: Bluetooth address, e.g. "98:17:3C:2B:70:C7".
    """

    capabilities = frozenset(
        {Capability.POWER, Capability.BRIGHTNESS, Capability.COLOR, Capability.COLOR_TEMP}
    )

    def __init__(self, name: str, address: str, scan_timeout: float = DEFAULT_SCAN_TIMEOUT) -> None:
        """Initialize the light. Nothing is sent until connect().

        Args:
            name: Name from the user's config.
            address: Bluetooth address, from `decibulb discover`.
            scan_timeout: Seconds to look for the light when connecting.
        """
        super().__init__(name)
        self.address = address.upper()
        self._scan_timeout = scan_timeout
        self._bulb: GoveeDevice | None = None

    async def connect(self) -> None:
        """Find the light and open a Bluetooth session.

        Does nothing if already connected.

        Raises:
            ConnectionError: If the light isn't found or won't connect.
        """
        if self._bulb is not None:
            return

        found = await _find(self.address, self._scan_timeout)
        if found is None:
            raise ConnectionError(
                f"{self.name}: no Govee light found at {self.address}. "
                "Check that it's powered on and not connected to a phone."
            )

        # idle_disconnect=0 keeps the link up. The default drops it after 8 s,
        # which would add a reconnect delay to the first fader move after a pause.
        bulb = create_device(found.ble_device, found.sku, found.advertisement, idle_disconnect=0)
        try:
            await bulb.connect()
        except GoveeBleError as err:
            await bulb.stop()
            raise ConnectionError(f"{self.name}: {err}") from err
        self._bulb = bulb

    async def close(self) -> None:
        """Disconnect from the light. Safe to call more than once."""
        if self._bulb is None:
            return
        bulb, self._bulb = self._bulb, None
        await bulb.stop()

    async def set_power(self, on: bool) -> None:
        """Turn the light on or off."""
        with self._translate_errors():
            await self._connected().set_power(on)

    async def set_brightness(self, level: float) -> None:
        """Set the brightness. Govee's dimmest setting is 1%, so 0.0 maps to 1%."""
        with self._translate_errors():
            await self._connected().set_brightness(brightness_to_percent(level))

    async def set_color(self, rgb: tuple[int, int, int]) -> None:
        """Set an RGB color."""
        with self._translate_errors():
            await self._connected().set_rgb(rgb)

    async def set_color_temp(self, kelvin: int) -> None:
        """Set a white color temperature, clamped to the light's supported range."""
        with self._translate_errors():
            bulb = self._connected()
            await bulb.set_color_temp(max(bulb.min_kelvin, min(bulb.max_kelvin, kelvin)))

    def _connected(self) -> GoveeDevice:
        """Return the library device, or raise if connect() hasn't run."""
        if self._bulb is None:
            raise ConnectionError(f"{self.name} is not connected")
        return self._bulb

    @contextmanager
    def _translate_errors(self) -> Iterator[None]:
        """Re-raise library errors as ConnectionError so callers handle one type."""
        try:
            yield
        except GoveeBleError as err:
            raise ConnectionError(f"{self.name}: {err}") from err