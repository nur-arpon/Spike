/// Opening a page the same way on both platforms (DESIGN.md "Desktop"): the phone pushes Settings,
/// Phone and robot and Memories on top; the desktop keeps them inside the window next to its
/// sidebar (shell branches), and shows what Spike remembers in Life.
library;

import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

import 'platform.dart';

void openPage(BuildContext context, String path) {
  if (AppPlatform.desktop && const {'/settings', '/phone', '/memories'}.contains(path)) {
    context.go(path == '/memories' ? '/life' : path);
  } else {
    context.push(path);
  }
}
