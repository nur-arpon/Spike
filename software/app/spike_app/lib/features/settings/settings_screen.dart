import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';

import '../../core/brand.dart';
import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/nav.dart';
import '../../core/platform.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/client.dart';
import '../../protocol/names.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../../desktop/desktop_page.dart';
import '../../desktop/desktop_settings.dart';
import 'away_settings.dart';
import '../story/push_copy.dart' show storyTitle;


class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final s = ref.watch(settingsProvider);
    final n = ref.read(settingsProvider.notifier);
    final link = ref.watch(lanStatusProvider).value ?? const LinkStatus(); // the laptop link
    void set(AppSettings Function(AppSettings) f) {
      Haptics.tick();
      n.update(f);
    }

    return Scaffold(
      appBar: AppPlatform.desktop ? null : AppBar(title: const Text('Settings')),
      body: SettingsBody(
        children: [
          // ------------------------------------------------ connection (desktop: the brain on this computer)
          if (AppPlatform.desktop) const DesktopSettings(),
          if (AppPlatform.desktop) const SectionHeader('Voice', subtitle: 'How Spike and Spicy sound'),
          if (AppPlatform.desktop) const DesktopVoiceCard(),
          if (!AppPlatform.desktop) const SectionHeader('Spike\'s brain at home', subtitle: 'The laptop'),
          if (!AppPlatform.desktop) SpikeCard(
            padding: EdgeInsets.zero,
            child: Column(children: [
              ListTile(
                leading: Icon(link.isConnected ? Icons.link_rounded : Icons.link_off_rounded, color: link.isConnected ? Brand.ok : p.muted),
                title: Text(link.isConnected ? link.routeLabel : (link.isTrying ? 'Reconnecting' : 'Not connected')),
                subtitle: Text(s.endpoint == null
                    ? 'No brain chosen yet'
                    : '${link.isConnected && link.viaAlt ? '${link.host}:${s.endpoint!.port}' : s.endpoint!.label}'
                        '${link.hello != null ? '  ·  brain ${link.hello!.version}' : ''}${link.rttMs != null ? '  ·  ${link.rttMs} ms' : ''}'),
              ),
              Divider(height: 1, color: p.line),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(Icons.public_rounded, size: 20, color: s.endpoint?.alt.isNotEmpty == true ? Brand.ok : p.muted),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Away from home, the app reaches the laptop through Tailscale. Install the free Tailscale app on this '
                      'phone and sign in to the same account as the laptop.'
                      '${s.endpoint?.alt.isNotEmpty == true ? ' This laptop is on Tailscale, so it is tried after home Wi-Fi.' : ''}',
                      style: context.tt.bodySmall,
                    ),
                  ),
                ]),
              ),
              Divider(height: 1, color: p.line),
              ListTile(
                leading: Icon(Icons.wifi_find_rounded, color: p.accent),
                // the full connect screen (kept from before onboarding v2, which opens straight into exploring)
                title: Text(s.endpoint == null ? 'Connect to Spike' : 'Connect to Spike, or pair again'),
                subtitle: const Text('Find his brain on your Wi-Fi, scan a code, or type an address'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => context.push('/connect'),
              ),
              if (link.phase != LinkPhase.idle) ...[
                Divider(height: 1, color: p.line),
                ListTile(
                  leading: const Icon(Icons.power_settings_new_rounded, color: Brand.tongue),
                  title: const Text('Disconnect'),
                  onTap: () {
                    Haptics.confirm();
                    ref.read(brainClientProvider).disconnect();
                    n.update((x) => x.copyWith(clearEndpoint: true));
                  },
                ),
              ],
            ]),
          ),
          // ------------------------------------------------ names + voices
          const SectionHeader('Names', subtitle: 'Both names are yours to change'),
          SpikeCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              _NameField(label: 'Dog name', value: s.dogName, onSave: (v) => n.update((x) => x.copyWith(dogName: v))),
              const SizedBox(height: 12),
              _NameField(label: 'Cat name', value: s.catName, onSave: (v) => n.update((x) => x.copyWith(catName: v))),
              const SizedBox(height: 8),
              Text(
                  AppPlatform.desktop
                      ? 'Names show in this app. He still answers to his wake words (${_wakeWords(ref)}).'
                      : 'Names show in this app. He still answers to his wake words (${_wakeWords(ref)}), and his voice is set on the laptop.',
                  style: context.tt.bodySmall),
            ]),
          ),
          // ------------------------------------------------ talking (tap-to-talk voice session)
          const SectionHeader('Talking', subtitle: 'Tap the mic once; tap it again to stop'),
          SpikeCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Row(children: [
                Expanded(child: Text('Wait before Spike answers', style: context.tt.titleMedium)),
                Text('${s.voiceWaitS.toStringAsFixed(1)} s',
                    key: const ValueKey('voiceWaitValue'),
                    style: context.tt.titleMedium?.copyWith(color: p.accent, fontWeight: FontWeight.w800)),
              ]),
              Slider(
                key: const ValueKey('voiceWaitSlider'),
                value: s.voiceWaitS,
                min: 1.5,
                max: 6,
                divisions: 9,
                label: '${s.voiceWaitS.toStringAsFixed(1)} s',
                onChanged: (v) {
                  if (v != s.voiceWaitS) set((x) => x.copyWith(voiceWaitS: v));
                },
              ),
              Text('How long you can pause (a breath, an "umm", a thought) before he takes it that you have finished.',
                  style: context.tt.bodySmall),
            ]),
          ),
          // ------------------------------------------------ feel
          const SectionHeader('Look and feel'),
          SpikeCard(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(children: [
              SwitchListTile(
                title: const Text('Show captions on Spike\'s screen'),
                subtitle: const Text('Speech bubbles under his face'),
                value: s.showCaptions,
                onChanged: (v) {
                  set((x) => x.copyWith(showCaptions: v));
                  ref.read(commandsProvider).setCaptions(v); // v1.2 set_display (kept by the brain)
                },
              ),
              if (AppPlatform.haptics) SwitchListTile(
                title: const Text('Haptics'),
                subtitle: const Text('Feel pats, boops and every button'),
                value: s.haptics,
                onChanged: (v) {
                  n.update((x) => x.copyWith(haptics: v));
                  Haptics.confirm();
                },
              ),
              SwitchListTile(
                title: Text(AppPlatform.desktop ? 'Face sounds' : 'Face sounds on this phone'),
                subtitle: Text(AppPlatform.desktop
                    ? 'Yips, purrs and squeaks from his face in this window'
                    : 'Yips, purrs and squeaks from the phone face, with or without the robot'),
                value: s.faceSounds,
                onChanged: (v) => set((x) => x.copyWith(faceSounds: v)),
              ),
              ListTile(
                title: const Text('Theme'),
                trailing: _Choice<ThemeMode>(
                  value: s.themeMode,
                  items: const {ThemeMode.system: 'Auto', ThemeMode.light: 'Light', ThemeMode.dark: 'Dark'},
                  onChanged: (v) => set((x) => x.copyWith(themeMode: v)),
                ),
              ),
            ]),
          ),
          // ------------------------------------------------ away from home (v1.3)
          if (AppPlatform.awayFromHome) const AwaySettings(),
          // ------------------------------------------------ privacy
          const SectionHeader('Privacy'),
          SpikeCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              for (final (icon, text) in AppPlatform.desktop ? _desktopPrivacy : const [
                (Icons.home_rounded, 'At home Spike\'s brain runs on your own laptop. Speech, vision and memory stay there.'),
                (Icons.mic_rounded, 'The phone\'s microphone is used only after you tap the mic, until you tap it again, and never while the app is in the background.'),
                (Icons.smartphone_rounded, 'Away from home, what he remembers stays on this phone. His replies come from the AI key you add, or the offline brain.'),
                (Icons.videocam_off_rounded, 'Camera pictures are looked at in memory and never saved.'),
                (Icons.no_accounts_rounded, 'No account and no tracking in this app.'),
              ])
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(icon, size: 20, color: Brand.ok),
                    const SizedBox(width: 12),
                    Expanded(child: Text(text, style: context.tt.bodyMedium)),
                  ]),
                ),
              PillButton(label: 'See or erase what he remembers', icon: Icons.auto_stories_rounded, onTap: () => openPage(context, '/memories')),
            ]),
          ),
          // ------------------------------------------------ the robot story (every size)
          const SectionHeader("Spike's robot", subtitle: 'The body he is getting'),
          SpikeCard(
            onTap: () => context.push('/story'),
            child: Row(children: [
              Icon(Icons.smart_toy_rounded, color: p.accent, size: 30),
              const SizedBox(width: 14),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(storyTitle, style: context.tt.titleMedium),
                  Text('Who is building him, how it is going, and how to get one', style: context.tt.bodySmall),
                ]),
              ),
              Icon(Icons.chevron_right_rounded, color: p.muted),
            ]),
          ),
          // ------------------------------------------------ about
          const SectionHeader('About'),
          SpikeCard(
            child: Row(children: [
              SvgPicture.asset('assets/icon/spike_icon.svg', width: 56, height: 56),
              const SizedBox(width: 14),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(AppBrand.productName, style: context.tt.titleLarge),
                  Text(
                      'Made by ${AppBrand.developerName}'
                      '${AppBrand.publisherDisplayName.isEmpty ? '' : ' · ${AppBrand.publisherDisplayName}'}',
                      key: const ValueKey('aboutMadeBy'),
                      style: context.tt.bodyMedium),
                  Text('Version $appVersion', key: const ValueKey('aboutVersion'), style: context.tt.bodyMedium),
                  Text('Protocol v$protocolRelease  ·  ${s.deviceId}', style: context.tt.bodySmall),
                ]),
              ),
              TextButton(
                onPressed: () => showLicensePage(context: context, applicationName: AppBrand.productName, applicationVersion: appVersion),
                child: const Text('Licences'),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}

/// The settings list: the phone's single column; on a desktop window a centred reading column, and
/// from the expanded size class up two columns: this computer and its AI on the left (what the owner
/// sets up first), everything else on the right (DESIGN.md "Desktop > Proportions").
class SettingsBody extends StatelessWidget {
  const SettingsBody({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final phonePad = EdgeInsets.fromLTRB(20, 0, 20, 30 + MediaQuery.paddingOf(context).bottom);
    if (!AppPlatform.desktop || !context.isWide) return ListView(padding: phonePad, children: children);
    return DesktopPage(
      title: 'Settings',
      body: (context, room) {
        // two equal reading columns (1 : 1, both are lists of the same kind of setting) once each can be
        // at least 520 wide; this computer and its AI first, on the left, because they are set up first
        const minCol = 520.0;
        if (room.maxWidth < 2 * minCol + Space.x8 || children.first is! DesktopSettings) {
          return Align(
            alignment: Alignment.topLeft,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: DesktopMetrics.readingMax),
              child: ListView(padding: EdgeInsets.zero, children: children),
            ),
          );
        }
        final col = math.min((room.maxWidth - Space.x8) / 2, DesktopMetrics.readingMax + Space.x16);
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: col, child: ListView(padding: EdgeInsets.zero, children: [children.first])),
          const SizedBox(width: Space.x8),
          SizedBox(width: col, child: ListView(padding: EdgeInsets.zero, children: _openColumn(children.sublist(1)))),
        ]);
      },
    );
  }
}
/// The right column's first header sits flush with the column's top, like the left one's.
List<Widget> _openColumn(List<Widget> items) => [
      if (items.first case final SectionHeader h)
        SectionHeader(h.title, subtitle: h.subtitle, trailing: h.trailing, first: true)
      else
        items.first,
      ...items.skip(1),
    ];

/// The privacy notes on the desktop (the brain runs on this computer; Gemini with the owner's key).
const _desktopPrivacy = [
  (Icons.computer_rounded, 'Spike\'s brain runs on this computer. What he remembers, your alarms and settings stay here.'),
  (Icons.mic_rounded, 'The microphone is used on this computer to hear his name and you. Speech is turned into words here; switch it off in Spike on this computer.'),
  (Icons.key_rounded, 'Your Gemini key stays in Windows\' protected storage for your account and is sent only to Google.'),
  (Icons.cloud_outlined, 'To think and talk, the words of your conversation go to Google\'s Gemini with your key.'),
  (Icons.no_accounts_rounded, 'No account, no ads and no tracking in this app.'),
];

String _wakeWords(WidgetRef ref) {
  final w = ref.watch(spikeStateProvider.select((s) => s.wakeWords));
  final all = [...?w['dog'], ...?w['cat']];
  return all.isEmpty ? 'Spike, Hey Buddy, Spicy' : all.join(', ');
}

class _NameField extends StatefulWidget {
  const _NameField({required this.label, required this.value, required this.onSave});
  final String label;
  final String value;
  final ValueChanged<String> onSave;
  @override
  State<_NameField> createState() => _NameFieldState();
}

class _NameFieldState extends State<_NameField> {
  late final _c = TextEditingController(text: widget.value);
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  void _save() {
    final v = _c.text.trim();
    if (v.isEmpty || v.length > 20) {
      _c.text = widget.value;
      return;
    }
    if (v != widget.value) {
      Haptics.confirm();
      widget.onSave(v);
    }
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: _c,
        maxLength: 20,
        textCapitalization: TextCapitalization.words,
        onSubmitted: (_) => _save(),
        onTapOutside: (_) {
          FocusScope.of(context).unfocus();
          _save();
        },
        decoration: InputDecoration(labelText: widget.label, counterText: ''),
      );
}

class _Choice<T> extends StatelessWidget {
  const _Choice({required this.value, required this.items, required this.onChanged});
  final T value;
  final Map<T, String> items;
  final ValueChanged<T> onChanged;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.cardHi, borderRadius: BorderRadius.circular(18)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        for (final e in items.entries)
          GestureDetector(
            onTap: () => onChanged(e.key),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(color: e.key == value ? p.accent : Colors.transparent, borderRadius: BorderRadius.circular(15)),
              child: Text(e.value, style: context.tt.labelMedium?.copyWith(color: e.key == value ? p.accentInk : p.ink, fontWeight: FontWeight.w800)),
            ),
          ),
      ]),
    );
  }
}
