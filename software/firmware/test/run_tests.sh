#!/bin/sh
# Every host-side test of the firmware (no hardware needed). Run from anywhere in Git Bash:
#   sh software/firmware/test/run_tests.sh
# 1 pin map vs the guide  2 table/raster self-test  3 body safety + limits  3a gait + edge threshold  3b v1.3 link (BLE framing
# vectors, one brain at a time, ESP-NOW packet) + passkey overlay  4 synth sounds  5 golden images vs the
# JS face  6 behaviour trace vs the JS engine  7 protocol messages vs the brain (+ v1.3 types)
# 8 frame budget. Stops at the first failure.
set -e
FW="$(cd "$(dirname "$0")/.." && pwd)"
SW="$FW/.."
"$SW/laptop/.venv/Scripts/python.exe" "$FW/tools/check_pinmap.py" | tail -1
node "$FW/test/js_cases.js"
cmd //c "$(cygpath -w "$FW/pc/build.bat")" > "$FW/test/out/build.log" 2>&1 || { cat "$FW/test/out/build.log"; exit 1; }
tail -1 "$FW/test/out/build.log"
mkdir -p "$FW/test/out/raw/cpp"
"$FW/pc/build/face_pc.exe" selftest
"$FW/pc/build/face_pc.exe" body
# walking / give paw / balance calibration / desk-edge threshold against a 3-D statics plant (pc/gait_test.cpp)
"$FW/pc/build/face_pc.exe" gait
# protocol v1.3 away mode: BLE framing vs software/protocol/ble_frame_vectors.json, the one-brain policy,
# the ESP-NOW hand-over packet; and the pairing passkey overlay (test/out/passkey.png, look at it)
"$SW/laptop/.venv/Scripts/python.exe" "$FW/test/ble_vectors_to_txt.py" "$FW/test/out/ble_vectors.txt"
"$FW/pc/build/face_pc.exe" link "$FW/test/out/ble_vectors.txt"
"$FW/pc/build/face_pc.exe" passkey "$FW/test/out/passkey.png" 482917 0.7
mkdir -p "$FW/test/out/sounds"
"$FW/pc/build/face_pc.exe" sounds "$FW/test/out/sounds" | tail -1
"$FW/pc/build/face_pc.exe" cases "$FW/test/out/cases.txt" "$FW/test/out/raw/cpp" 5
"$SW/laptop/.venv/Scripts/python.exe" "$FW/test/compare.py"
node "$FW/test/life_trace.js"
"$FW/pc/build/face_pc.exe" life "$FW/test/out/life_script.txt" "$FW/test/out/life_cpp.txt"
node "$FW/test/life_trace.js" compare
cp "$FW/test/out/raw/cpp/stats.csv" "$FW/test/out/frame_stats.csv"
"$SW/laptop/.venv/Scripts/python.exe" "$FW/test/frame_budget.py"
"$SW/laptop/.venv/Scripts/python.exe" "$FW/test/protocol_check.py" | tail -1
rm -rf "$FW/test/out/raw"   # 200+ MB of intermediates; the report and sheets stay
