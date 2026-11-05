"""User configuration: which board, which devices, and what each control does.

The config is a YAML file, config.yaml by default. See config.example.yaml.

Classes:
    ConfigError: Raised when the config is missing or invalid.
    Action: What a control does.
    Curve: How fader position maps to brightness.
    DeviceConfig: One entry under `devices:`.
    ControlMapping: One entry under `controls:`.
    Config: A parsed and validated config file.

Functions:
    load_config: Read and validate a config file.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(Exception):
    """Raised when the config is missing or invalid."""


class Action(Enum):
    """What a control does when it moves."""

    BRIGHTNESS = "brightness"
    COLOR = "color"
    COLOR_TEMP = "color_temp"
    TOGGLE_POWER = "toggle_power"
    MASTER_BRIGHTNESS = "master_brightness"


class Curve(Enum):
    """How fader position maps to brightness."""

    PERCEPTUAL = "perceptual"
    LINEAR = "linear"


# Actions that apply to every device, so they don't take a `device:`.
GLOBAL_ACTIONS = frozenset({Action.MASTER_BRIGHTNESS})


@dataclass(frozen=True)
class DeviceConfig:
    """One entry under `devices:`.

    Attributes:
        name: The entry's key, e.g. "desk_lamp".
        type: Device plugin to use, e.g. "govee_ble".
        options: Plugin-specific settings, e.g. {"address": "AA:BB:..."}.
    """

    name: str
    type: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlMapping:
    """One entry under `controls:`.

    Attributes:
        control: Control name from the board profile, e.g. "fader.1".
        action: What the control does.
        devices: Names of the devices it acts on. Empty for global actions.
    """

    control: str
    action: Action
    devices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    """A parsed and validated config file.

    Attributes:
        profile: Board profile name, e.g. "zoom-r24".
        port: Exact MIDI port name, or None to auto-detect.
        devices: Device entries by name.
        controls: Control mappings by control name.
        brightness_curve: How fader position maps to brightness.
    """

    profile: str
    port: str | None
    devices: dict[str, DeviceConfig]
    controls: dict[str, ControlMapping]
    brightness_curve: Curve = Curve.PERCEPTUAL


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read and validate a config file.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed config.

    Raises:
        ConfigError: If the file is missing, isn't valid YAML, or has an
            invalid setting. The message names the setting to fix.
    """
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise ConfigError(
            f"No config file at {path}. Copy config.example.yaml to {path} to start."
        ) from None
    except yaml.YAMLError as err:
        raise ConfigError(f"{path} isn't valid YAML: {err}") from err

    if not isinstance(data, dict):
        raise ConfigError(f"{path} is empty")

    board = _mapping(data.get("board"), "board")
    if "profile" not in board:
        raise ConfigError("board.profile is required, e.g. profile: zoom-r24")

    try:
        curve = Curve(data.get("brightness_curve", Curve.PERCEPTUAL.value))
    except ValueError:
        raise ConfigError("brightness_curve must be perceptual or linear") from None

    devices = _parse_devices(_mapping(data.get("devices"), "devices"))
    controls = _parse_controls(_mapping(data.get("controls"), "controls"), devices)
    return Config(board["profile"], board.get("port"), devices, controls, curve)


def _mapping(value: Any, where: str) -> dict[str, Any]:
    """Return `value` as a dict, treating a missing section as empty."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a section of key: value settings")
    return value


def _parse_devices(raw: dict[str, Any]) -> dict[str, DeviceConfig]:
    """Validate the `devices:` section."""
    devices = {}
    for name, settings in raw.items():
        settings = _mapping(settings, f"devices.{name}")
        if "type" not in settings:
            raise ConfigError(f"devices.{name} needs a type, e.g. type: govee_ble")
        # YAML reads unquoted all-digit addresses like 12:34:56:12:34:56 as a number.
        if "address" in settings and not isinstance(settings["address"], str):
            raise ConfigError(f'devices.{name}.address must be in quotes, e.g. "AA:BB:CC:DD:EE:FF"')
        options = {key: value for key, value in settings.items() if key != "type"}
        devices[name] = DeviceConfig(name, settings["type"], options)
    return devices


def _parse_controls(
    raw: dict[str, Any], devices: dict[str, DeviceConfig]
) -> dict[str, ControlMapping]:
    """Validate the `controls:` section against the parsed devices."""
    valid_actions = ", ".join(action.value for action in Action)
    controls = {}
    for control, settings in raw.items():
        settings = _mapping(settings, f"controls.{control}")
        try:
            action = Action(settings.get("action"))
        except ValueError:
            raise ConfigError(
                f"controls.{control} needs an action. Choose from: {valid_actions}"
            ) from None

        names = settings.get("device", [])
        names = [names] if isinstance(names, str) else list(names)

        if action in GLOBAL_ACTIONS:
            if names:
                raise ConfigError(f"controls.{control}: {action.value} applies to every device")
        elif not names:
            raise ConfigError(f"controls.{control}: {action.value} needs a device")

        unknown = [name for name in names if name not in devices]
        if unknown:
            known = ", ".join(devices) or "none"
            raise ConfigError(
                f"controls.{control}: unknown device {unknown[0]!r}. Devices: {known}"
            )
        controls[control] = ControlMapping(control, action, tuple(names))
    return controls