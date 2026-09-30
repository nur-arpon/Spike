import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/messages.dart';

/// Push-to-talk against the REAL brain, with the same client and the same
/// message sequence as lib/features/talk/ptt.dart (head tap, 40 ms pcm_s16le
/// chunks at 16 kHz in real time, 600 ms of silence).
///
/// Skipped unless SPIKE_LIVE_WAV points at a 16 kHz mono 16-bit WAV of a
/// request, and the brain runs on 127.0.0.1:8765:
///   set SPIKE_LIVE_WAV=C:\path\ask_time.wav
///   flutter test test/live_brain_test.dart
void main() {
  final wav = Platform.environment['SPIKE_LIVE_WAV'];
  test('spoken request over the protocol gets a spoken answer', () async {
    final client = BrainClient(identity: const ClientIdentity(deviceId: 'app-livetest', fw: '0.1.0', caps: ['face', 'text', 'mic']));
    final said = <String>[];
    final states = <String>[];
    final sub = client.messages.listen((m) {
      if (m is SayMsg && m.text.isNotEmpty) said.add(m.text);
      if (m is ListeningMsg) states.add(m.state);
    });
    client.connect(const BrainEndpoint(host: '127.0.0.1', port: 8765));
    await client.status.firstWhere((s) => s.isConnected).timeout(const Duration(seconds: 8));

    final bytes = File(wav!).readAsBytesSync();
    final pcm = Uint8List.sublistView(bytes, 44); // canonical RIFF header
    const chunk = 16000 * 2 * 40 ~/ 1000;
    var seq = 0;
    expect(client.send(const TouchMsg(zone: 'head', gesture: 'tap')), isTrue);
    await Future<void>.delayed(const Duration(milliseconds: 250));
    for (var off = 0; off < pcm.length; off += chunk) {
      final end = off + chunk > pcm.length ? pcm.length : off + chunk;
      client.send(AudioMsg(data: base64Encode(Uint8List.sublistView(pcm, off, end)), seq: ++seq));
      await Future<void>.delayed(const Duration(milliseconds: 40));
    }
    for (var i = 0; i < 15; i++) {
      client.send(AudioMsg(data: base64Encode(Uint8List(chunk)), seq: ++seq));
      await Future<void>.delayed(const Duration(milliseconds: 40));
    }
    final deadline = DateTime.now().add(const Duration(seconds: 20));
    while (said.isEmpty && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    // ignore: avoid_print
    print('listening states: $states\nSpike said: $said');
    await sub.cancel();
    await client.dispose();
    expect(states, contains('listening'));
    expect(said, isNotEmpty);
  }, skip: wav == null ? 'set SPIKE_LIVE_WAV to run against the real brain' : false, timeout: const Timeout(Duration(seconds: 60)));
}
