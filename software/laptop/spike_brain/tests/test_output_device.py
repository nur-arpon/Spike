"""The laptop speaker is chosen by name, never by PortAudio's default (which was Sonar's virtual mic sink)."""
from spike_brain.speech.output import resolve_output_device

DEVS = [
    {"name": "Microsoft Sound Mapper - Input", "max_output_channels": 0},
    {"name": "SteelSeries Sonar - Microphone (SteelSeries Sonar Virtual Audio Device)", "max_output_channels": 2},
    {"name": "Microsoft Sound Mapper - Output", "max_output_channels": 2},
    {"name": "Speakers (Realtek(R) Audio)", "max_output_channels": 2},
    {"name": "SteelSeries Sonar - Media (SteelSeries Sonar Virtual Audio Device)", "max_output_channels": 2},
]


def test_empty_setting_uses_windows_default_not_sonar_mic():
    assert resolve_output_device("", DEVS) == 2
    assert resolve_output_device(None, DEVS) == 2


def test_setting_matches_by_name_case_insensitive():
    assert resolve_output_device("realtek", DEVS) == 3
    assert resolve_output_device("Sonar - Media", DEVS) == 4


def test_unknown_name_falls_back_to_windows_default():
    assert resolve_output_device("bluetooth headphones", DEVS) == 2


def test_index_passes_through():
    assert resolve_output_device(3, DEVS) == 3


def test_no_mapper_returns_none():
    assert resolve_output_device("", [d for d in DEVS if "Mapper" not in d["name"]]) is None
