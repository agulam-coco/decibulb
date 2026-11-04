"""Tests for decibulb.profiles."""

import pytest

from decibulb.profiles import available_profiles, load_profile


@pytest.mark.parametrize("name", available_profiles())
def test_every_bundled_profile_loads(name):
    profile = load_profile(name)
    assert profile.name
    assert profile.port_match
    assert profile.faders or profile.buttons or profile.encoders


@pytest.mark.parametrize("name", available_profiles())
def test_control_names_are_unique(name):
    profile = load_profile(name)
    names = [*profile.faders.values(), *profile.buttons.values(), *profile.encoders.values()]
    assert len(names) == len(set(names))


def test_unknown_profile_lists_available():
    with pytest.raises(FileNotFoundError, match="zoom-r24"):
        load_profile("does-not-exist")