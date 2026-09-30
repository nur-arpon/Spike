"""The protocol port on Windows: another program's wildcard listener ([::]:P,
like `python -m http.server P`) must be noticed even though Windows lets us
bind 127.0.0.1:P right next to it."""
import asyncio
import json
import socket

import pytest
from websockets.asyncio.client import connect

from spike_brain.brain import Brain, RunOptions
from spike_brain.server import BrainServer, PortBusy, port_in_use


def hold_dual_stack_wildcard(port: int = 0) -> socket.socket:
    """Listen on [::]:port for IPv6 AND IPv4, exactly like Python's http.server does."""
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("::", port))
    s.listen(5)
    return s


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def held():
    try:
        s = hold_dual_stack_wildcard()
    except OSError:
        pytest.skip("no IPv6 on this machine")
    yield s.getsockname()[1]
    s.close()


def test_a_plain_bind_would_not_notice(held):
    """The trap itself: binding 127.0.0.1 next to the wildcard listener succeeds."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", held))
    except OSError:
        pytest.skip("this OS refuses the shared bind, so the trap does not exist here")
    finally:
        s.close()
    assert port_in_use(held), "the probe must see the other program"


def test_probe_says_free_for_a_free_port():
    assert not port_in_use(free_port())


async def test_server_moves_off_a_port_held_on_ipv6_wildcard(held):
    srv = BrainServer("127.0.0.1", held)
    await srv.start()
    try:
        assert srv.port != held and held < srv.port <= held + 10
        assert srv.local_url == f"ws://127.0.0.1:{srv.port}"
        async with connect(srv.local_url) as ws:           # and it really is us on the new port
            await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "tool", "device_id": "t",
                                      "fw": "0", "caps": []}))
            hello = json.loads(await asyncio.wait_for(ws.recv(), 2))
            assert hello["server"] == "spike-brain"
    finally:
        await srv.stop()


async def test_no_fallback_means_a_clear_error(held):
    srv = BrainServer("127.0.0.1", held, port_fallback=0)
    with pytest.raises(PortBusy) as e:
        await srv.start()
    assert str(held) in str(e.value) and "another program" in str(e.value)


async def test_brain_moves_to_another_port(settings, held):
    brain = Brain(settings.override({"life": {"greet_on_start": False}}),
                  RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=held))
    seen = []
    brain.opts.on_listening = seen.append
    await brain.start()
    try:
        assert brain.server.port != held and seen == [brain.server.port]
    finally:
        await brain.shutdown()


async def test_our_port_is_exclusive():
    """Nobody can quietly bind next to Spike once he has the port."""
    srv = BrainServer("127.0.0.1", 0)
    await srv.start()
    try:
        assert port_in_use(srv.port)
        other = socket.socket()
        with pytest.raises(OSError):
            other.bind(("127.0.0.1", srv.port))
        other.close()
    finally:
        await srv.stop()
