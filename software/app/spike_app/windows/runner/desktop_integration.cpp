#include "desktop_integration.h"

#include <appmodel.h>
#include <dwmapi.h>
#include <flutter/method_channel.h>
#include <flutter/standard_method_codec.h>

#include <memory>
#include <thread>

#include <winrt/Windows.ApplicationModel.Activation.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Foundation.h>

namespace desktop {
namespace {

using flutter::EncodableValue;
using flutter::MethodCall;
using flutter::MethodChannel;
using flutter::MethodResult;
using winrt::Windows::ApplicationModel::StartupTask;
using winrt::Windows::ApplicationModel::StartupTaskState;

std::unique_ptr<MethodChannel<EncodableValue>> g_channel;
HANDLE g_mutex = nullptr;

// A result finished on a worker thread, handed back to the platform thread by PostMessage.
struct PendingResult {
  std::unique_ptr<MethodResult<EncodableValue>> result;
  std::string value;
  std::string error;
};

std::string StateName(StartupTaskState s) {
  switch (s) {
    case StartupTaskState::Enabled: return "enabled";
    case StartupTaskState::Disabled: return "disabled";
    case StartupTaskState::DisabledByUser: return "disabledByUser";   // switched off in Task Manager / Settings
    case StartupTaskState::DisabledByPolicy: return "disabledByPolicy";
    case StartupTaskState::EnabledByPolicy: return "enabledByPolicy";
  }
  return "unknown";
}

// Runs `work` (which may block on WinRT async calls) off the UI thread, then answers on it.
void RunAsync(HWND window, std::unique_ptr<MethodResult<EncodableValue>> result, std::string (*work)()) {
  auto* pending = new PendingResult{std::move(result), "", ""};
  std::thread([window, pending, work]() {
    try {
      winrt::init_apartment(winrt::apartment_type::multi_threaded);
      pending->value = work();
    } catch (const winrt::hresult_error& e) {
      pending->error = winrt::to_string(e.message());
    } catch (...) {
      pending->error = "unknown error";
    }
    if (!::PostMessage(window, kStartupResultMessage, 0, reinterpret_cast<LPARAM>(pending))) {
      delete pending;  // the window is gone: nobody is waiting any more
    }
  }).detach();
}

std::string StartupGet() {
  return StateName(StartupTask::GetAsync(kStartupTaskId).get().State());
}

std::string StartupEnable() {
  auto task = StartupTask::GetAsync(kStartupTaskId).get();
  if (task.State() == StartupTaskState::Disabled) {
    return StateName(task.RequestEnableAsync().get());
  }
  return StateName(task.State());  // user/policy decisions are Windows' to change, not ours
}

std::string StartupDisable() {
  auto task = StartupTask::GetAsync(kStartupTaskId).get();
  if (task.State() == StartupTaskState::Enabled) task.Disable();
  return StateName(task.State());
}

}  // namespace

bool IsPackaged() {
  UINT32 length = 0;
  const LONG rc = ::GetCurrentPackageFullName(&length, nullptr);
  return rc != APPMODEL_ERROR_NO_PACKAGE;
}

bool LaunchedByStartupTask() {
  if (!IsPackaged()) return false;
  try {
    auto args = winrt::Windows::ApplicationModel::AppInstance::GetActivatedEventArgs();
    return args && args.Kind() == winrt::Windows::ApplicationModel::Activation::ActivationKind::StartupTask;
  } catch (...) {
    return false;
  }
}

UINT ShowMessage() {
  static const UINT id = ::RegisterWindowMessageW(kShowMessageName);
  return id;
}

bool ClaimSingleInstance() {
  g_mutex = ::CreateMutexW(nullptr, TRUE, kSingleInstanceMutex);
  if (g_mutex != nullptr && ::GetLastError() == ERROR_ALREADY_EXISTS) {
    // another copy runs (maybe hidden in the tray): ask it to show itself
    ::AllowSetForegroundWindow(ASFW_ANY);
    ::PostMessageW(HWND_BROADCAST, ShowMessage(), 0, 0);
    ::CloseHandle(g_mutex);
    g_mutex = nullptr;
    return false;
  }
  return true;
}

void RegisterChannel(flutter::FlutterEngine* engine, HWND window) {
  g_channel = std::make_unique<MethodChannel<EncodableValue>>(
      engine->messenger(), "spikebuddy/desktop", &flutter::StandardMethodCodec::GetInstance());
  g_channel->SetMethodCallHandler(
      [window](const MethodCall<EncodableValue>& call, std::unique_ptr<MethodResult<EncodableValue>> result) {
        const std::string& m = call.method_name();
        if (m == "isPackaged") {
          result->Success(EncodableValue(IsPackaged()));
        } else if (m == "setCaptionColors") {
          // Windows 11: paint the title bar in the app's own background colour, so the window's chrome
          // and the app read as one surface (the caption buttons, Snap layouts and dragging stay native).
          // Older Windows ignores these attributes.
          const auto* args = std::get_if<flutter::EncodableMap>(call.arguments());
          auto colorref = [&](const char* key) -> COLORREF {
            const auto it = args->find(EncodableValue(std::string(key)));
            const int64_t argb = it == args->end() ? 0 : it->second.LongValue();
            return RGB((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF);
          };
          if (args) {
            const COLORREF caption = colorref("caption"), text = colorref("text");
            ::DwmSetWindowAttribute(window, 35 /* DWMWA_CAPTION_COLOR */, &caption, sizeof(caption));
            ::DwmSetWindowAttribute(window, 34 /* DWMWA_BORDER_COLOR */, &caption, sizeof(caption));
            ::DwmSetWindowAttribute(window, 36 /* DWMWA_TEXT_COLOR */, &text, sizeof(text));
          }
          result->Success();
        } else if (m == "startupTask.get" || m == "startupTask.enable" || m == "startupTask.disable") {
          if (!IsPackaged()) {
            result->Success(EncodableValue(std::string("unsupported")));  // a dev build has no package
            return;
          }
          RunAsync(window, std::move(result),
                   m == "startupTask.get" ? &StartupGet : (m == "startupTask.enable" ? &StartupEnable : &StartupDisable));
        } else {
          result->NotImplemented();
        }
      });
}

bool HandleMessage(HWND hwnd, UINT message, WPARAM, LPARAM lparam) {
  if (message == kStartupResultMessage) {
    std::unique_ptr<PendingResult> pending(reinterpret_cast<PendingResult*>(lparam));
    if (pending->error.empty()) {
      pending->result->Success(EncodableValue(pending->value));
    } else {
      pending->result->Error("startup_task", pending->error);
    }
    return true;
  }
  if (message == ShowMessage() && ShowMessage() != 0) {
    // a second launch asked us to come forward (we may be hidden in the tray)
    ::ShowWindow(hwnd, ::IsIconic(hwnd) ? SW_RESTORE : SW_SHOW);
    ::SetForegroundWindow(hwnd);
    if (g_channel) g_channel->InvokeMethod("shown", nullptr);
    return true;
  }
  return false;
}

}  // namespace desktop
