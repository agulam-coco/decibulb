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


@dataclass(frozen=True)
class ControlEvent:
    """A single change on a board control.

    Attributes:
        control: Control name from the board profile, e.g. "fader.1".
        kind: The type of control.
        value: Position from 0.0 to 1.0. Buttons use 1.0 for pressed and
            0.0 for released.
    """

    control: str
    kind: ControlKind
    value: float

    @property
    def pressed(self) -> bool:
        """Return True if this is a button event and the button is down."""
        return self.kind is ControlKind.BUTTON and self.value >= 0.5
