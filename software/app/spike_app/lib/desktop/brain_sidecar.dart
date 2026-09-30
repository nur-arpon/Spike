/// The built-in brain on Windows: the frozen Python spike_brain (software/laptop/desktop_build)
/// started and stopped by the app as a background helper (software/app/DESIGN.md "Desktop").
///
///  * Where: `<app folder>\brain\spike_brain.exe` with its read-only models in `brain\models`.
///    Its data (memories, alarms, the pairing token, logs) lives in `%LOCALAPPDATA%\<internal id>\brain`,
///    a folder named after the PERMANENT internal id, never the product name (RENAMING.md).
///  * Port: the first free one of 8765..8769 (the package's firewall rule opens exactly these, on
///    Private networks only). The app itself connects over 127.0.0.1, where no token is needed.
///  * The Gemini key: read from Windows' protected storage by the caller and handed to this one
///    process in its environment (GEMINI_API_KEY). Never an argument (other programs can read
///    command lines), never a file, never logged. With no key the variable is set EMPTY, so a
///    GEMINI_API_KEY in the user's own environment is never picked up by accident.
///  * Life: `--parent-pid` makes the brain stop if the app dies; [stop] closes its stdin (a clean
///    stop, `--stop-on-stdin-eof`) and kills it only if it has not ended after [stopGrace].
///    A crash is restarted with back-off (1, 2, 5, 10, 30 s); five crashes within ten minutes = failed.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

enum BrainRun { stopped, starting, running, restarting, failed, missing }

@immutable
class BrainSidecarState {
  const BrainSidecarState({this.run = BrainRun.stopped, this.port, this.detail, this.pid});
  final BrainRun run;
  final int? port;
  final String? detail;
  final int? pid;
  bool get up => run == BrainRun.running;
  @override
  String toString() => 'BrainSidecarState($run, port $port${detail == null ? '' : ', $detail'})';
}

/// How to start the brain: the frozen exe (release) or a Python in a dev checkout.
@immutable
class BrainCommand {
  const BrainCommand({required this.exe, this.prefix = const [], required this.models, this.workDir});
  final String exe;
  final List<String> prefix; // e.g. ['-m', 'spike_brain'] for a dev Python
  final String models;
  final String? workDir;

  /// The packaged brain next to the app's exe, else a developer's checkout named by the
  /// SPIKE_BRAIN_PYTHON (a python.exe) and SPIKE_BRAIN_DIR (software/laptop) variables.
  static BrainCommand? locate({String? appExe, Map<String, String>? env}) {
    final e = env ?? Platform.environment;
    final dir = File(appExe ?? Platform.resolvedExecutable).parent.path;
    final frozen = '$dir\\brain\\spike_brain.exe';
    if (File(frozen).existsSync()) return BrainCommand(exe: frozen, models: '$dir\\brain\\models', workDir: '$dir\\brain');
    final py = e['SPIKE_BRAIN_PYTHON'], src = e['SPIKE_BRAIN_DIR'];
    if (py != null && src != null && File(py).existsSync() && Directory(src).existsSync()) {
      return BrainCommand(exe: py, prefix: const ['-m', 'spike_brain'], models: '$src\\models', workDir: src);
    }
    return null;
  }
}

typedef ProcessStarter = Future<Process> Function(String exe, List<String> args,
    {required Map<String, String> environment, String? workingDirectory});

typedef PortCheck = Future<bool> Function(int port);

Future<Process> _startProcess(String exe, List<String> args,
        {required Map<String, String> environment, String? workingDirectory}) =>
    Process.start(exe, args, environment: environment, workingDirectory: workingDirectory, runInShell: false);

/// Nobody answers on 127.0.0.1:[port] and it can be bound on every address (like the brain's own check).
Future<bool> portIsFree(int port) async {
  try {
    final s = await Socket.connect(InternetAddress.loopbackIPv4, port, timeout: const Duration(milliseconds: 300));
    s.destroy();
    return false; // someone is listening (another brain, another program)
  } catch (_) {}
  try {
    final srv = await ServerSocket.bind(InternetAddress.anyIPv4, port, shared: false);
    await srv.close();
    return true;
  } catch (_) {
    return false;
  }
}

class BrainSidecar {
  BrainSidecar({
    required this.command,
    required this.home,
    ProcessStarter? starter,
    PortCheck? portFree,
    this.ports = const [8765, 8766, 8767, 8768, 8769],
    this.stopGrace = const Duration(seconds: 10),
    this.backoff = const [Duration(seconds: 1), Duration(seconds: 2), Duration(seconds: 5), Duration(seconds: 10), Duration(seconds: 30)],
    int? parentPid,
  })  : _starter = starter ?? _startProcess,
        _portFree = portFree ?? portIsFree,
        _parentPid = parentPid ?? pid;

  final BrainCommand? command;
  final String home;
  final List<int> ports;
  final Duration stopGrace;
  final List<Duration> backoff;
  final ProcessStarter _starter;
  final PortCheck _portFree;
  final int _parentPid;

  Process? _proc;
  BrainSidecarState _state = const BrainSidecarState();
  final _states = StreamController<BrainSidecarState>.broadcast();
  final List<DateTime> _crashes = [];
  Timer? _retry;
  bool _wanted = false;
  String? _key;
  bool _mic = true;
  int _gen = 0;

  BrainSidecarState get state => _state;
  Stream<BrainSidecarState> get states => _states.stream;

  void _set(BrainSidecarState s) {
    _state = s;
    if (!_states.isClosed) _states.add(s);
  }

  /// The arguments for one run (pure; tested). The key is NOT among them.
  List<String> args(int port, {required bool mic}) => [
        ...?command?.prefix,
        '--profile', 'desktop',
        '--home', home,
        '--models', command?.models ?? '',
        '--port', '$port',
        '--parent-pid', '$_parentPid',
        '--stop-on-stdin-eof',
        '--log-file', 'logs\\brain.log',
        '--no-camera',
        if (!mic) '--no-mic',
      ];

  /// The environment for one run (pure; tested): only GEMINI_API_KEY is set by us.
  static Map<String, String> environment(String? key) => {
        'GEMINI_API_KEY': key ?? '',
        'PYTHONIOENCODING': 'utf-8',
      };

  /// Start (or keep) the brain with this key and microphone choice. Returns the port, or null.
  Future<int?> start({String? geminiKey, bool mic = true}) async {
    _wanted = true;
    _key = geminiKey;
    _mic = mic;
    if (_proc != null && _state.up) return _state.port;
    return _launch();
  }

  Future<int?> _launch() async {
    final gen = ++_gen;
    _retry?.cancel();
    final cmd = command;
    if (cmd == null) {
      _set(const BrainSidecarState(run: BrainRun.missing, detail: 'the built-in brain is not installed'));
      return null;
    }
    _set(BrainSidecarState(run: _crashes.isEmpty ? BrainRun.starting : BrainRun.restarting));
    int? port;
    for (final p in ports) {
      if (await _portFree(p)) {
        port = p;
        break;
      }
    }
    if (gen != _gen) return null;
    if (port == null) {
      _set(BrainSidecarState(run: BrainRun.failed, detail: 'ports ${ports.first}-${ports.last} are all in use'));
      return null;
    }
    try {
      await Directory(home).create(recursive: true);
      final proc = await _starter(cmd.exe, args(port, mic: _mic),
          environment: environment(_key), workingDirectory: cmd.workDir);
      if (gen != _gen) {
        await _end(proc);
        return null;
      }
      _proc = proc;
      // the brain logs to its own file; drain the pipes so it can never block on a full buffer
      proc.stdout.drain<void>().ignore();
      proc.stderr.drain<void>().ignore();
      _set(BrainSidecarState(run: BrainRun.running, port: port, pid: proc.pid));
      final started = DateTime.now();
      unawaited(proc.exitCode.then((code) => _onExit(proc, code, started, gen)));
      return port;
    } catch (e) {
      _set(BrainSidecarState(run: BrainRun.failed, detail: 'could not start the brain (${e.runtimeType})'));
      return null;
    }
  }

  void _onExit(Process proc, int code, DateTime started, int gen) {
    if (!identical(proc, _proc)) return;
    _proc = null;
    if (!_wanted || gen != _gen) {
      _set(const BrainSidecarState(run: BrainRun.stopped));
      return;
    }
    final now = DateTime.now();
    _crashes.add(now);
    _crashes.removeWhere((t) => now.difference(t) > const Duration(minutes: 10));
    if (_crashes.length > backoff.length) {
      _set(BrainSidecarState(run: BrainRun.failed, detail: 'the brain keeps stopping (exit code $code)'));
      return;
    }
    final wait = backoff[(_crashes.length - 1).clamp(0, backoff.length - 1)];
    _set(BrainSidecarState(run: BrainRun.restarting, detail: 'exit code $code, again in ${wait.inSeconds} s'));
    _retry = Timer(wait, () {
      if (_wanted && _proc == null) unawaited(_launch());
    });
  }

  /// Start again with new settings (a new key, the microphone switched).
  Future<int?> restart({String? geminiKey, bool? mic}) async {
    _key = geminiKey;
    if (mic != null) _mic = mic;
    await _stopProcess();
    _crashes.clear();
    if (!_wanted) return null;
    return _launch();
  }

  /// Try again after [BrainRun.failed].
  Future<int?> retry() {
    _crashes.clear();
    _wanted = true;
    return _launch();
  }

  /// A clean stop: stdin closed (the brain's cue), killed only if it hangs.
  Future<void> stop() async {
    _wanted = false;
    _retry?.cancel();
    await _stopProcess();
    _set(const BrainSidecarState(run: BrainRun.stopped));
  }

  Future<void> _stopProcess() async {
    _gen++;
    final p = _proc;
    _proc = null;
    if (p != null) await _end(p);
  }

  Future<void> _end(Process p) async {
    try {
      await p.stdin.close();
    } catch (_) {}
    try {
      await p.exitCode.timeout(stopGrace);
    } on TimeoutException {
      p.kill(ProcessSignal.sigkill);
      try {
        await p.exitCode.timeout(const Duration(seconds: 3));
      } catch (_) {}
    }
  }

  Future<void> dispose() async {
    await stop();
    await _states.close();
  }
}
