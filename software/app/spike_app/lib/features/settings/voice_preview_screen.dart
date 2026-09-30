/// "Hear Spike's voices": Spike and Spicy through Gemini (Live with our speaking
/// directions, and TTS with our style prompts). A Spike | Spicy switch at the
/// top; each character's voice styles (a Google voice + how it talks) to hear
/// and pick; the pick is saved and then always used. Plus the settings card
/// that opens it. No key is ever shown here.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../away/ai/gemini_live.dart' show liveModels;
import '../../away/ai/gemini_voices.dart';
import '../../away/ai/key_store.dart';
import '../../away/ai/live_talk.dart';
import '../../away/voice/gemini_tts.dart';
import '../../core/haptics.dart';
import '../../core/platform.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../state/away.dart';
import '../../state/link.dart' show commandsProvider;
import '../../state/live_voice.dart';
import '../../state/settings.dart';
import '../../state/voice_out.dart' show voiceSourceProvider;

String liveEndMessage(LiveTalkEnd? e) => switch (e) {
      LiveTalkEnd.rateLimited => "Gemini's free voice time is used up for now. Spike will use his next voice until it's back.",
      LiveTalkEnd.badKey => 'Google refused the key for live voice. Check it with "Test key" (Away from home > His thinking brain).',
      LiveTalkEnd.network => 'No connection to Gemini right now. Check the internet and try again.',
      LiveTalkEnd.noMic => 'Allow the microphone to talk live.',
      LiveTalkEnd.crisis => 'Safety stepped in, so this conversation carries on with the checked voice.',
      LiveTalkEnd.unavailable => "Gemini Live didn't start with this key.",
      _ => '',
    };

/// The end message plus Google's own short reason, when there is one (never the key).
String liveEndNote(LiveTalkEnd? e, String? detail) {
  final m = liveEndMessage(e);
  if (m.isEmpty || detail == null || detail.isEmpty) return m;
  return '$m\nGoogle said: $detail';
}

String ttsErrorNote(TtsError e) {
  final base = e.kind == 'rate_limited' || e.kind == 'resting'
      ? liveEndMessage(LiveTalkEnd.rateLimited)
      : e.kind == 'bad_key'
          ? liveEndMessage(LiveTalkEnd.badKey)
          : e.kind == 'network'
              ? liveEndMessage(LiveTalkEnd.network)
              : 'Gemini TTS did not answer.';
  return e.message.isEmpty ? base : '$base (${e.message})';
}

class GeminiVoiceCard extends ConsumerStatefulWidget {
  const GeminiVoiceCard({super.key});
  @override
  ConsumerState<GeminiVoiceCard> createState() => _GeminiVoiceCardState();
}

class _GeminiVoiceCardState extends ConsumerState<GeminiVoiceCard> {
  @override
  Widget build(BuildContext context) {
    final hasKey = ref.watch(awayProvider.select((a) => a.hasKey));
    final picks = ref.read(awayProvider.notifier).voicePicks;
    final s = ref.watch(settingsProvider);
    String label(String mode) {
      final st = picks.styleFor(mode);
      return '${s.nameFor(mode)}: ${st.label} (${st.voice})';
    }

    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.graphic_eq_rounded, color: hasKey ? Brand.ok : context.sp.accent),
          const SizedBox(width: 10),
          Expanded(child: Text('Gemini natural voice', style: context.tt.titleMedium)),
          if (hasKey) const StatusPill(label: 'Ready', dot: Brand.ok),
        ]),
        const SizedBox(height: 6),
        Text(
            hasKey
                ? 'Spike talks through Google Gemini with your key whenever there is internet, at home too. '
                    '${label('dog')}. ${label('cat')}.'
                : 'Save a Gemini key above and Spike gets a natural voice, with nothing to download.',
            style: context.tt.bodySmall),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Use the laptop voice instead'),
          subtitle: const Text('At home, hear the laptop\'s own voice for Spike rather than Gemini.'),
          value: picks.laptopFirst,
          onChanged: (v) async {
            Haptics.tick();
            await picks.setLaptopFirst(v);
            ref.read(voiceSourceProvider.notifier).refresh();
            if (mounted) setState(() {});
          },
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Live conversation when away'),
          subtitle: const Text('He hears you and answers in his own voice straight away. Our safety rules still listen in.'),
          value: picks.liveOn,
          onChanged: (v) async {
            Haptics.tick();
            await picks.setLiveOn(v);
            if (mounted) setState(() {});
          },
        ),
        Wrap(spacing: 8, children: [
          PillButton(
            label: "Hear Spike's voices",
            icon: Icons.play_circle_outline_rounded,
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const VoicePreviewScreen())),
          ),
        ]),
      ]),
    );
  }
}

class VoicePreviewScreen extends ConsumerStatefulWidget {
  const VoicePreviewScreen({super.key});
  @override
  ConsumerState<VoicePreviewScreen> createState() => _VoicePreviewScreenState();
}

class _VoicePreviewScreenState extends ConsumerState<VoicePreviewScreen> {
  String _mode = 'dog'; // the Spike | Spicy switch
  String? _busy; // "<styleId>.tts" | ".live" | ".talk"
  String _note = '';
  GeminiTtsVoice? _tts;
  bool _cancel = false;

  GeminiVoicePicks get _picks => ref.read(awayProvider.notifier).voicePicks;
  late final GeminiLiveController _live;

  @override
  void initState() {
    super.initState();
    _live = ref.read(liveVoiceProvider.notifier);
  }

  @override
  void dispose() {
    _cancel = true;
    unawaited(_live.stop());
    unawaited(_tts?.stop());
    _tts?.close();
    super.dispose();
  }

  Future<void> _stopAll() async {
    _cancel = true;
    await _live.stop();
    await _tts?.stop();
    if (mounted) setState(() => _busy = null);
  }

  Future<void> _playTts(VoiceStyle st) async {
    await _stopAll();
    final key = await ref.read(secretStoreProvider).read(aiKeyName('gemini'));
    if (!mounted) return;
    if (key == null || key.isEmpty) {
      setState(() => _note = AppPlatform.desktop
          ? 'Save a Gemini key first (Settings > Spike\'s AI).'
          : 'Save a Gemini key first (Away from home > His thinking brain).');
      return;
    }
    _cancel = false;
    _tts?.close();
    final tts = _tts = GeminiTtsVoice(apiKey: key, voiceFor: (_) => st.voice, styleFor: (m, soft) => ttsStyle(m, soft: soft, style: st));
    setState(() {
      _busy = '${st.id}.tts';
      _note = 'Gemini TTS, ${st.voice}, style: "${st.tts}"';
    });
    try {
      for (final line in st.samples) {
        if (_cancel || !mounted) break;
        setState(() => _note = '${st.label} · ${st.voice} (TTS): "$line"');
        final p = await tts.prepare(line, mode: _mode);
        if (_cancel) break;
        await p.play();
      }
    } on TtsError catch (e) {
      if (mounted) setState(() => _note = ttsErrorNote(e));
    } catch (e) {
      if (mounted) setState(() => _note = 'Gemini TTS did not play (${e.runtimeType}).');
    }
    if (mounted && _busy == '${st.id}.tts') setState(() => _busy = null);
  }

  Future<void> _playLive(VoiceStyle st, {bool talk = false}) async {
    await _stopAll();
    if (!mounted) return;
    _cancel = false;
    final name = ref.read(settingsProvider).nameFor(_mode);
    setState(() {
      _busy = '${st.id}.${talk ? 'talk' : 'live'}';
      _note = talk ? 'Talk to $name: say something, then pause.' : 'Gemini Live, ${st.voice} (${st.label})';
    });
    final end = talk ? await _live.previewTalk(_mode, st) : await _live.preview(_mode, st, [...st.samples, sampleQuestion]);
    if (!mounted) return;
    final live = ref.read(liveVoiceProvider);
    setState(() {
      _busy = null;
      _note = end == null ? (live.said.isEmpty && !talk ? 'Gemini Live connected but said nothing.' : '') : liveEndNote(end, live.detail);
    });
  }

  @override
  Widget build(BuildContext context) {
    final live = ref.watch(liveVoiceProvider);
    final s = ref.watch(settingsProvider);
    final chosen = _picks.styleFor(_mode);
    return Scaffold(
      appBar: AppBar(title: const Text("Hear Spike's voices")),
      body: ListView(
        padding: EdgeInsets.fromLTRB(20, 8, 20, 30 + MediaQuery.paddingOf(context).bottom),
        children: [
          SegmentedButton<String>(
            segments: [
              ButtonSegment(value: 'dog', label: Text(s.nameFor('dog')), icon: const Icon(Icons.pets_rounded)),
              ButtonSegment(value: 'cat', label: Text(s.nameFor('cat')), icon: const Icon(Icons.auto_awesome_rounded)),
            ],
            selected: {_mode},
            onSelectionChanged: (v) async {
              Haptics.tick();
              await _stopAll();
              if (mounted) setState(() => _mode = v.first);
            },
          ),
          const SizedBox(height: 12),
          Text(
              'Google Gemini voices, each with our directions for how ${s.nameFor(_mode)} talks. Tap one to hear it, '
              'then pick it: it is used from then on, live and for every other line.',
              style: context.tt.bodyMedium),
          if (_note.isNotEmpty || live.said.isNotEmpty) ...[
            const SizedBox(height: 12),
            SpikeCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (_busy != null) StatusPill(label: live.phase == LivePhase.connecting ? 'Connecting' : live.talkState, pulse: true),
                if (_note.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Text(_note, style: context.tt.bodySmall)),
                if (live.said.isNotEmpty && _busy != null && !_busy!.endsWith('tts'))
                  Padding(padding: const EdgeInsets.only(top: 6), child: Text('"${live.said}"', style: context.tt.bodyMedium)),
              ]),
            ),
          ],
          SectionHeader(s.nameFor(_mode), subtitle: 'Now: ${chosen.label} · ${chosen.voice}'),
          for (final st in voiceStyles[_mode]!) _styleCard(context, st, st.id == chosen.id),
          const SizedBox(height: 16),
          Text(AppPlatform.desktop
              ? 'Voices use ${ttsModels.first} on Google\'s free tier with your key. When the free quota runs out, Spike '
                  'quietly uses Windows\' own voice until it is back.'
              : 'Live uses ${liveModels.first}; TTS uses ${ttsModels.first}. Both are on Google\'s free tier with your '
                  'key. When the free quota runs out, Spike quietly uses his next voice.',
              style: context.tt.bodySmall),
        ],
      ),
    );
  }

  Widget _styleCard(BuildContext context, VoiceStyle st, bool chosen) {
    final busy = _busy?.startsWith('${st.id}.') ?? false;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: SpikeCard(
        padding: const EdgeInsets.fromLTRB(6, 8, 6, 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ListTile(
            leading: Icon(chosen ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded,
                color: chosen ? context.sp.accent : null),
            title: Text('${st.label}  ·  ${st.voice} (${st.google})${st.id == defaultStyle[_mode] ? '  · default' : ''}'),
            subtitle: Text(st.why),
            onTap: () async {
              Haptics.tick();
              await _picks.pickStyle(_mode, st.id);
              ref.read(commandsProvider).voiceStyle(_mode, st.id); // v1.8: a brain that speaks with Gemini itself
              if (mounted) setState(() {});
            },
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Wrap(spacing: 8, runSpacing: 8, children: [
              if (busy)
                PillButton(label: 'Stop', icon: Icons.stop_rounded, filled: true, onTap: _stopAll)
              else ...[
                PillButton(label: AppPlatform.desktop ? 'Hear it' : 'Gemini TTS', icon: Icons.record_voice_over_rounded, onTap: () => _playTts(st)),
                // Gemini Live is the phone's away-from-home conversation; the desktop brain speaks with TTS
                if (!AppPlatform.desktop) ...[
                  PillButton(label: 'Gemini Live', icon: Icons.bolt_rounded, onTap: () => _playLive(st)),
                  PillButton(label: 'Talk live', icon: Icons.mic_rounded, onTap: () => _playLive(st, talk: true)),
                ],
              ],
            ]),
          ),
        ]),
      ),
    );
  }
}
