"""Board plugin for Mackie Control devices.

Mackie Control is the protocol spoken by DAW controllers like the Zoom R24
and Behringer X-Touch. Faders send 14-bit pitch bend, one MIDI channel per
fader. Buttons send note on/off. Encoders send relative control changes.

Classes:
    MackieBoard: A Mackie Control board, connected now or later.

Functions:
    translate: Convert one MIDI message into a ControlEvent.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator

import mido

from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import BoardProfile

PITCH_MIN = -8192
PITCH_SPAN = 16383  # PITCH_MAX (8191) - PITCH_MIN
ENCODER_SIGN_BIT = 64  # values 1-63 turn clockwise, 65-127 counterclockwise
PORT_POLL_SECONDS = 2.0

logger = logging.getLogger(__name__)


def translate(msg: mido.Message, profile: BoardProfile) -> ControlEvent | None:
    """Convert one MIDI message into a ControlEvent.

    Args:
        msg: A message received from the board.
        profile: Names for the board's controls.

    Returns:
        The matching event, or None if the profile doesn't name the control
        or the message carries no change.
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
        if steps == 0:
            # The R24 sends zero-step jog messages when switching menus.
            return None
        return ControlEvent(profile.encoders[msg.control], ControlKind.ENCODER, float(steps))

    return None


class MackieBoard:
    """A Mackie Control board, connected now or later.

    Attributes:
        profile: Names for the board's controls.
        port_name: Exact MIDI port to use, or None to use the first port
            whose name contains profile.port_match.
    """

    def __init__(self, profile: BoardProfile, port_name: str | None = None) -> None:
        """Set up the board. Nothing is opened until read() or listen().

        Args:
            profile: Names for the board's controls.
            port_name: Exact port to open. If None, the port is found by
                profile.port_match each time the board is opened.
        """
        self.profile = profile
        self.port_name = port_name

    def find_port(self) -> str:
        """Return the board's MIDI port name.

        Raises:
            OSError: If the board isn't connected. The message lists the
                ports that are.
        """
        port = self._available_port()
        if port is None:
            wanted = self.port_name or self.profile.port_match
            connected = ", ".join(mido.get_input_names()) or "none"
            raise OSError(f"No MIDI input matching {wanted!r}. Connected: {connected}")
        return port

    def read(self) -> Iterator[tuple[mido.Message, ControlEvent | None]]:
        """Yield every message from the board with its translated event.

        Blocks while waiting for input and runs until the caller stops.

        Yields:
            (message, event) pairs. The event is None when translate()
            produces no event.

        Raises:
            OSError: If the board isn't connected.
        """
        with mido.open_input(self.find_port()) as port:
            for msg in port:
                yield msg, translate(msg, self.profile)

    async def listen(
        self, poll_seconds: float = PORT_POLL_SECONDS
    ) -> AsyncIterator[tuple[mido.Message, ControlEvent | None]]:
        """Yield messages like read(), surviving the board coming and going.

        Waits for the board if it isn't connected yet, and waits for it to
        come back if it disappears, such as when it's turned off. Runs until
        the caller's task is cancelled.

        Args:
            poll_seconds: How often to check whether the board is connected.

        Yields:
            (message, event) pairs, the same as read().
        """
        waiting_logged = False
        while True:
            port = self._available_port()
            if port is None:
                if not waiting_logged:
                    logger.warning("Waiting for %s to be connected...", self.profile.name)
                    waiting_logged = True
                await asyncio.sleep(poll_seconds)
                continue

            waiting_logged = False
            print(f"{self.profile.name} connected on {port}.")
            async for item in self._listen_until_gone(port, poll_seconds):
                yield item
            logger.warning("%s disconnected.", self.profile.name)

    async def _listen_until_gone(
        self, port: str, poll_seconds: float
    ) -> AsyncIterator[tuple[mido.Message, ControlEvent | None]]:
        """Yield messages from `port` until it disappears."""
        loop = asyncio.get_running_loop()
        messages: asyncio.Queue[mido.Message] = asyncio.Queue()

        def on_message(msg: mido.Message) -> None:
            # Runs on the MIDI library's own thread, so hand off to the event loop.
            loop.call_soon_threadsafe(messages.put_nowait, msg)

        with mido.open_input(port, callback=on_message):
            while True:
                try:
                    msg = await asyncio.wait_for(messages.get(), poll_seconds)
                except TimeoutError:
                    # A board that's turned off sends no error, it just goes quiet.
                    if port not in mido.get_input_names():
                        return
                    continue
                yield msg, translate(msg, self.profile)

    def _available_port(self) -> str | None:
        """Return the port to open if the board is connected, otherwise None."""
        ports = mido.get_input_names()
        if self.port_name is not None:
            return self.port_name if self.port_name in ports else None
        return next((name for name in ports if self.profile.port_match in name), None)