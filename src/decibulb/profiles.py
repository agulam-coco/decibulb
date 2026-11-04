"""Board profiles: friendly names for a board's raw controls.

Profiles are YAML files bundled in decibulb/profiles/. Each one maps a
board's raw MIDI numbers to control names like "fader.1" or "play".

Classes:
    BoardProfile: A loaded board profile.

Functions:
    available_profiles: List bundled profile names.
    load_profile: Load a bundled profile by name.
"""

from dataclasses import dataclass, field
from importlib import resources

import yaml

_PROFILE_DIR = resources.files("decibulb") / "profiles"


@dataclass(frozen=True)
class BoardProfile:
    """Control names for one model of board.

    Attributes:
        name: Human-readable board name, e.g. "Zoom R24".
        protocol: Board plugin that reads this board, e.g. "mackie".
        port_match: Text that appears in the board's MIDI port name.
        faders: MIDI channel to fader name.
        buttons: MIDI note number to button name.
        encoders: MIDI control change number to encoder name.

    """

    name: str
    protocol: str
    port_match: str
    faders: dict[int, str] = field(default_factory=dict)
    buttons: dict[int, str] = field(default_factory=dict)
    encoders: dict[int, str] = field(default_factory=dict)


def available_profiles() -> list[str]:
    """Return the names of all bundled profiles, sorted."""
    return sorted(
        f.name.removesuffix(".yaml")
        for f in _PROFILE_DIR.iterdir()
        if f.name.endswith(".yaml")
    )


def load_profile(name: str) -> BoardProfile:
    """Load a bundled board profile.

    Args:
        name: Profile file name without the extension, e.g. "zoom-r24".

    Returns:
        The parsed profile.

    Raises:
        FileNotFoundError: If no bundled profile has that name.
    """
    path = _PROFILE_DIR / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(available_profiles())
        raise FileNotFoundError(f"No board profile named {name!r}. Available: {available}")

    data = yaml.safe_load(path.read_text())
    return BoardProfile(
        name=data["name"],
        protocol=data["protocol"],
        port_match=data["port_match"],
        faders={int(k): v for k, v in data.get("faders", {}).items()},
        buttons={int(k): v for k, v in data.get("buttons", {}).items()},
        encoders={int(k): v for k, v in data.get("encoders", {}).items()},    
    )
