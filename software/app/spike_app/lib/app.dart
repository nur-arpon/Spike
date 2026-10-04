import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'away/ai/gemini_voices.dart' show sampleQuestion, styleById;
import 'away/ai/key_store.dart';
import 'away/ai/live_selftest.dart';
import 'core/brand.dart';
import 'core/haptics.dart';
import 'core/motion.dart';
import 'core/platform.dart';
import 'core/theme.dart';
import 'core/layout.dart';
import 'desktop/desktop_home.dart';
import 'desktop/desktop_nav.dart';
import 'desktop/mini_window.dart';
import 'features/talk/chat_panel.dart';
import 'desktop/desktop_window.dart';
import 'features/connect/connect_screen.dart';
import 'features/home/home_screen.dart';
import 'features/life/life_screen.dart';
import 'features/life/memories_screen.dart';
import 'features/remote/remote_screen.dart';
import 'features/settings/settings_screen.dart';
import 'features/story/push_sheets.dart';
import 'features/story/story_screen.dart';
import 'features/studio/studio_screen.dart';
import 'features/talk/talk_screen.dart';
import 'features/talk/voice_pill.dart';
import 'features/viewer3d/viewer_screen.dart';
import 'state/away.dart';
import 'state/link.dart';
import 'state/pairing_sync.dart';
import 'state/settings.dart';
import 'state/voice.dart';
import 'state/live_voice.dart';
import 'state/voice_out.dart';

/// The root navigator (dialogs from above the router: the desktop's close-to-tray note).
final rootNavigatorKey = GlobalKey<NavigatorState>();

/// `--route=/play` on the command line opens that page first (the desktop app's screenshots and
/// support: 'open Spike at Settings'). Only the app's own pages are accepted.
String? startRouteFrom(List<String> args) {
  for (final a in args) {
    if (a.startsWith('--route=')) {
      final r = a.substring(8);
      if (const {'/home', '/play', '/talk', '/studio', '/life', '/settings', '/phone', '/memories', '/viewer', '/story'}.contains(r)) return r;
    }
  }
  return null;
}

/// Set once from main() (see [startRouteFrom]).
String? _startRoute;

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    navigatorKey: rootNavigatorKey,
    // Onboarding v2 (4 Oct 2026): always straight into the app, exploring. There is no setup gate: the
    // moment something needs Spike's brain the app asks (features/connect/brain_needed.dart). The old
    // connect screen stays at /connect, reachable from Settings > Connect to Spike. (The desktop app is
    // the brain's home and never asks.)
    initialLocation: _startRoute ?? '/home',
    // the desktop has no separate Talk page: the conversation is on Home
    redirect: (context, state) => AppPlatform.desktop && state.matchedLocation == '/talk' ? '/home' : null,
    routes: [
      GoRoute(path: '/connect', pageBuilder: (c, s) => _fade(s, const ConnectScreen())),
      GoRoute(path: '/viewer', pageBuilder: (c, s) => _slideUp(s, const ViewerScreen())),
      // the robot story (features/story/): from the Home banner, the robot cards, the sheets and Settings
      GoRoute(path: '/story', builder: (c, s) => const StoryScreen()),
      // the phone: Settings and Memories are pushed pages; the desktop keeps them inside the shell, next to
      // the sidebar (below), and shows what he remembers in Life
      if (!AppPlatform.desktop) GoRoute(path: '/settings', builder: (c, s) => const SettingsScreen()),
      GoRoute(path: '/memories', builder: (c, s) => const DesktopFrame(maxWidth: 840, child: MemoriesScreen())),
      if (!AppPlatform.desktop) GoRoute(path: '/phone', builder: (c, s) => const PhoneAndRobotScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: '/home', builder: (c, s) => const HomeScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/play', builder: (c, s) => const RemoteScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/talk', builder: (c, s) => const TalkScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/studio', builder: (c, s) => const StudioScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/life', builder: (c, s) => const LifeScreen())]),
          if (AppPlatform.desktop) ...[
            StatefulShellBranch(routes: [GoRoute(path: '/settings', builder: (c, s) => const SettingsScreen())]),
            StatefulShellBranch(routes: [GoRoute(path: '/phone', builder: (c, s) => const PhoneAndRobotScreen())]),
          ],
        ],
      ),
    ],
  );
});

Page<void> _fade(GoRouterState s, Widget child) => CustomTransitionPage(
      key: s.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 450),
      transitionsBuilder: (c, a, _, w) => FadeTransition(
        opacity: CurvedAnimation(parent: a, curve: Curves.easeOutCubic),
        child: ScaleTransition(scale: Tween(begin: 1.04, end: 1.0).animate(CurvedAnimation(parent: a, curve: Springs.smoothCurve)), child: w),
      ),
    );

Page<void> _slideUp(GoRouterState s, Widget child) => CustomTransitionPage(
      key: s.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 520),
      reverseTransitionDuration: const Duration(milliseconds: 320),
      transitionsBuilder: (c, a, _, w) => SlideTransition(
        position: Tween(begin: const Offset(0, 1), end: Offset.zero)
            .animate(CurvedAnimation(parent: a, curve: Springs.smoothCurve, reverseCurve: Curves.easeInCubic)),
        child: w,
      ),
    );

class SpikeApp extends ConsumerWidget {
  SpikeApp({super.key, this.startHidden = false, String? startRoute}) {
    _startRoute = startRoute;
  }

  /// Desktop: Windows started the app at sign-in; it waits in the tray.
  final bool startHidden;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(settingsProvider.select((s) => s.themeMode));
    // Keep the brain link alive for the whole app session.
    ref.watch(linkBootProvider);
    return MaterialApp.router(
      title: AppBrand.productName,
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: mode,
      routerConfig: ref.watch(routerProvider),
      // the voice pill: on every screen while the mic is on (state/voice.dart)
      builder: (context, child) {
        final app = VoiceOverlay(child: child ?? const SizedBox.shrink());
        if (!AppPlatform.desktop) return app;
        return DesktopShell(startHidden: startHidden, navigatorKey: rootNavigatorKey, child: app);
      },
    );
  }
}

/// Connects to the saved brain at start-up.
final linkBootProvider = Provider<void>((ref) {
  final c = ref.read(brainClientProvider);
  if (!AppPlatform.desktop) {
    // the phone: the laptop it was paired with (the desktop connects to its own built-in brain
    // once that has started: desktop/desktop_state.dart)
    final ep = ref.read(settingsProvider).endpoint;
    if (ep != null && c.current.phase.name == 'idle') c.connect(ep);
  }
  // warm the state notifiers so no early message is missed
  ref.read(spikeStateProvider);
  ref.read(chatProvider);
  ref.read(timersProvider);
  ref.read(memoryProvider);
  ref.read(pairingSyncProvider); // v1.2: Wi-Fi pairing learnt over USB, USB -> Wi-Fi failover
  ref.read(awayProvider); // v1.3: the phone becomes the brain when the laptop can't be reached (never on the desktop)
  ref.read(voiceProvider); // tap-to-talk: one session for the whole app, on every screen
  if (AppPlatform.desktop) return; // the brain on this computer speaks for itself (no phone voice)
  ref.listen(voiceSourceProvider, (_, _) {}); // v1.7: Gemini voice first at home (voice_out.dart)
  watchLiveSelfTest(() => ref.read(secretStoreProvider).read(aiKeyName('gemini')), // debug builds only
      preview: (sink) async {
    final c = ref.read(liveVoiceProvider.notifier);
    final st = styleById('dog', null);
    final end = await c.preview('dog', st, [...st.samples, sampleQuestion], sink: sink);
    final s = ref.read(liveVoiceProvider);
    return 'end ${end?.name ?? 'normal'}, said "${s.said}", detail ${s.detail}';
  });
  ref.read(laptopVoiceProvider); // v1.5: the laptop's voice plays here for this phone's conversations
});

// ---------------------------------------------------------------- shell + navigation

class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.shell});
  final StatefulNavigationShell shell;

  static const items = [
    (Icons.pets_rounded, 'Home'),
    (Icons.sports_esports_rounded, 'Play'),
    (Icons.chat_bubble_rounded, 'Talk'),
    (Icons.face_retouching_natural_rounded, 'Studio'),
    (Icons.favorite_rounded, 'Life'),
  ];

  /// The desktop's sections (DESIGN.md "Desktop > Information architecture"): Home and Talk are one
  /// (the conversation lives next to his face), so four: Home, Play, Studio, Life (+ Phone, Settings).
  static const desktopSections = [
    (Icons.pets_rounded, 'Home', 0),
    (Icons.sports_esports_rounded, 'Play', 1),
    (Icons.face_retouching_natural_rounded, 'Studio', 3),
    (Icons.favorite_rounded, 'Life', 4),
  ];

  void _go(int i) {
    if (i != shell.currentIndex) Haptics.tick();
    shell.goBranch(i, initialLocation: i == shell.currentIndex);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // the desktop from the medium size class up (core/layout.dart); the phone keeps its bar
    if (AppPlatform.desktop && context.isWide) return _desktopShell(context, ref);
    final bottom = MediaQuery.paddingOf(context).bottom;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: (context.isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark)
          .copyWith(systemNavigationBarColor: Colors.transparent, statusBarColor: Colors.transparent),
      child: Scaffold(
        extendBody: true,
        body: ReminderHost(child: shell), // the 3-day robot reminder, on app open (features/story/push_sheets.dart)
        bottomNavigationBar: Padding(
          padding: EdgeInsets.fromLTRB(16, 0, 16, bottom + 10),
          child: _NavBar(index: shell.currentIndex, items: items, onTap: _go),
        ),
      ),
    );
  }

  /// Desktop: the navigation (desktop/desktop_nav.dart) and the keyboard: Ctrl+1..5 the pages,
  /// Ctrl+, Settings, Ctrl+M the mini window, Space talk (outside a text box), and any other
  /// printable key starts a message to Spike (desktop DESIGN "Natural use").
  Widget _desktopShell(BuildContext context, WidgetRef ref) {
    if (ref.watch(miniWindowProvider)) return const MiniView();
    return CallbackShortcuts(
      bindings: {
        for (var i = 0; i < desktopSections.length; i++)
          SingleActivator(LogicalKeyboardKey(LogicalKeyboardKey.digit1.keyId + i), control: true): () => _go(desktopSections[i].$3),
        const SingleActivator(LogicalKeyboardKey.comma, control: true): () => shell.goBranch(5),
        const SingleActivator(LogicalKeyboardKey.keyM, control: true): () =>
            ref.read(miniWindowProvider.notifier).enter(MediaQuery.sizeOf(context)),
      },
      child: Focus(
        autofocus: true,
        onKeyEvent: (node, e) => desktopTypeAnywhere(ref, e),
        child: Scaffold(
          body: Row(children: [
            DesktopNav(index: shell.currentIndex, items: desktopSections, onTap: _go),
            Expanded(child: shell),
          ]),
        ),
      ),
    );
  }
}

/// Space = the mic on/off; a printable key = start a message (when no text box has the focus).
KeyEventResult desktopTypeAnywhere(WidgetRef ref, KeyEvent e) {
  if (e is! KeyDownEvent) return KeyEventResult.ignored;
  final focused = FocusManager.instance.primaryFocus?.context?.widget;
  if (focused is EditableText) return KeyEventResult.ignored;
  final k = HardwareKeyboard.instance;
  if (k.isControlPressed || k.isAltPressed || k.isMetaPressed) return KeyEventResult.ignored;
  if (e.logicalKey == LogicalKeyboardKey.space) {
    ref.read(voiceProvider.notifier).toggle();
    return KeyEventResult.handled;
  }
  final ch = e.character;
  if (ch != null && ch.length == 1 && ch.codeUnitAt(0) >= 0x21 && ChatPanel.typeInto(ch)) return KeyEventResult.handled;
  return KeyEventResult.ignored;
}
class _NavBar extends StatelessWidget {
  const _NavBar({required this.index, required this.items, required this.onTap});
  final int index;
  final List<(IconData, String)> items;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Container(
      height: 68,
      decoration: BoxDecoration(
        color: p.card.withValues(alpha: context.isDark ? 0.96 : 0.97),
        borderRadius: BorderRadius.circular(34),
        border: Border.all(color: p.line),
        boxShadow: [BoxShadow(color: p.shadow.withValues(alpha: context.isDark ? 0.5 : 0.16), blurRadius: 30, offset: const Offset(0, 10))],
      ),
      padding: const EdgeInsets.all(6),
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth / items.length;
        return Stack(children: [
          AnimatedPositioned(
            duration: const Duration(milliseconds: 520),
            curve: Springs.curve,
            left: w * index,
            top: 0,
            bottom: 0,
            width: w,
            child: Container(
              decoration: BoxDecoration(color: p.accent.withValues(alpha: context.isDark ? 0.24 : 0.14), borderRadius: BorderRadius.circular(28)),
            ),
          ),
          Row(children: [
            for (var i = 0; i < items.length; i++)
              Expanded(
                child: Pressable(
                  haptic: false,
                  scale: 0.86,
                  semanticLabel: items[i].$2,
                  onTap: () => onTap(i),
                  child: _NavItem(icon: items[i].$1, label: items[i].$2, selected: i == index),
                ),
              ),
          ]),
        ]);
      }),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({required this.icon, required this.label, required this.selected});
  final IconData icon;
  final String label;
  final bool selected;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final color = selected ? p.accent : p.muted;
    return Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      AnimatedScale(
        scale: selected ? 1.12 : 1,
        duration: const Duration(milliseconds: 420),
        curve: Springs.curve,
        child: Icon(icon, color: color, size: 24),
      ),
      const SizedBox(height: 3),
      AnimatedDefaultTextStyle(
        duration: const Duration(milliseconds: 250),
        style: context.tt.labelSmall!.copyWith(color: color, fontWeight: selected ? FontWeight.w800 : FontWeight.w600),
        child: Text(label),
      ),
    ]);
  }
}
