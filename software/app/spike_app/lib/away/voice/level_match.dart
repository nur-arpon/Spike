/// Level matching for the phone's own voices (owner request, 30 Sep): the laptop's voice streams to
/// the phone at about -21 dBFS RMS (spike_brain DESIGN.md 6d), so Kokoro and Gemini (TTS and Live)
/// are brought to the same perceived loudness where the app controls the PCM, with a soft limiter
/// so the gain can never clip. Android's own TTS gives the app no PCM: see [androidTtsVolume].
///
/// Loudness = RMS over the *spoken* stretches only (windows above [gateDbfs]), because pauses would
/// otherwise make a slow voice look quiet and get pushed too hot.
library;

import 'dart:math';
import 'dart:typed_data';

/// The laptop voice's decoded level (DESIGN.md 6d).
const double targetRmsDbfs = -21.0;

/// Never boost or cut by more than this: a silent or broken clip must not become a roar.
const double maxBoostDb = 18.0, maxCutDb = -18.0;

/// Windows quieter than this (20 ms RMS) count as pause, not speech.
const double gateDbfs = -50.0;

/// The limiter starts to bend at [limiterKnee] and can never exceed [limiterCeiling] (linear, 1.0 = full scale).
const double limiterKnee = 0.7, limiterCeiling = 0.95;

/// Android's own TTS is not touched (no PCM to measure). Its `volume` parameter is 0..1 of the media
/// stream, the same stream the other voices use, so full is the right setting: the engine's own
/// output sits well under -21 dBFS, and lowering it would only widen the gap.
const double androidTtsVolume = 1.0;

double _db(double linear) => 20 * log(linear) / ln10;
double _lin(double db) => pow(10, db / 20).toDouble();

/// Average RMS (dBFS) of the spoken windows of [x] (-1..1) at [rate] Hz; null when nothing is loud enough.
double? speechRmsDbfs(Float32List x, int rate) {
  final win = max(1, rate ~/ 50);
  final gate = _lin(gateDbfs);
  var sum = 0.0, n = 0;
  for (var i = 0; i < x.length; i += win) {
    final end = min(x.length, i + win);
    var acc = 0.0;
    for (var j = i; j < end; j++) {
      acc += x[j] * x[j];
    }
    if (sqrt(acc / (end - i)) >= gate) {
      sum += acc;
      n += end - i;
    }
  }
  if (n == 0) return null;
  return _db(sqrt(sum / n));
}

/// The gain in dB that takes [currentRmsDbfs] to [target], clamped to [maxCutDb]..[maxBoostDb].
double gainDbFor(double currentRmsDbfs, {double target = targetRmsDbfs}) =>
    (target - currentRmsDbfs).clamp(maxCutDb, maxBoostDb).toDouble();

/// Smooth, continuous, symmetric: identity up to the knee, then bends toward [limiterCeiling] and never passes it.
double softLimit(double x) {
  final a = x.abs();
  if (a <= limiterKnee) return x;
  final room = limiterCeiling - limiterKnee;
  final e = exp(2 * (a - limiterKnee) / room);
  final y = limiterKnee + room * (e - 1) / (e + 1);
  return x < 0 ? -y : y;
}

/// A whole clip (Kokoro, Gemini TTS): gain toward -21 dBFS, then the limiter. A clip with no speech comes back unchanged.
Float32List levelMatch(Float32List x, int rate, {double target = targetRmsDbfs}) {
  final rms = speechRmsDbfs(x, rate);
  if (rms == null) return x;
  final g = _lin(gainDbFor(rms, target: target));
  final out = Float32List(x.length);
  for (var i = 0; i < x.length; i++) {
    out[i] = softLimit(x[i] * g);
  }
  return out;
}

/// The same for 16-bit little-endian PCM bytes.
Uint8List levelMatchPcm16(Uint8List pcm, int rate, {double target = targetRmsDbfs}) {
  final n = pcm.length ~/ 2;
  final bd = ByteData.sublistView(pcm);
  final x = Float32List(n);
  for (var i = 0; i < n; i++) {
    x[i] = bd.getInt16(i * 2, Endian.little) / 32768.0;
  }
  final y = levelMatch(x, rate, target: target);
  final out = Uint8List(pcm.length);
  final ob = ByteData.sublistView(out);
  for (var i = 0; i < n; i++) {
    ob.setInt16(i * 2, (y[i].clamp(-1.0, 1.0) * 32767).round(), Endian.little);
  }
  if (pcm.length.isOdd) out[pcm.length - 1] = pcm[pcm.length - 1];
  return out;
}

/// Streaming version for Gemini Live, whose audio arrives in small pieces with no way to look ahead.
/// It keeps a running mean-square of the spoken windows (about the last 4 s of speech), so the gain
/// settles within a phrase and follows the voice after that. The gain moves in a straight ramp
/// across each piece (no clicks), and the limiter always runs.
class StreamLeveler {
  StreamLeveler({this.rate = 24000, this.target = targetRmsDbfs});
  final int rate;
  final double target;
  double _energy = 0; // sum of squares of spoken samples, decayed
  double _count = 0; // how many samples that sum stands for
  double _gain = 1.0; // linear, where the last piece ended

  /// Forget the previous utterance.
  void reset() {
    _energy = 0;
    _count = 0;
    _gain = 1.0;
  }

  /// The current gain in dB (0 before any speech has been heard).
  double get gainDb => _db(_gain);

  Uint8List process(Uint8List pcm) {
    final n = pcm.length ~/ 2;
    if (n == 0) return pcm;
    final bd = ByteData.sublistView(pcm);
    final x = Float32List(n);
    for (var i = 0; i < n; i++) {
      x[i] = bd.getInt16(i * 2, Endian.little) / 32768.0;
    }
    final win = max(1, rate ~/ 50), gate = _lin(gateDbfs), cap = rate * 4.0;
    for (var i = 0; i < n; i += win) {
      final end = min(n, i + win);
      var acc = 0.0;
      for (var j = i; j < end; j++) {
        acc += x[j] * x[j];
      }
      if (sqrt(acc / (end - i)) >= gate) {
        _energy += acc;
        _count += end - i;
        if (_count > cap) {
          _energy *= cap / _count;
          _count = cap;
        }
      }
    }
    final goal = _count == 0 ? _gain : _lin(gainDbFor(_db(sqrt(_energy / _count)), target: target));
    final out = Uint8List(pcm.length);
    final ob = ByteData.sublistView(out);
    final from = _gain;
    for (var i = 0; i < n; i++) {
      final g = from + (goal - from) * (i + 1) / n;
      ob.setInt16(i * 2, (softLimit(x[i] * g).clamp(-1.0, 1.0) * 32767).round(), Endian.little);
    }
    _gain = goal;
    if (pcm.length.isOdd) out[pcm.length - 1] = pcm[pcm.length - 1];
    return out;
  }
}
