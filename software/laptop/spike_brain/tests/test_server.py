"""The protocol server with real WebSocket clients: handshake, errors,
heartbeats, auth, origin check, routing, and speech delivery + mic mute."""
import asyncio
import json

import numpy as np
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from spike_brain import protocol as P
from spike_brain.server import BrainServer, origin_allowed
from spike_brain.speech.output import SpeechOut
from spike_brain.speech.tts import Speech, mouth_envelope

HELLO = {"v": 1, "type": "hello", "id": 1, "role": "tool", "device_id": "t", "fw": "0", "caps": ["face", "speaker"]}


async def recv(ws, timeout=2.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


async def recv_type(ws, type_, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while True:
        m = await recv(ws, max(0.05, end - asyncio.get_running_loop().time()))
        if m["type"] == type_:
            return m


@pytest.fixture
async def server():
    got = []

    async def on_message(client, msg):
        got.append(msg)

    srv = BrainServer("127.0.0.1", 0, heartbeat_s=0.3, hello_timeout_s=0.5, on_message=on_message,
                      welcome=lambda c: {"mode": "cat", "names": {"dog": "Spike", "cat": "Spicy"}})
    srv.got = got
    await srv.start()
    yield srv
    await srv.stop()


async def test_handshake_and_routing(server):
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps(HELLO))
        w = await recv(ws)
        assert w["type"] == "hello" and w["re"] == 1 and w["server"] == "spike-brain"
        assert w["mode"] == "cat" and w["names"]["cat"] == "Spicy" and w["heartbeat_s"] == 0.3
        await ws.send(json.dumps({"v": 1, "type": "touch", "id": 2, "zone": "head", "extra": 1}))
        await asyncio.sleep(0.1)
        assert server.got and server.got[-1]["zone"] == "head"
        client = next(iter(server.clients.values()))
        assert client.role == "tool" and client.has("speaker")


async def test_errors_do_not_close_the_link(server):
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps(HELLO))
        await recv(ws)
        await ws.send("{broken")
        assert (await recv_type(ws, "error"))["code"] == "bad_json"
        await ws.send(json.dumps({"v": 1, "type": "teleport", "id": 5}))
        e = await recv_type(ws, "error")
        assert e["code"] == "unknown_type" and e["re"] == 5
        await ws.send(json.dumps({"v": 1, "type": "ping", "id": 6}))
        assert (await recv_type(ws, "pong"))["re"] == 6


async def test_first_message_must_be_hello(server):
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps({"v": 1, "type": "touch", "id": 1, "zone": "head"}))
        assert (await recv(ws))["code"] == "not_ready"
        with pytest.raises(ConnectionClosed):
            await recv(ws)


async def test_hello_timeout_closes(server):
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        with pytest.raises(ConnectionClosed):
            await recv(ws, 2)
        assert ws.close_code == P.CLOSE_HELLO_TIMEOUT


async def test_version_mismatch_closes_4001(server):
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps({**HELLO, "v": 2}))
        assert (await recv(ws))["code"] == "version_mismatch"
        with pytest.raises(ConnectionClosed):
            await recv(ws)
        assert ws.close_code == P.CLOSE_VERSION


async def test_heartbeat_pings_and_drops_silent_clients(server):
    async with connect(f"ws://127.0.0.1:{server.port}/", ping_interval=None) as ws:
        await ws.send(json.dumps(HELLO))
        await recv(ws)
        ping = await recv_type(ws, "ping", 2)
        assert isinstance(ping["id"], int)
        # stay silent: after 3 x heartbeat the server closes us
        with pytest.raises(ConnectionClosed):
            for _ in range(40):
                await recv(ws, 2)


async def test_token_required_on_network_address():
    with pytest.raises(ValueError):
        BrainServer("0.0.0.0", 0)


async def test_bad_token_is_refused():
    srv = BrainServer("127.0.0.1", 0, token="s3cret", hello_timeout_s=1)
    await srv.start()
    try:
        async with connect(f"ws://127.0.0.1:{srv.port}/") as ws:
            await ws.send(json.dumps({**HELLO, "token": "wrong"}))
            assert (await recv(ws))["code"] == "auth"
            with pytest.raises(ConnectionClosed):
                await recv(ws)
            assert ws.close_code == P.CLOSE_AUTH
        async with connect(f"ws://127.0.0.1:{srv.port}/") as ws:
            await ws.send(json.dumps({**HELLO, "token": "s3cret"}))
            assert (await recv(ws))["type"] == "hello"
    finally:
        await srv.stop()


async def test_foreign_web_origin_is_refused(server):
    async with connect(f"ws://127.0.0.1:{server.port}/", origin="https://evil.example") as ws:
        with pytest.raises(ConnectionClosed):
            await recv(ws)
    assert origin_allowed(None) and origin_allowed("null") and origin_allowed("file://")
    assert origin_allowed("http://localhost:5500") and origin_allowed("http://127.0.0.1")
    assert not origin_allowed("https://localhost.evil.com") and not origin_allowed("http://192.168.1.5")


class ToneVoice:
    """A stand-in for Piper: 0.4 s of tone per sentence, instantly."""
    rate = 22050

    def synthesize(self, text, soft=False):
        t = np.arange(int(self.rate * 0.4)) / self.rate
        pcm = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
        return Speech(text, pcm, self.rate, mouth_envelope(pcm, self.rate))


async def test_speech_delivery_mute_and_unmute(server):
    mute_log = []
    done = []

    async def on_done(utt):
        done.append(utt.id)

    out = SpeechOut(server, {"dog": ToneVoice()}, output="robot", mute_tail_ms=100, report_timeout_s=5,
                    set_mic_muted=mute_log.append, on_done=on_done)
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps(HELLO))
        await recv(ws)
        utt = out.begin("dog")
        await out.segment(utt, "Hello there!", mood="happy")
        await out.segment(utt, "", final=True)                # end marker
        say = await recv_type(ws, "say")
        assert say["utt"] == utt.id and say["seq"] == 0 and say["text"] == "Hello there!"
        assert say["audio"]["rate"] == 22050 and say["audio"]["chunks"] == 2
        assert say["mouth"]["rate_hz"] == 50 and max(say["mouth"]["values"]) > 30
        chunks = [await recv_type(ws, "say_audio"), await recv_type(ws, "say_audio")]
        assert [c["index"] for c in chunks] == [0, 1] and chunks[1]["last"]
        pcm = b"".join(P.unb64(c["data"]) for c in chunks)
        assert len(pcm) == say["audio"]["samples"] * 2
        marker = await recv_type(ws, "say")
        assert marker["final"] and marker["text"] == "" and marker["audio"] is None
        assert mute_log == [True]                             # muted while speaking
        await ws.send(json.dumps({"v": 1, "type": "say_state", "id": 2, "utt": utt.id, "seq": 0, "state": "started"}))
        await ws.send(json.dumps({"v": 1, "type": "say_state", "id": 3, "utt": utt.id, "seq": 0, "state": "finished"}))
        await asyncio.sleep(0.05)
        route = server.got[-1]
        out.on_say_state(route["utt"], route["seq"], route["state"])
        out.on_say_state(utt.id, 0, "started")
        await asyncio.sleep(0.05)
        assert mute_log == [True]                             # still muted during the 100 ms tail
        await asyncio.sleep(0.15)
        assert mute_log == [True, False] and done == [utt.id]


async def test_stop_speaking_is_broadcast_and_unmutes(server):
    mute_log = []
    out = SpeechOut(server, {"dog": ToneVoice()}, output="robot", mute_tail_ms=50, set_mic_muted=mute_log.append)
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps(HELLO))
        await recv(ws)
        utt = out.begin("dog")
        await out.segment(utt, "A long story.")
        out.stop()
        assert (await recv_type(ws, "stop_speaking"))["utt"] == utt.id
        await asyncio.sleep(0.1)
        assert mute_log == [True, False]


async def test_speech_finishes_on_timeout_without_reports(server):
    mute_log = []
    out = SpeechOut(server, {"dog": ToneVoice()}, output="robot", mute_tail_ms=10, report_timeout_s=0.1,
                    set_mic_muted=mute_log.append)
    async with connect(f"ws://127.0.0.1:{server.port}/") as ws:
        await ws.send(json.dumps(HELLO))
        await recv(ws)
        utt = out.begin("dog")
        await out.segment(utt, "Nobody reports back.", final=True)
        await asyncio.wait_for(utt.done.wait(), 2)            # 0.4 s audio + 0.1 s grace
        await asyncio.sleep(0.05)
        assert mute_log == [True, False]
