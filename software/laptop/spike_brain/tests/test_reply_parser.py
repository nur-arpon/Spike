"""The reply format parser and the streaming sentence chunker."""
import pytest

from spike_brain.mind.reply import (StreamParser, clean_speech, normalize_action, normalize_mood, parse_reply,
                                    split_sentences)


@pytest.mark.parametrize("raw,mood,action,text", [
    ("[mood:happy] [action:headTilt] Hello there!", "happy", "headTilt", "Hello there!"),
    ("[mood:playful][action:none] Nope.", "playful", None, "Nope."),
    ("[mood: confused] Huh?", "confusion", None, "Huh?"),
    ("[Mood=Sad] Oh no.", "sad", None, "Oh no."),
    ("[happy] Yay!", "happy", None, "Yay!"),
    ("[headTilt] [caring] Hmm?", "caring", "headTilt", "Hmm?"),
    ("Mood: happy\nAction: zoomies\nWheee!", "happy", "zoomies", "Wheee!"),
    ("*wags tail* Hi friend!", None, "tailWagDance", "Hi friend!"),
    ("<think>plan the joke</think>[mood:laughing] Ha!", "laughing", None, "Ha!"),
    ("\"[mood:smug] I knew it.\"", "smugness", None, "I knew it."),
    ("Just words, no tags.", None, None, "Just words, no tags."),
    ("[mood:happy] **Bold** and \U0001F436 emoji #1", "happy", None, "Bold and emoji 1"),
    ("[mood:unknownthing] Hi", None, None, "Hi"),
    ("[mood:cute_angry] Grr.", "cuteAngry", None, "Grr."),
])
def test_parse_reply(raw, mood, action, text):
    r = parse_reply(raw)
    assert (r.mood, r.action, r.text) == (mood, action, text)


def test_synonyms_cover_common_model_slips():
    for word, mood in [("grateful", "gratitude"), ("jealous", "jealousy"), ("tired", "sleepy"),
                       ("sassy", "smugness"), ("worried", "nervousness"), ("CURIOUS", "curious")]:
        assert normalize_mood(word) == mood
    assert normalize_action("tail wag dance") == "tailWagDance"
    assert normalize_action("roll over") is None      # hidden: the body cannot do it (capabilities.py)
    assert normalize_action("none") is None


def run_stream(text: str, piece: int, **kw):
    sp = StreamParser(**kw)
    events = []
    for i in range(0, len(text), piece):
        events += sp.feed(text[i:i + piece])
    events += sp.finish()
    return events


@pytest.mark.parametrize("piece", [1, 2, 3, 5, 8, 50])
def test_stream_tags_first_then_sentences(piece):
    ev = run_stream("[mood:excited] [action:zoomies] You're home! I missed you so much. Where were you?", piece)
    assert ev[0] == ("tags", "excited", "zoomies")
    sentences = [e[1] for e in ev if e[0] == "sentence"]
    assert sentences == ["You're home!", "I missed you so much.", "Where were you?"]


@pytest.mark.parametrize("piece", [1, 3, 7])
def test_stream_no_tags(piece):
    ev = run_stream("Hello! How are you?", piece)
    assert ev[0] == ("tags", None, None)
    assert [e[1] for e in ev if e[0] == "sentence"] == ["Hello!", "How are you?"]


def test_first_chunk_can_break_at_a_comma_for_speed():
    ev = run_stream("[mood:caring] Oh no, that sounds like a really rough day, come here. Tell me.", 2,
                    first_chunk_min_words=2)
    s = [e[1] for e in ev if e[0] == "sentence"]
    assert s[0] == "Oh no,"
    assert s[1:] == ["that sounds like a really rough day, come here.", "Tell me."]


def test_numbers_and_abbreviations_do_not_split():
    chunks, rest = split_sentences("See you at 7.30 tonight. Dr. Paws says hi. Bye", first=False)
    assert chunks == ["See you at 7.30 tonight.", "Dr. Paws says hi."] and rest == "Bye"


def test_long_sentences_are_cut():
    text = "word " * 80
    chunks, rest = split_sentences(text, first=False, max_chars=100)
    assert chunks and all(len(c) <= 100 for c in chunks)


def test_stage_directions_become_actions_mid_stream():
    ev = run_stream("[mood:happy] Hi! *wags tail* Ta-da!", 2)
    assert ("action", "tailWagDance") in ev
    assert [e[1] for e in ev if e[0] == "sentence"] == ["Hi!", "Ta-da!"]


def test_think_block_is_never_spoken():
    ev = run_stream("<think>I should be funny.</think>[mood:playful] Beep boop.", 3)
    assert ev[0] == ("tags", "playful", None)
    assert [e[1] for e in ev if e[0] == "sentence"] == ["Beep boop."]


def test_bracket_that_is_not_a_tag_is_spoken():
    ev = run_stream("[laughs loudly and falls over twice more] Oops.", 4)
    assert ev[0][0] == "tags"
    joined = " ".join(e[1] for e in ev if e[0] == "sentence")
    assert "Oops." in joined


def test_clean_speech():
    assert clean_speech("  *sigh*  Okay   then \U0001F600 ") == "Okay then"
    assert clean_speech("[action:yawn] zzz") == "zzz"


@pytest.mark.parametrize("raw,text", [
    ("[mood] You want to work? ...Fine.", "You want to work? ...Fine."),
    ("[mood|action] Hi.", "Hi."),
    ("[caring|snuggle] I'm here.", "I'm here."),
])
def test_copied_format_placeholders_are_never_spoken(raw, text):
    assert parse_reply(raw).text == text
    ev = run_stream(raw, 3)
    assert " ".join(e[1] for e in ev if e[0] == "sentence") == text


def test_emphasis_stars_keep_their_word_but_stage_directions_go():
    r = parse_reply("[mischief] Because it's too *wet*. *wags tail* Ha!")
    assert r.text == "Because it's too wet. Ha!" and r.action == "tailWagDance"


@pytest.mark.parametrize("raw,out", [
    ("Oh sweetie, that sounds really heavy.", "Oh, that sounds really heavy."),
    ("Honey, come here.", "Come here."),
    ("I love you, darling!", "I love you!"),
    ("Oh dear, that is bad.", "Oh dear, that is bad."),
    ("Oh my poor girl. It is okay.", "Oh. It is okay."),
])
def test_no_romantic_pet_names(raw, out):
    from spike_brain.mind.reply import strip_pet_names
    assert strip_pet_names(raw) == out
