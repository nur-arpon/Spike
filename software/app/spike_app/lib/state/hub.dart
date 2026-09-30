/// One link for every screen, whichever brain is live (protocol v1.3):
/// the laptop brain over the home Wi-Fi ([BrainClient]) or the phone brain
/// ([PhoneBrain]) away from home. Screens listen to [SpikeHub.messages] and
/// send with [SpikeHub.send] exactly as before; the hub forwards whichever
/// source is active. The automatic choice lives in `away.dart`.
library;

import 'dart:async';

import '../away/brain/phone_brain.dart';
import '../protocol/client.dart';
import '../protocol/messages.dart';

class SpikeHub implements SpikeLink {
  SpikeHub(this.lan) {
    _lanMsgs = lan.messages.listen((m) {
      if (active == BrainHost.laptop) _add(m);
    });
    _lanStatus = lan.status.listen((s) {
      if (active == BrainHost.laptop) _emit(s);
    });
  }

  final BrainClient lan;
  SpikeLink? _phone;
  BrainHost active = BrainHost.laptop;
  final _msgs = StreamController<SpikeMessage>.broadcast();
  final _status = StreamController<LinkStatus>.broadcast();
  late final StreamSubscription<SpikeMessage> _lanMsgs;
  late final StreamSubscription<LinkStatus> _lanStatus;
  StreamSubscription<SpikeMessage>? _phoneMsgs;
  StreamSubscription<LinkStatus>? _phoneStatus;

  PhoneBrain? get phone => _phone is PhoneBrain ? _phone as PhoneBrain : null;
  bool get away => active == BrainHost.phone;

  void _add(SpikeMessage m) {
    if (!_msgs.isClosed) _msgs.add(m);
  }

  void _emit(LinkStatus s) {
    if (!_status.isClosed) _status.add(s);
  }

  /// Attach the phone brain (once it is built).
  void attachPhone(SpikeLink p) {
    if (identical(p, _phone)) return;
    _phoneMsgs?.cancel();
    _phoneStatus?.cancel();
    _phone = p;
    _phoneMsgs = p.messages.listen((m) {
      if (active == BrainHost.phone) _add(m);
    });
    _phoneStatus = p.status.listen((s) {
      if (active == BrainHost.phone) _emit(s);
    });
  }

  /// Make [host] the brain the screens see; the caller starts/stops the brains.
  void setActive(BrainHost host) {
    if (host == active) return;
    active = host;
    _emit(current);
  }

  @override
  Stream<SpikeMessage> get messages => _msgs.stream;
  @override
  Stream<LinkStatus> get status => _status.stream;
  @override
  LinkStatus get current => away ? (_phone?.current ?? const LinkStatus(brain: BrainHost.phone)) : lan.current;
  @override
  bool get legacyBrain => away ? false : lan.legacyBrain;
  @override
  bool send(SpikeMessage msg) => away ? (_phone?.send(msg) ?? false) : lan.send(msg);

  // ---- the laptop link, as the Connect and Settings screens use it
  void connect(BrainEndpoint ep) => lan.connect(ep);
  void updateEndpoint(BrainEndpoint ep) => lan.updateEndpoint(ep);
  Future<void> disconnect() => lan.disconnect();
  void retryNow() => lan.retryNow();

  Future<void> dispose() async {
    await _lanMsgs.cancel();
    await _lanStatus.cancel();
    await _phoneMsgs?.cancel();
    await _phoneStatus?.cancel();
    await lan.dispose();
    await phone?.dispose();
    await _msgs.close();
    await _status.close();
  }
}
