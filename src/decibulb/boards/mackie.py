"""Board plugin for Mackie Control devices.

Mackie Control is the protocol spoken by DAW controllers like the Zoom R24
and Behringer X-Touch. Faders send 14-bit pitch bend, one MIDI channel per
fader. Buttons send note on/off. Encoders send relative control changes.

Classes:
    MackieBoard: A connected Mackie Control board.

Functions:
    find_port: Find a MIDI input port by partial name.
    translate: Convert one MIDI message into a ControlEvent.
"""

from collections.abc import Iterator

import mido

from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import BoardProfile

PITCH_MIN = -8192
PITCH_SPAN = 16383  # PITCH_MAX (8191) - PITCH_MIN
ENCODER_SIGN_BIT = 64  # values 1-63 turn clockwise, 65-127 counterclockwise


def find_port(match: str) -> str:
    """Return the first MIDI input port whose name contains `match`.

    Args:
        match: Text to look for in the port name, e.g. "R24 MIDI".

    Returns:
        The full port name.

    Raises:
        OSError: If no connected port matches.
    """
    ports = mido.get_input_names()
    for name in ports:
        if match in name:
            return name
    connected = ", ".join(ports) or "none"
    raise OSError(f"No MIDI input matching {match!r}. Connected: {connected}")


def translate(msg: mido.Message, profile: BoardProfile) -> ControlEvent | None:
    """Convert one MIDI message into a ControlEvent.

    Args:
        msg: A message received from the board.
        profile: Names for the board's controls.

    Returns:
        The matching event, or None if the profile doesn't name the control.
    """
    if msg.type == "pitchwheel" and msg.channel in profile.faders:
        value = (msg.pitch - PITCH_MIN) / PITCH_SPAN
        return ControlEvent(profile.faders[msg.channel], ControlKind.FADER, value)

    if msg.type in ("note_on", "note_off") and msg.note in profile.buttons:
        # Some devices release with note_on velocity 0 instead of note_off.
        pressed = msg.type == "note_on" and msg.velocity > 0
        return ControlEvent(profile.buttons[msg.note], ControlKind.BUTTON, float(pressed))
    
    if msg.type == "control_change" and msg.control in profile.encoders:
        steps = msg.value if msg.value < ENCODER_SIGN_BIT else -(msg.value - ENCODER_SIGN_BIT)
        return ControlEvent(profile.encoders[msg.control], ControlKind.ENCODER, float(steps))

    return None


class MackieBoard:
    """A connected Mackie Control board.

    Attributes:
        profile: Names for the board's controls.
        port_name: The MIDI input port being read.
    """

    def __init__(self, profile: BoardProfile, port_name: str | None = None) -> None:
        """Locate the board's MIDI port.

        Args:
            profile: Names for the board's controls.
            port_name: Exact port to open. If None, the first port containing
                profile.port_match is used.

        Raises:
            OSError: If port_name is None and no matching port is found.
        """
        self.profile = profile
        self.port_name = port_name or find_port(profile.port_match)

    def read(self) -> Iterator[tuple[mido.Message, ControlEvent | None]]:
        """Yield every message from the board with its translated event.

        Blocks while waiting for input and runs until the caller stops.

        Yields:
            (message, event) pairs. The event is None for controls the
            profile doesn't name.
        """
        with mido.open_input(self.port_name) as port:
            for msg in port:
                yield msg, translate(msg, self.profile)
