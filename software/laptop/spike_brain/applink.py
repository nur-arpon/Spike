"""The phone app's side of the brain (PROTOCOL.md section 10, v1.2).

A client that says `role: "app"` in its hello may send, besides the robot's own types:
  - the face and body, as the brain would send them: action, mood, event, sound, set_mode,
    set_recipe ("Wear this face"), set_display (captions on the robot's screen);
  - drive (the joystick): forwarded to the robot at most `drive_rate_hz` times a second, and
    a stop is sent by the brain itself when the phone goes quiet for `ttl_ms` (dead man's
    switch) or disconnects. The robot's own desk-edge and pick-up reflexes always win: the
    robot filters every drive command, and nothing here can switch that off;
  - lists: timers_get / timer_set / timer_cancel, memory_get / memory_forget /
    memory_forget_all; pairing_get; keepalive (v1.6: silent, no face or sound);
    voice_source (v1.7: "phone" = it speaks its replies itself, the brain sends text only);
  - camera_subscribe / camera_unsubscribe: the robot's camera frames, relayed live
    (never stored), at most `camera_max_fps`.
And it receives: timers, memory (again whenever they change), robot_status (a board connected
or dropped), battery (relayed from the robot), camera (when subscribed), heard (what the owner
said, for the Talk screen), brain_status (the language model: ready / warming / asleep / off).

Everything here is app-only: robot boards and the simulator see exactly what they saw in v1.1
(plus set_recipe / set_display relays they already ignore or understand, and `drive`, which
only goes to clients with the `drive` capability).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import discovery
from . import protocol as P
from .server import Client, is_loopback
from .speech.output import reply_to

if TYPE_CHECKING:  # pragma: no cover
    from .brain import Brain

log = logging.getLogger("spike.app")

SLEEP_ACTIONS = ("fallAsleep", "napping", "dozing", "deepSleepDreams")
QUIET_ACTIONS = ("wakeUp", "snuggle", "slowWag", "boop")        # no spoken line with these
# v1.4 body actions (PROTOCOL.md 5.2): optional fields on "action" that only mean something
# for "walk" / "paw"; forwarded to the robot as given (walk and paw are tricks - Ta-da! - so
# these ride along through do_trick, same as any other action).
BODY_ACTION_FIELDS = ("direction", "steps", "style", "side", "from")
ROBOT_ONLY = ("battery", "camera", "say_state", "edge", "imu", "mood_state")   # never accepted from a phone
MAX_RECIPE_CODE = 400
MAX_LABEL = 80


def _num(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


class AppLink:
    def __init__(self, brain: "Brain"):
        self.b = brain
        self.server = brain.server
        cfg = brain.s.cfg.get("app") or None
        get = (lambda k, d: cfg.get(k, d)) if cfg is not None else (lambda k, d: d)
        self.drive_interval = 1.0 / max(1.0, float(get("drive_rate_hz", 20)))
        self.drive_ttl_default = int(get("drive_ttl_ms", 300))
        self.camera_max_fps = float(get("camera_max_fps", 10))
        self.memory_list_max = int(get("memory_list_max", 200))
        self.poll_s = float(get("list_poll_s", 1.0))
        self.mdns = bool(get("mdns", True))
        self.prefs_path = Path(brain.memory.path).parent / "app_prefs.json" \
            if isinstance(brain.memory.path, Path) else None
        self.prefs: dict = self._load_prefs()
        # drive
        self._drive_want = (0.0, 0.0)
        self._drive_ttl = self.drive_ttl_default
        self._drive_from: int | None = None
        self._drive_last_fwd = -1e9
        self._drive_moving = False
        self._drive_pending: asyncio.TimerHandle | None = None
        self._deadman: asyncio.TimerHandle | None = None
        self.drives_sent: list[tuple[float, float]] = []      # (x, y) forwarded (tests, debug)
        # camera
        self._cam_subs: dict[int, tuple[float, float]] = {}   # conn_id -> (fps, last sent)
        # battery / text / lists
        self.battery: dict | None = None
        self._last_text: tuple[int, str] | None = None
        self._timers_sig = None
        self._memory_sig = None
        self._task: asyncio.Task | None = None
        self.advertiser: discovery.Advertiser | None = None

    # ------------------------------------------------------------------ prefs
    def _load_prefs(self) -> dict:
        if self.prefs_path is None:
            return {}
        try:
            data = json.loads(self.prefs_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_prefs(self) -> None:
        if self.prefs_path is None:
            return
        try:
            self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.prefs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.prefs, indent=1), encoding="utf-8")
            tmp.replace(self.prefs_path)
        except OSError as e:
            log.warning("could not save the app settings: %s", e)

    # ------------------------------------------------------------------ clients
    def apps(self) -> list[Client]:
        return [c for c in self.server.clients.values() if c.role == "app"]

    def boards(self) -> list[Client]:
        return [c for c in self.server.clients.values() if c.role in P.BOARD_ROLES]

    def robot_online(self) -> bool:
        return bool(self.boards())

    def _to_apps(self, type_: str, **fields) -> None:
        for c in self.apps():
            self.server.send(c, type_, **fields)

    def robot_status_fields(self) -> dict:
        roles = sorted({c.role for c in self.server.clients.values() if c.role != "app" and c.role != "tool"})
        return {"online": self.robot_online(), "boards": roles,
                "drive": any(c.has("drive") for c in self.boards()),
                "camera": any(c.role == "camera" or c.has("camera") for c in self.boards())}

    def llm_state(self) -> str:
        svc = getattr(self.b, "ollama", None)
        if svc is not None:
            return svc.state
        return "ready" if self.b.llm is not None else "off"

    # ------------------------------------------------------------------ life
    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll(), name="app-lists")
        if not is_loopback(self.server.host) and self.mdns:
            self.advertiser = discovery.Advertiser(self.server.port, name=self.b.names.get("dog", "Spike"),
                                                   token_required=bool(self.server.token))
            await self.advertiser.start()
        if not is_loopback(self.server.host):
            log.info("listening on the Wi-Fi: pair a phone with pair_phone.bat (python -m spike_brain --pair)")

    async def stop(self) -> None:
        self._stop_drive("brain stopping")
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self.advertiser:
            await self.advertiser.stop()

    async def on_connect(self, client: Client) -> None:
        if client.role == "app":
            self.server.send(client, "robot_status", **self.robot_status_fields())
            self.server.send(client, "brain_status", llm=self.llm_state())
            if self.battery and self.robot_online():
                self.server.send(client, "battery", **self.battery)
            if "captions" in self.prefs:
                self.server.send(client, "set_display", captions=bool(self.prefs["captions"]))
            self._send_timers(client)
            self._send_memory(client)
            wake = getattr(self.b, "wake_llm", None)
            if wake:
                wake("app connected")
            return
        if client.has("face"):
            # what the owner chose in the app, for a robot or simulator that (re)connects
            for mode, rec in (self.prefs.get("recipes") or {}).items():
                if mode in P.MODES and isinstance(rec, dict):
                    self.server.send(client, "set_recipe", mode=mode, **rec)
            if "captions" in self.prefs:
                self.server.send(client, "set_display", captions=bool(self.prefs["captions"]))
        self._to_apps("robot_status", **self.robot_status_fields())

    async def on_disconnect(self, client: Client) -> None:
        if client.role == "app":
            self._cam_subs.pop(client.conn_id, None)
            if self._drive_from == client.conn_id:
                self._stop_drive("the phone disconnected")
            return
        if not self.robot_online():
            self.battery = None
        self._to_apps("robot_status", **self.robot_status_fields())

    # ------------------------------------------------------------------ hooks from the brain
    def heard(self, text: str, via: str) -> None:
        """What the owner said (or typed), for the app's Talk screen."""
        mine = self._last_text
        for c in self.apps():
            own = mine is not None and mine[0] == c.conn_id and mine[1] == text
            self.server.send(c, "heard", text=text, via=via, mine=own)
        self._last_text = None

    def on_llm_state(self, state: str) -> None:
        self._to_apps("brain_status", llm=state)

    # ------------------------------------------------------------------ messages
    async def handle(self, client: Client, msg: dict) -> bool:
        """Deal with app-level messages. True = handled here (the brain skips it)."""
        t = msg["type"]
        if client.role != "app":
            if t == "battery" and client.role in P.BOARD_ROLES:
                self.battery = {k: msg[k] for k in ("percent", "volts", "charging") if k in msg}
                self._to_apps("battery", **self.battery)
            elif t == "camera" and client.role in P.BOARD_ROLES:
                self._relay_camera(msg)
            return False
        if t == "say_state" and client.has("audio_out"):
            return False                                    # v1.5: a phone that plays the voice reports it
        if t in ROBOT_ONLY:
            return True                                     # a phone is not the robot
        if t == "text":
            self._last_text = (client.conn_id, msg["text"].strip()[:500])
            return False
        handler = getattr(self, "_on_" + t, None)
        if handler is None:
            return False                                    # touch, alarm_ack, audio, log: the brain's
        try:
            await handler(client, msg)
        except P.ProtocolError as e:
            self.server.send(client, "error", re=msg.get("id"), code=e.code, message=e.message)
        return True

    # --- face and body
    async def _on_action(self, client: Client, msg: dict) -> None:
        action, quiet = msg["action"], bool(msg.get("quiet", False))
        extra = {k: msg[k] for k in BODY_ACTION_FIELDS if k in msg}
        self.b.interacted()
        if action in SLEEP_ACTIONS:
            self.b.send_face("action", action=action, **extra)
            if not quiet:
                self.b._spawn(self.b.for_app(client, self.b.say_line("sleep")))
        elif quiet or action in QUIET_ACTIONS:
            self.b.send_face("action", action=action, **extra)
        else:
            self.b._spawn(self.b.for_app(client, self.b.do_trick(action, **extra)))   # then "Ta-da!" (29 Sep)

    async def _on_mood(self, client: Client, msg: dict) -> None:
        self.b.robot_mood = msg["mood"]
        fields = {"mood": msg["mood"]}
        if isinstance(msg.get("hold_s"), (int, float)) and not isinstance(msg.get("hold_s"), bool):
            fields["hold_s"] = _num(float(msg["hold_s"]), 0, 600)
        self.b.send_face("mood", **fields)

    async def _on_event(self, client: Client, msg: dict) -> None:
        self.b.interacted()
        self.b.send_face("event", event=msg["event"])

    async def _on_sound(self, client: Client, msg: dict) -> None:
        self.b.send_face("sound", sound=msg["sound"])
        self.b._mute_briefly()

    async def _on_set_mode(self, client: Client, msg: dict) -> None:
        mode = msg["mode"]
        if mode == self.b.mode:
            self.server.send(client, "set_mode", mode=mode)  # already: just keep the phone in step
            return
        with reply_to(self.b.reply_origin(client)):       # v1.5: the announcement plays on that phone
            await self.b.set_mode(mode, announce=not msg.get("quiet", False))

    async def _on_set_recipe(self, client: Client, msg: dict) -> None:
        code, recipe = msg.get("code"), msg.get("recipe")
        if code is not None:
            if not code or len(code) > MAX_RECIPE_CODE:
                raise P.ProtocolError("bad_value", "set_recipe: bad code")
            rec = {"code": code}
        elif isinstance(recipe, dict) and len(json.dumps(recipe)) <= 4096:
            rec = {"recipe": recipe}
        else:
            raise P.ProtocolError("missing_field", "set_recipe: needs 'code' or 'recipe'")
        self.prefs.setdefault("recipes", {})[msg["mode"]] = rec
        self._save_prefs()
        for c in self.server.clients.values():
            if c is not client and c.has("face"):
                self.server.send(c, "set_recipe", mode=msg["mode"], **rec)
        log.info("the app chose a new %s face", msg["mode"])

    async def _on_set_display(self, client: Client, msg: dict) -> None:
        self.prefs["captions"] = bool(msg["captions"])
        self._save_prefs()
        self.b.send_face("set_display", captions=self.prefs["captions"])

    # --- drive (joystick)
    async def _on_drive(self, client: Client, msg: dict) -> None:
        lo, hi = P.DRIVE_TTL_MS
        ttl = int(_num(float(msg.get("ttl_ms") or self.drive_ttl_default), lo, hi))
        x, y = _num(float(msg["x"]), -1, 1), _num(float(msg["y"]), -1, 1)
        if abs(x) < 0.02 and abs(y) < 0.02:
            x = y = 0.0
        self._drive_from, self._drive_ttl = client.conn_id, ttl
        self._drive_want = (round(x, 3), round(y, 3))
        loop = asyncio.get_running_loop()
        if self._deadman:
            self._deadman.cancel()
            self._deadman = None
        stop = x == 0 and y == 0
        if not stop:
            self._deadman = loop.call_later(ttl / 1000, self._deadman_fire)
        since = time.monotonic() - self._drive_last_fwd
        if stop or since >= self.drive_interval:
            self._forward_drive()
        elif self._drive_pending is None:
            self._drive_pending = loop.call_later(self.drive_interval - since, self._forward_drive)

    def _forward_drive(self) -> None:
        if self._drive_pending:
            self._drive_pending.cancel()
        self._drive_pending = None
        x, y = self._drive_want
        if x == 0 and y == 0 and not self._drive_moving:
            return                                          # already stopped: nothing to say
        self._drive_last_fwd = time.monotonic()
        self._drive_moving = not (x == 0 and y == 0)
        self.drives_sent.append((x, y))
        if len(self.drives_sent) > 200:
            del self.drives_sent[:100]
        self.server.broadcast("drive", cap="drive", x=x, y=y, ttl_ms=self._drive_ttl)

    def _deadman_fire(self) -> None:
        self._deadman = None
        if self._drive_moving:
            log.info("drive: no word from the phone for %d ms, stopping the wheels", self._drive_ttl)
            self._drive_want = (0.0, 0.0)
            self._forward_drive()

    def _stop_drive(self, why: str) -> None:
        for h in (self._deadman, self._drive_pending):
            if h:
                h.cancel()
        self._deadman = self._drive_pending = None
        if self._drive_moving:
            log.info("drive: stop (%s)", why)
            self._drive_want = (0.0, 0.0)
            self._forward_drive()
        self._drive_from = None

    # --- camera
    async def _on_camera_subscribe(self, client: Client, msg: dict) -> None:
        fps = msg.get("fps")
        fps = _num(float(fps), 0.5, self.camera_max_fps) if isinstance(fps, (int, float)) else 5.0
        self._cam_subs[client.conn_id] = (fps, 0.0)

    async def _on_camera_unsubscribe(self, client: Client, msg: dict) -> None:
        self._cam_subs.pop(client.conn_id, None)

    def _relay_camera(self, msg: dict) -> None:
        if not self._cam_subs:
            return
        now = time.monotonic()
        fields = {k: msg[k] for k in ("seq", "format", "width", "height", "data") if k in msg}
        for cid, (fps, last) in list(self._cam_subs.items()):
            c = self.server.clients.get(cid)
            if c is None:
                self._cam_subs.pop(cid, None)
                continue
            if now - last < 1.0 / fps or c.queue.qsize() > 2:   # a slow phone gets fewer frames, never a backlog
                continue
            self._cam_subs[cid] = (fps, now)
            self.server.send(c, "camera", **fields)

    # --- alarms and reminders
    def timer_items(self) -> list[dict]:
        return [{"id": t.id, "kind": t.kind, "due": int(t.due), "label": t.label,
                 "repeat": t.repeat or None, "state": t.state} for t in self.b.scheduler.listing()]

    def _send_timers(self, client: Client | None = None) -> None:
        items = self.timer_items()
        self._timers_sig = json.dumps(items)
        if client is not None:
            self.server.send(client, "timers", items=items)
        else:
            self._to_apps("timers", items=items)

    async def _on_timers_get(self, client: Client, msg: dict) -> None:
        self._send_timers(client)

    async def _on_timer_set(self, client: Client, msg: dict) -> None:
        due = float(msg["due"])
        if due < time.time() - 60 or due > time.time() + 366 * 86400:
            raise P.ProtocolError("bad_value", "timer_set: 'due' must be in the next year")
        kind = msg["kind"]
        label = (msg.get("label") or "").strip()[:MAX_LABEL] or ("Wake up" if kind == "alarm" else "that thing")
        t = self.b.scheduler.add(kind, datetime.fromtimestamp(due), label, msg.get("repeat") or "")
        log.info("the app set %s #%d for %s (%s)", kind, t.id, t.due_dt.strftime("%a %H:%M"), label)
        self._send_timers()

    async def _on_timer_cancel(self, client: Client, msg: dict) -> None:
        tid = msg["timer_id"]
        ringer = self.b.ringer
        if ringer is not None and ringer.timer_id == tid:
            await self.b.alarm_stop(quiet=True)
            self.b.scheduler.cancel_id(tid)
        elif not self.b.scheduler.cancel_id(tid):
            raise P.ProtocolError("bad_value", f"timer_cancel: no pending timer {tid}")
        log.info("the app cancelled timer #%d", tid)
        self._send_timers()

    # --- memory
    def memory_items(self) -> tuple[list[dict], int]:
        facts = self.b.memory.newest(self.memory_list_max)
        return ([{"id": f.id, "text": f.text[:300], "kind": f.kind, "at": int(f.created)} for f in facts],
                self.b.memory.count())

    def _send_memory(self, client: Client | None = None) -> None:
        items, total = self.memory_items()
        self._memory_sig = self.b.memory.signature()
        if client is not None:
            self.server.send(client, "memory", items=items, total=total)
        else:
            self._to_apps("memory", items=items, total=total)

    async def _on_memory_get(self, client: Client, msg: dict) -> None:
        self._send_memory(client)

    async def _on_memory_forget(self, client: Client, msg: dict) -> None:
        if not self.b.memory.forget(msg["fact_id"]):
            raise P.ProtocolError("bad_value", f"memory_forget: no fact {msg['fact_id']}")
        log.info("the app made Spike forget fact #%d", msg["fact_id"])
        self._send_memory()

    async def _on_memory_forget_all(self, client: Client, msg: dict) -> None:
        self.b.memory.wipe()
        self.b.conv.clear()
        log.info("the app made Spike forget everything")
        self._send_memory()

    # --- v1.6: the phone mic session is open and the owner is quiet (PROTOCOL.md 10.9)
    async def _on_keepalive(self, client: Client, msg: dict) -> None:
        self.b.keepalive()                                  # no face event, no sound, no relay, no interacted()

    # --- v1.7: who voices the replies this phone plays (PROTOCOL.md 10.10)
    async def _on_voice_source(self, client: Client, msg: dict) -> None:
        client.phone_voice = msg["voice"] == "phone"
        log.info("phone %s voices its own replies: %s", client.device_id, client.phone_voice)

    # --- v1.8: the owner's Gemini voice style for Spike or Spicy (PROTOCOL.md 10.11; desktop light brain)
    async def _on_voice_style(self, client: Client, msg: dict) -> None:
        picks = getattr(self.b, "voice_picks", None)
        if picks is None or not picks.set(msg["mode"], msg["style"]):
            raise P.ProtocolError("bad_value", f"voice_style: no style {msg['style']!r} for {msg['mode']}")
        self.prefs["voice_styles"] = picks.as_dict()
        self._save_prefs()
        log.info("the app picked the %s voice style for %s", msg["style"], msg["mode"])
        # every app (this laptop's and the phones) shows the same pick
        self._to_apps("voice_style", styles=picks.as_dict())

    # --- pairing (a phone on USB learns the Wi-Fi pairing, or shows it to a second phone)
    async def _on_pairing_get(self, client: Client, msg: dict) -> None:
        lan = not is_loopback(self.server.host)
        ip = discovery.lan_ip() if lan else None
        ts, ts_name = await asyncio.to_thread(discovery.tailscale_addrs) if ip else (None, None)
        url = discovery.pairing_url(ip, self.server.port, self.server.token, self.b.names.get("dog", "Spike"),
                                    ts=ts, ts_name=ts_name) if ip else ""
        self.server.send(client, "pairing", lan=bool(ip), url=url)

    # ------------------------------------------------------------------ change polling
    async def _poll(self) -> None:
        """Send the lists again when they change, whatever changed them (voice, app, an alarm firing)."""
        while True:
            await asyncio.sleep(self.poll_s)
            if not self.apps():
                continue
            try:
                if json.dumps(self.timer_items()) != self._timers_sig:
                    self._send_timers()
                if self.b.memory.signature() != self._memory_sig:
                    self._send_memory()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.debug("list poll failed", exc_info=True)
