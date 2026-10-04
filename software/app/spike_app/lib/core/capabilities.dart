/// What the real robot body can (not) do - ONE source of truth for the app.
///
/// Owner rule: the app must never SHOW or DO anything the physical body cannot.
/// The code for the impossible actions is kept (face_v2 still has the animations,
/// the protocol still names them) but nothing may offer, choose or send them.
/// Mirror of laptop spike_brain/capabilities.py - keep the two lists identical
/// (a laptop test reads this file and compares).
///
/// Sources: cad/servo_load_check_v3_1.md, cad/stability_research_review.md,
/// firmware/DESIGN.md section 15.
library;

/// Actions the robot cannot do today. 'beggingAction' = both front paws up,
/// 'rollOver' = a full roll.
const hiddenActions = {'rollOver', 'beggingAction'};

/// True if the body can do [action] (null / empty = no action = fine).
bool isAvailable(String? action) => action == null || action.isEmpty || !hiddenActions.contains(action);

/// Keep only what the body can do, order preserved.
List<T> availableOnly<T>(Iterable<T> items, String Function(T) actionOf) =>
    [for (final i in items) if (isAvailable(actionOf(i))) i];

/// Spoken tricks that need a hidden action -> the real trick we offer instead.
const unavailableTricks = {'roll over': 'playBow', 'beg': 'paw', 'high five': 'paw'};

const _offerWords = {'paw': 'give paw', 'playBow': 'a play bow', 'tailWagDance': 'a happy wag'};

/// (spoken line, offered action) for a trick the body cannot do yet.
(String, String) unavailableLine(String trick, String mode) {
  final offer = unavailableTricks[trick] ?? 'playBow';
  final what = _offerWords[offer] ?? offer;
  if (mode == 'cat') {
    return ("[smugness] Hmph. I can't $trick yet, and I would not anyway. I could do $what if you ask nicely.", offer);
  }
  return ("[sad] Aww, I can't $trick yet, my legs are not that clever. Want to see $what instead?", offer);
}

/// What the real body can do on a desk, in plain words, for the robot story and the "imagine this on
/// your desk" cards (features/story/). ONE list so the sales copy can never promise more than the body
/// does: every entry is a real ability from the list at the top of this file; [inDevelopment] marks the
/// two the body is still being taught (walk, give paw). Never add an action that is in [hiddenActions].
typedef BodyAbility = ({String label, String action, bool inDevelopment});

const bodyAbilities = <BodyAbility>[
  (label: 'Drive around your desk', action: 'drive', inDevelopment: false),
  (label: 'Sit', action: 'sit', inDevelopment: false),
  (label: 'Lie down', action: 'lieDown', inDevelopment: false),
  (label: 'Bow', action: 'playBow', inDevelopment: false),
  (label: 'Tilt his head', action: 'headTilt', inDevelopment: false),
  (label: 'Snuggle', action: 'snuggle', inDevelopment: false),
  (label: 'Wag his tail', action: 'tailWagDance', inDevelopment: false),
  (label: 'Quick happy spins', action: 'zoomies', inDevelopment: false),
  (label: 'Lift a back paw', action: 'backPaw', inDevelopment: false),
  (label: 'Walk', action: 'walk', inDevelopment: true),
  (label: 'Give paw', action: 'paw', inDevelopment: true),
];
