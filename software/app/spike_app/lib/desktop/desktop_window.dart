/// The desktop window and the icon by the clock (software/app/DESIGN.md "Desktop").
///
///  * Window: 1280 x 820 to start, never smaller than 900 x 620, centred; shown by us once the
///    first frame is ready (the runner no longer shows it), and not at all when Windows started the
///    app at sign-in (`--startup`): Spike then waits quietly in the tray.
///  * Closing the window (X, Alt+F4) hides it: Spike keeps running (the brain, alarms, the phone and
///    the robot links). The first time, a short note says so, with a way to quit instead.
///  * Tray: a click opens the window; right click = the menu: Open, Start with Windows (a check), Quit.
///    Quit stops the built-in brain cleanly, then the app.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:screen_retriever/screen_retriever.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import '../core/brand.dart';
import '../core/theme.dart';
import '../state/settings.dart';
import 'desktop_channel.dart';
import 'desktop_state.dart';
import 'mini_window.dart';

/// The smallest window: the medium size class (900) and a 1366 x 768 laptop's height minus the taskbar.
const minWindowSize = Size(900, 620);

/// The first start: 1280 x 820 (fits a 1366 x 768 laptop at 100 % once Windows trims it, and a 1920
/// laptop at 150 %); after that, wherever and however big the owner left it.
const startWindowSize = Size(1280, 820);

const _boundsKey = 'spike.desktop.bounds.v1';

/// The last window position and size ("x,y,w,h,maximized"), if it is still on a screen.
Future<(Rect, bool)?> savedBounds(SharedPreferences prefs) async {
  final raw = prefs.getString(_boundsKey);
  if (raw == null) return null;
  final v = raw.split(',');
  if (v.length != 5) return null;
  final n = v.take(4).map(double.tryParse).toList();
  if (n.any((x) => x == null)) return null;
  final r = Rect.fromLTWH(n[0]!, n[1]!, n[2]!, n[3]!);
  try {
    // a monitor that was unplugged since: start centred instead of off screen
    final displays = await screenRetriever.getAllDisplays();
    final visible = displays.any((d) {
      final o = d.visiblePosition ?? Offset.zero;
      final s = d.visibleSize ?? d.size;
      return (o & s).overlaps(r.deflate(40));
    });
    if (!visible) return null;
  } catch (_) {}
  return (r, v[4] == '1');
}

Future<void> saveBounds(SharedPreferences prefs, Rect r, bool maximized) =>
    prefs.setString(_boundsKey, '${r.left.round()},${r.top.round()},${r.width.round()},${r.height.round()},${maximized ? 1 : 0}');

/// Before runApp: size, title and minimum size; hidden until the first frame (DesktopShell).
Future<void> initDesktopWindow(SharedPreferences prefs) async {
  await windowManager.ensureInitialized();
  final saved = await savedBounds(prefs);
  await windowManager.waitUntilReadyToShow(
    WindowOptions(
      size: saved?.$1.size ?? startWindowSize,
      minimumSize: minWindowSize,
      center: saved == null,
      title: AppBrand.productName,
      titleBarStyle: TitleBarStyle.normal,
    ),
  );
  if (saved != null) {
    await windowManager.setBounds(saved.$1);
    if (saved.$2) await windowManager.maximize();
  }
  await windowManager.setPreventClose(true); // X hides to the tray (DesktopShell._onClose)
}

Future<void> showWindow() async {
  await windowManager.show();
  await windowManager.focus();
}

/// Wraps the app on the desktop: close-to-tray, the tray icon and its menu.
class DesktopShell extends ConsumerStatefulWidget {
  const DesktopShell({super.key, required this.child, required this.startHidden, required this.navigatorKey});
  final Widget child;
  final bool startHidden;
  final GlobalKey<NavigatorState> navigatorKey;

  @override
  ConsumerState<DesktopShell> createState() => _DesktopShellState();
}

class _DesktopShellState extends ConsumerState<DesktopShell> with WindowListener {
  bool _quitting = false;
  TrayIcon? _tray;
  Menu? _menu;
  MenuItem? _startItem;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
    ref.read(desktopChannelProvider).onShown = () => unawaited(showWindow());
    _setupTray();
    unawaited(ref.read(desktopProvider.notifier).boot());
    if (!widget.startHidden) {
      WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(showWindow()));
    }
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    _tray?.dispose();
    _menu?.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------- tray (tray_manager 0.7, native API)
  MenuItem? _item(String label, MenuItemType type, void Function() onClick) {
    final it = MenuItem.createWithLabelAndType(label, type);
    it?.addListener((e) {
      if (e is MenuItemClickedEvent) onClick();
    });
    return it;
  }

  void _setupTray() {
    try {
      final tray = TrayIcon.create();
      final menu = Menu.create();
      if (tray == null || menu == null) return;
      tray.icon = ImageAsset.fromAsset('assets/icon/tray.ico');
      tray.setTooltip(AppBrand.productName);
      menu.addItem(_item('Open ${AppBrand.productName}', MenuItemType.normal, () => unawaited(showWindow())));
      menu.addSeparator();
      _startItem = _item('Start with Windows', MenuItemType.checkbox, () {
        final on = ref.read(desktopProvider).startWithWindows.isOn;
        unawaited(ref.read(desktopProvider.notifier).setStartWithWindows(!on));
      });
      menu.addItem(_startItem);
      menu.addSeparator();
      menu.addItem(_item('Quit ${AppBrand.productName}', MenuItemType.normal, () => unawaited(quit())));
      tray.setContextMenu(menu);
      tray.setContextMenuTrigger(ContextMenuTrigger.rightClicked);
      tray.addListener((e) {
        if (e is TrayIconClickedEvent || e is TrayIconDoubleClickedEvent) unawaited(showWindow());
      });
      tray.setVisible(true);
      _tray = tray;
      _menu = menu;
      _syncStartItem(ref.read(desktopProvider).startWithWindows);
    } catch (e) {
      debugPrint('tray unavailable: $e');
    }
  }

  void _syncStartItem(StartWithWindows s) {
    final it = _startItem;
    if (it == null) return;
    it.state = s.isOn ? MenuItemState.checked : MenuItemState.unchecked;
    it.isEnabled = s.canChange;
  }

  // ---------------------------------------------------------------- window
  // remember where the window is (not while it is the mini window: that has its own place)
  Timer? _saveBounds;
  void _boundsChanged() {
    if (ref.read(miniWindowProvider)) return;
    _saveBounds?.cancel();
    _saveBounds = Timer(const Duration(milliseconds: 600), () async {
      try {
        final max = await windowManager.isMaximized();
        final r = await windowManager.getBounds();
        if (!ref.read(miniWindowProvider)) await saveBounds(ref.read(prefsProvider), r, max);
      } catch (_) {}
    });
  }

  @override
  void onWindowResized() => _boundsChanged();
  @override
  void onWindowMoved() => _boundsChanged();
  @override
  void onWindowMaximize() => _boundsChanged();
  @override
  void onWindowUnmaximize() => _boundsChanged();

  @override
  void onWindowClose() => unawaited(_onClose());

  Future<void> _onClose() async {
    if (_quitting) return;
    final s = ref.read(settingsProvider);
    if (!s.trayHintShown) {
      final ctx = widget.navigatorKey.currentContext;
      if (ctx != null) {
        final quitInstead = await showDialog<bool>(
          context: ctx,
          builder: (c) => AlertDialog(
            icon: const Icon(Icons.pets_rounded),
            title: Text('${AppBrand.productName} keeps running'),
            content: Text(
                'Closing the window keeps ${s.dogName} awake by the clock, so alarms, your phone and the robot '
                'still work. Open him again from the icon in the notification area, or quit from its menu.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Quit instead')),
              FilledButton(onPressed: () => Navigator.pop(c, false), child: const Text('Got it')),
            ],
          ),
        );
        ref.read(settingsProvider.notifier).update((x) => x.copyWith(trayHintShown: true));
        if (quitInstead == true) {
          await quit();
          return;
        }
      }
    }
    await windowManager.hide();
  }

  /// Quit for real: the brain first (a clean stop), then the window and the process.
  Future<void> quit() async {
    if (_quitting) return;
    _quitting = true;
    await windowManager.hide();
    try {
      await ref.read(desktopProvider.notifier).shutdown().timeout(const Duration(seconds: 15));
    } catch (_) {}
    _tray?.setVisible(false);
    await windowManager.setPreventClose(false);
    await windowManager.destroy();
  }

  int? _captionSent;

  @override
  Widget build(BuildContext context) {
    // the title bar in the page's own background colour (Windows 11), light or dark with the app
    final bg = context.sp.bg.toARGB32();
    if (_captionSent != bg) {
      _captionSent = bg;
      unawaited(ref.read(desktopChannelProvider).setCaptionColors(bg, context.sp.ink.toARGB32()));
    }
    // keep the tray's "Start with Windows" check in step with Settings
    ref.listen(desktopProvider.select((d) => d.startWithWindows), (_, s) => _syncStartItem(s));
    return widget.child;
  }
}
