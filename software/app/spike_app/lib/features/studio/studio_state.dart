import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../state/settings.dart';

/// The face_v2 recipe catalogue, read from the bundled recipe.js at run time
/// (SpikeFace.call('catalog')), so the Studio can never drift from the engine.
@immutable
class FaceCatalog {
  const FaceCatalog({
    required this.slots,
    required this.slotLabels,
    required this.optionLabels,
    required this.colors,
    required this.colorLabels,
    required this.numbers,
    required this.numberLabels,
    required this.presets,
    required this.moods,
    required this.actions,
    required this.defaults,
  });

  final Map<String, List<String>> slots;
  final Map<String, String> slotLabels;
  final Map<String, String> optionLabels;
  final List<String> colors;
  final Map<String, String> colorLabels;
  final Map<String, List<double>> numbers;
  final Map<String, String> numberLabels;
  final List<FacePreset> presets;
  final List<({String id, String label})> moods;
  final List<({String id, String label})> actions;
  final Map<String, Map<String, dynamic>> defaults;

  /// face_v2 studio.js order of the feature pickers.
  static const slotOrder = [
    'frame', 'pattern', 'patternSide', 'muzzle', 'eyeStyle', 'eyeShape', 'lashes', 'brows',
    'nose', 'mouth', 'ears', 'whiskers', 'accessory', 'freckles', //
  ];

  static FaceCatalog fromJson(Map<String, dynamic> j) {
    Map<String, String> sm(Object? o) => {for (final e in (o as Map).entries) e.key as String: e.value.toString()};
    return FaceCatalog(
      slots: {
        for (final e in (j['slots'] as Map).entries) e.key as String: (e.value as List).map((x) => x.toString()).toList(),
      },
      slotLabels: sm(j['slotLabels']),
      optionLabels: sm(j['optionLabels']),
      colors: (j['colors'] as List).map((x) => x.toString()).toList(),
      colorLabels: sm(j['colorLabels']),
      numbers: {
        for (final e in (j['numbers'] as Map).entries)
          e.key as String: (e.value as List).map((x) => (x as num).toDouble()).toList(),
      },
      numberLabels: sm(j['numberLabels']),
      presets: [for (final p in j['presets'] as List) FacePreset.fromJson(p as Map<String, dynamic>)],
      moods: [for (final m in j['moods'] as List) (id: m['id'] as String, label: m['label'] as String)],
      actions: [for (final m in j['actions'] as List) (id: m['id'] as String, label: m['label'] as String)],
      defaults: {
        for (final e in (j['defaults'] as Map).entries) e.key as String: Map<String, dynamic>.from(e.value as Map),
      },
    );
  }
}

@immutable
class FacePreset {
  const FacePreset({required this.id, required this.name, required this.kind, required this.recipe, required this.code});
  final String id;
  final String name;
  final String kind; // dog | cat
  final Map<String, dynamic> recipe;
  final String code;
  static FacePreset fromJson(Map<String, dynamic> j) => FacePreset(
        id: j['id'] as String,
        name: j['name'] as String,
        kind: j['kind'] as String,
        recipe: Map<String, dynamic>.from(j['recipe'] as Map),
        code: j['code'] as String,
      );
}

@immutable
class SavedFace {
  const SavedFace({required this.recipe, required this.mode, required this.savedAt});
  final Map<String, dynamic> recipe;
  final String mode;
  final DateTime savedAt;
  String get name => (recipe['name'] as String?) ?? 'My face';
  Map<String, Object?> toJson() => {'recipe': recipe, 'mode': mode, 'at': savedAt.toIso8601String()};
  static SavedFace? fromJson(Object? o) {
    if (o is! Map || o['recipe'] is! Map) return null;
    return SavedFace(
      recipe: Map<String, dynamic>.from(o['recipe'] as Map),
      mode: o['mode'] == 'cat' ? 'cat' : 'dog',
      savedAt: DateTime.tryParse(o['at']?.toString() ?? '') ?? DateTime.now(),
    );
  }
}

const studioSlotCount = 6;

@immutable
class StudioState {
  const StudioState({this.current = const {}, this.slots = const [], this.catalog});

  /// The face each character wears now (null = the engine default).
  final Map<String, Map<String, dynamic>?> current;
  final List<SavedFace?> slots;
  final FaceCatalog? catalog;

  StudioState copyWith({Map<String, Map<String, dynamic>?>? current, List<SavedFace?>? slots, FaceCatalog? catalog}) =>
      StudioState(current: current ?? this.current, slots: slots ?? this.slots, catalog: catalog ?? this.catalog);
}

class StudioNotifier extends Notifier<StudioState> {
  static const _k = 'spike.studio.v1';

  @override
  StudioState build() {
    final raw = ref.read(prefsProvider).getString(_k);
    var current = <String, Map<String, dynamic>?>{};
    var slots = List<SavedFace?>.filled(studioSlotCount, null);
    if (raw != null) {
      try {
        final j = jsonDecode(raw) as Map<String, dynamic>;
        final c = j['current'] as Map<String, dynamic>? ?? const {};
        current = {for (final e in c.entries) if (e.value is Map) e.key: Map<String, dynamic>.from(e.value as Map)};
        final s = j['slots'] as List? ?? const [];
        for (var i = 0; i < studioSlotCount && i < s.length; i++) {
          slots[i] = SavedFace.fromJson(s[i]);
        }
      } catch (_) {}
    }
    return StudioState(current: current, slots: slots);
  }

  void _save() {
    ref.read(prefsProvider).setString(
          _k,
          jsonEncode({
            'current': state.current,
            'slots': [for (final s in state.slots) s?.toJson()],
          }),
        );
  }

  void setCatalog(FaceCatalog c) => state = state.copyWith(catalog: c);

  void wear(String mode, Map<String, dynamic> recipe) {
    state = state.copyWith(current: {...state.current, mode: recipe});
    _save();
  }

  void saveSlot(int i, String mode, Map<String, dynamic> recipe) {
    final s = [...state.slots];
    s[i] = SavedFace(recipe: recipe, mode: mode, savedAt: DateTime.now());
    state = state.copyWith(slots: s);
    _save();
  }

  void clearSlot(int i) {
    final s = [...state.slots];
    s[i] = null;
    state = state.copyWith(slots: s);
    _save();
  }
}

final studioProvider = NotifierProvider<StudioNotifier, StudioState>(StudioNotifier.new);
