"""Voice commands (rules, not the LLM) and spoken time parsing."""
from datetime import datetime

import pytest

from spike_brain.life.timeparse import parse_duration_minutes, parse_when, say_duration, say_time, words_to_numbers
from spike_brain.mind.intents import match_intent

NAMES = {"dog": "Spike", "cat": "Spicy"}
EVENING = datetime(2026, 9, 28, 18, 0)      # a Monday, 6 pm
LATE = datetime(2026, 9, 28, 22, 0)


def intent(text, now=EVENING, **kw):
    return match_intent(text, NAMES, now, **kw)


@pytest.mark.parametrize("text,mode", [
    ("Cat mode!", "cat"), ("be a cat", "cat"), ("Spicy mode please", "cat"), ("switch to the cat", "cat"),
    ("Be a dog.", "dog"), ("dog mode", "dog"), ("come back Spike", "dog"), ("puppy mode", "dog"),
])
def test_mode_switching(text, mode):
    i = intent(text)
    assert i.name == "set_mode" and i.slots["mode"] == mode


def test_renamed_persona_names_work():
    i = match_intent("Pepper mode", {"dog": "Spike", "cat": "Pepper"}, EVENING)
    assert i.name == "set_mode" and i.slots["mode"] == "cat"


@pytest.mark.parametrize("text,at,what", [
    ("Remind me to call my mum at 7.30 tonight.", datetime(2026, 9, 28, 19, 30), "call your mum"),
    ("remind me in 10 minutes to check the oven", datetime(2026, 9, 28, 18, 10), "check the oven"),
    ("remind me at 9 tomorrow to take the bins out", datetime(2026, 9, 29, 9, 0), "take the bins out"),
    ("remind me to drink water in an hour", datetime(2026, 9, 28, 19, 0), "drink water"),
    ("remind me tomorrow morning at 8 about the dentist", datetime(2026, 9, 29, 8, 0), "the dentist"),
])
def test_reminders(text, at, what):
    i = intent(text)
    assert i.name == "set_reminder" and i.slots["at"] == at and i.slots["what"] == what


def test_reminder_without_a_time_asks():
    i = intent("remind me to feed the cat")
    assert i.name == "set_reminder" and i.slots["at"] is None


@pytest.mark.parametrize("text,now,at", [
    ("Wake me up at 6:30 a.m.", EVENING, datetime(2026, 9, 29, 6, 30)),
    ("Set an alarm for seven", EVENING, datetime(2026, 9, 29, 7, 0)),        # evening -> morning
    ("wake me up at 3", datetime(2026, 9, 28, 13, 0), datetime(2026, 9, 28, 15, 0)),  # a nap alarm
    ("set an alarm for half past six", LATE, datetime(2026, 9, 29, 6, 30)),
    ("wake me up in 20 minutes", EVENING, datetime(2026, 9, 28, 18, 20)),
])
def test_alarms(text, now, at):
    i = intent(text, now)
    assert i.name == "set_alarm" and i.slots["at"] == at


def test_alarm_ringing_commands():
    assert intent("okay okay I'm up", alarm_ringing=True).name == "alarm_stop"
    s = intent("five more minutes", alarm_ringing=True)
    assert s.name == "snooze" and s.slots["minutes"] == 5
    assert intent("snooze", alarm_ringing=True).name == "snooze"
    assert intent("stop", alarm_ringing=True).name == "alarm_stop"


@pytest.mark.parametrize("text,name", [
    ("Forget that.", "forget_last"), ("forget it", "forget_last"), ("scratch that", "forget_last"),
    ("forget everything", "forget_all"), ("wipe your memory", "forget_all"),
    ("what do you know about me?", "recall_all"), ("What time is it?", "tell_time"),
    ("what's the date", "tell_date"), ("Let's play rock paper scissors!", "rps_start"),
    ("stop", "stop"), ("shush", "stop"), ("go to sleep spike", "sleep"), ("do a trick", "trick"),
    ("cancel my alarms", "cancel_alarm"), ("what reminders do I have", "list_timers"),
    ("set a timer for 5 minutes", "set_reminder"),
])
def test_commands(text, name):
    assert intent(text).name == name


@pytest.mark.parametrize("text,action", [("Spin!", "zoomies"), ("sit", "playBow"), ("spin", "zoomies"),
                                         ("play dead", "fallAsleep"), ("can you dance", "tailWagDance")])
def test_tricks(text, action):
    i = intent(text)
    assert i.name == "trick" and i.slots["action"] == action


@pytest.mark.parametrize("text,action", [
    ("walk", "walk"), ("Walk!", "walk"), ("walk forward", "walk"), ("come here", "walk"),
    ("can you come here", "walk"), ("please walk", "walk"),
    ("give paw", "paw"), ("paw", "paw"), ("shake", "paw"), ("can you shake", "paw"),
])
def test_body_action_tricks(text, action):
    # v1.4 (PROTOCOL.md 5.2): walk and paw are real body actions, not face_v2 poses.
    i = intent(text)
    assert i.name == "trick" and i.slots["action"] == action


def test_remember_and_forget_about():
    i = intent("Remember that my sister Anna has her birthday on March 3rd.")
    assert i.name == "remember" and i.slots["fact"] == "my sister Anna has her birthday on March 3rd"
    f = intent("forget that I like pizza")
    assert f.name == "forget_about" and f.slots["what"] == "i like pizza"


def test_forget_all_needs_confirmation():
    assert intent("yes, forget everything", confirming_forget_all=True).name == "forget_all_confirmed"
    assert intent("no wait", confirming_forget_all=True).name == "forget_all_cancelled"


def test_rps_voice_choice():
    assert intent("Scissors!", in_rps=True).slots["choice"] == "scissors"
    assert intent("stone", in_rps=True).slots["choice"] == "rock"


@pytest.mark.parametrize("text", ["How are you today?", "I love pizza", "Do you remember when we met?",
                                  "tell me a joke", "my sister's name is Anna", "I'll sit down now and relax"])
def test_conversation_is_not_a_command(text):
    assert intent(text) is None


# ---- time parsing -----------------------------------------------------------------
def test_words_to_numbers():
    assert words_to_numbers("seven thirty five") == "7 35"
    assert words_to_numbers("seven oh five") == "7 05"
    assert words_to_numbers("someone at twenty past") == "someone at 20 past"


@pytest.mark.parametrize("text,at", [
    ("at noon", datetime(2026, 9, 29, 12, 0)),
    ("at midnight", datetime(2026, 9, 29, 0, 0)),
    ("quarter to nine tomorrow", datetime(2026, 9, 29, 8, 45)),
    ("at 7.30pm", datetime(2026, 9, 29, 19, 30)),
    ("in half an hour", datetime(2026, 9, 28, 22, 30)),
    ("in an hour and a half", datetime(2026, 9, 28, 23, 30)),
    ("in 2 hours", datetime(2026, 9, 29, 0, 0)),
    ("tomorrow morning at seven oh five", datetime(2026, 9, 29, 7, 5)),
    ("at 10", datetime(2026, 9, 29, 10, 0)),
])
def test_parse_when(text, at):
    assert parse_when(text, LATE).at == at


def test_no_time_found():
    assert parse_when("call someone", LATE) is None
    assert parse_duration_minutes("five more minutes") == 5
    assert parse_duration_minutes("an hour") == 60


def test_spoken_times():
    assert say_time(datetime(2026, 9, 29, 7, 0), LATE) == "tomorrow at 7 am"
    assert say_time(datetime(2026, 9, 28, 19, 30)) == "7:30 pm"
    assert say_duration(datetime(2026, 1, 1, 1, 30) - datetime(2026, 1, 1, 0, 0)) == "1 hour and 30 minutes"
