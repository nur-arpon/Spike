"""Protocol v1.5 (PROTOCOL.md 10.8, DESIGN.md 6d): Spike's laptop voice played on the phone.

Encoding (Ogg Opus written by stream_audio.py, checked by FFmpeg's own decoder), codec
negotiation, and the routing rule: a reply plays on the phone the conversation came from
and nowhere else; everything else keeps today's behaviour."""
import asyncio
import io
import json
import time

import numpy as np
import pytest

from spike_brain import protocol as P
from spike_brain.speech import stream_audio as SA
from spike_brain.speech.output import REPLY_TO, SpeechOut, reply_to

from .test_applink import APP_HELLO, BOARD_HELLO, Phone, _board, _join, rig  # noqa: F401  (rig is a fixture)
from .test_brain import Robot
from .test_server import ToneVoice

av = pytest.importorskip("av")

VOICE_HELLO = {**APP_HELLO, "device_id": "phone-voice", "caps": ["face", "text", "mic", "audio_out"],
               "audio_out": {"formats": ["ogg_opus", "pcm_s16le"], "rates": [24000]}}


def _tone(seconds: float, rate: int = 24000, hz: float = 220) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (np.sin(2 * np.pi * hz * t) * 8000).astype(np.int16)


def _decode_ogg(data: bytes) -> tuple[np.ndarray, int]:
    c = av.open(io.BytesIO(data), format="ogg")
    out, rate = [], 0
    for fr in c.decode(audio=0):
        out.append(fr.to_ndarray().reshape(-1))
        rate = fr.sample_rate
    c.close()
    return (np.concatenate(out) if out else np.zeros(0, np.float32)), rate


# ------------------------------------------------------------------ encoding and framing
def test_ogg_crc_matches_ffmpeg_pages():
    """Our CRC must equal the one FFmpeg's Ogg muxer writes (else strict decoders drop every page)."""
    buf = io.BytesIO()
    c = av.open(buf, "w", format="ogg")
    s = c.add_stream("libopus", rate=24000)
    s.layout = "mono"
    f = av.AudioFrame.from_ndarray(_tone(0.5).reshape(1, -1), format="s16", layout="mono")
    f.sample_rate = 24000
    for p in [*s.encode(f), *s.encode(None)]:
        c.mux(p)
    c.close()
    data = buf.getvalue()
    pos, checked = 0, 0
    while pos < len(data):
        assert data[pos:pos + 4] == b"OggS"
        nseg = data[pos + 26]
        body = sum(data[pos + 27:pos + 27 + nseg])
        end = pos + 27 + nseg + body
        page = bytearray(data[pos:end])
        want = int.from_bytes(page[22:26], "little")
        page[22:26] = b"\0\0\0\0"
        assert SA._crc(bytes(page)) == want
        pos, checked = end, checked + 1
    assert checked >= 3


def test_opus_stream_is_one_decodable_stream_per_utterance():
    s = SA.OpusOggStream(24000)
    a, n1 = s.add(_tone(1.0))
    b, n2 = s.add(_tone(0.51, hz=330))                  # not a whole frame: padded to 20 ms
    assert a.startswith(b"OggS") and b"OpusHead" in a[:80] and b"OpusHead" not in b
    assert n1 == 24000 and n2 % 480 == 0 and n2 >= int(24000 * 0.51)
    pcm, rate = _decode_ogg(a + b)
    assert rate == 48000
    pre_skip = int.from_bytes(s._head[10:12], "little")
    assert abs(len(pcm) - ((n1 + n2) * 2 - pre_skip)) <= 960
    assert float(np.sqrt(np.mean(pcm[4800:-4800] ** 2))) > 0.05       # not silence
    # the first sentence alone is complete: it decodes to its full length without the second one
    first, _ = _decode_ogg(a)
    assert abs(len(first) - (n1 * 2 - pre_skip)) <= 960
    assert len(a) < 24000 * 2 / 6                                # compressed: well under a sixth of PCM16


def test_negotiation():
    assert SA.choose_format(["ogg_opus", "pcm_s16le"]) == "ogg_opus"
    assert SA.choose_format(["pcm_s16le"]) == "pcm_s16le"
    assert SA.choose_format(["mp3"]) == "pcm_s16le" and SA.choose_format(None) == "pcm_s16le"
    assert SA.choose_rate("ogg_opus", [44100, 16000]) == 16000
    assert SA.choose_rate("ogg_opus", [44100]) == 24000
    assert SA.choose_rate("pcm_s16le", [44100]) == 44100 and SA.choose_rate("pcm_s16le", []) == 24000
    assert "audio_out" in P.CAPS


# ------------------------------------------------------------------ routing
async def _voice_phone(brain, hello=VOICE_HELLO):
    ws = await _join(brain.server.port, hello)
    ph = Phone(ws)
    h = await ph.pump(lambda m: m["type"] == "hello")
    await ph.pump(lambda m: m["type"] == "memory")
    return ws, ph, h


async def _collect_reply(ph: Phone, timeout=6.0):
    """Everything up to the end of one utterance (its final say)."""
    start = len(ph.seen)
    await ph.pump(lambda m: m["type"] == "say" and m["final"], timeout=timeout)
    return ph.seen[start:]


async def test_hello_tells_the_phone_its_format(rig):
    brain, _ = rig
    ws, ph, h = await _voice_phone(brain)
    assert h["audio"] == {"format": "ogg_opus", "rate": 24000, "channels": 1, "to_app": True}
    await ws.close()
    ws, ph, h = await _voice_phone(brain, {**VOICE_HELLO, "device_id": "p2", "audio_out": {"formats": ["pcm_s16le"]}})
    assert h["audio"]["format"] == "pcm_s16le"
    await ws.close()


async def test_typed_on_the_phone_plays_on_the_phone_only(rig):
    brain, old_phone = rig
    bws, board = await _board(brain)
    ws, ph, _ = await _voice_phone(brain)
    await ph.send("text", text="hello there")
    got = await _collect_reply(ph)
    says = [m for m in got if m["type"] == "say" and m["text"]]
    assert says and all(m.get("play") is True for m in says)
    assert says[0]["audio"]["format"] == "ogg_opus" and says[0]["audio"]["rate"] == 24000
    data = b"".join(P.unb64(m["data"]) for m in got if m["type"] == "say_audio")
    assert len(data) == sum(m["audio"]["bytes"] for m in says)
    pcm, _ = _decode_ogg(data)
    assert len(pcm) > 48000 * 0.3 and float(np.abs(pcm).max()) > 0.1
    # the robot shows the caption and moves its mouth, but plays nothing; the laptop speaker is untouched
    await board.pump(lambda m: m["type"] == "say" and m["final"], timeout=3)
    bsays = [m for m in board.seen if m["type"] == "say" and m["text"]]
    assert bsays and all(m["audio"] is None and m["mouth"] for m in bsays)
    assert not any(m["type"] == "say_audio" for m in board.seen)
    assert brain.speech.local is None
    # another phone (no audio_out) gets captions only, never play
    await old_phone.pump(timeout=0.3)
    assert all(m.get("play") is None for m in old_phone.seen if m["type"] == "say")
    await ws.close()
    await bws.close()


async def test_phone_reports_end_the_utterance_robot_reports_do_not(rig):
    brain, _ = rig
    bws, board = await _board(brain)                     # answers every say with started/finished at once
    ws, ph, _ = await _voice_phone(brain)
    await ph.send("text", text="tell me something")
    got = await _collect_reply(ph)
    await board.pump(timeout=0.3)
    utt = brain.speech.utts[got[-1]["utt"]]
    assert not utt.done.is_set(), "the robot's caption reports must not end the phone's utterance"
    for m in got:
        if m["type"] == "say" and m["text"]:
            await ph.send("say_state", utt=m["utt"], seq=m["seq"], state="started")
            await ph.send("say_state", utt=m["utt"], seq=m["seq"], state="finished")
    await asyncio.wait_for(utt.done.wait(), 2)
    await ws.close()
    await bws.close()


async def test_voice_from_the_laptop_or_robot_keeps_todays_behaviour(rig):
    brain, _ = rig
    bws, board = await _board(brain)
    ws, ph, _ = await _voice_phone(brain)
    await board.send("text", text="hi from the robot")    # the robot's own input: not the phone's
    await board.pump(lambda m: m["type"] == "say" and m["final"], timeout=5)
    assert any(m["type"] == "say_audio" for m in board.seen)
    await ph.pump(timeout=0.3)
    assert all(m.get("play") is None for m in ph.seen if m["type"] == "say")
    assert not any(m["type"] == "say_audio" for m in ph.seen)
    await ws.close()
    await bws.close()


async def test_routing_rule_and_voice_origin(rig):
    brain, _ = rig
    ws, ph, _ = await _voice_phone(brain)
    phone = next(c for c in brain.server.clients.values() if c.device_id == "phone-voice")
    old = next(c for c in brain.server.clients.values() if c.device_id == "phone-1")
    assert brain.reply_origin(phone) is phone
    assert brain.reply_origin(old) is None                # an older app: no audio_out
    assert brain.reply_origin(None) is None
    assert brain.voice_origin() is None
    await ph.send("audio", data=P.b64(bytes(640)), rate=16000, seq=1)
    await asyncio.sleep(0.1)
    assert brain.voice_origin() is phone                  # heard speech came through this phone's mic
    brain.app_mic = (phone, time.monotonic() - brain.APP_MIC_WINDOW_S - 1)
    assert brain.voice_origin() is None                   # too long ago: the laptop's own mic
    await ws.close()
    await asyncio.sleep(0.1)
    brain.app_mic = (phone, time.monotonic())
    assert brain.voice_origin() is None                   # gone
    # a disconnected phone falls back to today's target
    utt = brain.speech.begin("dog", to=phone)
    assert brain.speech.app_client(utt) is None


async def test_trick_from_the_phone_answers_on_the_phone(rig):
    brain, _ = rig
    ws, ph, _ = await _voice_phone(brain)
    await ph.send("action", action="zoomies")
    say = await ph.pump(lambda m: m["type"] == "say" and m["text"], timeout=5)
    assert say is not None and say["play"] is True and say["audio"]["format"] == "ogg_opus"
    assert REPLY_TO.get() is None                         # never leaks out of the handler
    await ws.close()


async def test_pcm_phone_and_caption_only_segment(rig):
    brain, _ = rig
    ws, ph, _ = await _voice_phone(brain, {**VOICE_HELLO, "device_id": "p-pcm", "audio_out": {"formats": ["pcm_s16le"]}})
    phone = next(c for c in brain.server.clients.values() if c.device_id == "p-pcm")
    out: SpeechOut = brain.speech
    with reply_to(phone):
        utt = out.begin("dog")
    await out.segment(utt, "Plain samples.", final=False)
    brain.voices["dog"] = None                            # the laptop has no voice for the next sentence
    await out.segment(utt, "Say this one yourself.", final=True)
    brain.voices["dog"] = ToneVoice()
    got = await _collect_reply(ph)
    s0, s1 = [m for m in got if m["type"] == "say"]
    assert s0["audio"]["format"] == "pcm_s16le" and s0["audio"]["bytes"] == s0["audio"]["samples"] * 2
    assert s1["play"] is True and s1["audio"] is None     # the phone's own voice says it
    await ws.close()


async def test_stop_reaches_the_phone(rig):
    brain, _ = rig
    ws, ph, _ = await _voice_phone(brain)
    phone = next(c for c in brain.server.clients.values() if c.device_id == "phone-voice")
    utt = brain.speech.begin("dog", to=phone)
    await brain.speech.segment(utt, "A long story about bones.")
    brain.speech.stop()
    m = await ph.pump(lambda m: m["type"] == "stop_speaking", timeout=2)
    assert m is not None and m["utt"] == utt.id
    await ws.close()


# ------------------------------------------------------------------ v1.7: the phone voices its own replies
async def test_phone_voice_gets_checked_text_only_and_can_switch_back(rig):
    """Owner decision 30 Sep: Gemini TTS first, at home too. A phone that says `voice: "phone"` (hello
    audio_out, or `voice_source`) gets `play: true` with `audio: null` (nothing synthesised here), and
    still nothing plays on the laptop or the robot; `voice_source: laptop` brings the laptop voice back."""
    brain, _ = rig
    ws, ph, h = await _voice_phone(brain, {**VOICE_HELLO, "device_id": "p-gem",
                                           "audio_out": {"formats": ["ogg_opus"], "rates": [24000], "voice": "phone"}})
    assert h.get("voice_source") is True
    calls = []
    real = brain.voices["dog"]

    class Counting:
        wants_hints = False
        rate = getattr(real, "rate", 24000)

        def synthesize(self, *a, **k):
            calls.append(a[0])
            return real.synthesize(*a, **k)
    brain.voices["dog"] = Counting()
    await ph.send("text", text="hello there")
    got = await _collect_reply(ph)
    says = [m for m in got if m["type"] == "say" and m["text"]]
    assert says and all(m["play"] is True and m["audio"] is None for m in says)
    assert not any(m["type"] == "say_audio" for m in got)
    assert calls == [] and brain.speech.local is None
    await ph.send("voice_source", voice="laptop")
    await ph.send("text", text="hello again")
    got = await _collect_reply(ph)
    says = [m for m in got if m["type"] == "say" and m["text"]]
    assert says and says[0]["audio"] is not None and calls
    brain.voices["dog"] = real
    await ws.close()


def test_voice_source_validation():
    P.validate({"v": 1, "id": 1, "type": "voice_source", "voice": "phone"}, "from_app")
    with pytest.raises(P.ProtocolError):
        P.validate({"v": 1, "id": 1, "type": "voice_source", "voice": "robot"}, "from_app")


def test_json_frames_stay_small():
    data, _ = SA.OpusOggStream(24000).add(_tone(8.0))
    chunks = SA.split_bytes(data)
    msg = P.encode(P.make("say_audio", 1, utt="u1", seq=0, index=0, last=True, data=P.b64(chunks[0])))
    assert len(msg) < 24 * 1024 and json.loads(msg)["type"] == "say_audio"
