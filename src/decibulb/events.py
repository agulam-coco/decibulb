"""Board-independent control events.

Board plugins turn raw hardware messages into ControlEvents, so the rest
of decibulb never handles MIDI directly.

Classes:
    ControlKind: The type of physical control.
    ControlEvent: A single change on a control.
"""

from dataclasses import dataclass
from enum import Enum


class ControlKind(Enum):
    """The type of physical control that produced an event."""

    FADER = "fader"
    BUTTON = "button"
    ENCODER = "encoder"


@dataclass(frozen=True)
class ControlEvent:
    """A single change on a board control.

    Attributes:
        control: Control name from the board profile, e.g. "fader.1".
        kind: The type of control.
        value: Depends on kind. Faders: position from 0.0 to 1.0.
        Buttons: 1.0 pressed, 0.0 released. Encoders: signed step
        count since the last event (positive is clockwise).
    """

    control: str
    kind: ControlKind
    value: float

    @property
    def pressed(self) -> bool:
        """Return True if this is a button event and the button is down."""
        return self.kind is ControlKind.BUTTON and self.value >= 0.5
