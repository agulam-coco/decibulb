"""Tests for decibulb.boards.mackie.

MIDI values come from a real Zoom R24 captured with aseqdump.
"""

import mido
import pytest

from decibulb.boards.mackie import translate
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