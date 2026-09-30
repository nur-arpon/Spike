// Windows-only glue for the desktop app (software/app/DESIGN.md "Desktop"):
//  * one running copy: a second launch shows the first one's window and exits;
//  * "Start with Windows": the package's StartupTask (TaskId "SpikeStartup", off by default),
//    switched from Settings/tray through the method channel "spikebuddy/desktop";
//  * whether this launch came from that startup task (the app then starts quietly in the tray).
#ifndef RUNNER_DESKTOP_INTEGRATION_H_
#define RUNNER_DESKTOP_INTEGRATION_H_

#include <flutter/flutter_engine.h>
#include <windows.h>

#include <string>

namespace desktop {

// The id every copy of the app agrees on (the PERMANENT internal id, never the product name).
constexpr wchar_t kSingleInstanceMutex[] = L"Local\\spikebuddy.desktop.single-instance";
constexpr wchar_t kShowMessageName[] = L"spikebuddy.desktop.show";
constexpr wchar_t kStartupTaskId[] = L"SpikeStartup";
constexpr UINT kStartupResultMessage = WM_APP + 0x51;

// True when this process runs from an installed MSIX package (it has a package identity).
bool IsPackaged();

// True when Windows started this launch through the package's StartupTask (at sign-in).
bool LaunchedByStartupTask();

// The registered "show yourself" message a second launch broadcasts to the first one.
UINT ShowMessage();

// Holds the named mutex. Returns false when another copy already runs (it has been asked to show).
bool ClaimSingleInstance();

// The method channel "spikebuddy/desktop" (startup task state, packaged or not).
void RegisterChannel(flutter::FlutterEngine* engine, HWND window);

// For FlutterWindow::MessageHandler: handles our own messages. Returns true when handled.
bool HandleMessage(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);

}  // namespace desktop

#endif  // RUNNER_DESKTOP_INTEGRATION_H_
