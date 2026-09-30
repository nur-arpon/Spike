/// Spike's laptop voice, played on the phone (protocol v1.5, PROTOCOL.md 10.8).
///
/// When the owner talks to Spike through this phone, the laptop brain sends
/// the reply's audio here (`say` with `play: true`, then `say_audio` chunks)
/// instead of playing it on its own speaker. Each utterance is ONE continuing
/// Ogg Opus stream (or PCM16): every sentence is appended to the same player
/// buffer the moment its last chunk arrives, so sentences follow each other
/// without a gap, and the first one starts as soon as it is here.
///
/// The fallback chain (owner decision "laptop voice first"):
///   laptop audio -> the phone's own voice (Kokoro if downloaded, else Android TTS).
/// A sentence that came with no audio (`audio: null`), whose audio never
/// completed, or that the player could not take, is said by the phone voice
/// after what is already buffered has played. If the link drops mid-reply,
/// every sentence already announced is still said, the missing audio by the
/// phone voice, so Spike never goes silent half way.
///
/// Playback is reported back with `say_state` (started / finished per
/// segment), which is what the brain waits for before it opens its mic again.
/// [speaking] is true from the first sentence of a reply until 300 ms after its
/// last one: the Talk screen's continuous listening pauses the mic on it.
///
/// This file is pure logic over two small interfaces ([VoiceOutput],
/// [SpikeVoice]) so it is tested without audio hardware; the real output is
/// `soloud_output.dart`.
library;

import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:typed_data';

import '../../protocol/messages.dart';
import 'speaker.dart';

/// What the phone can play, sent in hello (`audio_out`), best first.
const audioOutFormats = ['ogg_opus', 'pcm_s16le'];
const audioOutRates = [24000];

/// One utterance's audio on the phone's player.
abstract class VoiceStream {
  /// Append encoded bytes (the format given to [VoiceOutput.open]); starts playing on the first call.
  void add(Uint8List bytes);

  /// No more data will come: play to the end.
  void end();

  /// How far playback has got in this stream.
  Duration get position;

  /// Everything added has been played (after [end]), or the player gave up.
  bool get done;

  Future<void> stop();
}

abstract class VoiceOutput {
  /// A new stream for [format] (`ogg_opus` or `pcm_s16le`) at [rate] Hz mono.
  Future<VoiceStream> open({required String format, required int rate});
}

/// Which voice the owner last heard, for the tiny hint in Settings.
enum VoiceHeard { laptop, phone }

class _Seg {
  _Seg(this.say);
  final SayMsg say;
  final chunks = <int, Uint8List>{};
  bool complete = false;
  int? start, end; // in samples of the stream's rate
  bool started = false, finished = false;

  int get expected => (say.audio?['chunks'] as num?)?.toInt() ?? 0;
}

class _Utt {
  _Utt(this.id);
  final String id;
  final segs = SplayTreeMap<int, _Seg>();
  int? lastSeq; // seq of the final segment, once known
  bool stopped = false;
  VoiceStream? stream;
  String? format;
  int rate = 24000;
  int appended = 0; // samples in the stream
  Completer<void> _changed = Completer<void>();

  void poke() {
    if (!_changed.isCompleted) _changed.complete();
  }

  /// Wait for news about this utterance. False = [timeout] passed with none.
  Future<bool> changed(Duration timeout) async {
    if (_changed.isCompleted) _changed = Completer<void>();
    var poked = true;
    await _changed.future.timeout(timeout, onTimeout: () => poked = false);
    return poked;
  }
}

class LaptopVoicePlayer {
  LaptopVoicePlayer({
    required this.output,
    required this.phoneVoice,
    required this.report,
    required this.mode,
    this.enabled = _yes,
    this.tick = const Duration(milliseconds: 40),
    this.tail = const Duration(milliseconds: 300),
    this.waitNext = const Duration(seconds: 30),
  });

  static bool _yes() => true;

  /// The stream player, or null when this phone has none (every sentence is then said by [phoneVoice]).
  final Future<VoiceOutput?> Function() output;

  /// The phone's own voice for fallbacks (Kokoro -> Android TTS).
  final Future<SpikeVoice> Function() phoneVoice;

  /// Sends say_state to the brain (false = not connected; nothing else to do).
  final bool Function(String utt, int seq, String state) report;

  /// dog / cat, for the phone voice.
  final String Function() mode;

  /// False: the owner switched the phone's speech off; the timing (captions, mouth, reports) still runs.
  final bool Function() enabled;
  final Duration tick;
  final Duration tail;

  /// How long a reply may pause between sentences before the phone stops waiting for the next one.
  final Duration waitNext;

  final _utts = <String, _Utt>{};
  final _queue = Queue<_Utt>();
  bool _running = false;
  bool _linkUp = true;
  Timer? _ticker;
  Timer? _tailTimer;
  _Utt? _current;
  SpikeVoice? _fallbackPlaying;

  final _speaking = StreamController<bool>.broadcast();
  final _saying = StreamController<SayMsg>.broadcast();
  final _heard = StreamController<VoiceHeard>.broadcast();
  bool _isSpeaking = false;
  VoiceHeard? lastHeard;

  /// True while Spike talks through this phone (pause the mic).
  Stream<bool> get speaking => _speaking.stream;
  bool get isSpeaking => _isSpeaking;

  /// Each segment at the moment it starts playing, for the face's mouth and caption.
  Stream<SayMsg> get nowSaying => _saying.stream;
  Stream<VoiceHeard> get heard => _heard.stream;

  // ---------------------------------------------------------------- input
  /// Every message from the LAPTOP brain.
  void onMessage(SpikeMessage m) {
    switch (m) {
      case BrainHello():
        _linkUp = true;
      case SayMsg() when m.play:
        _onSay(m);
      case SayMsg() when m.isEndMarker:
        final u = _utts[m.utt];
        if (u != null) {
          u.lastSeq = m.seq;
          u.segs[m.seq] = _Seg(m)..complete = true;
          u.poke();
        }
      case SayAudioMsg():
        final seg = _utts[m.utt]?.segs[m.seq];
        if (seg == null || seg.complete) return;
        try {
          seg.chunks[m.index] = base64Decode(m.data);
        } catch (_) {
          return;
        }
        if (seg.chunks.length >= seg.expected) seg.complete = true;
        _utts[m.utt]?.poke();
      case StopSpeakingMsg():
        stop(m.utt);
      default:
        break;
    }
  }

  /// The laptop link dropped: finish what was announced with the phone voice.
  void onLinkLost() {
    _linkUp = false;
    for (final u in _utts.values) {
      u.poke();
    }
  }

  void _onSay(SayMsg m) {
    var u = _utts[m.utt];
    if (u == null) {
      u = _utts[m.utt] = _Utt(m.utt);
      _queue.add(u);
      _setSpeaking(true);
    }
    final seg = _Seg(m);
    if (m.audio == null) seg.complete = true;
    u.segs[m.seq] = seg;
    if (m.isFinal) u.lastSeq = m.seq;
    u.poke();
    _pump();
  }

  /// stop_speaking: [utt] null = everything.
  Future<void> stop([String? utt]) async {
    final hit = [for (final u in _utts.values) if (utt == null || u.id == utt) u];
    for (final u in hit) {
      u.stopped = true;
      u.poke();
      await u.stream?.stop();
    }
    if (_current != null && hit.contains(_current)) await _fallbackPlaying?.stop();
  }

  // ---------------------------------------------------------------- playback
  void _pump() {
    if (_running) return;
    _running = true;
    unawaited(() async {
      try {
        while (_queue.isNotEmpty) {
          final u = _queue.removeFirst();
          _current = u;
          try {
            await _play(u);
          } catch (_) {
            // a player failure never leaves the queue stuck
          }
          _current = null;
          _utts.remove(u.id);
          if (_utts.length > 40) _utts.clear();
        }
      } finally {
        _running = false;
        if (_queue.isEmpty) _endSpeakingSoon();
      }
    }());
  }

  Future<void> _play(_Utt u) async {
    var next = 0;
    while (!u.stopped) {
      final seg = u.segs[next];
      if (seg == null) {
        if (u.lastSeq != null && next > u.lastSeq!) break;
        if (!_linkUp) break;
        if (!await u.changed(waitNext)) break; // the brain went quiet: stop waiting for the rest
        continue;
      }
      if (seg.say.isEndMarker) {
        next++;
        continue;
      }
      while (!seg.complete && _linkUp && !u.stopped) {
        if (!await u.changed(waitNext)) break; // no more chunks came: the phone voice says it
      }
      if (u.stopped) break;
      if (!(seg.complete && seg.say.audio != null && enabled() && await _append(u, seg))) {
        await _drain(u);
        if (u.stopped) break;
        await _sayOnPhone(u, seg);
      }
      next++;
    }
    u.stream?.end();
    if (!u.stopped) await _drain(u);
    _ticker?.cancel();
    _ticker = null;
    _checkProgress(u, all: true);
  }

  /// Put a segment's audio into the utterance's stream. False = the phone voice must say it.
  Future<bool> _append(_Utt u, _Seg seg) async {
    final a = seg.say.audio!;
    final fmt = a['format'] as String? ?? 'pcm_s16le';
    final rate = (a['rate'] as num?)?.toInt() ?? 24000;
    final samples = (a['samples'] as num?)?.toInt() ?? 0;
    if (!audioOutFormats.contains(fmt) || samples <= 0) return false;
    try {
      if (u.stream != null && (u.format != fmt || u.rate != rate)) {
        await _drain(u); // a format change mid-reply (the brain fell back to PCM): a fresh stream
        u.stream!.end();
        u.stream = null;
      }
      if (u.stream == null) {
        final out = await output();
        if (out == null) return false;
        u.stream = await out.open(format: fmt, rate: rate);
        u.format = fmt;
        u.rate = rate;
        u.appended = 0;
      }
      final b = BytesBuilder(copy: false);
      for (var i = 0; i < seg.expected; i++) {
        final c = seg.chunks[i];
        if (c == null) return false;
        b.add(c);
      }
      u.stream!.add(b.takeBytes());
    } catch (_) {
      return false;
    }
    seg.start = u.appended;
    u.appended += samples;
    seg.end = u.appended;
    _ticker ??= Timer.periodic(tick, (_) => _checkProgress(u));
    _checkProgress(u);
    return true;
  }

  int _posSamples(_Utt u) {
    final s = u.stream;
    if (s == null) return 0;
    if (s.done) return u.appended;
    return s.position.inMicroseconds * u.rate ~/ 1000000;
  }

  /// Report started / finished as the player's position passes each segment.
  void _checkProgress(_Utt u, {bool all = false}) {
    final pos = all ? 1 << 62 : _posSamples(u);
    for (final seg in u.segs.values) {
      final st = seg.start, en = seg.end;
      if (st == null || en == null) continue;
      if (!seg.started && (pos >= st || all)) {
        seg.started = true;
        if (!all || !u.stopped) _startedSeg(u, seg, VoiceHeard.laptop);
      }
      if (!seg.finished && (pos >= en - (u.rate ~/ 50) || all)) {
        seg.finished = true;
        report(u.id, seg.say.seq, u.stopped ? 'stopped' : 'finished');
      }
    }
  }

  void _startedSeg(_Utt u, _Seg seg, VoiceHeard how, {SpokenClip? clip}) {
    report(u.id, seg.say.seq, 'started');
    final s = seg.say;
    if (_saying.isClosed) return;
    _saying.add(clip == null
        ? s
        : SayMsg(
            utt: s.utt, seq: s.seq, isFinal: s.isFinal, text: s.text, mood: s.mood, durationMs: clip.durationMs,
            mouth: clip.mouth == null ? null : {'rate_hz': clip.mouthHz, 'values': clip.mouth},
          ));
    if (enabled()) {
      lastHeard = how;
      _heard.add(how);
    }
  }

  /// Wait until the stream has played everything added so far.
  Future<void> _drain(_Utt u) async {
    final s = u.stream;
    if (s == null) return;
    final deadline = DateTime.now().add(Duration(milliseconds: u.appended * 1000 ~/ u.rate + 4000));
    while (!u.stopped && !s.done && _posSamples(u) < u.appended - (u.rate ~/ 50) && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(tick);
      _checkProgress(u);
    }
    _checkProgress(u);
  }

  Future<void> _sayOnPhone(_Utt u, _Seg seg) async {
    final text = seg.say.text.trim();
    if (text.isEmpty) return;
    SpikeVoice v;
    try {
      v = enabled() ? await phoneVoice() : SilentVoice();
    } catch (_) {
      v = SilentVoice();
    }
    PreparedSpeech p;
    try {
      p = await v.prepare(text, mode: mode());
    } catch (_) {
      v = SilentVoice();
      p = await v.prepare(text, mode: mode());
    }
    if (u.stopped) return;
    seg.started = true;
    _startedSeg(u, seg, VoiceHeard.phone, clip: p.clip);
    _fallbackPlaying = v;
    try {
      await p.play();
    } finally {
      _fallbackPlaying = null;
    }
    seg.finished = true;
    report(u.id, seg.say.seq, u.stopped ? 'stopped' : 'finished');
  }

  void _setSpeaking(bool on) {
    _tailTimer?.cancel();
    _tailTimer = null;
    if (on == _isSpeaking || _speaking.isClosed) return;
    _isSpeaking = on;
    _speaking.add(on);
  }

  void _endSpeakingSoon() {
    _tailTimer?.cancel();
    _tailTimer = Timer(tail, () {
      if (_queue.isEmpty && !_running) _setSpeaking(false);
    });
  }

  Future<void> dispose() async {
    await stop();
    _ticker?.cancel();
    _tailTimer?.cancel();
    await _speaking.close();
    await _saying.close();
    await _heard.close();
  }
}
