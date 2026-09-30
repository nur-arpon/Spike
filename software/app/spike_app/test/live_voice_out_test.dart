import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/voice/laptop_voice.dart';
import 'package:spike_app/away/voice/speaker.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/state/link.dart';

/// Protocol v1.5 against the REAL brain, with the app's own client, hello and player:
/// a typed message must come back as laptop audio routed to this "phone" (Ogg Opus,
/// one stream, played and reported by LaptopVoicePlayer). The captured stream is written
/// to SPIKE_LIVE_VOICE_OUT so a decoder can check it (spike_brain/tools/phone_voice_check.py
/// does the same from Python and decodes it).
///
/// Skipped unless SPIKE_LIVE_VOICE (a port number) is set and a brain listens on 127.0.0.1 there:
///   set SPIKE_LIVE_VOICE=8799
///   flutter test test/live_voice_out_test.dart
class _Capture implements VoiceStream, VoiceOutput {
  final bytes = BytesBuilder();
  Stopwatch? sw;
  String? format;
  bool ended = false;
  @override
  Future<VoiceStream> open({required String format, required int rate}) async {
    this.format = format;
    return this;
  }

  @override
  void add(Uint8List b) {
    bytes.add(b);
    sw ??= Stopwatch()..start();
  }

  @override
  void end() => ended = true;
  @override
  Duration get position => sw?.elapsed ?? Duration.zero; // "plays" in real time
  @override
  bool get done => ended && position > const Duration(seconds: 30);
  @override
  Future<void> stop() async {}
}

void main() {
  final port = int.tryParse(Platform.environment['SPIKE_LIVE_VOICE'] ?? '');
  test('typed on the phone -> the laptop voice plays on the phone', () async {
    final client = BrainClient(
        identity: const ClientIdentity(deviceId: 'app-live-voice', fw: appVersion, role: 'app', caps: appCaps,
            audioOut: appAudioOut));
    final cap = _Capture();
    final reports = <String>[];
    final phoneSaid = <String>[];
    final player = LaptopVoicePlayer(
      output: () async => cap,
      phoneVoice: () async => SilentVoice(),
      report: (u, s, st) {
        reports.add('$u/$s/$st');
        return client.send(SayStateMsg(utt: u, seq: s, state: st));
      },
      mode: () => 'dog',
    );
    Duration? firstAudio;
    final sw = Stopwatch();
    client.messages.listen((m) {
      if (m is SayAudioMsg) firstAudio ??= sw.elapsed;
      if (m is SayMsg && m.play && m.audio == null && m.text.isNotEmpty) phoneSaid.add(m.text);
      player.onMessage(m);
    });
    client.connect(BrainEndpoint(host: '127.0.0.1', port: port!));
    final st = await client.status.firstWhere((s) => s.isConnected).timeout(const Duration(seconds: 8));
    expect(st.hello?.audio?['format'], 'ogg_opus');
    await Future<void>.delayed(const Duration(milliseconds: 800));
    sw.start();
    expect(client.send(const TextMsg(text: 'what time is it')), isTrue);
    final end = DateTime.now().add(const Duration(seconds: 40));
    while (!reports.any((r) => r.endsWith('/finished')) && DateTime.now().isBefore(end)) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    final data = cap.bytes.toBytes();
    // ignore: avoid_print
    print('typed -> first audio frame: ${firstAudio?.inMilliseconds} ms; ${data.length} bytes; reports $reports');
    expect(cap.format, 'ogg_opus');
    expect(String.fromCharCodes(data.sublist(0, 4)), 'OggS');
    expect(String.fromCharCodes(data.sublist(28, 36)), 'OpusHead');
    expect(data.length, greaterThan(2000));
    expect(reports.first, endsWith('/started'));
    expect(phoneSaid, isEmpty);
    final out = Platform.environment['SPIKE_LIVE_VOICE_OUT'];
    if (out != null) File(out).writeAsBytesSync(data);
    await player.dispose();
    await client.dispose();
  }, skip: port == null ? 'set SPIKE_LIVE_VOICE=<port> with a brain running' : false, timeout: const Timeout(Duration(minutes: 2)));
}
