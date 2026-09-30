/// The real [VoiceOutput]: flutter_soloud's buffer stream (SoLoud, C++).
///
/// Why SoLoud (DESIGN.md "Laptop voice on the phone"): it decodes Ogg Opus
/// itself (libopus/libogg ship in the plugin for Android), plays a stream that
/// grows while it plays (each sentence is appended to the same buffer: no gap,
/// no player restart), and pauses by itself when the buffer runs dry and goes
/// on when the next sentence arrives. audioplayers (already in the app) can
/// only play whole files; just_audio would need a custom StreamAudioSource and
/// still restarts per file. Version 4.x: 5.x conflicts with flutter_gemma_litertlm.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_soloud/flutter_soloud.dart';

import 'laptop_voice.dart';

class SoloudOutput implements VoiceOutput {
  SoloudOutput._();

  static Future<SoloudOutput?>? _once;

  /// The engine, started once; null if it cannot start on this phone (the phone voice is then used).
  static Future<SoloudOutput?> instance() => _once ??= () async {
        try {
          final s = SoLoud.instance;
          if (!s.isInitialized) await s.init(channels: Channels.mono, sampleRate: 48000, bufferSize: 1024);
          return SoloudOutput._();
        } catch (_) {
          _once = null; // try again next time
          return null;
        }
      }();

  @override
  Future<VoiceStream> open({required String format, required int rate}) async {
    final src = SoLoud.instance.setBufferStream(
      maxBufferSizeBytes: 64 * 1024 * 1024, // a limit, not an allocation
      bufferingType: BufferingType.preserved, // keeps the position meaningful for say_state
      bufferingTimeNeeds: 0.15, // after a dry spell, go on once 150 ms of the next sentence is in
      sampleRate: rate,
      channels: Channels.mono,
      format: format == 'ogg_opus' ? BufferType.auto : BufferType.s16le,
    );
    return _SoloudStream(src);
  }
}

class _SoloudStream implements VoiceStream {
  _SoloudStream(this._src);
  final AudioSource _src;
  SoundHandle? _h;
  bool _ended = false;
  bool _disposed = false;
  bool _failed = false;

  SoLoud get _s => SoLoud.instance;

  @override
  void add(Uint8List bytes) {
    if (_disposed) return;
    _s.addAudioDataStream(_src, bytes); // throws on a bad stream: the player says it with the phone voice
    _h ??= _s.play(_src);
  }

  @override
  void end() {
    if (_disposed || _ended) return;
    _ended = true;
    try {
      _s.setDataIsEnded(_src);
    } catch (_) {
      _failed = true;
    }
    if (_h == null) unawaited(_dispose());
  }

  @override
  Duration get position {
    final h = _h;
    if (h == null || _disposed) return Duration.zero;
    try {
      return _s.getPosition(h);
    } catch (_) {
      return Duration.zero;
    }
  }

  @override
  bool get done {
    if (_disposed || _failed) return true;
    final h = _h;
    if (h == null) return _ended;
    bool valid;
    try {
      valid = _s.getIsValidVoiceHandle(h);
    } catch (_) {
      valid = false;
    }
    if (!valid && _ended) unawaited(_dispose());
    return !valid && _ended;
  }

  @override
  Future<void> stop() async {
    final h = _h;
    if (h != null && !_disposed) {
      try {
        await _s.stop(h);
      } catch (_) {}
    }
    _ended = true;
    await _dispose();
  }

  Future<void> _dispose() async {
    if (_disposed) return;
    _disposed = true;
    try {
      await _s.disposeSource(_src);
    } catch (_) {}
  }
}
