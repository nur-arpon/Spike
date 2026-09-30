import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/haptics.dart';
import '../../core/theme.dart';
import '../../protocol/client.dart';
import 'pairing.dart';

/// Opens the camera and returns the brain endpoint from Spike's pairing QR.
Future<BrainEndpoint?> showQrSheet(BuildContext context) => showModalBottomSheet<BrainEndpoint>(
      context: context,
      useRootNavigator: true, // above the tab bar
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => const _QrSheet(),
    );

class _QrSheet extends StatefulWidget {
  const _QrSheet();
  @override
  State<_QrSheet> createState() => _QrSheetState();
}

class _QrSheetState extends State<_QrSheet> {
  final _ctl = MobileScannerController(formats: const [BarcodeFormat.qrCode], detectionSpeed: DetectionSpeed.noDuplicates);
  bool _done = false;
  String? _hint;

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture cap) {
    if (_done) return;
    for (final b in cap.barcodes) {
      final raw = b.rawValue;
      if (raw == null) continue;
      final ep = parsePairing(raw);
      if (ep != null) {
        _done = true;
        Haptics.success();
        Navigator.of(context).pop(ep);
        return;
      }
      Haptics.error();
      setState(() => _hint = 'That QR is not Spike\'s pairing code');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final h = MediaQuery.sizeOf(context).height * 0.72;
    return SizedBox(
      height: h,
      child: Column(children: [
        Text('Scan Spike\'s pairing code', style: context.tt.titleLarge),
        const SizedBox(height: 4),
        Text(_hint ?? 'It appears on his screen when the brain asks for pairing',
            style: context.tt.bodySmall?.copyWith(color: _hint != null ? Brand.tongue : p.muted)),
        const SizedBox(height: 16),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(28),
              child: Stack(fit: StackFit.expand, children: [
                MobileScanner(
                  controller: _ctl,
                  onDetect: _onDetect,
                  errorBuilder: (c, e) => ColoredBox(
                    color: p.cardHi,
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text('The camera is not available (${e.errorCode.name}). Type the address instead.',
                            textAlign: TextAlign.center),
                      ),
                    ),
                  ),
                ),
                IgnorePointer(
                  child: Center(
                    child: Container(
                      width: 230,
                      height: 230,
                      decoration: BoxDecoration(
                        border: Border.all(color: Colors.white.withValues(alpha: 0.9), width: 3),
                        borderRadius: BorderRadius.circular(32),
                      ),
                    ),
                  ),
                ),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}
