# Spike protocol, version 1

This is the one wire protocol between Spike's laptop brain and everything
that is "the robot": the ESP32 screen board, the ESP32 camera board, and the
browser face simulator (`software/face_v2`). The brain (Python,
`software/laptop/spike_brain`) implements it in `spike_brain/protocol.py`;
the simulator in `face_v2/brain_link.js`; the ESP32 firmware must implement
exactly what is written here. If code and this file disagree, this file wins
and the code is the bug.

Status: **v1.8, 2026-09-30** (backward compatible with v1.0 to v1.7; the wire
version `v` stays `1`).

Changelog:
- v1.0 (2026-09-28): first release.
- v1.1 (2026-09-28): comfort actions `snuggle` and `slowWag` (section 5.2).
- v1.2 (2026-09-29): the phone app. New role `app`; app-to-brain messages for
  the face and body, the wheels (`drive` with a dead man's switch), alarms,
  memories, the camera view and pairing; brain-to-app `timers`, `memory`,
  `robot_status`, `battery`, `camera`, `heard`, `brain_status`, `pairing`;
  brain-to-robot `drive` and `set_display`; mDNS `_spike._tcp` and the QR
  pairing link; clients on the brain's own laptop need no token. All of it is
  in **section 10**. Nothing in sections 1 to 9 changed meaning: a v1.1 robot,
  simulator or firmware keeps working unchanged (it ignores `drive` and
  `set_display` by rule 2 until it implements them).
- v1.3 (2026-09-29): away from home. The phone can be Spike's brain: a
  Bluetooth LE GATT service on the screen board carrying the same JSON
  messages (framed over the MTU, LE Secure Connections with a passkey shown on
  Spike's screen, bonding), the phone's hotspot for the camera and heavy
  traffic (`hotspot_join` / `hotspot_leave` / `hotspot_state` over BLE), the
  robot-internal ESP-NOW hand-over of the hotspot to the camera board,
  `robot_link` status and the error code `busy` (one brain at a time). All of
  it is in **section 11**. Nothing earlier changed meaning; a robot without BLE
  simply never meets a phone brain.
- v1.4 (2026-09-29): two **body actions** in `action` (section 5.2), `walk`
  and `paw`, with optional fields. Robot-side only (like the v1.1 comfort
  actions); an older robot ignores them. The robot reports how a walk ended
  with a `log` message (6.11).
- v1.5 (2026-09-30): **Spike's laptop voice on the phone** (section 10.8). An
  app may announce the cap `audio_out` with the formats it can play
  (`ogg_opus`, `pcm_s16le`); when the owner talks to Spike through that phone,
  the brain sends the reply's audio to that phone only (`say` gains `play`,
  `audio.format` may be `ogg_opus`) and the phone reports `say_state`. Nothing
  else changed: an older brain ignores the cap and plays on its own speaker; an
  older app never announces it and never gets audio.

- v1.6 (2026-09-30): **`keepalive`** (section 10.9), an app-to-brain message
  that silently keeps the language model warm and an open listening window
  open while the phone's mic session is on and the owner is quiet, replacing
  the fake head tap the app used for that (which flickered the face). The
  brain's hello says `"keepalive":true` when it understands it. Nothing else
  changed: an older brain never says so and the app then sends nothing.

- v1.7 (2026-09-30): **`voice_source`** (section 10.10): a phone with cap
  `audio_out` can say it voices its own replies (Gemini TTS on the phone,
  design rule "Gemini voice first, at home too"); the brain then sends
  those sentences as checked text only (`play: true`, `audio: null`) and
  synthesises nothing. Also optional `audio_out.voice` in the app's hello. The
  brain's hello says `"voice_source":true` when it understands it. The app now
  also sends what the phone's own recognizer heard as plain `text` (section
  10.2 is unchanged; the mic stream stays as the fallback).

- v1.8 (2026-09-30): **`voice_style`** (section 10.11) for the Windows desktop
  app's light brain, which speaks with Gemini TTS itself: the app picks each
  character's Gemini voice style (`{"type":"voice_style","mode":"dog",
  "style":"street"}`), the brain keeps it and tells every app
  (`{"type":"voice_style","styles":{"dog":"street","cat":"sassy"}}`). The
  brain's hello carries `"voice_style":{...}` only when it speaks with Gemini
  TTS; an app sends `voice_style` only to such a brain. Nothing else changed.

## 1. Transport

- WebSocket (RFC 6455). The **brain is the server**; robot boards and the
  simulator are clients.
- URL: `ws://<brain-host>:<port>/` (default port `8765`). The path is
  ignored in v1.
- One message = one **text frame** containing one UTF-8 JSON object.
  v1 never sends binary frames; a receiver that gets one ignores it.
- Size: a message must not exceed **64 KiB** (the brain refuses frames over
  256 KiB). Audio and camera data are chunked (sections 5.4, 6.7, 6.8) so an
  ESP32 never has to parse more than about 24 KiB of JSON.
- A client on the same machine (the simulator) always uses
  `ws://127.0.0.1:<port>/`, never `ws://localhost:...`: a browser may
  resolve `localhost` to `::1`, where another program can be listening.
  If the default port is taken, the brain uses the next free one and
  opens the simulator with it.
- Default bind is `127.0.0.1` (simulator only). When a real robot connects
  over Wi-Fi the brain binds `0.0.0.0` and **requires a pairing token** in
  `hello` (section 4). No audio or video crosses the network except between
  the robot and the brain on the owner's own LAN.

## 2. Envelope

Every message is a JSON object with these envelope fields:

| field  | type    | req | meaning |
|--------|---------|-----|---------|
| `v`    | integer | yes | Protocol **major** version. Always `1` for this spec. |
| `type` | string  | yes | Message type (sections 5 and 6). |
| `id`   | integer | yes | Sender's message counter for this connection: starts at 1, +1 per message, fits in uint32. |
| `re`   | integer | no  | The `id` of the message this one answers (`hello` reply, `pong`, `error`). |
| `ts`   | number  | no  | Sender's clock in milliseconds (brain: Unix epoch ms; robot: ms since boot). Logging and latency only; never used for logic. |

All other fields sit next to the envelope fields (flat object, no
`payload` wrapper), which keeps ArduinoJson filters simple.

Rules:

1. **Unknown fields are ignored**, always. New optional fields may be added
   in any v1.x without notice.
2. **Unknown `type`**: the robot ignores it silently. The brain ignores it
   and answers `error` with code `unknown_type`.
3. A message whose `v` is not `1` is answered with `error`
   `version_mismatch`; if it was the `hello`, the brain then closes with
   code 4001.
4. Field names are `snake_case`. Enum values are strings. Mood and action
   names are **exactly** the camelCase ids in `face_v2/moods.js` (`MOODS`)
   and `face_v2/actions.js` (`ACTIONS`), for example `cuteAngry`,
   `tailWagDance`. The brain has a test that fails if its lists drift from
   those files.
5. Numbers: coordinates and levels are JSON numbers; counters are integers.
6. Within v1 the meaning of an existing field never changes. Anything
   incompatible is v2.

## 3. Connection lifecycle

1. Client opens the WebSocket and sends `hello` **within 5 s**, otherwise
   the brain closes with 4000.
2. The brain answers with its own `hello` (`re` = the client's hello id).
   Until then the client sends nothing else. Messages before `hello` are
   answered with `error` `not_ready` and dropped.
3. Right after the reply the brain re-sends the current state: `set_mode`,
   then `mood`. A reconnecting robot therefore never needs to remember
   anything the brain told it.
4. **Heartbeat.** The brain sends `ping` every `heartbeat_s` seconds (from
   its hello, default 5). The client answers `pong` with `re` = the ping id.
   Either side treats the link as dead after `3 x heartbeat_s` with no
   inbound message of any kind, closes it and (client) reconnects.
   WebSocket-level ping frames are also sent by the brain; clients must
   answer them (all common libraries do this automatically).
5. **Reconnect** (client): wait 0.5 s, then 1, 2, 4, 8, and at most 10 s
   between attempts, each +-20 % random jitter; reset after a successful
   hello. On reconnect send a fresh `hello`.
6. Close codes: 1000 normal, 1001 brain shutting down, 4000 hello timeout,
   4001 version mismatch, 4002 protocol abuse (more than 20 invalid
   messages in 10 s), 4003 bad or missing token.

A physical robot with two boards opens **two connections** with the same
`device_id` and different `role`: the screen board (`role: "face"`) and the
camera board (`role: "camera"`).

## 4. hello

### 4.1 Client to brain

```json
{"v":1,"type":"hello","id":1,"role":"face","device_id":"spike-7c9e2a",
 "fw":"0.1.0","caps":["face","speaker","mic","touch","imu","edge","battery"],
 "audio_out":{"rates":[16000,22050],"format":"pcm_s16le"},
 "token":"<pairing token, only when the brain requires one>"}
```

| field       | type     | req | meaning |
|-------------|----------|-----|---------|
| `role`      | string   | yes | `simulator`, `face` (screen board), `camera` (camera board), `robot` (single-board robot), `tool` (tests, debug consoles), `app` (the phone app, v1.2, section 10). |
| `device_id` | string   | yes | Stable per physical robot (ESP32: from the eFuse MAC). Simulator: random per page load is fine. |
| `fw`        | string   | yes | Firmware / page version, semver. |
| `caps`      | string[] | yes | Capabilities, any of: `face`, `speaker`, `mic`, `camera`, `touch`, `imu`, `edge`, `battery`, `drive`, `text`. The brain only sends a client what its caps can use (`say` audio needs `speaker`; `look_at` needs `face`). |
| `audio_out` | object   | no  | Speaker formats the client accepts: `rates` (Hz, preferred first), `format` (only `pcm_s16le` in v1). Default: any rate. |
| `token`     | string   | no  | Pairing token; required when the brain is bound to a non-loopback address. |

### 4.2 Brain to client

```json
{"v":1,"type":"hello","id":1,"re":1,"server":"spike-brain","version":"0.1.0",
 "session":"a41f","heartbeat_s":5,"mode":"dog",
 "names":{"dog":"Spike","cat":"Spicy"},
 "wake_words":{"dog":["Spike","Hey Buddy"],"cat":["Spicy"]},
 "audio":{"format":"pcm_s16le","rate":22050,"channels":1}}
```

`names` and `wake_words` come from the brain's config; clients show these
instead of their own built-in names. `audio` is the format of `say_audio`
for this client (the brain resamples to the client's first `audio_out`
rate when one is given).

## 5. Brain to robot

### 5.1 `mood`
`{"type":"mood","mood":"caring","hold_s":0}` sets the face mood.
`hold_s` (optional, default 0): keep it at least this long before the
robot's own idle life may drift it; 0 = the robot's normal rules apply.

### 5.2 `action`
`{"type":"action","action":"headTilt"}` plays a physical action (face,
sound and body). Names: the keys of `ACTIONS` in `face_v2/actions.js`
(`wakeUp`, `fallAsleep`, `napping`, `dozing`, `deepSleepDreams`,
`tripBump`, `sneeze`, `hiccup`, `shiver`, `pant`, `tailWagDance`, `zoomies`,
`headTilt`, `sniffAround`, `beggingAction`, `rollOver`, `playBow`, `yawn`,
`boop`). Unknown names are ignored.

v1.1 adds two **comfort actions** that are not in face_v2's table and must be
implemented by the robot itself (the simulator draws them in
`brain_link.js`): `snuggle` (lean in toward the owner: head dips and tilts,
eyes soften, ears relax, a small sigh; body: a slow lean forward) and
`slowWag` (a slow, contented tail wag: three soft sways; body: tail at half
speed). The brain sends them when the owner is sad, lonely or tired, where a
big happy action would feel wrong. A v1.0 robot ignores them (rule above).

v1.4 adds two **body actions**, also robot-side only (the robot owns the
motion and its safety; the brain or app only asks):

- `{"type":"action","action":"walk","direction":"forward","steps":4,"style":"auto"}`
  walks. `direction`: `forward` (default) or `back`. `steps`: 1 to 16
  (default 4), one paw step each. `style` (default `auto`): `tiltStep` (every
  paw lifts in turn, glides between), `rearStep` (back paws only), `march`
  (wheels roll, legs bob, paws stay down). The robot may use a gentler style
  than asked (no balance calibration yet, tilted desk, low battery, repeated
  aborts) and stops at a desk edge or obstacle.
- `{"type":"action","action":"paw","side":"left","from":"stand"}` offers a
  front paw. `side`: `left` (default) or `right`. `from`: `stand` (default) or
  `sit` (only if the robot has the puppy-sit variant switched on; otherwise it
  offers the paw from the stand).

When it ends, the robot sends `{"type":"log","level":"info"|"warn","msg":"gait
<style>: <result> - <why>"}`.

### 5.3 `event`
`{"type":"event","event":"comeHome"}` asks the robot to run one of its own
built-in life reflexes (face_v2 `behaviour.js`): `sayHi`,
`greetByTimeOfDay`, `comeHome`, `ownerLooksSad`, `pickedUp`, `fellOver`,
`ignoredNudge`. The robot owns the animation; the brain only says when.

### 5.4 `say` and `say_audio`
Speech is sent one sentence (a "segment") at a time so it can start before
the whole reply exists. One reply = one `utt` (utterance id, string);
its segments have `seq` 0, 1, 2, ...

```json
{"type":"say","utt":"u17","seq":0,"final":false,"text":"Oh, you're home!",
 "mood":"excited","duration_ms":1240,
 "audio":{"format":"pcm_s16le","rate":22050,"channels":1,"samples":27342,"chunks":2},
 "mouth":{"rate_hz":50,"values":[0,12,55,80,61,30,4,0]}}
```
followed by `chunks` messages:
```json
{"type":"say_audio","utt":"u17","seq":0,"index":0,"last":false,"data":"<base64>"}
```

| field | meaning |
|-------|---------|
| `text` | Caption for this segment (already cleaned: no tags, no emoji). |
| `final` | `true` on the last segment of the utterance. |
| `mood` | Optional mood to show when this segment starts playing. |
| `duration_ms` | Audio length of this segment. |
| `audio` | `null` for a caption-only segment (show `text` for `duration_ms`). Otherwise the PCM format, total `samples`, and how many `say_audio` chunks follow. |
| `mouth` | Mouth-open envelope aligned with the audio start: one value per `1/rate_hz` s, 0 (closed) to 100 (wide open). |
| `say_audio.data` | Base64 of raw little-endian 16-bit mono PCM, at most 8192 samples (16 KiB raw, about 22 KiB base64) per chunk. |

**End marker.** The brain streams a reply as it is written, so it may only
learn that the utterance is over after its last segment went out. It then
sends an end marker: a `say` with `text` "", `audio` null, `duration_ms` 0
and `final` true. The robot shows and plays nothing for it and does not
report `say_state` for it. Caption-only segments (`audio` null, non-empty
`text`) are reported like audio segments: `started` when shown, `finished`
after `duration_ms`.

Playback rules: segments of one `utt` play back to back in `seq` order with
no gap. A new `utt` queues behind the current one. `stop_speaking` (5.5)
cuts everything. A robot may start playing a segment as soon as its first
chunk arrives (streaming into its I2S buffer).

The robot reports playback with `say_state` (6.6). **The brain keeps the
microphone muted from the first `say` until 300 ms after the robot reports
the final segment `finished`** (with a timeout of `duration + 2 s` in case
the report is lost), so Spike never hears himself.

### 5.5 `stop_speaking`
`{"type":"stop_speaking","utt":"u17"}` stops playback now and drops queued
segments. `utt` optional: absent = everything.

### 5.6 `listening`
`{"type":"listening","state":"listening"}` where `state` is `idle`,
`wake` (heard his name or a head tap), `listening` (recording a request),
`thinking` (working on a reply), `speaking`. The face shows it (ears perk
when listening, eyes glance up when thinking).

### 5.7 `look_at`
`{"type":"look_at","x":-0.4,"y":0.1,"source":"camera"}`. Where the eyes
should look, in face-screen space as seen by a person facing the robot:
`x` -1 (screen left) to +1 (screen right), `y` -1 (up) to +1 (down).
The brain already maps camera image position to this space. Sent at most
10 times a second, only while a face is tracked.

### 5.8 `sound`
`{"type":"sound","sound":"whine"}`. Built-in synthesized sounds: `yip`,
`bark`, `whine`, `sniff`, `sigh`, `snore`, `giggle`, `meow`, `purr`,
`hiss`, `trill`, `yawn`, `sneeze`, `hiccup`, `growl` (stomach), `munch`,
`pop`, `boop`, `patSqueak`.

### 5.9 `alarm`
```json
{"type":"alarm","alarm_id":3,"state":"ringing","level":1,"label":"Wake up"}
```
`state`: `ringing` (with `level` 0 soft whine, 1 yips, 2 barks + jokes,
3 everything), `snoozed` (with `until`, Unix seconds), `stopped`. The robot
plays its own escalating alarm face and sounds; spoken jokes arrive as
normal `say` messages.

### 5.10 `game`
Rock paper scissors:
```json
{"type":"game","game":"rps","phase":"reveal","owner":"rock","robot":"paper",
 "result":"lose","score":{"owner":1,"robot":2,"draws":0}}
```
`phase`: `start`, `countdown` (with `count` 3, 2, 1), `shoot`, `reveal`,
`end`. `result` is from the **owner's** point of view (`win`, `lose`,
`draw`). `owner` may be `unknown` if nothing was seen or heard.

### 5.11 `set_mode`
`{"type":"set_mode","mode":"cat"}`: `dog` (Spike) or `cat` (Spicy).

### 5.12 `set_recipe`
`{"type":"set_recipe","mode":"dog","code":"SPK1..."}` or with `recipe`
(a face_v2 recipe object) instead of `code`. Changes the face look.

### 5.13 `ping`
`{"type":"ping"}`; answer with `pong`.

## 6. Robot to brain

### 6.1 `touch`
`{"type":"touch","zone":"head","gesture":"tap"}`. `zone`: `head`, `nose`,
`back`, `chin`. `gesture`: `tap`, `pat` (stroke), `hold`, `release`.
A head tap wakes Spike to listen; during an alarm it snoozes it.

### 6.2 `imu`
`{"type":"imu","event":"pickup"}`. `event`: `pickup`, `putdown`,
`shake`, `fall`, `lap` (held still on a lap).

### 6.3 `edge`
`{"type":"edge","sensor":"front_left","state":"edge"}`. `state`: `edge`
or `clear`. The robot's own reflex already stopped the wheels; this is
information for the brain.

### 6.4 `battery`
`{"type":"battery","percent":27,"volts":7.12,"charging":false}`. Sent on
change of at least 1 %, on charging change, and every 60 s.

### 6.5 `mood_state`
`{"type":"mood_state","mood":"sleepy","mode":"dog","action":null}`. Sent
when the robot's own engine changes mood, mode or action. A `mode` change
made on the robot (a button) is authoritative: the brain follows it.

### 6.6 `say_state`
`{"type":"say_state","utt":"u17","seq":0,"state":"started"}`. `state`:
`started` (segment began playing), `finished` (segment ended),
`stopped` (cut by `stop_speaking`).

### 6.7 `audio` (microphone)
```json
{"type":"audio","seq":1042,"rate":16000,"format":"pcm_s16le","data":"<base64>"}
```
Mono, 16 kHz, 20 to 100 ms per chunk, `seq` +1 per chunk (a gap means lost
audio; the brain carries on). The brain ignores this stream while it is
talking (mic mute), so the robot may keep streaming.

Optional `end_silence_ms` (int, v1.2 app mic): how long a silence ends a
request while this stream carries it (the app's "Wait before Spike
answers", default 3000). The brain clamps it to 1500..6000 and goes back to
its own `vad.end_silence_ms` when a chunk from that client comes without it
or the client disconnects. Older brains ignore it.

### 6.8 `camera`
```json
{"type":"camera","seq":88,"format":"jpeg","width":320,"height":240,"data":"<base64>"}
```
At most 10 frames per second, each at most 48 KiB of JPEG. Frames are
processed in memory and never stored unless the brain runs with its debug
flag.

### 6.9 `text`
`{"type":"text","text":"what's the time?"}`. Typed input from the
simulator or a tool; handled exactly like heard speech, wake word not
needed.

### 6.10 `alarm_ack`
`{"type":"alarm_ack","action":"stop"}` (`stop` or `snooze`), from a
button on the robot or simulator.

### 6.11 `log`
`{"type":"log","level":"warn","msg":"I2S underrun"}`. Optional; the brain
prints it.

### 6.12 `pong`
`{"type":"pong","re":41}`.

## 7. error (both directions)
```json
{"type":"error","re":12,"code":"bad_value","message":"unknown mood 'happpy'"}
```
Codes: `bad_json`, `missing_field`, `bad_value`, `unknown_type`,
`version_mismatch`, `not_ready`, `auth`, `too_big`, `busy` (v1.3, section
11.4: the robot already has another brain). An error never closes
the connection by itself, except the cases in section 3.

## 8. Reserved for later (do not use in v1)
`move` (come to the owner across the desk, go to the ArUco home spot),
`ota`, `config`, binary audio frames. These names are reserved.

## 9. Example session
```
robot -> {"v":1,"type":"hello","id":1,"role":"simulator","device_id":"sim-3f2a","fw":"2.0.0","caps":["face","speaker","touch","text","battery"]}
brain -> {"v":1,"type":"hello","id":1,"re":1,"server":"spike-brain",...}
brain -> {"v":1,"type":"set_mode","id":2,"mode":"dog"}
brain -> {"v":1,"type":"mood","id":3,"mood":"neutral"}
robot -> {"v":1,"type":"touch","id":2,"zone":"head","gesture":"tap"}
brain -> {"v":1,"type":"listening","id":4,"state":"listening"}
brain -> {"v":1,"type":"listening","id":5,"state":"thinking"}
brain -> {"v":1,"type":"say","id":6,"utt":"u1","seq":0,"final":true,"text":"Hi! I missed you.",...}
brain -> {"v":1,"type":"say_audio","id":7,"utt":"u1","seq":0,"index":0,"last":true,"data":"..."}
robot -> {"v":1,"type":"say_state","id":3,"utt":"u1","seq":0,"state":"started"}
robot -> {"v":1,"type":"say_state","id":4,"utt":"u1","seq":0,"state":"finished"}
brain -> {"v":1,"type":"listening","id":8,"state":"idle"}
```

## 10. The phone app (v1.2)

The Spike app on the owner's phone is a client like the robot, with
`role: "app"` in its `hello` (section 4.1 gains the role `app`). A brain older
than v1.2 answers that hello with `error` `bad_value`; the app then says hello
again as `role: "tool"` and falls back to the v1.1 behaviour (typed words).

An `app` client should announce the caps `face` (it mirrors the face, so the
brain sends it every face message like to a robot), `text` and `mic`. It must
**not** announce `speaker` (that is the robot's cap: the brain would treat the
phone as Spike's body). Since v1.5 it may announce `audio_out` instead
(section 10.8): then the phone plays the voice of the conversations that come
from it, and only those.

### 10.1 Security

- On the LAN every client needs the pairing token (section 4). Only a client
  whose TCP peer is the brain's own laptop (loopback: the simulator, or a
  phone through `adb reverse`) may leave it out (`[server] trust_loopback`).
- The types in 10.2 to 10.6 are accepted **only** from role `app`. From any
  other role they are `unknown_type`, as before. A phone can never send the
  robot's own reports: `battery`, `camera`, `say_state`, `edge`, `imu` and
  `mood_state` from an `app` client are ignored. (v1.5: `say_state` from an
  app with `audio_out` is accepted, but only for an utterance that phone is
  playing, section 10.8.)
- Message ids: fields that name a timer or a memory are `timer_id` and
  `fact_id`, never `id` (that is the envelope's message counter).

### 10.2 App to brain: the face and the body

Exactly the brain-to-robot messages of section 5, sent by the app; the brain
validates them with the same tables, updates its own state and passes them
on to every `face` client (the robot, the simulator, other phones):

| type | fields | what the brain does |
|------|--------|---------------------|
| `action` | `action` (5.2), `quiet` (bool, optional) | Plays it. For a trick the brain also answers out loud like it does to the spoken command ("Ta-da!", Spicy first refuses); `fallAsleep` says the goodnight line; `wakeUp`, `snuggle`, `slowWag`, `boop` and anything with `quiet: true` are silent. |
| `mood` | `mood`, `hold_s` (0..600) | Sets the face mood. |
| `event` | `event` (5.3) | The robot runs that reflex. |
| `sound` | `sound` (5.8) | The robot plays it (the brain's mic ignores it). |
| `set_mode` | `mode`, `quiet` (optional) | Switches Spike/Spicy; the brain announces it unless `quiet`. Same mode: the brain only echoes `set_mode` to the sender. |
| `set_recipe` | `mode`, and `code` (max 400 chars) or `recipe` (max 4 KiB of JSON) | "Wear this face": passed to every other `face` client, and **kept by the brain**, which sends it again to every robot or simulator that connects later. |
| `set_display` | `captions` (bool) | Caption bubbles on the robot's screen on or off; kept and re-sent on connect like `set_recipe`. |

`set_display` is also a new brain-to-robot type: `{"type":"set_display",
"captions":false}`. A robot that does not know it ignores it (rule 2) and keeps
showing captions.

### 10.3 Wheels: `drive`

```json
app  -> {"type":"drive","x":0.0,"y":0.6,"ttl_ms":300}
brain-> {"type":"drive","x":0.0,"y":0.6,"ttl_ms":300}     (to clients with the cap "drive")
```

- `x` turn, -1 (left) .. +1 (right); `y` speed, -1 (back) .. +1 (forward).
  Values outside are clamped; |x| and |y| under 0.02 count as 0.
  Robot mixing (arcade): `left = y + x`, `right = y - x`, each clamped to
  -1..1, then the robot's own speed caps apply.
- `ttl_ms` (100..1000, default 300): **dead man's switch.** The robot stops
  the wheels when `ttl_ms` passes without a newer `drive`. The app repeats
  `drive` about 20 times a second while the stick is held and sends one
  `x=0,y=0` on release.
- The brain forwards at most `[app] drive_rate_hz` (20) per second, newest
  value wins, a stop is forwarded at once. The brain has its own dead man's
  switch too: no `drive` from the phone within `ttl_ms` of the last one, or
  the phone disconnects, and the brain sends `x=0,y=0` itself.
- **The robot's reflexes always win.** Desk-edge, obstacle, pick-up, fall
  and low-battery stops run on the robot and filter every `drive`; no message
  can switch them off. `drive` is not the reserved `move` (section 8).
- A robot without the `drive` cap is never sent `drive`.

### 10.4 Lists: alarms, reminders and memories

Types: `timers_get`, `timer_set`, `timer_cancel` (app to brain), `timers`
(brain to app); `memory_get`, `memory_forget`, `memory_forget_all`, `memory`.

```json
app  -> {"type":"timers_get"}
brain-> {"type":"timers","items":[{"id":12,"kind":"alarm","due":1759219800,"label":"Wake up","repeat":null,"state":"active"}]}
app  -> {"type":"timer_set","kind":"reminder","due":1759219800,"label":"drink water","repeat":""}
app  -> {"type":"timer_cancel","timer_id":12}

app  -> {"type":"memory_get"}
brain-> {"type":"memory","items":[{"id":31,"text":"Arpon likes tea with honey","kind":"fact","at":1759180000}],"total":1}
app  -> {"type":"memory_forget","fact_id":31}
app  -> {"type":"memory_forget_all","confirm":true}
```

- `timers.items`: everything still to come or ringing, soonest first. `due`
  is Unix seconds; `kind` `alarm` or `reminder`; `repeat` `null` or
  `"daily"`; `state` `active`, `snoozed` or `ringing`.
- `timer_set`: `due` within the next year; `label` optional (max 80
  characters; alarms default to "Wake up"); `repeat` `""` or `"daily"`.
- `timer_cancel` of a ringing alarm stops it. An unknown or finished
  `timer_id` is answered `error` `bad_value`.
- `memory.items`: the newest `[app] memory_list_max` (200) facts, newest
  first, `text` at most 300 characters; `total` is how many there are.
- `memory_forget_all` needs `"confirm":true` (the app asks the owner first).
  It forgets facts, the mood diary and events; alarms stay.
- The brain sends `timers` and `memory` on connect and again **whenever
  they change**, whatever changed them (a voice command, another phone, an
  alarm firing). List operations are silent: the app shows the result.

### 10.5 Status for the app

| type (brain to app) | fields | when |
|---------------------|--------|------|
| `robot_status` | `online` (a robot board is connected: role `face`, `camera` or `robot`), `boards` (roles connected, the simulator included), `drive`, `camera` (bools) | on connect, and whenever a board connects or drops |
| `battery` | as 6.4 | relayed from the robot as it arrives; the last one on connect while the robot is online |
| `brain_status` | `llm`: `ready`, `warming` (starting Ollama / loading the model), `asleep` (unloaded after `[llm] idle_unload` without use; the next request wakes it), `off` (no Ollama: scripted lines) | on connect and on every change |
| `heard` | `text`, `via` (`typed`, or how it was heard), `mine` (true for the app that typed it) | every time the owner said or typed something to Spike |

### 10.6 Camera view

Types: `camera_subscribe`, `camera_unsubscribe` (app to brain), `camera`
(brain to app).

`{"type":"camera_subscribe","fps":5}` (0.5 to `[app] camera_max_fps`, 10)
makes the brain relay the robot's `camera` frames (6.8, same fields) to that
phone, newest only: a phone whose send queue is behind skips frames. It stops
on `camera_unsubscribe` or disconnect. Frames are never stored. Only frames
from the robot's own boards are relayed (never the laptop webcam).

### 10.7 Finding and pairing

- **mDNS / DNS-SD.** While it listens on the LAN the brain announces
  `_spike._tcp` on the laptop's main network address (not VPN or virtual
  adapters), port = the protocol port, TXT: `name` (Spike), `v=1`,
  `pv=1.2`, `ver` (brain version), `token=1` when a token is needed (never
  the token itself), `host` (the laptop's name). It re-announces when the
  laptop's address changes.
- **Pairing link** (shown as a QR by `python -m spike_brain --pair`):
  `spike://pair?host=<LAN IP>&port=<port>&token=<token>&name=Spike`.
  The token is `SPIKE_TOKEN` from `.env`, or, when none is set, one the brain
  makes once and keeps in `data/pairing_token.txt`.

### 10.8 Spike's voice on the phone (v1.5)

Design rule "laptop voice first": whenever the phone can reach the laptop
brain (home Wi-Fi or Tailscale), the owner hears the laptop's real voice
(Chatterbox Turbo, the voice cache, his recordings) on the phone.

**Hello.** The app adds the cap `audio_out` and says what it can play:

```json
{"type":"hello","role":"app","caps":["face","text","mic","audio_out"],
 "audio_out":{"formats":["ogg_opus","pcm_s16le"],"rates":[24000]}, ...}
```

`formats`, best first: `ogg_opus` (Ogg-encapsulated Opus, RFC 7845, mono,
about 32 kbit/s) and/or `pcm_s16le`. The brain picks the first it can make
(PCM16 if none match, or if it has no Opus encoder) and says so in its hello:
`"audio":{"format":"ogg_opus","rate":24000,"channels":1,"to_app":true}`. For
Opus the rate is the first of `rates` that Opus supports (8, 12, 16, 24 or
48 kHz), else 24 kHz.

**Where it plays (the routing rule).** A reply plays on the phone the
conversation came from, and nowhere else, when that phone has `audio_out`
and is still connected:
- the owner typed on that phone (`text`), or spoke into it (its `audio` mic
  stream fed the request, within the last 3 s, or its head `touch` started
  it), or pressed something on it that Spike answers out loud (a trick's
  "Ta-da!", goodnight, a mode switch announcement);
- the laptop's speaker and the robot's speaker then stay silent; the robot,
  the simulator and other phones get the same `say` with `audio: null` and
  the mouth timing (they show the caption and move the mouth);
- everything else (the robot's or the laptop's own microphone, alarms,
  greetings, nudges, a phone without `audio_out`) plays as before.

**Messages to that phone.** Each segment is a `say` (5.4) with `"play":true`,
followed by its `say_audio` chunks:

```json
{"type":"say","utt":"u17","seq":0,"final":false,"text":"Oh, you're home!","play":true,
 "duration_ms":1260,"mouth":{"rate_hz":50,"values":[0,12,55]},
 "audio":{"format":"ogg_opus","rate":24000,"channels":1,"samples":30240,"chunks":1,"bytes":5210}}
{"type":"say_audio","utt":"u17","seq":0,"index":0,"last":true,"data":"<base64>"}
```

- `ogg_opus`: all segments of one utterance form **one** Ogg Opus stream: the
  first segment's bytes start with the two header pages (`OpusHead`,
  `OpusTags`), later segments continue the same stream (same serial, page
  numbers and granule positions go on). Each segment is padded with silence
  to a whole 20 ms frame and ends on a page boundary, so it decodes to its
  last sample without waiting for the next one. `samples` counts the padded
  samples at `rate`; `duration_ms` = `samples` / `rate`.
- `pcm_s16le`: raw 16-bit mono samples, as 5.4.
- `data` is base64 of up to 12 KiB of the stream; `bytes` is the segment's
  total. Chunks never split across segments.
- `"play":true` with `"audio":null` = the laptop has no voice for this
  sentence: the phone says `text` with its own voice.
- The end marker (5.4) ends the utterance as usual. `stop_speaking` (5.5)
  cuts it.

**The phone** appends each segment to its player as soon as its last chunk
is in (sentences follow each other without a gap), reports `say_state`
`started` / `finished` per segment as playback passes them (the brain keeps
its mic muted until the final one, 5.4, with the same timeout), and says a
segment with its own voice (Kokoro, else Android's) when it came without
audio, its audio did not complete, or it cannot play the format. If the link
drops mid-reply it still says every segment it was told about. A brain older
than v1.5 never sends `play`, so the app plays nothing and the brain's own
speaker is heard, as before.
  When the laptop runs Tailscale (signed in, running) the link also carries
  `ts=<100.x.y.z>` and `tsname=<MagicDNS name>`, read with
  `tailscale status --json` (read-only). The app tries `host` first (home
  Wi-Fi), then `ts`, then `tsname`, with the same token, so it reaches the
  brain from any network when the phone is on the same tailnet. Older apps
  ignore the extra fields.
- `pairing_get` (app to brain) / `pairing` (brain to app):
  `{"type":"pairing_get"}` from an `app` client is answered
  `{"type":"pairing","lan":true,"url":"spike://pair?..."}` (`lan:false`,
  `url:""` when the brain is on loopback only). A phone paired over USB uses
  it to switch to Wi-Fi, or to show the QR to a second phone.

### 10.9 Keep-alive (v1.6)

`{"type":"keepalive","warm":true}` (app to brain; `warm` optional, default
true). While the owner's mic session is open and he is quiet, the app sends it
about every 2 s. The brain then (a) restarts the language model's idle-unload
timer, waking the model if it had unloaded, and (b) pushes back the end of a
listening window that is open with nothing said, so it does not time out. It
produces **no** face event, sound, `listening` message or relay to the robot,
does not count as owner interaction, and does not open a listening window that
is closed (a head `touch` does that). No reply is sent.

Detection: a brain that understands it adds `"keepalive":true` to its `hello`.
An app must send `keepalive` only to a brain whose hello has that field (an
older brain answers `unknown_type`) and otherwise sends nothing at all; it
must not fall back to a head `touch`.

### 10.10 Who voices the phone's replies (v1.7)

App to brain, any time after hello, and again after every reconnect:
`{"type":"voice_source","voice":"phone"}` or `"laptop"` (default `laptop`; the
hello may carry the first value as `audio_out: {..., "voice": "phone"}`).

- `phone`: replies routed to this phone (10.8) are sent as `say` with
  `play: true` and `audio: null`; the brain synthesises nothing and plays
  nothing on the laptop or the robot (they get the caption and mouth timing as
  in 10.8). Every sentence has passed the brain's own safety checks before it
  is sent, exactly as for its own voice. The phone speaks it (Gemini TTS, then
  its other voices).
- `laptop`: the brain's own voice, as in 10.8.
- The app switches back to `laptop` when its Gemini voice is unavailable (no
  key, free quota used up) or the owner picks "Use the laptop voice instead".
- The brain's hello says `"voice_source": true` when it understands this; an
  older brain never says so and the app never sends it (it would only earn an
  `unknown_type` error).

### 10.11 The laptop's Gemini voice style (v1.8)

The Windows desktop app runs a light brain that speaks with Gemini TTS itself
(`[tts] engine = "gemini"`, software/app/DESIGN.md "Desktop"), in the same
Google voices and style prompts as the phone (Spike: `energetic` Fenrir
(default), `upbeat` Puck, `friendly` Achird, `street` Algenib; Spicy: `sassy`
Kore (default), `smooth` Despina, `drawl` Callirrhoe, `caring` Kore).

```json
brain-> {"type":"hello", ..., "voice_style":{"dog":"energetic","cat":"sassy"}}
app  -> {"type":"voice_style","mode":"dog","style":"street"}
brain-> {"type":"voice_style","styles":{"dog":"street","cat":"sassy"}}      (to every app)
```

- `voice_style` (app to brain): `mode` `dog` or `cat`, `style` one of that
  character's ids above; anything else is answered `error` `bad_value`. The
  brain keeps the pick (it survives restarts) and sends the new picks to every
  connected app.
- The brain's hello has `voice_style` (the current picks) **only** when it
  speaks with Gemini TTS; an app sends `voice_style` only to such a brain (an
  older or non-Gemini brain would answer `unknown_type` or ignore it).
- Sad, lonely and crisis lines always use the soft direction, whatever the
  style; the safety checks are the same for every style.

## 11. Away from home (v1.3)

Away from the home Wi-Fi the **phone is Spike's brain** (the app's "phone
brain": persona, moods, commands, the language model, the safety layer). It
speaks this same protocol to the robot, exactly as the laptop brain does:
the robot is still the client of sections 3 to 6, only the pipe changes.

| Link | Pipe | Used for |
|------|------|----------|
| home | WebSocket to the laptop brain (sections 1 to 10) | at home: the laptop is the brain |
| BLE | Bluetooth LE GATT (11.1 to 11.3) | away: the main phone <-> robot link |
| hotspot | WebSocket from the robot boards to the phone, over the phone's hotspot (11.5) | away: the camera, and a backup when BLE is poor |

Spike's own setup access point (the screen board's captive portal) stays for
first-time setup only; it is never a brain link.

### 11.1 The GATT service (screen board)

| What | UUID | Properties | Security |
|------|------|------------|----------|
| service "Spike link" | `c0de5b1e-0001-4a3c-9e5f-5370696b6500` | primary, advertised | - |
| `rx` (phone -> robot) | `c0de5b1e-0002-4a3c-9e5f-5370696b6500` | write, write without response | encrypted + authenticated (MITM) |
| `tx` (robot -> phone) | `c0de5b1e-0003-4a3c-9e5f-5370696b6500` | notify | encrypted + authenticated: the robot sends and accepts nothing until the link is encrypted, MITM-authenticated and bonded; a subscription on an unauthenticated link is answered with a Security Request (NimBLE gives every CCCD one permission, so the CCCD write itself is not refused) |
| `info` | `c0de5b1e-0004-4a3c-9e5f-5370696b6500` | read | open (nothing secret) |

- **Advertising:** connectable, the service UUID in the advertisement, the
  local name `Spike-xxxxxx` (the last 6 of `device_id`) in the scan response.
  The robot advertises whenever no phone is connected (one connection at a
  time), and keeps doing so while it is on Wi-Fi: BLE and Wi-Fi coexist.
- **`info`** is a small JSON object (at most 180 bytes), readable before
  pairing so the app can show what it found:
  `{"pv":"1.3","fw":"0.2.0","device_id":"spike-7c9e2a","brain":"lan"}`.
  `brain` is as in `robot_link` (11.4).
- **Pairing: LE Secure Connections, MITM protection, bonding.** The robot's
  IO capability is *DisplayOnly*: when a phone pairs, the robot shows a random
  6-digit passkey big on its face screen and the phone's system dialog asks the
  owner to type it. Seeing the screen is the proof of being with Spike. Legacy
  pairing and "Just Works" are refused. The robot keeps at most 4 bonds; a new
  bond when full replaces the least recently used one. `ble forget` on the
  serial console clears them all.
- **MTU:** the phone asks for 517; frames use the negotiated `ATT_MTU`.

### 11.2 Framing

A protocol message (one JSON object, UTF-8, exactly as sections 2 to 11) is
sent as one or more **frames**. Each frame is one write to `rx` or one
notification on `tx`:

```
byte 0     header: bit 7 START (first frame of a message)
                   bit 6 END   (last frame of a message)
                   bits 5..0   frame counter
bytes 1..  payload: the next piece of the message's UTF-8 bytes
```

- A message that fits is one frame with START and END both set. The frame
  payload is at most `ATT_MTU - 3 - 1` bytes (19 at the minimum MTU of 23).
- The frame counter counts every frame in that direction, 0 to 63 and round
  again, starting at 0 when the phone subscribes to `tx` (robot to phone) and
  at 0 on the first write after connecting (phone to robot).
- The receiver keeps the counter it expects next. A frame with another counter
  means frames were lost: it throws away the message it was building, takes
  the new counter, and starts collecting again at the next START frame. A
  START frame while a message is being built also starts over (the old one is
  dropped). A continuation frame (no START) while nothing is being built is
  dropped.
- A message may be at most **16 KiB** over BLE; a receiver drops a longer one
  (and answers `error` `too_big` once). `say_audio` and `camera` are never sent
  over BLE: they are too big for it and go over the hotspot (11.5).
- So a receiver never needs more than one 16 KiB message buffer per direction.

Shared test vectors for every implementation (app, firmware, fake robot):
`software/protocol/ble_frame_vectors.json`.

### 11.3 The session over BLE

- The phone waits for the robot's `hello` (up to 15 s: pairing may still be finishing) rather than relying on the subscription failing.
- When the phone subscribes to `tx`, the robot starts section 3 exactly as on
  a WebSocket: it sends its `hello` (`role` `face`, its caps, and `"link":"ble"`)
  within 5 s. No `token`: the bond is the authentication. The phone brain
  answers with its brain `hello`, then `set_mode` and `mood` (3.3).
- Heartbeat and dead link: as section 3.4 (`heartbeat_s` from the phone
  brain's hello). A BLE disconnect is a closed link.
- Reconnect: the phone (the BLE central) reconnects; the robot just keeps
  advertising. After a reconnect the robot sends a fresh `hello`.
- Everything in sections 5 and 6 works over BLE except the big messages
  above. The phone brain plays Spike's voice **on the phone** while away, so
  its `say` segments to the robot are caption-only (`audio` null) with
  `duration_ms` and the `mouth` envelope: the robot moves its mouth to the
  phone's voice and reports `say_state` as usual. The robot's microphones are
  not used away (the phone listens); a head tap still sends `touch`, and the
  phone brain starts listening on it.

### 11.4 One brain at a time: `robot_link` and `busy`

The robot follows **one brain at a time**. When `robot_link.brain` becomes `ble` or `hotspot` again (the laptop link dropped), the phone brain re-sends its state (`set_mode`, `mood`, `set_recipe`, `set_display`): what it sent meanwhile was answered `busy`.
 The laptop brain wins: while the
robot's WebSocket brain link to the home brain has completed its hello, brain
messages that arrive over BLE are ignored and answered with `error` code `busy`
(`ping`, the BLE `hello` exchange, `hotspot_join` and `hotspot_leave` are still
handled). As soon as that home link drops, the BLE brain is followed again.
The phone brain over the hotspot (11.5) is the same brain as over BLE: the
robot accepts it on both links and sends each robot-to-brain message on one
link only, the hotspot WebSocket when it is up, else BLE.

Robot to phone over BLE, on connect and whenever it changes:

```json
{"type":"robot_link","brain":"ble","wifi":"hotspot","ip":"192.168.49.23","camera":true}
```

| field | meaning |
|-------|---------|
| `brain` | whose commands the robot follows: `lan` (the laptop), `ble` (this phone over BLE), `hotspot` (this phone over the hotspot), `none` |
| `wifi` | `home` (joined the saved Wi-Fi), `hotspot` (joined the phone's), `off` (not joined) |
| `ip` | the robot's Wi-Fi address, or `""` |
| `camera` | optional: the camera board has joined the phone's hotspot (11.6) |

When the app sees `brain: "lan"` it connects to the laptop brain itself (the
phone is then an app of section 10 again).

### 11.5 The phone's hotspot

The camera, and any heavy traffic, need Wi-Fi. Away from home the phone
makes one (Android `startLocalOnlyHotspot`, or, when that is not possible,
the owner's own personal hotspot whose name and password the app keeps), runs
a small WebSocket server on it, and gives the robot the details **over BLE
only** (encrypted, bonded link; never over the air in the clear):

```json
phone -> {"type":"hotspot_join","ssid":"AndroidShare_1234","pass":"...","port":8766,"token":"9f2c...","host":""}
robot -> {"type":"hotspot_state","state":"joining"}
robot -> {"type":"hotspot_state","state":"joined","ip":"192.168.49.23"}
phone -> {"type":"hotspot_leave"}
robot -> {"type":"hotspot_state","state":"left"}
```

| field | meaning |
|-------|---------|
| `ssid`, `pass` | the hotspot's name (1..32 bytes) and WPA2 passphrase (8..63 printable ASCII characters) |
| `port` | the phone brain's WebSocket port on the hotspot |
| `token` | a one-time pairing token (16..32 characters, so the whole join fits one ESP-NOW packet, 11.6) for this hotspot session: every board's `hello` over the hotspot must carry it (section 4) |
| `host` | the phone's address on the hotspot (IPv4 or a host name); `""` = the Wi-Fi gateway (the phone is the access point) |
| `state` | `joining`, `joined` (with `ip`), `failed` (with `reason`: `not_found` (this includes a 5 GHz-only hotspot: the ESP32-S3 has 2.4 GHz only), `auth`, `timeout`, `bad_value`), `left` |

- On `hotspot_join` the screen board leaves the home Wi-Fi (if joined), joins
  the hotspot (20 s timeout), then opens its WebSocket brain link to
  `ws://<host or gateway>:<port>/` with the token and `"link":"hotspot"` in its
  hello. It also hands the hotspot to the camera board (11.6).
- The hotspot details live in RAM only, never in flash. The robot goes back to
  its saved home Wi-Fi on `hotspot_leave`, on a reboot, or when the hotspot
  link has been dead for 60 s and no phone is connected over BLE.
- The phone brain's server needs the token from every board (section 10.1
  applies); it accepts roles `face`, `camera` and `robot` only.

### 11.6 Camera board: ESP-NOW hand-over (robot internal)

The camera board has no BLE link to the phone. The screen board passes the
hotspot on over ESP-NOW, encrypted with the robot's **link key**: 32 random
bytes the screen board makes on first boot and keeps in NVS; the camera board
gets the same key once, at the bench or the factory (serial console `linkkey`
on the screen board prints it, `linkkey <64 hex>` on the camera board stores
it). Without a link key the camera board stays on the home Wi-Fi only.

ESP-NOW payload (broadcast, at most 250 bytes):

```
"SPK1" (4) | kind (1) | nonce (12) | ciphertext (n) | tag (16)
kind 1 = hotspot join: plaintext {"ssid":..,"pass":..,"port":..,"token":..,"host":..,"sid":..}
kind 2 = hotspot leave: plaintext {"sid":..}
sid = a random session id made by the screen board for each join; the camera board
obeys a kind 2 only if its sid matches the join it followed (a recorded kind 2
can't knock it off a later hotspot)
AES-256-GCM, key = link key, AAD = the first 5 bytes, nonce random per message
```

- The screen board sends it once a second on the hotspot's channel from the
  moment it has joined, until the phone confirms the camera board is online
  (`{"type":"robot_link_ack","camera":true}` over either link) or for 120 s.
- The camera board, while it has no working brain link, listens on channels 1
  to 13 in turn (1.5 s each). On a message that decrypts, it joins that
  hotspot (RAM only) and connects as `role: "camera"` with the token. `kind 2`
  or 60 s without its hotspot link sends it back to the home Wi-Fi.
- A frame that does not decrypt is ignored. Replaying an old message can at
  worst point the camera at a hotspot that no longer exists.

### 11.7 Summary of new types (v1.3)

| type | direction | link |
|------|-----------|------|
| `hotspot_join`, `hotspot_leave` | phone -> robot | BLE only |
| `hotspot_state`, `robot_link` | robot -> phone | BLE (also allowed on the hotspot) |
| `robot_link_ack` | phone -> robot | either |
| `error` `busy` | robot -> phone | BLE |

A laptop brain never sees any of these: they exist only between the robot and
a phone brain. The laptop brain treats them as `unknown_type` as before.
