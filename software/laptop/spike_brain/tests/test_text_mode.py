"""`--text` with piped input: scripted personality tests.

    printf "hi\\nwhat time is it\\n" | python -m spike_brain --text --no-camera

Runs the real command line in a subprocess (no model: --no-llm), with its
memory in a temp folder, and checks the transcript and a clean exit."""
import subprocess
import sys

from .conftest import LAPTOP


def run_text(tmp_path, lines: list[str], timeout=90):
    settings = tmp_path / "s.toml"
    settings.write_text(f'[memory]\ndb_path = "{(tmp_path / "m.sqlite").as_posix()}"\n'
                        f'llm_extraction = false\n[server]\nport = 0\n', encoding="utf-8")
    return subprocess.run([sys.executable, "-m", "spike_brain", "--text", "--no-camera", "--no-llm",
                           "--settings", str(settings)],
                          input="\n".join(lines) + "\n", capture_output=True, text=True, encoding="utf-8",
                          cwd=LAPTOP, timeout=timeout)


def test_piped_lines_get_replies_and_a_clean_exit(tmp_path, settings):
    r = run_text(tmp_path, ["hi", "what time is it", "", "cat mode", "spin"])
    assert r.returncode == 0, r.stderr[-1500:]
    out = [ln for ln in r.stdout.splitlines() if ln.strip()]
    replies = [ln for ln in out if ln.startswith(("Spike:", "Spicy:"))]
    # his hello comes first, before any input is answered
    dog = settings.personas["dog"]
    greetings = {dog.line(key, owner="you").split("] ", 1)[-1]          # no name known: "Good evening."
                 for key in ("greet_morning", "greet_afternoon", "greet_evening", "greet_night")}
    assert out[0].startswith("Spike:") and out[0].split("] ", 1)[-1] in greetings, out[:3]
    # every input is echoed, then answered, in order
    assert [ln for ln in out if ln.startswith("> ")] == ["> hi", "> what time is it", "> cat mode", "> spin"]
    # the time answer comes after the question (search only after it: the night greeting itself says "It's late")
    q = out.index("> what time is it")
    assert any("It's" in ln and ln.startswith("Spike:") for ln in out[q + 1:out.index("> cat mode")])
    after_cat = out[out.index("> cat mode") + 1:]
    assert after_cat[0].startswith("Spicy:"), "cat mode switched persona"
    trick = out[out.index("> spin") + 1:]
    assert len([ln for ln in trick if ln.startswith("Spicy:")]) == 2, "she refuses, then does it"
    assert len(replies) >= 6
    # logs go to stderr, so stdout stays a clean transcript
    assert "spike.brain" not in r.stdout and "spike.server" in r.stderr
    assert "end of typed input" in r.stderr


def test_empty_input_exits_straight_away(tmp_path):
    r = run_text(tmp_path, [], timeout=60)
    assert r.returncode == 0
    assert [ln for ln in r.stdout.splitlines() if ln.startswith("Spike:")], "only his hello"
