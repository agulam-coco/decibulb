"""Tests for decibulb.boards.mackie.

MIDI values come from a real Zoom R24 captured with aseqdump.
"""

import asyncio
import logging
import threading

import mido
import pytest

from decibulb.boards import mackie
from decibulb.boards.mackie import MackieBoard, translate
from decibulb.events import ControlKind
from decibulb.profiles import load_profile

R24 = load_profile("zoom-r24")


@pytest.mark.parametrize(
    ("pitch", "expected"),
    [(-8192, 0.0), (0, 0.5), (8191, 1.0)],
)
def test_fader_value_is_normalized(pitch, expected):
    event = translate(mido.Message("pitchwheel", channel=0, pitch=pitch), R24)
    assert event.control == "fader.1"
    assert event.kind is ControlKind.FADER
    assert event.value == pytest.approx(expected, abs=1e-4)


def test_master_fader_is_channel_8():
    event = translate(mido.Message("pitchwheel", channel=8, pitch=8191), R24)
    assert event.control == "master"


def test_button_press_and_note_off_release():
    press = translate(mido.Message("note_on", note=94, velocity=127), R24)
    release = translate(mido.Message("note_off", note=94), R24)
    assert (press.control, press.pressed) == ("play", True)
    assert (release.control, release.pressed) == ("play", False)


def test_note_on_velocity_zero_is_release():
    event = translate(mido.Message("note_on", note=96, velocity=0), R24)
    assert (event.control, event.pressed) == ("up", False)


@pytest.mark.parametrize(
    ("note", "control"),
    [(0, "rec.1"), (8, "solo.1"), (16, "mute.1"), (23, "mute.8")],
)
def test_status_keys_in_each_mode(note, control):
    event = translate(mido.Message("note_on", note=note, velocity=127), R24)
    assert event.control == control


@pytest.mark.parametrize(("value", "steps"), [(1, 1.0), (3, 3.0), (65, -1.0), (67, -3.0)])
def test_jog_steps(value, steps):
    event = translate(mido.Message("control_change", control=60, value=value), R24)
    assert event.control == "jog"
    assert event.kind is ControlKind.ENCODER
    assert event.value == steps


@pytest.mark.parametrize("value", [0, 64])
def test_zero_step_jog_is_skipped(value):
    assert translate(mido.Message("control_change", control=60, value=value), R24) is None


@pytest.mark.parametrize(
    "msg",
    [
        mido.Message("pitchwheel", channel=15, pitch=0),
        mido.Message("note_on", note=127, velocity=127),
        mido.Message("control_change", control=1, value=10),
        mido.Message("program_change", program=5),
    ],
)
def test_unknown_messages_return_none(msg):
    assert translate(msg, R24) is None


class FakeMidi:
    """Stands in for the MIDI system: a list of ports that tests can change."""

    def __init__(self, monkeypatch, ports=()):
        self.ports = list(ports)
        self.callback = None
        self.closed = 0
        monkeypatch.setattr(mido, "get_input_names", lambda: list(self.ports))
        monkeypatch.setattr(mido, "open_input", self.open_input)

    def open_input(self, name, callback=None):
        self.callback = callback
        midi = self

        class Port:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                midi.closed += 1

        return Port()

    def send(self, msg):
        """Deliver a message from another thread, like the real MIDI library."""
        thread = threading.Thread(target=self.callback, args=(msg,))
        thread.start()
        thread.join()


FADER_UP = mido.Message("pitchwheel", channel=0, pitch=8191)


def test_find_port_lists_connected_ports(monkeypatch):
    FakeMidi(monkeypatch, ["Midi Through:Midi Through Port-0 14:0"])
    with pytest.raises(OSError, match="No MIDI input matching 'R24 MIDI'. Connected: Midi Through"):
        MackieBoard(R24).find_port()


def test_find_port_uses_the_profiles_match(monkeypatch):
    FakeMidi(monkeypatch, ["Midi Through:Midi Through Port-0 14:0", "R24:R24 MIDI 1 24:0"])
    assert MackieBoard(R24).find_port() == "R24:R24 MIDI 1 24:0"


def test_listen_waits_for_the_board_and_survives_it_leaving(monkeypatch, caplog):
    midi = FakeMidi(monkeypatch)

    async def wait_for(condition):
        while not condition():
            await asyncio.sleep(0.01)

    async def main():
        listener = MackieBoard(R24).listen(poll_seconds=0.01)
        events = []

        async def collect():
            async for _msg, event in listener:
                events.append(event)

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)
        assert midi.callback is None  # still waiting for the board

        midi.ports = ["R24:R24 MIDI 1 24:0"]
        await wait_for(lambda: midi.callback is not None)
        midi.send(FADER_UP)
        await wait_for(lambda: len(events) == 1)

        # Turned off: the port disappears. Turned back on: it may get a new number.
        midi.ports = []
        await wait_for(lambda: midi.closed == 1)
        midi.callback = None
        midi.ports = ["R24:R24 MIDI 1 28:0"]
        await wait_for(lambda: midi.callback is not None)
        midi.send(FADER_UP)
        await wait_for(lambda: len(events) == 2)

        task.cancel()
        return events

    with caplog.at_level(logging.WARNING, logger=mackie.__name__):
        events = asyncio.run(asyncio.wait_for(main(), 2))
    assert [(event.control, event.value) for event in events] == [("fader.1", 1.0)] * 2
    assert "Waiting for Zoom R24 to be connected..." in caplog.text
    assert "Zoom R24 disconnected." in caplog.text