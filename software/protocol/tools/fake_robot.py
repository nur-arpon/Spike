"""A fake Spike screen board for testing the phone app away from home (PROTOCOL.md 11).

It advertises the "Spike link" GATT service over Bluetooth LE from this laptop
(the `bless` package, WinRT on Windows), speaks the framed JSON of 11.2, says
hello like the robot (role face), answers pings, prints everything the phone
brain sends (moods, actions, captions with their mouth envelope, drive), and
reports touches and a battery level when you type them. On `hotspot_join` it
can either fail politely (default: this laptop is not going to leave its Wi-Fi)
or, with --hotspot-ws HOST, connect to the phone's hotspot server as a board.

    python fake_robot.py --selftest          framing against ble_frame_vectors.json (no radio)
    python fake_robot.py                     advertise and wait for the phone (Ctrl+C to stop)
    python fake_robot.py --seconds 20        advertise for 20 s, then stop by itself

Typed commands while running: `tap` (head tap), `pat`, `boop`, `battery 42`,
`pickup`, `quit`.

Limits: Windows can't show a passkey or demand MITM pairing from a bless GATT
server, so the fake robot's characteristics are open (the real robot requires
an encrypted, authenticated bond). Use it on a test phone only.
Needs: .venv-fake-robot (python -m venv; pip install bless websockets).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from ble_frames import Decoder, Encoder, payload_size

SERVICE = "c0de5b1e-0001-4a3c-9e5f-5370696b6500"
RX = "c0de5b1e-0002-4a3c-9e5f-5370696b6500"
TX = "c0de5b1e-0003-4a3c-9e5f-5370696b6500"
INFO = "c0de5b1e-0004-4a3c-9e5f-5370696b6500"
DEVICE_ID = "spike-fa4e01"
VECTORS = Path(__file__).resolve().parents[1] / "ble_frame_vectors.json"


def selftest() -> int:
    v = json.loads(VECTORS.read_text(encoding="utf-8"))
    bad = 0
    for c in v["encode"]:
        e = Encoder()
        e.counter = c["start_counter"]
        got = [f.hex() for f in e.encode(c["message"].encode("utf-8"), c["att_mtu"])]
        if got != c["frames"]:
            bad += 1
            print("ENCODE MISMATCH:", c["name"])
    for c in v["decode"]:
        d = Decoder()
        out = [m.decode("utf-8") for f in c["frames"] if (m := d.feed(bytes.fromhex(f))) is not None]
        if out != c["messages"] or d.dropped != c["dropped"] or d.too_big != c["too_big"]:
            bad += 1
            print("DECODE MISMATCH:", c["name"])
    n = len(v["encode"]) + len(v["decode"])
    print(f"selftest: {n - bad}/{n} vector cases pass")
    return 1 if bad else 0


class FakeRobot:
    def __init__(self, hotspot_ws: str | None):
        self.enc, self.dec = Encoder(), Decoder()
        self.out_id = 0
        self.mtu = 23
        self.server = None
        self.subscribed = False
        self.brain_hello = False
        self.hotspot_ws = hotspot_ws
        self.loop: asyncio.AbstractEventLoop | None = None

    def msg(self, type_: str, **fields) -> dict:
        self.out_id += 1
        return {"v": 1, "type": type_, "id": self.out_id, "ts": int(time.monotonic() * 1000), **fields}

    def send(self, m: dict) -> None:
        if not self.server or not self.subscribed:
            return
        data = json.dumps(m, separators=(",", ":")).encode("utf-8")
        for f in self.enc.encode(data, self.mtu):
            self.server.get_characteristic(TX).value = bytearray(f)
            self.server.update_value(SERVICE, TX)
        print("robot ->", m["type"], {k: v for k, v in m.items() if k not in ("v", "id", "ts", "type")})

    def hello(self) -> None:
        self.enc.reset()
        self.brain_hello = False
        self.send(self.msg("hello", role="face", device_id=DEVICE_ID, fw="0.2.0-fake",
                           caps=["face", "touch", "imu", "edge", "battery", "drive"], link="ble"))

    def on_write(self, value: bytes) -> None:
        m = self.dec.feed(bytes(value))
        if m is None:
            return
        try:
            obj = json.loads(m.decode("utf-8"))
        except ValueError:
            print("phone sent bad JSON")
            return
        t = obj.get("type")
        if t == "hello":
            self.brain_hello = True
            print(f"phone brain hello: {obj.get('server')} {obj.get('version')} mode={obj.get('mode')}")
            self.send(self.msg("robot_link", brain="ble", wifi="off", ip=""))
            self.send(self.msg("battery", percent=76, volts=7.9, charging=False))
            return
        if t == "ping":
            self.send(self.msg("pong", re=obj.get("id")))
            return
        if t == "say":
            mouth = (obj.get("mouth") or {}).get("values") or []
            print(f"  say [{obj.get('utt')}#{obj.get('seq')}] {obj.get('text')!r} {obj.get('duration_ms')} ms, "
                  f"mouth {len(mouth)} values")
            if obj.get("text"):
                self.send(self.msg("say_state", utt=obj["utt"], seq=obj["seq"], state="started"))
            return
        if t == "hotspot_join":
            print(f"  hotspot_join ssid={obj.get('ssid')!r} port={obj.get('port')} token={len(obj.get('token', ''))} chars")
            if self.hotspot_ws:
                asyncio.run_coroutine_threadsafe(self.join_ws(self.hotspot_ws, obj), self.loop)
                self.send(self.msg("hotspot_state", state="joined", ip="127.0.0.1"))
            else:
                self.send(self.msg("hotspot_state", state="failed", reason="not_found"))
            return
        print("phone ->", t, {k: v for k, v in obj.items() if k not in ("v", "id", "ts", "type")})

    async def join_ws(self, host: str, join: dict) -> None:
        """Act as the camera board on the phone's hotspot server (e.g. via adb forward)."""
        from websockets.asyncio.client import connect
        url = f"ws://{host}:{join['port']}/"
        try:
            async with connect(url) as ws:
                await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "camera", "device_id": DEVICE_ID,
                                          "fw": "0.2.0-fake", "caps": ["camera"], "token": join["token"],
                                          "link": "hotspot"}))
                print("camera board: connected to", url)
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("type") == "ping":
                        await ws.send(json.dumps({"v": 1, "type": "pong", "id": 2, "re": m.get("id")}))
        except OSError as e:
            print("camera board: could not reach", url, e)

    async def run(self, seconds: float | None) -> None:
        from bless import BlessGATTCharacteristic, BlessServer, GATTAttributePermissions, GATTCharacteristicProperties

        self.loop = asyncio.get_running_loop()
        server = BlessServer(name=f"Spike-{DEVICE_ID[-6:]}", loop=self.loop)
        self.server = server

        def read_request(ch: BlessGATTCharacteristic, **kw) -> bytearray:
            return ch.value

        def write_request(ch: BlessGATTCharacteristic, value, **kw) -> None:
            if str(ch.uuid).lower() == RX:
                self.on_write(bytes(value))

        server.read_request_func = read_request
        server.write_request_func = write_request
        await server.add_new_service(SERVICE)
        rw = GATTAttributePermissions.readable | GATTAttributePermissions.writeable
        await server.add_new_characteristic(SERVICE, RX, GATTCharacteristicProperties.write |
                                            GATTCharacteristicProperties.write_without_response, None, rw)
        await server.add_new_characteristic(SERVICE, TX, GATTCharacteristicProperties.notify, None,
                                            GATTAttributePermissions.readable)
        info = json.dumps({"pv": "1.3", "fw": "0.2.0-fake", "device_id": DEVICE_ID, "brain": "none"}).encode()
        await server.add_new_characteristic(SERVICE, INFO, GATTCharacteristicProperties.read, bytearray(info),
                                            GATTAttributePermissions.readable)
        await server.start()
        print(f"advertising Spike-{DEVICE_ID[-6:]} (service {SERVICE})" + (f" for {seconds:.0f} s" if seconds else ""))
        started = time.monotonic()
        stdin_task = None if seconds else asyncio.create_task(self.console())
        try:
            while seconds is None or time.monotonic() - started < seconds:
                await asyncio.sleep(0.5)
                # bless has no subscribe callback on every backend: start the session once a phone is connected
                connected = await server.is_connected() if hasattr(server, "is_connected") else False
                if connected and not self.subscribed:
                    self.subscribed = True
                    self.mtu = 185
                    print("phone connected: saying hello")
                    self.hello()
                elif not connected and self.subscribed:
                    print("phone gone")
                    self.subscribed = False
                    self.dec.reset()
                if stdin_task and stdin_task.done():
                    break
        finally:
            if stdin_task:
                stdin_task.cancel()
            await server.stop()
            print("stopped advertising")

    async def console(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = (await loop.run_in_executor(None, sys.stdin.readline)).strip()
            if line in ("quit", "exit", ""):
                if line:
                    return
                continue
            parts = line.split()
            if parts[0] == "tap":
                self.send(self.msg("touch", zone="head", gesture="tap"))
            elif parts[0] == "pat":
                self.send(self.msg("touch", zone="back", gesture="pat"))
            elif parts[0] == "boop":
                self.send(self.msg("touch", zone="nose", gesture="tap"))
            elif parts[0] == "pickup":
                self.send(self.msg("imu", event="pickup"))
            elif parts[0] == "battery" and len(parts) > 1:
                self.send(self.msg("battery", percent=float(parts[1]), volts=7.4, charging=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seconds", type=float, default=None, help="stop by itself after this long")
    ap.add_argument("--hotspot-ws", default=None, help="on hotspot_join, connect as the camera board to this host")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        asyncio.run(FakeRobot(a.hotspot_ws).run(a.seconds))
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001 - report plainly (e.g. no Bluetooth adapter, or it can't advertise)
        print(f"could not run the BLE peripheral: {type(e).__name__}: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
