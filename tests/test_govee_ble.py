"""Tests for decibulb.devices.govee_ble.

The govee-ble-local library is replaced with mocks, so no Bluetooth
hardware is needed.
"""

import asyncio
from unittest import mock

import pytest
from bleak.exc import BleakBluetoothNotAvailableError, BleakBluetoothNotAvailableReason
from govee_ble_local import GoveeBleConnectionError, GoveeBleError

from decibulb.devices import govee_ble
from decibulb.devices.govee_ble import GoveeBleBulb, brightness_to_percent

ADDRESS = "AA:BB:CC:00:00:01"
POWERED_OFF = BleakBluetoothNotAvailableError(
    "No powered Bluetooth adapters found. Turn on Bluetooth and try again.",
    BleakBluetoothNotAvailableReason.POWERED_OFF,
)


@pytest.fixture
def library_bulb(monkeypatch):
    """Make connect() find a light and return a mock library device."""
    bulb = mock.AsyncMock()
    bulb.min_kelvin = 2700
    bulb.max_kelvin = 6500
    monkeypatch.setattr(govee_ble, "_find", mock.AsyncMock(return_value=mock.Mock()))
    create = mock.Mock(return_value=bulb)
    monkeypatch.setattr(govee_ble, "create_device", create)
    bulb.create_device = create
    return bulb


@pytest.mark.parametrize(
    ("level", "percent"),
    [(0.0, 1), (0.004, 1), (0.5, 50), (0.62, 62), (1.0, 100), (1.5, 100), (-1.0, 1)],
)
def test_brightness_to_percent(level, percent):
    assert brightness_to_percent(level) == percent


def test_address_is_uppercased():
    assert GoveeBleBulb("desk_lamp", ADDRESS.lower()).address == ADDRESS


def test_commands_before_connect_raise():
    with pytest.raises(ConnectionError, match="desk_lamp is not connected"):
        asyncio.run(GoveeBleBulb("desk_lamp", ADDRESS).set_brightness(0.5))


def test_missing_light_raises_with_hint(monkeypatch):
    monkeypatch.setattr(govee_ble, "_find", mock.AsyncMock(return_value=None))
    with pytest.raises(ConnectionError, match="not connected to a phone"):
        asyncio.run(GoveeBleBulb("desk_lamp", ADDRESS).connect())


def test_connection_stays_open(library_bulb):
    asyncio.run(GoveeBleBulb("desk_lamp", ADDRESS).connect())
    assert library_bulb.create_device.call_args.kwargs["idle_disconnect"] == 0


def test_commands_are_converted_and_forwarded(library_bulb):
    async def scenario():
        async with GoveeBleBulb("desk_lamp", ADDRESS) as lamp:
            await lamp.set_power(True)
            await lamp.set_brightness(0.62)
            await lamp.set_color((255, 0, 0))
            await lamp.set_color_temp(9000)
            await lamp.set_color_temp(1000)

    asyncio.run(scenario())
    library_bulb.set_power.assert_awaited_once_with(True)
    library_bulb.set_brightness.assert_awaited_once_with(62)
    library_bulb.set_rgb.assert_awaited_once_with((255, 0, 0))
    assert library_bulb.set_color_temp.await_args_list == [mock.call(6500), mock.call(2700)]
    library_bulb.stop.assert_awaited_once()


def test_close_is_safe_to_call_twice(library_bulb):
    async def scenario():
        lamp = GoveeBleBulb("desk_lamp", ADDRESS)
        await lamp.connect()
        await lamp.close()
        await lamp.close()

    asyncio.run(scenario())
    library_bulb.stop.assert_awaited_once()


def test_library_errors_become_connection_errors(library_bulb):
    library_bulb.set_brightness.side_effect = GoveeBleError("link lost")

    async def scenario():
        async with GoveeBleBulb("desk_lamp", ADDRESS) as lamp:
            await lamp.set_brightness(1.0)

    with pytest.raises(ConnectionError, match="desk_lamp: link lost"):
        asyncio.run(scenario())


def test_failed_handshake_cleans_up(library_bulb):
    library_bulb.connect.side_effect = GoveeBleError("handshake failed")
    with pytest.raises(ConnectionError, match="handshake failed"):
        asyncio.run(GoveeBleBulb("desk_lamp", ADDRESS).connect())
    library_bulb.stop.assert_awaited_once()


def test_scan_with_bluetooth_off_gives_clean_error(monkeypatch):
    async def failing_discover(timeout):
        try:
            raise POWERED_OFF
        except BleakBluetoothNotAvailableError as err:
            raise GoveeBleConnectionError(f"BLE scan failed: {err}") from err

    monkeypatch.setattr(govee_ble, "discover", failing_discover)
    with pytest.raises(OSError) as exc_info:
        asyncio.run(govee_ble.discover_bulbs())
    assert str(exc_info.value) == (
        "Bluetooth is unavailable: No powered Bluetooth adapters found. "
        "Turn on Bluetooth and try again."
    )


def test_connect_with_bluetooth_off_gives_clean_error(monkeypatch):
    monkeypatch.setattr(
        govee_ble.BleakScanner,
        "find_device_by_filter",
        mock.AsyncMock(side_effect=POWERED_OFF),
    )
    with pytest.raises(OSError, match="Bluetooth is unavailable: No powered Bluetooth"):
        asyncio.run(GoveeBleBulb("desk_lamp", ADDRESS).connect())


def test_read_power_asks_the_light(library_bulb):
    library_bulb.update.return_value = mock.Mock(is_on=False)

    async def scenario():
        async with GoveeBleBulb("desk_lamp", ADDRESS) as lamp:
            return await lamp.read_power()

    assert asyncio.run(scenario()) is False
    library_bulb.update.assert_awaited_once()


def test_read_power_errors_become_connection_errors(library_bulb):
    library_bulb.update.side_effect = GoveeBleError("no reply")

    async def scenario():
        async with GoveeBleBulb("desk_lamp", ADDRESS) as lamp:
            await lamp.read_power()

    with pytest.raises(ConnectionError, match="desk_lamp: no reply"):
        asyncio.run(scenario())