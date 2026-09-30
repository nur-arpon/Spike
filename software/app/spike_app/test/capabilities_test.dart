// The body cannot do everything the face can draw (core/capabilities.dart).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/brain/intents.dart' as intents;
import 'package:spike_app/away/brain/reply.dart';
import 'package:spike_app/core/capabilities.dart';
import 'package:spike_app/features/remote/remote_screen.dart';

void main() {
  test('the hidden list is the agreed one', () {
    expect(hiddenActions, {'rollOver', 'beggingAction'});
    expect(isAvailable('playBow'), isTrue);
    expect(isAvailable('paw'), isTrue);
    expect(isAvailable(null), isTrue);
    expect(isAvailable('rollOver'), isFalse);
    expect(isAvailable('beggingAction'), isFalse);
  });

  test('the trick buttons never include a hidden action (the full list still does, for later)', () {
    expect(tricks.where((t) => hiddenActions.contains(t.id)), isEmpty);
    expect(allTricks.map((t) => t.id), containsAll(hiddenActions));
    expect(tricks.length, allTricks.length - hiddenActions.length);
  });

  test('the model is never offered or parsed into a hidden action', () {
    expect(llmActions.toSet().intersection(hiddenActions), isEmpty);
    for (final w in ['rollOver', 'roll over', 'roll', 'rolls over', 'beg', 'begging', 'beggingAction']) {
      expect(normalizeAction(w), isNull, reason: w);
      expect(parseReply('[mood:happy] [action:$w] hi').action, isNull, reason: w);
    }
    expect(parseReply('[happy] *rolls over* hi').action, isNull);
    expect(parseReply('[happy] *begs* hi').action, isNull);
  });

  test('voice tricks that need a hidden action become trick_unavailable', () {
    for (final t in ['roll over', 'Roll over!', 'beg', 'high five', 'can you roll over please']) {
      expect(intents.matchIntent(t, const {})?.name, 'trick_unavailable', reason: t);
    }
    for (final e in intents.tricks.entries) {
      if (isAvailable(e.value)) expect(intents.matchIntent(e.key, const {})?.name, 'trick', reason: e.key);
    }
  });

  test('the "not yet" line is in character and offers a real trick', () {
    for (final t in ['roll over', 'beg', 'high five']) {
      for (final mode in ['dog', 'cat']) {
        final (line, offer) = unavailableLine(t, mode);
        expect(isAvailable(offer), isTrue);
        expect(line, contains("can't"));
        expect(line, contains(t));
        expect(parseReply(line).action, isNull);
      }
    }
    expect(unavailableLine('high five', 'dog').$2, 'paw');
  });

  test('no screen mentions a hidden action by name (they all go through capabilities)', () {
    final hits = <String>[];
    for (final f in Directory('lib/features').listSync(recursive: true).whereType<File>()) {
      if (!f.path.endsWith('.dart') || f.path.endsWith('remote_screen.dart')) continue;
      final s = f.readAsStringSync();
      for (final a in hiddenActions) {
        if (s.contains("'$a'")) hits.add('${f.path}: $a');
      }
    }
    expect(hits, isEmpty);
  });

  test('the Python list in the laptop brain is identical', () {
    final f = File('../../laptop/spike_brain/capabilities.py');
    if (!f.existsSync()) return;
    final m = RegExp(r'HIDDEN_ACTIONS\s*=\s*frozenset\(\{([^}]*)\}\)').firstMatch(f.readAsStringSync())!;
    final py = m.group(1)!.split(',').map((x) => x.trim().replaceAll('"', '').replaceAll("'", '')).where((x) => x.isNotEmpty).toSet();
    expect(py, hiddenActions);
  });
}
