"""What the real robot body can (not) do - ONE source of truth for the laptop brain.

Owner rule: the software must never SHOW or DO anything the physical body cannot.
Code for the impossible actions is kept (face_v2 still has the animations, the
protocol still names them) but nothing is allowed to choose, send or offer them.
Mirror of app/spike_app/lib/core/capabilities.dart - keep the two lists identical
(tests/test_capabilities.py checks the Dart file).

Sources: cad/servo_load_check_v3_1.md, cad/stability_research_review.md,
software/firmware/DESIGN.md section 15.
"""
from __future__ import annotations

# Actions the robot cannot do today. 'beggingAction' = both front paws up,
# 'rollOver' = a full roll (also what "high five" used to map to / play-dead-as-roll).
HIDDEN_ACTIONS = frozenset({"rollOver", "beggingAction"})

# Spoken tricks that need a hidden action -> the real trick we offer instead.
UNAVAILABLE_TRICKS = {
    "roll over": "playBow",
    "beg": "paw",
    "high five": "paw",
}

# Words used when offering the substitute.
OFFER_WORDS = {"paw": "give paw", "playBow": "a play bow", "tailWagDance": "a happy wag"}


def is_available(action: str | None) -> bool:
    """True if the body can do `action` (None / empty = no action = fine)."""
    return not action or action not in HIDDEN_ACTIONS


def available(actions):
    """Keep only what the body can do, order preserved."""
    return tuple(a for a in actions if is_available(a))


def unavailable_line(trick: str, mode: str = "dog") -> tuple[str, str | None]:
    """(spoken line, offered action) for a trick the body cannot do yet."""
    offer = UNAVAILABLE_TRICKS.get(trick, "playBow")
    what = OFFER_WORDS.get(offer, offer)
    if mode == "cat":
        return (f"[smugness] Hmph. I can't {trick} yet, and I would not anyway. "
                f"I could do {what} if you ask nicely.", offer)
    return (f"[sad] Aww, I can't {trick} yet, my legs are not that clever. "
            f"Want to see {what} instead?", offer)
