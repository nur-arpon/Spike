import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../away/ai/key_store.dart';
import '../../away/ai/llm.dart';
import '../../away/ai/offline_brain.dart';
import '../../away/download/bundle.dart';
import '../../away/download/bundle_downloader.dart';
import '../../away/download/downloads.dart';
import '../../away/voice/speaker.dart';
import '../../core/haptics.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../state/away.dart';
import '../../state/settings.dart';
import 'voice_preview_screen.dart';
import 'voice_heard_hint.dart';

/// Settings for away from home (protocol v1.3): the phone brain, its AI key,
/// the offline brain, the phone voice, and the hotspot for the camera.
class AwaySettings extends ConsumerWidget {
  const AwaySettings({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(settingsProvider);
    final n = ref.read(settingsProvider.notifier);
    final away = ref.watch(awayProvider);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionHeader('Away from home', subtitle: 'When the laptop is out of reach, your phone becomes his brain'),
      SpikeCard(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(children: [
          SwitchListTile(
            title: const Text('Phone brain when away'),
            subtitle: Text(away.away ? 'On now: the phone is his brain' : 'Takes over by itself when the laptop is unreachable'),
            value: s.awayMode,
            onChanged: (v) {
              Haptics.tick();
              n.update((x) => x.copyWith(awayMode: v));
            },
          ),
          SwitchListTile(
            title: const Text('Spike talks on this phone'),
            subtitle: const VoiceHeardHint(), // v1.5: also the laptop's voice at home (voice_heard_hint.dart)
            value: s.phoneSpeaks,
            onChanged: (v) {
              Haptics.tick();
              n.update((x) => x.copyWith(phoneSpeaks: v));
            },
          ),
        ]),
      ),
      const SectionHeader('His thinking brain (away)', subtitle: 'For real conversations while you are out'),
      const GeminiKeyCard(),
      const SizedBox(height: 12),
      const _OfflineCard(),
      const SectionHeader('His voice on the phone'),
      const GeminiVoiceCard(), // Gemini natural voice + "Hear Spike's voices" (voice_preview_screen.dart)
      const SizedBox(height: 12),
      const _VoiceCard(),
      const SectionHeader('Camera away from home', subtitle: 'His camera needs Wi-Fi: the phone makes a hotspot for it'),
      const _HotspotCard(),
    ]);
  }
}

// ---------------------------------------------------------------- the AI key

/// The Gemini key: paste, test, save, remove. The phone (away brain) and the desktop (the built-in
/// brain, which is restarted with the new key: [onChanged]) use the same card.
class GeminiKeyCard extends ConsumerStatefulWidget {
  const GeminiKeyCard({super.key, this.onChanged, this.savedText = 'Saved. Spike can chat away from home.', this.whereKept = 'the phone\'s secure keystore'});
  final Future<void> Function()? onChanged;
  final String savedText;
  final String whereKept;
  @override
  ConsumerState<GeminiKeyCard> createState() => _KeyCardState();
}

class _KeyCardState extends ConsumerState<GeminiKeyCard> {
  final _c = TextEditingController();
  bool _busy = false;
  String? _result;
  bool _ok = false;

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final d = await Clipboard.getData(Clipboard.kTextPlain);
    if (d?.text != null) setState(() => _c.text = tidyKey(d!.text!));
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final key = tidyKey(_c.text);
    if (key.isEmpty) {
      setState(() {
        _result = 'Paste a key first';
        _ok = false;
      });
      return;
    }
    setState(() => _busy = true);
    final problem = await ref.read(awayProvider.notifier).testKey(key);
    // a key that works (or is only out of quota for now) is kept; a wrong one is not
    final keep = problem == null || problem.contains('quota') || problem.contains('internet');
    if (keep) {
      await ref.read(awayProvider.notifier).saveKey(key);
      await widget.onChanged?.call();
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _ok = problem == null;
      _result = problem == null ? widget.savedText : (keep ? 'Saved. $problem.' : problem);
      if (keep) _c.clear();
    });
    keep ? Haptics.success() : Haptics.error();
  }

  Future<void> _test() async {
    setState(() => _busy = true);
    final problem = await ref.read(awayProvider.notifier).testKey();
    if (!mounted) return;
    setState(() {
      _busy = false;
      _ok = problem == null;
      _result = problem ?? 'The key works.';
    });
    problem == null ? Haptics.success() : Haptics.error();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final hasKey = ref.watch(awayProvider.select((a) => a.hasKey));
    final info = cloudProviders.first;
    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.key_rounded, color: hasKey ? Brand.ok : p.accent),
          const SizedBox(width: 10),
          Expanded(child: Text(info.label, style: context.tt.titleMedium)),
          if (hasKey) const StatusPill(label: 'Key saved', dot: Brand.ok),
        ]),
        const SizedBox(height: 6),
        Text('Get a free key at ${info.keyUrl}, then paste it here. It is kept in ${widget.whereKept}.',
            style: context.tt.bodySmall),
        const SizedBox(height: 12),
        TextField(
          controller: _c,
          obscureText: true,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(
            hintText: hasKey ? 'Paste a new key to replace it' : info.keyHint,
            suffixIcon: IconButton(onPressed: _paste, icon: const Icon(Icons.content_paste_rounded), tooltip: 'Paste'),
          ),
          onSubmitted: (_) => _save(),
        ),
        if (_result != null)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Row(children: [
              Icon(_ok ? Icons.check_circle_rounded : Icons.info_outline_rounded, size: 18, color: _ok ? Brand.ok : Brand.warn),
              const SizedBox(width: 8),
              Expanded(child: Text(_result!, style: context.tt.bodySmall)),
            ]),
          ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          PillButton(label: _busy ? 'Checking...' : 'Save', icon: Icons.save_rounded, filled: true, onTap: _busy ? null : _save),
          if (hasKey) PillButton(label: 'Test key', icon: Icons.network_check_rounded, onTap: _busy ? null : _test),
          if (hasKey)
            PillButton(
              label: 'Remove',
              icon: Icons.delete_outline_rounded,
              onTap: _busy
                  ? null
                  : () async {
                      Haptics.confirm();
                      await ref.read(awayProvider.notifier).deleteKey();
                      await widget.onChanged?.call();
                      setState(() => _result = null);
                    },
            ),
        ]),
      ]),
    );
  }
}

// ---------------------------------------------------------------- big downloads (shared)

/// Progress bar and one plain line for a big download.
class _DownloadProgress extends StatelessWidget {
  const _DownloadProgress(this.s);
  final DlStatus? s; // null while paused after a restart (progress not known yet)

  @override
  Widget build(BuildContext context) {
    final s = this.s;
    final pct = ((s?.fraction ?? 0) * 100).floor();
    final label = s == null
        ? 'Paused. Press Resume: it carries on where it stopped.'
        : switch (s.phase) {
            DlPhase.starting => 'Starting...',
            DlPhase.waitingForNetwork => 'Waiting for the internet. It carries on by itself.',
            DlPhase.verifying => 'Checking the download...',
            DlPhase.paused => 'Paused at $pct%. Press Resume: it carries on where it stopped.',
            DlPhase.failed => 'Stopped at $pct%.',
            _ => '$pct% of ${mb(s.total)}',
          };
    final indeterminate = s != null && s.busy && (s.fraction == 0 || s.phase == DlPhase.verifying);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SizedBox(height: 12),
      ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: LinearProgressIndicator(value: indeterminate ? null : (s?.fraction ?? 0), minHeight: 8),
      ),
      const SizedBox(height: 6),
      Text(label, style: context.tt.bodySmall),
    ]);
  }
}

/// Size, free space and (on mobile data) a one-line note, shown before a download.
class _SizeLine extends StatefulWidget {
  const _SizeLine(this.bytes);
  final int bytes;
  @override
  State<_SizeLine> createState() => _SizeLineState();
}

class _SizeLineState extends State<_SizeLine> {
  String? _line;
  @override
  void initState() {
    super.initState();
    unawaited(() async {
      final line = await sizeLine(widget.bytes, mobile: await onMobileData());
      if (mounted) setState(() => _line = line);
    }());
  }

  @override
  Widget build(BuildContext context) =>
      _line == null ? const SizedBox.shrink() : Padding(padding: const EdgeInsets.only(top: 6), child: Text(_line!, style: context.tt.bodySmall));
}

Widget _warnLine(BuildContext context, String text) =>
    Padding(padding: const EdgeInsets.only(top: 8), child: Text(text, style: context.tt.bodySmall?.copyWith(color: Brand.warn)));

// ---------------------------------------------------------------- the offline brain

class _OfflineCard extends ConsumerStatefulWidget {
  const _OfflineCard();
  @override
  ConsumerState<_OfflineCard> createState() => _OfflineCardState();
}

class _OfflineCardState extends ConsumerState<_OfflineCard> {
  String? _problem; // refused before starting (space)

  /// Download, or resume from the partial data.
  Future<void> _download() async {
    final brain = ref.read(offlineBrainProvider);
    final away = ref.read(awayProvider.notifier); // before the long wait (the card may be gone after)
    Haptics.confirm();
    setState(() => _problem = null);
    final need = await BundleDownloader.forBundle(await brain.bundle()).remainingBytes();
    final problem = await spaceProblem(need);
    if (problem != null) {
      if (mounted) setState(() => _problem = problem);
      return;
    }
    await askNotificationPermission();
    await brain.download();
    away.modelsChanged();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final brain = ref.read(offlineBrainProvider);
    final st = ref.watch(offlineStatusProvider).value ?? brain.current;
    final spec = brain.spec;
    final busy = st.state == OfflineState.downloading;
    final stopped = st.state == OfflineState.paused || st.state == OfflineState.failed;
    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.cloud_off_rounded, color: st.state == OfflineState.installed ? Brand.ok : p.accent),
          const SizedBox(width: 10),
          Expanded(child: Text('Offline brain', style: context.tt.titleMedium)),
          if (st.state == OfflineState.installed) const StatusPill(label: 'Installed', dot: Brand.ok),
        ]),
        const SizedBox(height: 6),
        Text(
            'A small brain that runs on the phone with no internet (${spec.label}, ${spec.licence}). '
            'Simpler than Gemini. Downloads ${spec.sizeMb} MB, only if you ask.',
            style: context.tt.bodySmall),
        if (busy || stopped) _DownloadProgress(st.dl ?? (busy ? const DlStatus(DlPhase.starting) : null)),
        if (st.state == OfflineState.failed && st.error != null) _warnLine(context, st.error!),
        if (_problem != null) _warnLine(context, _problem!),
        if (st.state == OfflineState.notInstalled || st.state == OfflineState.unknown) _SizeLine(spec.sizeBytes),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (busy) ...[
            PillButton(label: 'Pause', icon: Icons.pause_rounded, onTap: () {
              Haptics.tap();
              brain.pause();
            }),
            PillButton(label: 'Cancel', icon: Icons.close_rounded, onTap: () {
              Haptics.tap();
              brain.cancel();
            }),
          ] else if (stopped) ...[
            PillButton(label: 'Resume', icon: Icons.play_arrow_rounded, filled: true, onTap: _download),
            PillButton(label: 'Cancel', icon: Icons.close_rounded, onTap: () {
              Haptics.tap();
              brain.cancel();
            }),
          ] else if (st.state == OfflineState.installed)
            PillButton(label: 'Delete (${spec.sizeMb} MB)', icon: Icons.delete_outline_rounded, onTap: () async {
              Haptics.confirm();
              await brain.delete();
              ref.read(awayProvider.notifier).modelsChanged();
            })
          else
            PillButton(label: 'Download offline brain (${spec.sizeMb} MB)', icon: Icons.download_rounded, onTap: _download),
        ]),
      ]),
    );
  }
}

// ---------------------------------------------------------------- the voice pack

class _VoiceCard extends ConsumerStatefulWidget {
  const _VoiceCard();
  @override
  ConsumerState<_VoiceCard> createState() => _VoiceCardState();
}

class _VoiceCardState extends ConsumerState<_VoiceCard> {
  KokoroPack? _pack;
  BundleDownloader? _dl;
  StreamSubscription<DlStatus>? _sub;
  DlStatus? _st; // null = nothing in progress
  bool _partial = false; // part-downloaded before, file list not cached: progress unknown
  bool _preparing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(ref.read(awayProvider.notifier).voicePack().then((p) async {
      if (!mounted) return;
      setState(() => _pack = p);
      await _restore(p);
    }));
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  /// A download from before: follow it if it is still running, else show it paused.
  Future<void> _restore(KokoroPack p) async {
    if (p.installed || !await p.dir.exists()) return;
    try {
      final dl = _attach(await p.bundle(listIfMissing: false));
      if (dl.current.phase != DlPhase.idle) return; // already known in this app run
      if (await dl.runningInBackground()) {
        unawaited(_run(dl));
        return;
      }
      final left = await dl.remainingBytes();
      final total = dl.bundle.totalBytes;
      if (mounted) setState(() => _st = DlStatus(DlPhase.paused, done: total - left, total: total));
    } catch (_) {
      if (mounted) setState(() => _partial = true);
    }
  }

  BundleDownloader _attach(Bundle b) {
    final dl = _dl = BundleDownloader.forBundle(b);
    _sub ??= dl.status.listen((s) {
      if (mounted) setState(() => _st = s.phase == DlPhase.idle ? null : s);
    });
    if (dl.current.phase != DlPhase.idle) _st = dl.current;
    return dl;
  }

  /// Download, or resume: files already fetched (and checked) are kept.
  Future<void> _download() async {
    final pack = _pack;
    if (pack == null) return;
    Haptics.confirm();
    setState(() {
      _error = null;
      _preparing = true;
    });
    try {
      final dl = _attach(await pack.bundle());
      _partial = false;
      final problem = await spaceProblem(await dl.remainingBytes());
      if (problem != null) {
        if (mounted) setState(() => _error = problem);
        return;
      }
      await askNotificationPermission();
      if (mounted) setState(() => _preparing = false);
      await _run(dl);
    } catch (e) {
      if (mounted) setState(() => _error = 'Couldn\'t reach Hugging Face to list the voice files. Check the internet and try again.');
    } finally {
      if (mounted) setState(() => _preparing = false);
    }
  }

  Future<void> _run(BundleDownloader dl) async {
    // read before the long wait: the card may be gone when the download ends
    // (phone log 30 Sep 08:34: "Using ref when a widget ... has been unmounted")
    final away = ref.read(awayProvider.notifier);
    final s = await dl.start();
    if (s.phase == DlPhase.installed) {
      await away.voiceChanged();
      Haptics.success();
      if (mounted) setState(() => _st = null);
    }
  }

  Future<void> _cancel() async {
    Haptics.tap();
    final dl = _dl;
    if (dl != null) {
      await dl.cancel();
    } else {
      await _pack?.delete();
    }
    if (mounted) {
      setState(() {
        _st = null;
        _partial = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final installed = _pack?.installed ?? false;
    final st = _st;
    final busy = _preparing || (st?.busy ?? false);
    final stopped = !busy && (_partial || (st?.resumable ?? false));
    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.record_voice_over_rounded, color: installed ? Brand.ok : p.accent),
          const SizedBox(width: 10),
          Expanded(child: Text(installed ? 'Spike\'s own voice (on the phone)' : 'Phone voice', style: context.tt.titleMedium)),
          if (installed) const StatusPill(label: 'Installed', dot: Brand.ok),
        ]),
        const SizedBox(height: 6),
        Text(
            installed
                ? 'Kokoro voices chosen for Spike and Spicy, made on the phone. Android\'s voice steps in if needed.'
                : 'Now: Android\'s own voice. Download Spike\'s and Spicy\'s natural voices (Kokoro, about $kokoroApproxMb MB) to hear them away from home.',
            style: context.tt.bodySmall),
        if (busy || stopped) _DownloadProgress(_partial && st == null ? null : (st ?? const DlStatus(DlPhase.starting))),
        if (st?.phase == DlPhase.failed) _warnLine(context, downloadProblem(st!)),
        if (_error != null) _warnLine(context, _error!),
        if (!installed && !busy && !stopped) _SizeLine(kokoroApproxMb * 1000000),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (busy) ...[
            PillButton(label: 'Pause', icon: Icons.pause_rounded, onTap: _preparing ? null : () => _dl?.pause()),
            PillButton(label: 'Cancel', icon: Icons.close_rounded, onTap: _preparing ? null : _cancel),
          ] else if (stopped) ...[
            PillButton(label: 'Resume', icon: Icons.play_arrow_rounded, filled: true, onTap: _pack == null ? null : _download),
            PillButton(label: 'Cancel', icon: Icons.close_rounded, onTap: _cancel),
          ] else if (installed)
            PillButton(
              label: 'Delete voice (~$kokoroApproxMb MB)',
              icon: Icons.delete_outline_rounded,
              onTap: () async {
                Haptics.confirm();
                await _pack?.delete();
                await ref.read(awayProvider.notifier).voiceChanged();
                if (mounted) setState(() {});
              },
            )
          else
            PillButton(label: 'Download voice (~$kokoroApproxMb MB)', icon: Icons.download_rounded, onTap: _pack == null ? null : _download),
        ]),
      ]),
    );
  }
}

// ---------------------------------------------------------------- the hotspot

class _HotspotCard extends ConsumerStatefulWidget {
  const _HotspotCard();
  @override
  ConsumerState<_HotspotCard> createState() => _HotspotCardState();
}

class _HotspotCardState extends ConsumerState<_HotspotCard> {
  final _ssid = TextEditingController();
  final _pass = TextEditingController();
  bool _open = false;

  @override
  void initState() {
    super.initState();
    _ssid.text = ref.read(settingsProvider).manualHotspotSsid;
  }

  @override
  void dispose() {
    _ssid.dispose();
    _pass.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final s = ref.watch(settingsProvider);
    final away = ref.watch(awayProvider);
    final status = switch (away.hotspot) {
      HotspotConn.off => 'Off (comes on when you open his camera)',
      HotspotConn.starting => 'Starting...',
      HotspotConn.joining => 'Spike is joining...',
      HotspotConn.up => away.cameraOnline ? 'On: Spike and his camera are on it' : 'On: Spike is on it',
      HotspotConn.failed => hotspotProblem(away.hotspotReason),
    };
    return SpikeCard(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        ListTile(
          leading: Icon(Icons.wifi_tethering_rounded, color: away.hotspot == HotspotConn.up ? Brand.ok : p.accent),
          title: const Text('Phone hotspot'),
          subtitle: Text(status),
          trailing: away.hotspot == HotspotConn.failed
              ? TextButton(onPressed: () => ref.read(awayProvider.notifier).retryHotspot(), child: const Text('Retry'))
              : null,
        ),
        SwitchListTile(
          title: const Text('Keep it on while away'),
          subtitle: const Text('A backup link for Spike, not only for the camera (uses more battery)'),
          value: s.keepHotspot,
          onChanged: (v) {
            Haptics.tick();
            ref.read(settingsProvider.notifier).update((x) => x.copyWith(keepHotspot: v));
          },
        ),
        ListTile(
          title: const Text('Use my own hotspot instead'),
          subtitle: Text(s.manualHotspotSsid.isEmpty
              ? 'If your phone can\'t make one Spike can join (it needs 2.4 GHz)'
              : 'Saved: ${s.manualHotspotSsid}. Turn your hotspot on before opening the camera.'),
          trailing: Icon(_open ? Icons.expand_less_rounded : Icons.expand_more_rounded),
          onTap: () => setState(() => _open = !_open),
        ),
        if (_open)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              TextField(controller: _ssid, decoration: const InputDecoration(labelText: 'Hotspot name')),
              const SizedBox(height: 10),
              TextField(controller: _pass, obscureText: true, decoration: const InputDecoration(labelText: 'Hotspot password')),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: PillButton(
                    label: 'Save hotspot',
                    icon: Icons.save_rounded,
                    onTap: () async {
                      if (_pass.text.isNotEmpty && _pass.text.length < 8) {
                        showToast(context, 'Hotspot passwords are at least 8 characters', icon: Icons.error_outline_rounded);
                        return;
                      }
                      Haptics.confirm();
                      await ref.read(awayProvider.notifier).saveManualHotspot(_ssid.text, _pass.text);
                      _pass.clear();
                      if (mounted) setState(() => _open = false);
                    },
                  ),
                ),
              ]),
            ]),
          ),
      ]),
    );
  }
}

/// What a failed hotspot means, in plain words.
String hotspotProblem(String? reason) => switch (reason) {
      'permission' => 'Needs the Nearby Wi-Fi permission (Android asks when you open the camera)',
      'band' || 'not_found' => 'Spike couldn\'t see the hotspot (it needs 2.4 GHz). Save your own hotspot below.',
      'incompatible_mode' => 'Your phone\'s normal hotspot is on: turn it off, or save it below',
      'manual_missing' => 'Save your own hotspot below',
      'auth' => 'Spike couldn\'t join: check the hotspot password',
      'no_robot' => 'Spike isn\'t connected over Bluetooth yet',
      'timeout' => 'Spike didn\'t join in time. Retry, or save your own hotspot below.',
      'disallowed' => 'This phone doesn\'t allow app hotspots. Save your own hotspot below.',
      _ => 'Couldn\'t start the hotspot. Retry, or save your own hotspot below.',
    };
